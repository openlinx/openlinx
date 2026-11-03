"""Guard: code rules (018-add-schema-conventions; 020-add-crawl-core D7, D9, D13, D14, D19)."""

import ast
import re
import tomllib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
# Typer takes a class, not an instance, so build_app makes one per app (ADR-0006).
ALLOWED_SUBCLASSES = {("AppGroup", "OpenLinxGroup")}


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


def test_the_decidable_rules_of_adr_0006_hold_over_src_openlinx() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert violations(sources) == [], (
        "ADR-0006: give the dataclass or Struct frozen=True, compose instead of subclassing an "
        "own class, and give a memo an explicit maxsize"
    )


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
    base = "class Base: ...\nclass OpenLinxGroup: ...\n"
    derived = """
import base

class Plain(Base): ...
class Subscripted(Base[int]): ...
class Qualified(base.Base): ...
class Framework(Exception): ...
class AppGroup(OpenLinxGroup): ...
"""

    assert violations({"base.py": base, "derived.py": derived}) == [
        "derived.py: Plain subclasses Base",
        "derived.py: Subscripted subclasses Base",
        "derived.py: Qualified subclasses Base",
    ]


URL_MODULE = "openlinx/crawl/urls.py"
# Each store module that casts urls.url to a NormalizedUrl (design D13).
NORMALIZED_URL_MAKERS = {URL_MODULE, "openlinx/store/urls.py"}


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
                if name == "openlinx" or name.startswith(("openlinx.", "."))
            ]
        if module not in NORMALIZED_URL_MAKERS and any(map(_makes_normalized_url, ast.walk(tree))):
            found.append(f"{module} makes a NormalizedUrl")
    return found


def test_the_rules_of_design_d13_of_020_hold_over_src_openlinx() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert url_type_violations(sources) == [], (
        "a NormalizedUrl is made only in openlinx.crawl.urls and openlinx.store.urls, and "
        "openlinx.crawl.urls imports nothing of openlinx: call normalize_url instead"
    )


def test_an_import_of_openlinx_in_the_url_module_is_named() -> None:
    source = """
import re
import openlinx.output
from openlinx.store.records import LinkType
from . import scope

def late():
    import openlinx
"""

    assert url_type_violations({URL_MODULE: source}) == [
        f"{URL_MODULE} imports openlinx.output",
        f"{URL_MODULE} imports openlinx.store.records",
        f"{URL_MODULE} imports .",
        f"{URL_MODULE} imports openlinx",
    ]


def test_a_normalized_url_made_outside_its_makers_is_named() -> None:
    sources = {
        URL_MODULE: "NormalizedUrl('http://site.test/')\n",
        "openlinx/crawl/scope.py": "urls.NormalizedUrl('http://site.test/')\n",
        "openlinx/crawl/engine/dispatch.py": "url = NormalizedUrl('http://site.test/')\n",
        "openlinx/store/pages.py": "url = cast(NormalizedUrl, row.url)\n",
        "openlinx/store/urls.py": "url = NormalizedUrl(row.url)\n",
        "openlinx/store/origins.py": "url = typing.cast('NormalizedUrl', row.url)\n",
        "openlinx/crawl/frontier.py": "def f(url: NormalizedUrl) -> None: ...\n",
        "openlinx/crawl/pages/links.py": "n = cast(int, row.n)\n",
    }

    assert url_type_violations(sources) == [
        "openlinx/crawl/scope.py makes a NormalizedUrl",
        "openlinx/crawl/engine/dispatch.py makes a NormalizedUrl",
        "openlinx/store/pages.py makes a NormalizedUrl",
        "openlinx/store/origins.py makes a NormalizedUrl",
    ]


# Only the store writes SQL; the schema service loads sqlalchemy lazily (020-add-crawl-core D14).
SQLALCHEMY_IMPORTERS = ("openlinx/store/", "openlinx/services/schema.py")


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
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert sqlalchemy_violations(sources) == [], (
        "SQL lives in openlinx.store: build the statement there (openlinx.store.query for "
        "--where) and call it from your service"
    )


# Only the CLI loads Typer: a service called without it, as the MCP server will call it, must not
# load Typer or the CLI's adapters (023-fix-code-audit D9).
CLI_MODULES = ("openlinx/cli/", "openlinx/__main__.py")


def cli_import_violations(sources: Mapping[str, str]) -> list[str]:
    """Modules outside the CLI that import typer or openlinx.cli, given every module's source.
    Relative imports, which would hide the name, are banned by ruff's TID252."""
    return [
        f"{module} imports {name}"
        for module, source in sources.items()
        if not module.startswith(CLI_MODULES)
        for name in _modules_and_submodules(ast.parse(source))
        if name.partition(".")[0] == "typer"
        or name == "openlinx.cli"
        or name.startswith("openlinx.cli.")
    ]


def _modules_and_submodules(tree: ast.AST) -> list[str]:
    """The modules imported, and for `from openlinx import cli` the submodule too."""
    found = _imported_modules(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "openlinx" and not node.level:
            found += [f"openlinx.{alias.name}" for alias in node.names]
    return found


def test_no_service_imports_the_cli() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert cli_import_violations(sources) == [], (
        "a module outside openlinx.cli imports typer or openlinx.cli: take plain values and raise "
        "OpenLinxError, and let the CLI adapter in openlinx.cli map flags to them"
    )


def test_an_import_of_the_cli_under_it_is_named() -> None:
    sources = {
        "openlinx/services/crawling.py": "def late():\n    import typer\n",
        "openlinx/workspace/settings.py": "from openlinx.cli.options import OptionMeta\n",
        "openlinx/output/writer.py": "from typer.testing import CliRunner\n",
        "openlinx/extract/page_data.py": "from openlinx import cli\n",
        "openlinx/store/urls.py": "import typing\nfrom openlinx.clock import Clock\n",
        "openlinx/query/compiler.py": "import typer\n",
        "openlinx/naming.py": "from openlinx.cli import options\n",
        "openlinx/cli/crawl.py": "import typer\n",
        "openlinx/__main__.py": "from openlinx.cli.app import main\n",
    }

    assert cli_import_violations(sources) == [
        "openlinx/services/crawling.py imports typer",
        "openlinx/workspace/settings.py imports openlinx.cli.options",
        "openlinx/output/writer.py imports typer.testing",
        "openlinx/extract/page_data.py imports openlinx.cli",
        "openlinx/query/compiler.py imports typer",
        "openlinx/naming.py imports openlinx.cli",
    ]


def test_an_import_of_sqlalchemy_outside_the_store_is_named() -> None:
    sources = {
        "openlinx/crawl/engine/dispatch.py": "import sqlalchemy\n",
        "openlinx/crawl/frontier.py": "from sqlalchemy.dialects.sqlite import insert\n",
        "openlinx/services/crawling.py": "def late():\n    from sqlalchemy import select\n",
        "openlinx/crawl/pages/links.py": "import sqlalchemy_utils\n"
        "from openlinx.store import urls\n",
        "openlinx/store/urls.py": "from sqlalchemy import insert\n",
        "openlinx/services/schema.py": "def late():\n    from sqlalchemy.dialects import sqlite\n",
    }

    assert sqlalchemy_violations(sources) == [
        "openlinx/crawl/engine/dispatch.py imports sqlalchemy",
        "openlinx/crawl/frontier.py imports sqlalchemy.dialects.sqlite",
        "openlinx/services/crawling.py imports sqlalchemy",
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


# The crawl core never imports the layers that wire it or plug into it (020-add-crawl-core D9).
PLUGIN_LAYERS = ("openlinx.services", "openlinx.extract", "openlinx.rules", "openlinx.cli")


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
            # `from openlinx import rules` names the layer in the alias.
            found += (
                [f"{base}.{alias.name}" for alias in node.names] if base == "openlinx" else [base]
            )
    return [
        name
        for name in found
        if any(name == layer or name.startswith(f"{layer}.") for layer in PLUGIN_LAYERS)
    ]


def plugin_import_violations(sources: Mapping[str, str]) -> list[str]:
    """Modules of openlinx.crawl that import a plugin layer, given every module's source by path."""
    return [
        f"{module} imports {name}"
        for module, source in sources.items()
        if module.startswith("openlinx/crawl/")
        for name in _plugin_imports(module, ast.parse(source))
    ]


def test_the_crawl_core_imports_no_plugin_layer() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert plugin_import_violations(sources) == [], (
        "the crawl core imports no plugin layer: register the hook in default_hooks() in "
        "openlinx.services.hooks, which the crawl core never imports"
    )


def test_an_import_of_a_plugin_layer_in_the_crawl_core_is_named() -> None:
    sources = {
        "openlinx/crawl/engine/dispatch.py": "from openlinx.services.hooks import default_hooks\n",
        "openlinx/crawl/pages/preparation.py": "def late():\n    import openlinx.extract.page\n",
        "openlinx/crawl/scope.py": "from openlinx import rules, store\n",
        "openlinx/crawl/pages/links.py": "from ...cli import app\n",
        "openlinx/crawl/engine/hooks.py": "from openlinx.store import rows\n"
        "import openlinx.servicesx\n",
        "openlinx/services/crawling.py": "from openlinx.services.hooks import default_hooks\n",
    }

    assert plugin_import_violations(sources) == [
        "openlinx/crawl/engine/dispatch.py imports openlinx.services.hooks",
        "openlinx/crawl/pages/preparation.py imports openlinx.extract.page",
        "openlinx/crawl/scope.py imports openlinx.rules",
        "openlinx/crawl/pages/links.py imports openlinx.cli",
    ]


@dataclass(frozen=True)
class ImportRule:
    """Modules within `importers` import nothing within `forbidden` but what is within `allowed`.

    A name ending in ".*" holds the modules directly in its package.
    """

    importers: str
    forbidden: tuple[str, ...]
    allowed: tuple[str, ...] = ()


# Inside openlinx.crawl, imports run one way: top-level modules, fetch, then pages and robots, which
# are peers, then engine (020-add-crawl-core design D19).
IMPORT_RULES = (
    ImportRule(
        "openlinx.crawl.*",
        (
            "openlinx.crawl.fetch",
            "openlinx.crawl.pages",
            "openlinx.crawl.robots",
            "openlinx.crawl.engine",
        ),
    ),
    ImportRule(
        "openlinx.crawl.fetch",
        ("openlinx.crawl.pages", "openlinx.crawl.robots", "openlinx.crawl.engine"),
    ),
    ImportRule("openlinx.crawl.pages", ("openlinx.crawl.robots", "openlinx.crawl.engine")),
    ImportRule("openlinx.crawl.robots", ("openlinx.crawl.pages", "openlinx.crawl.engine")),
    # The one cycle between the crawl core and the store runs through urls, which imports nothing.
    ImportRule("openlinx.store", ("openlinx.crawl",), allowed=("openlinx.crawl.urls",)),
    # The parse pool's workers import pages, so they never load the writer.
    ImportRule("openlinx.crawl.pages", ("openlinx.store",), allowed=("openlinx.store.records",)),
)


def _module_name(path: str) -> str:
    return path.removesuffix(".py").removesuffix("/__init__").replace("/", ".")


def _within(module: str, name: str) -> bool:
    if name.endswith(".*"):
        package = name.removesuffix("*")
        return module.startswith(package) and "." not in module.removeprefix(package)
    return module == name or module.startswith(f"{name}.")


def _imported(path: str, tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(path, node.level, node.module)
            # `from openlinx.crawl import pages` names the module in the alias.
            found += [f"{base}.{alias.name}" for alias in node.names]
    return found


def import_rule_violations(
    sources: Mapping[str, str], rules: Sequence[ImportRule] = IMPORT_RULES
) -> list[str]:
    """Imports that break a rule, given every module's source by its path."""
    return [
        f"{path} imports {name}"
        for path, source in sources.items()
        for rule in rules
        if _within(_module_name(path), rule.importers)
        for name in _imported(path, ast.parse(source))
        if any(_within(name, forbidden) for forbidden in rule.forbidden)
        and not any(_within(name, allowed) for allowed in rule.allowed)
    ]


def unnamed_modules(rules: Sequence[ImportRule], paths: Iterable[str]) -> list[str]:
    """Names of the rules that name no module, and the packages of openlinx.crawl they leave out."""
    modules = {_module_name(path) for path in paths}
    named = {
        name.removesuffix(".*")
        for rule in rules
        for name in (rule.importers, *rule.forbidden, *rule.allowed)
    }
    packages = {
        _module_name(path)
        for path in paths
        if path.startswith("openlinx/crawl/")
        and path.endswith("/__init__.py")
        and path.count("/") == 3
    }
    return [f"{name} names no module" for name in sorted(named - modules)] + [
        f"{package} is a package of openlinx.crawl that no import rule names"
        for package in sorted(packages - named - {"openlinx.crawl"})
    ]


def _src_sources() -> dict[str, str]:
    return {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }


def test_the_crawl_imports_run_one_way() -> None:
    assert import_rule_violations(_src_sources()) == [], (
        "an import breaks a rule of IMPORT_RULES: move the shared code into a module the rule "
        "allows, and import it from there"
    )


def test_an_import_against_an_import_rule_is_named() -> None:
    sources = {
        "openlinx/crawl/fetch/requester.py": "from openlinx.crawl.pages.preparation import x\n",
        "openlinx/crawl/pages/links.py": "from ..robots.reader import OriginRobots\n",
        "openlinx/crawl/robots/loader.py": "def late():\n    from openlinx.crawl import engine\n",
        "openlinx/crawl/scope.py": "if TYPE_CHECKING:\n"
        "    from openlinx.crawl.pages import links\n",
        "openlinx/store/urls.py": (
            "from openlinx.crawl.scope import ScopeRules\n"
            "from openlinx.crawl.urls import NormalizedUrl\n"
        ),
        "openlinx/crawl/pages/preparation.py": (
            "import openlinx.store.writer\nfrom openlinx.store.records import ParseError\n"
        ),
        "openlinx/crawl/engine/units.py": (
            "from openlinx.crawl.pages.preparation import x\nfrom openlinx.store.writer import y\n"
        ),
        "openlinx/crawl/pages/headers.py": (
            "from .links import rel_tokens\nfrom openlinx.crawl.fetch.fetcher import FetchResult\n"
        ),
        "openlinx/crawl/references.py": "from openlinx.crawl.urls import NormalizedUrl\n",
    }

    assert import_rule_violations(sources) == [
        "openlinx/crawl/fetch/requester.py imports openlinx.crawl.pages.preparation.x",
        "openlinx/crawl/pages/links.py imports openlinx.crawl.robots.reader.OriginRobots",
        "openlinx/crawl/robots/loader.py imports openlinx.crawl.engine",
        "openlinx/crawl/scope.py imports openlinx.crawl.pages.links",
        "openlinx/store/urls.py imports openlinx.crawl.scope.ScopeRules",
        "openlinx/crawl/pages/preparation.py imports openlinx.store.writer",
    ]


def test_the_import_rules_name_each_crawl_package_and_no_missing_module() -> None:
    assert unnamed_modules(IMPORT_RULES, _src_sources()) == [], (
        "every package of openlinx.crawl has an import rule, and every rule names a module "
        "that exists: add the package to IMPORT_RULES, or fix the rule's name"
    )


def test_a_module_that_an_import_rule_names_and_that_does_not_exist_is_named() -> None:
    rules = (
        ImportRule("openlinx.crawl.frontier", ("openlinx.crawl.pages",)),
        ImportRule(
            "openlinx.store", ("openlinx.crawl",), allowed=("openlinx.crawl.fetch.retries",)
        ),
    )
    paths = (
        "openlinx/crawl/__init__.py",
        "openlinx/crawl/pages/__init__.py",
        "openlinx/crawl/pages/links.py",
        "openlinx/crawl/redirects/__init__.py",
        "openlinx/store/__init__.py",
    )

    assert unnamed_modules(rules, paths) == [
        "openlinx.crawl.fetch.retries names no module",
        "openlinx.crawl.frontier names no module",
        "openlinx.crawl.redirects is a package of openlinx.crawl that no import rule names",
    ]


# lexbor's serializer recurses into template content: `.html` of a <template> nested 20,000
# deep ends the process with a native stack overflow (020-add-crawl-core design Risks).
SERIALIZERS = frozenset({"html", "inner_html", "html_pretty", "inner_html_pretty"})
PAGE_READERS = ("openlinx/crawl/", "openlinx/extract/")


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
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert serializer_violations(sources) == [], (
        "a module that reads Pages never serializes a node, which overflows the stack on a "
        "deep tree: read the node's attributes or text instead"
    )


def test_a_serialization_of_a_node_is_named() -> None:
    sources = {
        "openlinx/crawl/pages/links.py": "def f(node):\n    return node.html\n",
        "openlinx/extract/page_data.py": "text = tree.body.inner_html\n",
        "openlinx/crawl/pages/preparation.py": "x = node.css('a')\ny = node.attributes\n",
        "openlinx/report/html.py": "page = node.html\n",
    }

    assert serializer_violations(sources) == [
        "openlinx/crawl/pages/links.py:2 serializes a node with .html, "
        "which overflows the stack on "
        "deeply nested templates",
        "openlinx/extract/page_data.py:1 serializes a node with .inner_html, which overflows the "
        "stack on deeply nested templates",
    ]


# With scripting off, a head <noscript><img> ends <head> (020-add-crawl-core design D5). The one
# fragment parse reads an HTML <noscript>'s text as markup.
FRAGMENT_PARSE = ("openlinx/crawl/pages/links.py", "_noscript_links")


def _calls_in_functions(
    node: ast.AST, function: str | None = None
) -> Iterator[tuple[ast.Call, str | None]]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _calls_in_functions(child, child.name)
            continue
        if isinstance(child, ast.Call):
            yield child, function
        yield from _calls_in_functions(child, function)


def _sets(call: ast.Call, flag: str) -> bool:
    return any(
        keyword.arg == flag
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def _parses(sources: Mapping[str, str]) -> list[tuple[str, int, str | None]]:
    """Each parser built in the modules that read Pages, with what it breaches, if anything."""
    found = []
    for module, source in sources.items():
        if not module.startswith(PAGE_READERS):
            continue
        tree = ast.parse(source)
        names = {"LexborHTMLParser"} | {
            alias.asname
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if alias.name == "LexborHTMLParser" and alias.asname
        }
        for call, function in _calls_in_functions(tree):
            if _base_name(call.func) not in names:
                continue
            breach = None
            if _sets(call, "is_fragment") and (module, function) != FRAGMENT_PARSE:
                breach = "parses a fragment outside the noscript re-parse"
            elif not _sets(call, "scripting") and not _sets(call, "is_fragment"):
                breach = "parses a document with scripting off"
            found.append((module, call.lineno, breach))
    return found


def parse_violations(sources: Mapping[str, str]) -> list[str]:
    """Parsers that break design D5, given every module's source by path."""
    return [f"{module}:{line} {breach}" for module, line, breach in _parses(sources) if breach]


def test_every_page_is_parsed_with_scripting_on() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert (parse_violations(sources), bool(_parses(sources))) == ([], True), (
        "a Page is parsed as a browser that runs scripts parses it: use "
        "openlinx.crawl.pages.links.parse_html"
    )


def test_a_parse_with_scripting_off_is_named() -> None:
    sources = {
        "openlinx/crawl/pages/links.py": (
            "tree = LexborHTMLParser(text)\n"
            "def _noscript_links(text):\n"
            "    return LexborHTMLParser(text, is_fragment=True)\n"
        ),
        "openlinx/extract/page_data.py": "tree = lexbor.LexborHTMLParser(text, scripting=False)\n",
        "openlinx/crawl/pages/preparation.py": (
            "a = LexborHTMLParser(text, scripting=True)\n"
            "def prepare(text):\n"
            "    return LexborHTMLParser(text, is_fragment=True)\n"
        ),
        "openlinx/crawl/pages/headers.py": (
            "from selectolax.lexbor import LexborHTMLParser as Parser\ntree = Parser(text)\n"
        ),
        "openlinx/report/html.py": "tree = LexborHTMLParser(text)\n",
    }

    assert parse_violations(sources) == [
        "openlinx/crawl/pages/links.py:1 parses a document with scripting off",
        "openlinx/extract/page_data.py:1 parses a document with scripting off",
        "openlinx/crawl/pages/preparation.py:3 parses a fragment outside the noscript re-parse",
        "openlinx/crawl/pages/headers.py:2 parses a document with scripting off",
    ]


# Every request of a Crawl goes through the Requester, which owns its politeness
# (020-add-crawl-core D7).
REQUESTER = "openlinx/crawl/fetch/requester.py"


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
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert request_violations(sources) == [], (
        "every request goes through the Requester: call request_url or request_robots_txt of "
        "openlinx.crawl.fetch.requester"
    )


def test_a_request_outside_the_requester_is_named() -> None:
    sources = {
        "openlinx/crawl/robots/loader.py": "async def f(self, url):\n"
        "    return await self._fetcher.fetch(Request(url))\n",
        "openlinx/crawl/engine/dispatch.py": (
            "fetch = context.fetcher.fetch\nrequest = fetcher.Request(u)\n"
        ),
        REQUESTER: "async def f(self, url):\n    return await self._fetcher.fetch(Request(url))\n",
        "openlinx/crawl/fetch/fetcher.py": "class AiohttpFetcher:\n"
        "    async def fetch(self, request): ...\n",
    }

    assert request_violations(sources) == [
        "openlinx/crawl/robots/loader.py:2 calls a Fetcher outside the Requester",
        "openlinx/crawl/robots/loader.py:2 makes a Request outside the Requester",
        "openlinx/crawl/engine/dispatch.py:1 calls a Fetcher outside the Requester",
        "openlinx/crawl/engine/dispatch.py:2 makes a Request outside the Requester",
    ]


# Built only through their generic factories, which check the type parameter where the hooks are
# registered: one built in place inside Hooks(...) takes it as Any (020-add-crawl-core D9).
FACTORIES = {
    "Handler": "src/openlinx/crawl/engine/hooks.py",
    "Extractor": "src/openlinx/crawl/pages/preparation.py",
}


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
        for folder in (SRC / "openlinx", root / "tests")
        for path in sorted(folder.rglob("*.py"))
    }

    assert factory_violations(sources) == [], (
        "a hook is built only through its factory: handler(name, handle, write) or "
        "extractor(name, extract, config)"
    )


def test_a_hook_built_outside_its_factory_is_named() -> None:
    sources = {
        "tests/crawl/test_hooks.py": "hooks = Hooks(handlers=(Handler('x', rows, write),))\n",
        "src/openlinx/services/hooks.py": "h = hooks.Handler('x', rows, write)\n",
        "src/openlinx/crawl/engine/hooks.py": "def handler(n, h, w):\n"
        "    return Handler(n, h, w)\n",
        "src/openlinx/services/pages.py": "e = pages.Extractor('x', extract, None)\n",
        "src/openlinx/crawl/pages/preparation.py": (
            "def extractor(n, e, c):\n    return Extractor(n, e, c)\n"
        ),
    }

    assert factory_violations(sources) == [
        "tests/crawl/test_hooks.py:1 builds Handler(...) outside its factory",
        "src/openlinx/services/hooks.py:1 builds Handler(...) outside its factory",
        "src/openlinx/services/pages.py:1 builds Extractor(...) outside its factory",
    ]


# A Crawl waits only through its Clock, so a fake Clock drives every wait of a test
# (020-add-crawl-core D7).
WAITERS = ("openlinx/crawl/", "openlinx/services/crawling.py")
# The one deadline outside the Clock bounds a real request, where timing tests put a fake Fetcher.
FETCHER = "openlinx/crawl/fetch/fetcher.py"
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
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert wait_violations(sources) == [], (
        "a Crawl waits only through its Clock: await clock.sleep(...), import asyncio's waits "
        "by module, and set a request's deadline only in the Fetcher"
    )


def test_a_wait_outside_the_clock_is_named() -> None:
    sources = {
        "openlinx/crawl/engine/dispatch.py": "await asyncio.sleep(0)\n"
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
        "openlinx/crawl/fetch/politeness.py": "from asyncio import sleep, Lock\n"
        "from time import sleep\n"
        "await self._clock.sleep(1)\n"
        "await asyncio.wait_for(task, None)\n"
        "await asyncio.wait(tasks)\n"
        "async with asyncio.timeout(None): ...\n"
        "from asyncio.tasks import sleep as nap\n"
        "for done in asyncio.as_completed(tasks): ...\n",
        "openlinx/crawl/fetch/fetcher.py": "timeout = aiohttp.ClientTimeout(total=20)\n",
        "openlinx/services/crawling.py": "async with asyncio.timeout(delay=1): ...\n",
        "openlinx/services/listing.py": "await asyncio.sleep(1)\n",
        "openlinx/clock.py": "await asyncio.sleep(seconds)\n",
    }

    assert wait_violations(sources) == [
        "openlinx/crawl/engine/dispatch.py:1 waits outside the Clock: asyncio.sleep(0)",
        "openlinx/crawl/engine/dispatch.py:2 waits outside the Clock: time.sleep(1)",
        "openlinx/crawl/engine/dispatch.py:3 waits outside the Clock: loop.call_later(1, f)",
        "openlinx/crawl/engine/dispatch.py:4 waits outside the Clock: self._loop.call_at(t, f)",
        "openlinx/crawl/engine/dispatch.py:5 waits outside the Clock: asyncio.wait_for(task, 5)",
        "openlinx/crawl/engine/dispatch.py:6 waits outside the Clock: "
        "asyncio.wait_for(task, timeout=5)",
        "openlinx/crawl/engine/dispatch.py:7 waits outside the Clock: "
        "asyncio.wait(tasks, timeout=5)",
        "openlinx/crawl/engine/dispatch.py:8 waits outside the Clock: asyncio.timeout(5)",
        "openlinx/crawl/engine/dispatch.py:9 waits outside the Clock: asyncio.timeout_at(when=t)",
        "openlinx/crawl/engine/dispatch.py:12 waits outside the Clock: aio.sleep(1)",
        "openlinx/crawl/engine/dispatch.py:13 waits outside the Clock: t.sleep(1)",
        "openlinx/crawl/engine/dispatch.py:14 waits outside the Clock: asyncio.tasks.sleep(1)",
        "openlinx/crawl/engine/dispatch.py:15 waits outside the Clock: "
        "asyncio.as_completed(tasks, timeout=5)",
        "openlinx/crawl/engine/dispatch.py:16 waits outside the Clock: cm.reschedule(t)",
        "openlinx/crawl/engine/dispatch.py:17 sets a deadline outside the Fetcher: "
        "aiohttp.ClientTimeout(total=5)",
        "openlinx/crawl/fetch/politeness.py:1 imports asyncio.sleep by name",
        "openlinx/crawl/fetch/politeness.py:2 imports time.sleep by name",
        "openlinx/crawl/fetch/politeness.py:7 imports asyncio.tasks.sleep by name",
        "openlinx/services/crawling.py:1 waits outside the Clock: asyncio.timeout(delay=1)",
    ]


# Work the loop waits for on another thread holds the Clock, so a test's virtual clock never
# jumps meanwhile (020-add-crawl-core D7).
HANDOFFS = {
    "to_thread",
    "run_in_executor",
    "wrap_future",
    "call_soon_threadsafe",
    "run_coroutine_threadsafe",
}
# A submitted unit's Future resolves at its commit, which comes at the loop's commit deadline
# and so waits for clock time: a hold would stop the time it waits for. This one call only.
WAITS_FOR_CLOCK_TIME = {("openlinx/store/writer.py", "submit_async", "asyncio.wrap_future(done)")}
# A signal handler schedules the stop from the loop's own thread, between two bytecodes; the
# loop waits for nothing it hands over, so no hold is needed. This one call only.
FROM_A_SIGNAL_HANDLER = {
    (
        "openlinx/services/interrupts.py",
        "handler",
        "loop.call_soon_threadsafe(stop.set, 'interrupt')",
    )
}


class _HandOffs(ast.NodeVisitor):
    """Hand-offs outside an off_loop() block. A function defined inside the block runs later,
    when the hold may be gone, so its calls count as outside."""

    def __init__(self, module: str, tree: ast.Module) -> None:
        self._module = module
        # `from asyncio import to_thread as off` makes a bare off() a hand-off too.
        self._names = {
            alias.asname or alias.name: alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if alias.name in HANDOFFS
        }
        self._held = 0
        self._function = ""
        self.found: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> None:
        held, function = self._held, self._function
        self._held = 0
        if not isinstance(node, ast.Lambda):
            self._function = node.name
        self.generic_visit(node)
        self._held, self._function = held, function

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_Lambda = visit_FunctionDef

    def visit_With(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item)
        holds = any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr == "off_loop"
            for item in node.items
        )
        self._held += holds
        for statement in node.body:
            self.visit(statement)
        self._held -= holds

    visit_AsyncWith = visit_With

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            name: str | None = node.func.attr
        elif isinstance(node.func, ast.Name):
            name = self._names.get(node.func.id)
        else:
            name = None
        call = (self._module, self._function, ast.unparse(node))
        exempt = call in WAITS_FOR_CLOCK_TIME or call in FROM_A_SIGNAL_HANDLER
        if name in HANDOFFS and not self._held and not exempt:
            self.found.append(
                f"{self._module}:{node.lineno} hands off outside clock.off_loop(): "
                f"{ast.unparse(node.func)}"
            )
        self.generic_visit(node)


def handoff_violations(sources: Mapping[str, str]) -> list[str]:
    """Hand-offs to another thread or process outside the Clock's hold, by module path."""
    found: list[str] = []
    for module, source in sources.items():
        tree = ast.parse(source)
        visitor = _HandOffs(module, tree)
        visitor.visit(tree)
        found += visitor.found
    return sorted(set(found))


def test_every_hand_off_to_another_thread_holds_the_clock() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted((SRC / "openlinx").rglob("*.py"))
    }

    assert handoff_violations(sources) == [], (
        "a hand-off to another thread or process holds the Clock: wrap it in "
        "`with clock.off_loop():`, so a FakeClock does not run ahead of it"
    )


def test_a_hand_off_outside_the_hold_is_named() -> None:
    sources = {
        "openlinx/services/crawling.py": "async def open():\n"
        "    writer = await asyncio.to_thread(CrawlWriter, path)\n"
        "    with clock.off_loop():\n"
        "        await asyncio.to_thread(writer.close)\n"
        "    await loop.run_in_executor(None, work)\n",
        "openlinx/store/writer.py": "async def submit_async(self):\n"
        "    asyncio.wrap_future(other)\n"
        "    return asyncio.wrap_future(done)\n"
        "async def run_async(self):\n"
        "    return await asyncio.wrap_future(done)\n",
        "openlinx/pool.py": "from asyncio import run_coroutine_threadsafe\n"
        "from asyncio import to_thread as off\n"
        "async def prepare():\n"
        "    with clock.off_loop():\n"
        "        def later():\n"
        "            loop.call_soon_threadsafe(done)\n"
        "        await off(work)\n"
        "    await off(work)\n"
        "    run_coroutine_threadsafe(job, loop)\n",
    }

    assert handoff_violations(sources) == [
        "openlinx/pool.py:6 hands off outside clock.off_loop(): loop.call_soon_threadsafe",
        "openlinx/pool.py:8 hands off outside clock.off_loop(): off",
        "openlinx/pool.py:9 hands off outside clock.off_loop(): run_coroutine_threadsafe",
        "openlinx/services/crawling.py:2 hands off outside clock.off_loop(): asyncio.to_thread",
        "openlinx/services/crawling.py:5 hands off outside clock.off_loop(): loop.run_in_executor",
        "openlinx/store/writer.py:2 hands off outside clock.off_loop(): asyncio.wrap_future",
        "openlinx/store/writer.py:5 hands off outside clock.off_loop(): asyncio.wrap_future",
    ]


# Real I/O makes no clock call, so the virtual clock would jump while a request is in flight and
# fire a deadline that production never fires (020-add-crawl-core D7).
REAL_IO_CALLS = {"AiohttpFetcher", "aiohttp_fetcher", "ClientSession"}
REAL_IO_FIXTURES = {"fixture_site", "fixture_hosts"}
# Without a fake Fetcher, these crawl through the aiohttp Fetcher.
CRAWLS = {"crawl_result", "start_crawl", "continued", "continue_crawl"}


def _called(call: ast.Call) -> str:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return call.func.id if isinstance(call.func, ast.Name) else ""


def fake_clock_with_real_io(sources: Mapping[str, str]) -> list[str]:
    """Test functions that pair FakeClock with the fixture site or the aiohttp Fetcher."""
    found: list[str] = []
    for module, source in sources.items():
        for function in ast.walk(ast.parse(source)):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
            called = {_called(call) for call in calls}
            if "FakeClock" not in called:
                continue
            arguments = {argument.arg for argument in function.args.args}
            unfaked_crawl = any(
                _called(call) in CRAWLS
                and not any(keyword.arg == "fetcher" for keyword in call.keywords)
                for call in calls
            )
            if arguments & REAL_IO_FIXTURES or called & REAL_IO_CALLS or unfaked_crawl:
                found.append(
                    f"{module}:{function.lineno} {function.name} pairs FakeClock with real I/O"
                )
    return sorted(found)


def test_no_test_pairs_the_virtual_clock_with_real_io() -> None:
    tests = Path(__file__).resolve().parent
    sources = {
        path.relative_to(tests.parent).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(tests.rglob("*.py"))
    }

    assert fake_clock_with_real_io(sources) == [], (
        "a FakeClock test uses FakeFetcher, never the fixture site or aiohttp: pass "
        "fetcher=FakeFetcher(clock, pages), or use SystemClock with the fixture site"
    )


def test_a_virtual_clock_beside_real_io_is_named() -> None:
    sources = {
        "tests/crawl/test_timing.py": "def test_site(temp_workspace, fixture_site):\n"
        "    clock = FakeClock()\n"
        "async def test_session():\n"
        "    async with aiohttp.ClientSession() as session:\n"
        "        await AiohttpFetcher(session, FakeClock()).fetch(request)\n"
        "def test_crawl(temp_workspace):\n"
        "    crawl_result(seed, clock=FakeClock())\n"
        "def test_fake(temp_workspace):\n"
        "    clock = FakeClock()\n"
        "    crawl_result(seed, clock=clock, fetcher=FakeFetcher(clock, {}))\n"
        "def test_system(temp_workspace, fixture_site):\n"
        "    crawl_result(server.url('/'), clock=SystemClock())\n"
        "def test_continue(temp_workspace):\n"
        "    continued(result, clock=FakeClock())\n",
    }

    assert fake_clock_with_real_io(sources) == [
        "tests/crawl/test_timing.py:1 test_site pairs FakeClock with real I/O",
        "tests/crawl/test_timing.py:13 test_continue pairs FakeClock with real I/O",
        "tests/crawl/test_timing.py:3 test_session pairs FakeClock with real I/O",
        "tests/crawl/test_timing.py:6 test_crawl pairs FakeClock with real I/O",
    ]


# Click's internals have no public path, and the runner owns the raw streams (design D15 of 023).
TID251_SUPPRESSIONS = {"openlinx/cli/click_compat.py": 2, "openlinx/cli/runner.py": 1}
# Every spelling that may silence it, a line's or a file's (ruff: or flake8:), in any case and
# with or without spaces, alone or among other codes; matching more is only stricter.
TID251_NOQA = re.compile(r"#\s*(?:(?:ruff|flake8)\s*:\s*)?noqa\s*:[^#\n]*\bTID251\b", re.IGNORECASE)
PYPROJECT = SRC.parent / "pyproject.toml"


def tid251_suppressions(source: str) -> int:
    return len(TID251_NOQA.findall(source))


@pytest.mark.parametrize(
    ("line", "count"),
    [
        ('sys.stdout.write("y")  # noqa: TID251', 1),
        ('sys.stdout.write("y")  # noqa:TID251', 1),
        ('sys.stdout.write("y")  #noqa : TID251', 1),
        ('sys.stdout.write("y")  # NOQA: TID251', 1),
        ('sys.stdout.write("y")  # noqa: E501, TID251', 1),
        ("# ruff: noqa: TID251", 1),
        ("# flake8: noqa: TID251", 1),
        ('sys.stdout.write("y")  # noqa: E501', 0),
        ('sys.stdout.write("y")  # noqa: TID2510', 0),
    ],
)
def test_every_spelling_of_a_tid251_suppression_is_counted(line: str, count: int) -> None:
    assert tid251_suppressions(line) == count


def test_only_the_streams_and_click_compat_suppress_tid251() -> None:
    found: dict[str, int] = {}
    for path, source in _src_sources().items():
        count = tid251_suppressions(source)
        if count:
            found[path] = count

    assert found == TID251_SUPPRESSIONS, (
        "TID251 is suppressed beyond its three lines in openlinx.cli.click_compat and the runner's "
        "streams: write output through openlinx.output, and import Click through "
        "openlinx.cli.click_compat"
    )


def test_no_per_file_ignore_silences_tid251_in_src() -> None:
    lint = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["ruff"]["lint"]
    ignores = {**lint.get("per-file-ignores", {}), **lint.get("extend-per-file-ignores", {})}

    # A prefix such as TID or ALL selects TID251 too.
    assert [
        pattern
        for pattern, codes in ignores.items()
        if not pattern.startswith(("tests/", "scripts/"))
        and any("TID251".startswith(code) or code == "ALL" for code in codes)
    ] == [], (
        "a per-file-ignore silences TID251 in src: remove it, and suppress only the lines "
        "in openlinx.cli.click_compat and the runner's streams"
    )
