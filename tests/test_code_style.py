"""Guard: decidable code rules (018-add-schema-conventions; 020-add-crawl-core D9, D13, D14)."""

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
