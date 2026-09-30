"""Relative links in the contributor docs resolve (task 8.1 of 000-scaffold-project)."""

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
NOT_A_FILE = ("http://", "https://", "mailto:", "#")


def links_in(markdown: str) -> list[str]:
    """Markdown link targets outside code; raw HTML links are not read."""
    text = INLINE_CODE.sub("", FENCED_CODE.sub("", markdown))
    targets = INLINE_LINK.findall(text) + REFERENCE_LINK.findall(text)
    return [target.removeprefix("<").removesuffix(">") for target in targets]


def resolves(doc: Path, target: str) -> bool:
    path = unquote(re.split(r"[?#]", target, maxsplit=1)[0])
    base = REPO_ROOT if path.startswith("/") else doc.parent
    return (base / path.lstrip("/")).exists()


def contributor_docs() -> list[Path]:
    return [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CONTRIBUTING.md",
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
    ],
)
def test_a_target_resolves_relative_to_its_doc_or_the_repo_root(target: str, exists: bool) -> None:
    assert resolves(REPO_ROOT / "README.md", target) is exists


def test_relative_links_in_the_contributor_docs_point_to_existing_files() -> None:
    assert broken_links() == []
