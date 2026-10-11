"""Guard: decidable code rules (018-add-schema-conventions; 020-add-crawl-core D13)."""

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


def _is_frozen(decorator: ast.expr) -> bool:
    return isinstance(decorator, ast.Call) and any(
        keyword.arg == "frozen"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in decorator.keywords
    )


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Subscript):
        base = base.value
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


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
            found += [
                f"{module}: {node.name} subclasses {name}"
                for name in map(_base_name, node.bases)
                if name in own_class_names and (node.name, name) not in ALLOWED_SUBCLASSES
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
NORMALIZED_URL_MAKERS = {URL_MODULE}


def _imported_modules(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
    return found


def _calls_normalized_url(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "NormalizedUrl")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "NormalizedUrl")
        )
        for node in ast.walk(tree)
    )


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
        if module not in NORMALIZED_URL_MAKERS and _calls_normalized_url(tree):
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
        "spider/crawl/frontier.py": "def f(url: NormalizedUrl) -> None: ...\n",
    }

    assert url_type_violations(sources) == [
        "spider/crawl/scope.py makes a NormalizedUrl",
        "spider/crawl/engine.py makes a NormalizedUrl",
    ]
