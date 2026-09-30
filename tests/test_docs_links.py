"""Guard: relative links in the contributor docs resolve (task 8.1 of 000-scaffold-project)."""

import re
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent
FENCED_CODE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
INLINE_LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
REFERENCE_LINK = re.compile(r"^\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
NOT_A_FILE = ("http://", "https://", "mailto:", "#")


def contributor_docs() -> list[Path]:
    return [
        REPO_ROOT / "README.md",
        REPO_ROOT / "CONTRIBUTING.md",
        *sorted((REPO_ROOT / "docs").rglob("*.md")),
    ]


def broken_links() -> list[str]:
    broken: list[str] = []
    for doc in contributor_docs():
        text = FENCED_CODE.sub("", doc.read_text(encoding="utf-8"))
        for target in INLINE_LINK.findall(text) + REFERENCE_LINK.findall(text):
            if target.startswith(NOT_A_FILE):
                continue
            path = unquote(target.split("#", 1)[0])
            if not (doc.parent / path).exists():
                broken.append(f"{doc.relative_to(REPO_ROOT).as_posix()}: {target}")
    return broken


def test_relative_links_in_the_contributor_docs_point_to_existing_files() -> None:
    assert broken_links() == []
