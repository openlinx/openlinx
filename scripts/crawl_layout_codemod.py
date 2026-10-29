"""Rewrites a tree's imports for the crawl package layout (020-add-crawl-core design D19).

Every branch that merges the layout move runs it once on its own tree, then lets ruff sort the
imports and wrap the lines:

    uv run python scripts/crawl_layout_codemod.py src tests scripts
    uv run ruff check --select I --fix . && uv run ruff format .

It rewrites the .py files under each path given and prints each file it changed; a second run
changes nothing. `from openlinx.crawl import engine` (or pages, robots) means the old module, and
a bare `openlinx.crawl.engine` (or pages, robots) the new package.
"""

import argparse
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

# The old modules of openlinx.crawl, each with its new place under openlinx.crawl.
MOVED = {
    "fetcher": "fetch.fetcher",
    "politeness": "fetch.politeness",
    "requester": "fetch.requester",
    "pages": "pages.preparation",
    "links": "pages.links",
    "headers": "pages.headers",
    "refresh": "pages.refresh",
    "decoding": "pages.decoding",
    "directives": "pages.directives",
    "robots": "robots.reader",
    "robots_loader": "robots.loader",
    "engine": "engine.dispatch",
    "units": "engine.units",
    "outcomes": "engine.outcomes",
    "discovery": "engine.discovery",
    "context": "engine.context",
    "hooks": "engine.hooks",
    "stop": "engine.stop",
    "warning_log": "engine.warning_log",
    "crawl_warnings": "engine.crawl_warnings",
}
# Names that went to another module than the rest of their old module.
MOVED_NAMES = {
    ("links", "DiscoveredLink"): "references",
    ("links", "resolve_reference"): "references",
}

_PACKAGES = {new.partition(".")[0] for new in MOVED.values()}
_SUBMODULES = {new.partition(".")[2] for new in MOVED.values()}
_SKIPPED_FOLDERS = {".git", ".venv", "node_modules", "__pycache__"}

_IMPORT_FROM = re.compile(
    r"^(?P<indent>[ \t]*)from openlinx\.crawl(?:\.(?P<old>\w+))? import "
    r"(?P<names>\([^)]*\)|[^\n]*)",
    re.MULTILINE,
)
_DOTTED = re.compile(r"openlinx\.crawl\.(?P<old>\w+)(?:\.(?P<name>\w+))?(?P<from> import)?")
_PATH = re.compile(r"openlinx/crawl/(?P<old>\w+)\.py\b")


def rewrite(source: str) -> str:
    source = _IMPORT_FROM.sub(_import_from, source)
    source = _DOTTED.sub(_dotted, source)
    return _PATH.sub(_path, source)


def _is_new(old: str, name: str) -> bool:
    # After the move, `engine`, `pages` and `robots` are packages whose submodules are names.
    return old in _PACKAGES and name in _SUBMODULES


def _new_module(old: str, name: str) -> str:
    return MOVED_NAMES.get((old, name), MOVED[old])


def _import_from(match: re.Match[str]) -> str:
    old, indent = match["old"], match["indent"]
    names = match["names"]
    comment = ""
    if not names.startswith("("):
        names, hash_mark, comment = names.partition("#")
        comment = f"  #{comment.rstrip()}" if hash_mark else ""
    items = [
        item.split("#")[0].strip()
        for line in names.strip("()").splitlines()
        for item in line.split("#")[0].split(",")
    ]
    items = [item for item in items if item]
    lines = (
        _from_crawl(items, indent)
        if old is None
        else _from_old(old, items, indent)
        if old in MOVED
        else None
    )
    if lines is None:
        return match[0]
    lines[0] += comment
    return "\n".join(lines)


def _from_old(old: str, items: list[str], indent: str) -> list[str] | None:
    by_module: dict[str, list[str]] = {}
    for item in items:
        name = item.split()[0]
        module = old if _is_new(old, name) else _new_module(old, name)
        by_module.setdefault(module, []).append(item)
    if list(by_module) == [old]:
        return None
    return [
        f"{indent}from openlinx.crawl.{module} import {', '.join(names)}"
        for module, names in by_module.items()
    ]


def _from_crawl(items: list[str], indent: str) -> list[str] | None:
    kept: list[str] = []
    lines: list[str] = []
    for item in items:
        name, _, local = item.partition(" as ")
        if name not in MOVED:
            kept.append(item)
            continue
        package, _, module = MOVED[name].rpartition(".")
        local = local.strip() or name
        alias = f" as {local}" if local != module else ""
        lines.append(f"{indent}from openlinx.crawl.{package} import {module}{alias}")
    if not lines:
        return None
    if kept:
        lines.insert(0, f"{indent}from openlinx.crawl import {', '.join(kept)}")
    return lines


def _dotted(match: re.Match[str]) -> str:
    old, name = match["old"], match["name"]
    # A `from … import` statement is _import_from's.
    if old not in MOVED or match["from"] or (name is not None and _is_new(old, name)):
        return match[0]
    if name is None:
        return match[0] if old in _PACKAGES else f"openlinx.crawl.{MOVED[old]}"
    return f"openlinx.crawl.{_new_module(old, name)}.{name}"


def _path(match: re.Match[str]) -> str:
    old = match["old"]
    if old not in MOVED:
        return match[0]
    return f"openlinx/crawl/{MOVED[old].replace('.', '/')}.py"


def _python_files(root: Path) -> Iterator[Path]:
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*.py")):
        if not _SKIPPED_FOLDERS.intersection(path.relative_to(root).parts):
            yield path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    parser.add_argument("paths", nargs="+", type=Path, help="files or folders to rewrite")
    itself = Path(__file__).resolve()
    for root in parser.parse_args(argv).paths:
        for path in _python_files(root):
            if path.resolve() == itself:
                continue
            data = path.read_bytes().decode("utf-8")
            crlf = "\r\n" in data
            source = data.replace("\r\n", "\n")
            rewritten = rewrite(source)
            if rewritten != source:
                path.write_bytes((rewritten.replace("\n", "\r\n") if crlf else rewritten).encode())
                print(path.as_posix())


if __name__ == "__main__":
    main()
