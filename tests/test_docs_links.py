"""Relative links and their heading anchors in the contributor docs resolve (000, 023 D15)."""

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FENCED_CODE = re.compile(r"^ {0,3}(```|~~~).*?^ {0,3}\1", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")
# The target ends at whitespace (a title may follow) or at the closing parenthesis;
# one level of parentheses inside it, as in `foo(1).md`, is allowed.
INLINE_LINK = re.compile(r"\]\(\s*(<[^>\n]*>|(?:[^()\s]|\([^()\s]*\))+)")
REFERENCE_LINK = re.compile(r"^ {0,3}\[(?!\^)[^\]]+\]:\s*(<[^>\n]*>|\S+)", re.MULTILINE)
NOT_A_FILE = ("http://", "https://", "mailto:")
HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
# GitHub's anchor of a heading: its text, lowercase, without punctuation, spaces as hyphens.
NOT_IN_AN_ANCHOR = re.compile(r"[^\w\- ]")
LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def links_in(markdown: str) -> list[str]:
    """Markdown link targets outside code; raw HTML links are not read."""
    text = INLINE_CODE.sub("", FENCED_CODE.sub("", markdown))
    targets = INLINE_LINK.findall(text) + REFERENCE_LINK.findall(text)
    return [target.removeprefix("<").removesuffix(">") for target in targets]


def anchors_in(markdown: str) -> set[str]:
    """The anchors GitHub gives the headings outside code, a repeated one numbered -1, -2..."""
    found: set[str] = set()
    for heading in HEADING.findall(FENCED_CODE.sub("", markdown)):
        text = LINK_TEXT.sub(r"\1", heading).replace("`", "")
        slug = NOT_IN_AN_ANCHOR.sub("", text.strip().lower()).replace(" ", "-")
        anchor, number = slug, 0
        while anchor in found:
            number += 1
            anchor = f"{slug}-{number}"
        found.add(anchor)
    return found


def resolves(doc: Path, target: str) -> bool:
    path_part, _, fragment = target.partition("#")
    path = unquote(path_part.split("?", maxsplit=1)[0])
    base = REPO_ROOT if path.startswith("/") else doc.parent
    file = doc if not path else base / path.lstrip("/")
    if not file.exists():
        return False
    if not fragment or file.suffix != ".md":
        return True
    return unquote(fragment).lower() in anchors_in(file.read_text(encoding="utf-8"))


def contributor_docs() -> list[Path]:
    return [
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "CONTEXT.md",
        REPO_ROOT / "README.md",
        REPO_ROOT / "CONTRIBUTING.md",
        REPO_ROOT / "ROADMAP.md",
        REPO_ROOT / "tests" / "fixture_site" / "README.md",
        *sorted((REPO_ROOT / "docs").rglob("*.md")),
    ]


def broken_links() -> list[str]:
    return [
        f"{doc.relative_to(REPO_ROOT).as_posix()}: {target}"
        for doc in contributor_docs()
        for target in links_in(doc.read_text(encoding="utf-8"))
        if not target.startswith(NOT_A_FILE) and not resolves(doc, target)
    ]


@pytest.mark.parametrize(
    ("markdown", "targets"),
    [
        ('[a](x.md "title")', ["x.md"]),
        ("[a](x.md 'title')", ["x.md"]),
        ("[a](x.md (title))", ["x.md"]),
        ("![image](pic.png)", ["pic.png"]),
        ("[a](<with space.md>)", ["with space.md"]),
        ("[a](foo(1).md)", ["foo(1).md"]),
        ("[a](x.md#part) [b](https://x.test) [c](#top)", ["x.md#part", "https://x.test", "#top"]),
        ("   [ref]: x.md", ["x.md"]),
        ("[^1]: a footnote", []),
        ("`[a](x.md)`", []),
        ("```\n[a](x.md)\n```", []),
        ("~~~\n[a](x.md)\n~~~", []),
        ('<a href="x.md">a</a>', []),
    ],
)
def test_link_targets_are_read_from_markdown(markdown: str, targets: list[str]) -> None:
    assert links_in(markdown) == targets


@pytest.mark.parametrize(
    ("target", "exists"),
    [
        ("CONTRIBUTING.md", True),
        ("docs/testing.md?plain=1#helpers", True),
        ("/docs/adr/", True),
        ("missing.md", False),
        ("CONTRIBUTING.md#common-changes", True),
        ("CONTRIBUTING.md#a-diagnostic-code", True),
        ("CONTRIBUTING.md#no-such-heading", False),
        ("#openlinx", True),
        ("#nowhere", False),
    ],
)
def test_a_target_resolves_relative_to_its_doc_or_the_repo_root(target: str, exists: bool) -> None:
    assert resolves(REPO_ROOT / "README.md", target) is exists


@pytest.mark.parametrize(
    ("markdown", "anchors"),
    [
        ("# A\n## A\n", {"a", "a-1"}),
        ("## `x` & y?\n", {"x--y"}),
        ("### [l](p) t\n", {"l-t"}),
        ("```\n# Not a heading\n```\n", set()),
    ],
)
def test_headings_give_the_anchors_github_gives_them(markdown: str, anchors: set[str]) -> None:
    assert anchors_in(markdown) == anchors


def test_relative_links_in_the_contributor_docs_point_to_existing_files() -> None:
    assert broken_links() == [], (
        "a relative link or its #anchor resolves to nothing: fix the path, or the anchor to the "
        "heading's text in lowercase, without punctuation, with hyphens for spaces"
    )
