"""Guard: decidable code rules (018-add-schema-conventions; 020-add-crawl-core D7, D9, D13, D14)."""

import ast
from collections.abc import Mapping
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
# Typer takes a class, not an instance, so build_app makes one per app (ADR-0006).
ALLOWED_SUBCLASSES = {("AppGroup", "SpiderGroup")}


def _is_dataclass(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Name):
        return target.id == "dataclass"
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "dataclass"
        and isinstance(target.value, ast.Name)
        and target.value.id == "dataclasses"
    )


def _sets_frozen(keywords: list[ast.keyword]) -> bool:
    return any(
        keyword.arg == "frozen"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in keywords
    )


def _is_frozen(decorator: ast.expr) -> bool:
    return isinstance(decorator, ast.Call) and _sets_frozen(decorator.keywords)


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Subscript):
        base = base.value
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _decorator_name(decorator: ast.expr) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return _base_name(target)


def _is_unbounded_memo(decorator: ast.expr) -> bool:
    name = _decorator_name(decorator)
    if name == "cache":
        return True
    if name != "lru_cache":
        return False
    if not isinstance(decorator, ast.Call):
        return True
    sizes = decorator.args[:1] + [k.value for k in decorator.keywords if k.arg == "maxsize"]
    return not sizes or any(isinstance(s, ast.Constant) and s.value is None for s in sizes)


def violations(sources: Mapping[str, str]) -> list[str]:
    """Each module's breaches of ADR-0006, given every module's source by its path."""
    trees = {module: ast.parse(source) for module, source in sources.items()}
    classes = {
        module: [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        for module, tree in trees.items()
    }
    own_class_names = {node.name for nodes in classes.values() for node in nodes}
    found = []
    for module, nodes in classes.items():
        for node in nodes:
            found += [
                f"{module}: {node.name} is a dataclass that is not frozen"
                for decorator in node.decorator_list
                if _is_dataclass(decorator) and not _is_frozen(decorator)
            ]
            if "Struct" in map(_base_name, node.bases) and not _sets_frozen(node.keywords):
                found.append(f"{module}: {node.name} is a Struct that is not frozen")
            found += [
                f"{module}: {node.name} subclasses {name}"
                for name in map(_base_name, node.bases)
                if name in own_class_names and (node.name, name) not in ALLOWED_SUBCLASSES
            ]
        found += [
            f"{module}: {node.name} is a memo without an explicit bound"
            for node in ast.walk(trees[module])
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and any(map(_is_unbounded_memo, node.decorator_list))
        ]
    return found


def test_the_decidable_rules_of_adr_0006_hold_over_src_spider() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "spider").rglob("*.py"))
    }

    assert violations(sources) == []


def test_a_dataclass_that_is_not_frozen_is_named() -> None:
    source = """
import dataclasses
from dataclasses import dataclass

@dataclass
class Bare: ...

@dataclass(slots=True)
class Called: ...

@dataclass(frozen=False)
class Thawed: ...

@dataclasses.dataclass(kw_only=True)
class Qualified: ...

@dataclass(frozen=True, slots=True)
class Frozen: ...
"""

    assert violations({"m.py": source}) == [
        "m.py: Bare is a dataclass that is not frozen",
        "m.py: Called is a dataclass that is not frozen",
        "m.py: Thawed is a dataclass that is not frozen",
        "m.py: Qualified is a dataclass that is not frozen",
    ]


def test_a_struct_that_is_not_frozen_is_named() -> None:
    source = """
import msgspec
from msgspec import Struct

class Bare(Struct): ...

class Keyworded(msgspec.Struct, kw_only=True): ...

class Thawed(Struct, frozen=False): ...

class Frozen(msgspec.Struct, frozen=True, kw_only=True): ...

class Other(Exception, frozen=False): ...
"""

    assert violations({"m.py": source}) == [
        "m.py: Bare is a Struct that is not frozen",
        "m.py: Keyworded is a Struct that is not frozen",
        "m.py: Thawed is a Struct that is not frozen",
    ]


def test_a_subclass_of_an_own_class_is_named() -> None:
    base = "class Base: ...\nclass SpiderGroup: ...\n"
    derived = """
import base

class Plain(Base): ...
class Subscripted(Base[int]): ...
class Qualified(base.Base): ...
class Framework(Exception): ...
class AppGroup(SpiderGroup): ...
"""

    assert violations({"base.py": base, "derived.py": derived}) == [
        "derived.py: Plain subclasses Base",
        "derived.py: Subscripted subclasses Base",
        "derived.py: Qualified subclasses Base",
    ]


URL_MODULE = "spider/crawl/urls.py"
# Group 4 adds each store module that casts urls.url to a NormalizedUrl (design D13).
NORMALIZED_URL_MAKERS = {URL_MODULE, "spider/store/urls.py"}


def _imported_modules(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
    return found


def _makes_normalized_url(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if _base_name(node.func) != "cast":
        return _base_name(node.func) == "NormalizedUrl"
    target = node.args[0] if node.args else None
    if isinstance(target, ast.Constant):
        return target.value == "NormalizedUrl"
    return target is not None and _base_name(target) == "NormalizedUrl"


def url_type_violations(sources: Mapping[str, str]) -> list[str]:
    """Breaches of design D13 of 020-add-crawl-core, given every module's source by its path."""
    found = []
    for module, source in sources.items():
        tree = ast.parse(source)
        if module == URL_MODULE:
            found += [
                f"{module} imports {name}"
                for name in _imported_modules(tree)
                if name == "spider" or name.startswith(("spider.", "."))
            ]
        if module not in NORMALIZED_URL_MAKERS and any(map(_makes_normalized_url, ast.walk(tree))):
            found.append(f"{module} makes a NormalizedUrl")
    return found


def test_the_rules_of_design_d13_of_020_hold_over_src_spider() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "spider").rglob("*.py"))
    }

    assert url_type_violations(sources) == []


def test_an_import_of_spider_in_the_url_module_is_named() -> None:
    source = """
import re
import spider.output
from spider.store.records import LinkType
from . import scope

def late():
    import spider
"""

    assert url_type_violations({URL_MODULE: source}) == [
        f"{URL_MODULE} imports spider.output",
        f"{URL_MODULE} imports spider.store.records",
        f"{URL_MODULE} imports .",
        f"{URL_MODULE} imports spider",
    ]


def test_a_normalized_url_made_outside_its_makers_is_named() -> None:
    sources = {
        URL_MODULE: "NormalizedUrl('http://site.test/')\n",
        "spider/crawl/scope.py": "urls.NormalizedUrl('http://site.test/')\n",
        "spider/crawl/engine.py": "url = NormalizedUrl('http://site.test/')\n",
        "spider/store/pages.py": "url = cast(NormalizedUrl, row.url)\n",
        "spider/store/urls.py": "url = NormalizedUrl(row.url)\n",
        "spider/store/origins.py": "url = typing.cast('NormalizedUrl', row.url)\n",
        "spider/crawl/frontier.py": "def f(url: NormalizedUrl) -> None: ...\n",
        "spider/crawl/links.py": "n = cast(int, row.n)\n",
    }

    assert url_type_violations(sources) == [
        "spider/crawl/scope.py makes a NormalizedUrl",
        "spider/crawl/engine.py makes a NormalizedUrl",
        "spider/store/pages.py makes a NormalizedUrl",
        "spider/store/origins.py makes a NormalizedUrl",
    ]


# Only the store writes SQL; the schema service loads sqlalchemy lazily (020 design D14).
SQLALCHEMY_IMPORTERS = ("spider/store/", "spider/services/schema.py")


def sqlalchemy_violations(sources: Mapping[str, str]) -> list[str]:
    """Modules outside the store that import sqlalchemy, given every module's source by its path."""
    return [
        f"{module} imports {name}"
        for module, source in sources.items()
        if not module.startswith(SQLALCHEMY_IMPORTERS)
        for name in _imported_modules(ast.parse(source))
        if name == "sqlalchemy" or name.startswith("sqlalchemy.")
    ]


def test_only_the_store_imports_sqlalchemy() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "spider").rglob("*.py"))
    }

    assert sqlalchemy_violations(sources) == []


def test_an_import_of_sqlalchemy_outside_the_store_is_named() -> None:
    sources = {
        "spider/crawl/engine.py": "import sqlalchemy\n",
        "spider/crawl/frontier.py": "from sqlalchemy.dialects.sqlite import insert\n",
        "spider/services/crawling.py": "def late():\n    from sqlalchemy import select\n",
        "spider/crawl/links.py": "import sqlalchemy_utils\nfrom spider.store import urls\n",
        "spider/store/urls.py": "from sqlalchemy import insert\n",
        "spider/services/schema.py": "def late():\n    from sqlalchemy.dialects import sqlite\n",
    }

    assert sqlalchemy_violations(sources) == [
        "spider/crawl/engine.py imports sqlalchemy",
        "spider/crawl/frontier.py imports sqlalchemy.dialects.sqlite",
        "spider/services/crawling.py imports sqlalchemy",
    ]


def test_a_memo_without_an_explicit_bound_is_named() -> None:
    source = """
import functools
from functools import cache, lru_cache

@cache
def bare_cache(x): ...

@functools.cache
def qualified_cache(x): ...

@lru_cache
def bare_lru(x): ...

@lru_cache()
def called_lru(x): ...

@functools.lru_cache(maxsize=None)
def unbounded_lru(x): ...

@lru_cache(None)
def positional_none(x): ...

@lru_cache(maxsize=1024)
def bounded(x): ...

@functools.lru_cache(256)
def positional_bound(x): ...
"""

    assert violations({"m.py": source}) == [
        "m.py: bare_cache is a memo without an explicit bound",
        "m.py: qualified_cache is a memo without an explicit bound",
        "m.py: bare_lru is a memo without an explicit bound",
        "m.py: called_lru is a memo without an explicit bound",
        "m.py: unbounded_lru is a memo without an explicit bound",
        "m.py: positional_none is a memo without an explicit bound",
    ]


# The crawl core never imports the layers that wire it or plug into it (020 design D9).
PLUGIN_LAYERS = ("spider.services", "spider.extract", "spider.rules", "spider.cli")


def _absolute(module: str, level: int, name: str | None) -> str:
    if not level:
        return name or ""
    package = module.removesuffix(".py").split("/")[:-1]
    base = package[: len(package) - level + 1]
    return ".".join([*base, name] if name else base)


def _plugin_imports(module: str, tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(module, node.level, node.module)
            # `from spider import rules` names the layer in the alias.
            found += (
                [f"{base}.{alias.name}" for alias in node.names] if base == "spider" else [base]
            )
    return [
        name
        for name in found
        if any(name == layer or name.startswith(f"{layer}.") for layer in PLUGIN_LAYERS)
    ]


def plugin_import_violations(sources: Mapping[str, str]) -> list[str]:
    """Modules of spider.crawl that import a plugin layer, given every module's source by path."""
    return [
        f"{module} imports {name}"
        for module, source in sources.items()
        if module.startswith("spider/crawl/")
        for name in _plugin_imports(module, ast.parse(source))
    ]


def test_the_crawl_core_imports_no_plugin_layer() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "spider").rglob("*.py"))
    }

    assert plugin_import_violations(sources) == []


def test_an_import_of_a_plugin_layer_in_the_crawl_core_is_named() -> None:
    sources = {
        "spider/crawl/engine.py": "from spider.services.hooks import default_hooks\n",
        "spider/crawl/pages.py": "def late():\n    import spider.extract.page\n",
        "spider/crawl/scope.py": "from spider import rules, store\n",
        "spider/crawl/links.py": "from ..cli import app\n",
        "spider/crawl/hooks.py": "from spider.store import rows\nimport spider.servicesx\n",
        "spider/services/crawling.py": "from spider.services.hooks import default_hooks\n",
    }

    assert plugin_import_violations(sources) == [
        "spider/crawl/engine.py imports spider.services.hooks",
        "spider/crawl/pages.py imports spider.extract.page",
        "spider/crawl/scope.py imports spider.rules",
        "spider/crawl/links.py imports spider.cli",
    ]


# lexbor's serializer recurses into template content: `.html` of a <template> nested 20,000
# deep ends the process with a native stack overflow (020-add-crawl-core design Risks).
SERIALIZERS = frozenset({"html", "inner_html", "html_pretty", "inner_html_pretty"})
PAGE_READERS = ("spider/crawl/", "spider/extract/")


def serializer_violations(sources: Mapping[str, str]) -> list[str]:
    """Reads of a serializer in the modules that read Pages, given every module's source by path."""
    return [
        f"{module}:{node.lineno} serializes a node with .{node.attr}, which overflows the stack "
        "on deeply nested templates"
        for module, source in sources.items()
        if module.startswith(PAGE_READERS)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and node.attr in SERIALIZERS
    ]


def test_no_module_that_reads_pages_serializes_a_node() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "spider").rglob("*.py"))
    }

    assert serializer_violations(sources) == []


def test_a_serialization_of_a_node_is_named() -> None:
    sources = {
        "spider/crawl/links.py": "def f(node):\n    return node.html\n",
        "spider/extract/page_data.py": "text = tree.body.inner_html\n",
        "spider/crawl/pages.py": "x = node.css('a')\ny = node.attributes\n",
        "spider/report/html.py": "page = node.html\n",
    }

    assert serializer_violations(sources) == [
        "spider/crawl/links.py:2 serializes a node with .html, which overflows the stack on deeply "
        "nested templates",
        "spider/extract/page_data.py:1 serializes a node with .inner_html, which overflows the "
        "stack on deeply nested templates",
    ]


# With scripting off, a head <noscript><img> ends <head> (020 design D5); a fragment is the
# content of a <noscript>, read as markup.
PARSE_FLAGS = ("scripting", "is_fragment")


def parse_violations(sources: Mapping[str, str]) -> list[str]:
    """Parsers built with neither flag in the modules that read Pages, given every module's
    source by path."""
    return [
        f"{module}:{node.lineno} parses a document with scripting off"
        for module, source in sources.items()
        if module.startswith(PAGE_READERS)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and _called_name(node.func) == "LexborHTMLParser"
        and not any(
            keyword.arg in PARSE_FLAGS
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        )
    ]


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None


def test_every_page_is_parsed_with_scripting_on() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "spider").rglob("*.py"))
    }

    assert parse_violations(sources) == []


def test_a_parse_with_scripting_off_is_named() -> None:
    sources = {
        "spider/crawl/links.py": "tree = LexborHTMLParser(text)\n",
        "spider/extract/page_data.py": "tree = lexbor.LexborHTMLParser(text, scripting=False)\n",
        "spider/crawl/pages.py": (
            "a = LexborHTMLParser(text, scripting=True)\n"
            "b = LexborHTMLParser(text, is_fragment=True)\n"
        ),
        "spider/report/html.py": "tree = LexborHTMLParser(text)\n",
    }

    assert parse_violations(sources) == [
        "spider/crawl/links.py:1 parses a document with scripting off",
        "spider/extract/page_data.py:1 parses a document with scripting off",
    ]


# Every request of a Crawl goes through the Requester, which owns its politeness (020 D7).
REQUESTER = "spider/crawl/requester.py"


def request_violations(sources: Mapping[str, str]) -> list[str]:
    """Requests made outside the Requester, given every module's source by its path."""
    found = []
    for module, source in sources.items():
        if module == REQUESTER:
            continue
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Attribute) and node.attr == "fetch":
                found.append(f"{module}:{node.lineno} calls a Fetcher outside the Requester")
            elif isinstance(node, ast.Call) and _base_name(node.func) == "Request":
                found.append(f"{module}:{node.lineno} makes a Request outside the Requester")
    return found


def test_every_request_goes_through_the_requester() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "spider").rglob("*.py"))
    }

    assert request_violations(sources) == []


def test_a_request_outside_the_requester_is_named() -> None:
    sources = {
        "spider/crawl/robots_loader.py": "async def f(self, url):\n"
        "    return await self._fetcher.fetch(Request(url))\n",
        "spider/crawl/engine.py": "fetch = context.fetcher.fetch\nrequest = fetcher.Request(u)\n",
        REQUESTER: "async def f(self, url):\n    return await self._fetcher.fetch(Request(url))\n",
        "spider/crawl/fetcher.py": "class AiohttpFetcher:\n"
        "    async def fetch(self, request): ...\n",
    }

    assert request_violations(sources) == [
        "spider/crawl/robots_loader.py:2 calls a Fetcher outside the Requester",
        "spider/crawl/robots_loader.py:2 makes a Request outside the Requester",
        "spider/crawl/engine.py:1 calls a Fetcher outside the Requester",
        "spider/crawl/engine.py:2 makes a Request outside the Requester",
    ]


# Built only through their generic factories, which check the type parameter where the hooks are
# registered: one built in place inside Hooks(...) takes it as Any (020 D9).
FACTORIES = {"Handler": "src/spider/crawl/hooks.py", "Extractor": "src/spider/crawl/pages.py"}


def factory_violations(sources: Mapping[str, str]) -> list[str]:
    """Hooks built outside their factories, given every module's source by its path."""
    found = []
    for module, source in sources.items():
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            name = _base_name(node.func)
            if name in FACTORIES and module != FACTORIES[name]:
                found.append(f"{module}:{node.lineno} builds {name}(...) outside its factory")
    return found


def test_hooks_are_built_only_through_their_factories() -> None:
    root = SRC.parent
    sources = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for folder in (SRC / "spider", root / "tests")
        for path in sorted(folder.rglob("*.py"))
    }

    assert factory_violations(sources) == []


def test_a_hook_built_outside_its_factory_is_named() -> None:
    sources = {
        "tests/crawl/test_hooks.py": "hooks = Hooks(handlers=(Handler('x', rows, write),))\n",
        "src/spider/services/hooks.py": "h = hooks.Handler('x', rows, write)\n",
        "src/spider/crawl/hooks.py": "def handler(n, h, w):\n    return Handler(n, h, w)\n",
        "src/spider/services/pages.py": "e = pages.Extractor('x', extract, None)\n",
        "src/spider/crawl/pages.py": "def extractor(n, e, c):\n    return Extractor(n, e, c)\n",
    }

    assert factory_violations(sources) == [
        "tests/crawl/test_hooks.py:1 builds Handler(...) outside its factory",
        "src/spider/services/hooks.py:1 builds Handler(...) outside its factory",
        "src/spider/services/pages.py:1 builds Extractor(...) outside its factory",
    ]


# A Crawl waits only through its Clock, so a fake Clock drives every wait of a test (020 D7).
WAITERS = ("spider/crawl/", "spider/services/crawling.py")
# The one deadline outside the Clock bounds a real request, where timing tests put a fake Fetcher.
FETCHER = "spider/crawl/fetcher.py"
SLEEPS = {("asyncio", "sleep"), ("time", "sleep")}
CALLBACKS = {"call_later", "call_at", "reschedule"}
# Where each asyncio call that may wait takes its timeout as a positional argument, if it does.
TIMEOUT_POSITIONS = {
    "wait_for": 1,
    "wait": None,
    "as_completed": None,
    "timeout": 0,
    "timeout_at": 0,
}
TIMEOUT_KEYWORDS = {"timeout", "delay", "when"}


def _package(module: str) -> str | None:
    """`asyncio` for asyncio and its submodules, `time` for time."""
    if module == "time":
        return module
    return "asyncio" if module.split(".")[0] == "asyncio" else None


def _imported_names(tree: ast.AST) -> dict[str, str]:
    """The module that each name an `import` binds stands for."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is None:
                    head = alias.name.split(".")[0]
                    names[head] = head
                else:
                    names[alias.asname] = alias.name
    return names


def _has_timeout(call: ast.Call, position: int | None) -> bool:
    given = [keyword.value for keyword in call.keywords if keyword.arg in TIMEOUT_KEYWORDS]
    if position is not None and len(call.args) > position:
        given.append(call.args[position])
    return any(not (isinstance(value, ast.Constant) and value.value is None) for value in given)


def _waits(call: ast.Call, names: Mapping[str, str]) -> bool:
    if not isinstance(call.func, ast.Attribute):
        return False
    name = call.func.attr
    head, dot, rest = ast.unparse(call.func.value).partition(".")
    owner = _package(names.get(head, head) + dot + rest)
    if name in CALLBACKS or (owner, name) in SLEEPS:
        return True
    return (
        owner == "asyncio"
        and name in TIMEOUT_POSITIONS
        and _has_timeout(call, TIMEOUT_POSITIONS[name])
    )


def _sets_a_deadline(module: str, call: ast.Call) -> bool:
    return module != FETCHER and _base_name(call.func) == "ClientTimeout"


def wait_violations(sources: Mapping[str, str]) -> list[str]:
    """Waits of a Crawl outside its Clock, given every module's source by its path."""
    found: list[str] = []
    for module, source in sources.items():
        if not module.startswith(WAITERS):
            continue
        tree = ast.parse(source)
        names = _imported_names(tree)
        for node in sorted(ast.walk(tree), key=lambda node: getattr(node, "lineno", 0)):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                package = _package(node.module)
                found.extend(
                    f"{module}:{node.lineno} imports {node.module}.{alias.name} by name"
                    for alias in node.names
                    if (package, alias.name) in SLEEPS
                    or (package == "asyncio" and alias.name in TIMEOUT_POSITIONS)
                )
            elif isinstance(node, ast.Call) and _waits(node, names):
                found.append(f"{module}:{node.lineno} waits outside the Clock: {ast.unparse(node)}")
            elif isinstance(node, ast.Call) and _sets_a_deadline(module, node):
                where = f"{module}:{node.lineno}"
                found.append(f"{where} sets a deadline outside the Fetcher: {ast.unparse(node)}")
    return found


def test_a_crawl_waits_only_through_its_clock() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "spider").rglob("*.py"))
    }

    assert wait_violations(sources) == []


def test_a_wait_outside_the_clock_is_named() -> None:
    sources = {
        "spider/crawl/engine.py": "await asyncio.sleep(0)\n"
        "time.sleep(1)\n"
        "loop.call_later(1, f)\n"
        "self._loop.call_at(t, f)\n"
        "await asyncio.wait_for(task, 5)\n"
        "await asyncio.wait_for(task, timeout=5)\n"
        "await asyncio.wait(tasks, timeout=5)\n"
        "async with asyncio.timeout(5): ...\n"
        "async with asyncio.timeout_at(when=t): ...\n"
        "import asyncio as aio\n"
        "import time as t\n"
        "await aio.sleep(1)\n"
        "t.sleep(1)\n"
        "await asyncio.tasks.sleep(1)\n"
        "for done in asyncio.as_completed(tasks, timeout=5): ...\n"
        "cm.reschedule(t)\n"
        "timeout = aiohttp.ClientTimeout(total=5)\n",
        "spider/crawl/politeness.py": "from asyncio import sleep, Lock\nfrom time import sleep\n"
        "await self._clock.sleep(1)\n"
        "await asyncio.wait_for(task, None)\n"
        "await asyncio.wait(tasks)\n"
        "async with asyncio.timeout(None): ...\n"
        "from asyncio.tasks import sleep as nap\n"
        "for done in asyncio.as_completed(tasks): ...\n",
        "spider/crawl/fetcher.py": "timeout = aiohttp.ClientTimeout(total=20)\n",
        "spider/services/crawling.py": "async with asyncio.timeout(delay=1): ...\n",
        "spider/services/listing.py": "await asyncio.sleep(1)\n",
        "spider/clock.py": "await asyncio.sleep(seconds)\n",
    }

    assert wait_violations(sources) == [
        "spider/crawl/engine.py:1 waits outside the Clock: asyncio.sleep(0)",
        "spider/crawl/engine.py:2 waits outside the Clock: time.sleep(1)",
        "spider/crawl/engine.py:3 waits outside the Clock: loop.call_later(1, f)",
        "spider/crawl/engine.py:4 waits outside the Clock: self._loop.call_at(t, f)",
        "spider/crawl/engine.py:5 waits outside the Clock: asyncio.wait_for(task, 5)",
        "spider/crawl/engine.py:6 waits outside the Clock: asyncio.wait_for(task, timeout=5)",
        "spider/crawl/engine.py:7 waits outside the Clock: asyncio.wait(tasks, timeout=5)",
        "spider/crawl/engine.py:8 waits outside the Clock: asyncio.timeout(5)",
        "spider/crawl/engine.py:9 waits outside the Clock: asyncio.timeout_at(when=t)",
        "spider/crawl/engine.py:12 waits outside the Clock: aio.sleep(1)",
        "spider/crawl/engine.py:13 waits outside the Clock: t.sleep(1)",
        "spider/crawl/engine.py:14 waits outside the Clock: asyncio.tasks.sleep(1)",
        "spider/crawl/engine.py:15 waits outside the Clock: asyncio.as_completed(tasks, timeout=5)",
        "spider/crawl/engine.py:16 waits outside the Clock: cm.reschedule(t)",
        "spider/crawl/engine.py:17 sets a deadline outside the Fetcher: "
        "aiohttp.ClientTimeout(total=5)",
        "spider/crawl/politeness.py:1 imports asyncio.sleep by name",
        "spider/crawl/politeness.py:2 imports time.sleep by name",
        "spider/crawl/politeness.py:7 imports asyncio.tasks.sleep by name",
        "spider/services/crawling.py:1 waits outside the Clock: asyncio.timeout(delay=1)",
    ]
