"""The codemod of the crawl package layout (020-add-crawl-core design D19)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CRAWL = ROOT / "src" / "openlinx" / "crawl"


def _codemod() -> ModuleType:
    path = ROOT / "scripts" / "crawl_layout_codemod.py"
    spec = importlib.util.spec_from_file_location("crawl_layout_codemod", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


codemod = _codemod()

# Spelt with {c} and {p}, so that the codemod run over this file leaves the cases as they are.
REWRITES = [
    (
        "from {c}.links import DiscoveredLink, extract_links\n",
        "from {c}.references import DiscoveredLink\nfrom {c}.pages.links import extract_links\n",
    ),
    ("from {c}.engine import run_crawl\n", "from {c}.engine.dispatch import run_crawl\n"),
    ("from {c}.engine import hooks\n", "from {c}.engine import hooks\n"),
    (
        "from {c}.hooks import (\n    Handler,\n    UrlResult as Result,\n)\n",
        "from {c}.engine.hooks import Handler, UrlResult as Result\n",
    ),
    (
        "if TYPE_CHECKING:\n    from {c}.links import DiscoveredLink\n",
        "if TYPE_CHECKING:\n    from {c}.references import DiscoveredLink\n",
    ),
    (
        "from {c}.stop import StopSignal  # noqa: F401\n",
        "from {c}.engine.stop import StopSignal  # noqa: F401\n",
    ),
    (
        "from {c} import pages, urls\n",
        "from {c} import urls\nfrom {c}.pages import preparation as pages\n",
    ),
    ("from {c} import links as found\n", "from {c}.pages import links as found\n"),
    ("import {c}.robots_loader as loader\n", "import {c}.robots.loader as loader\n"),
    ("x = {c}.links.resolve_reference\n", "x = {c}.references.resolve_reference\n"),
    ('name = "{c}.hooks:Hooks"\n', 'name = "{c}.engine.hooks:Hooks"\n'),
    ('forbidden = ("{c}.engine", "{c}.pages")\n', 'forbidden = ("{c}.engine", "{c}.pages")\n'),
    ('REQUESTER = "{p}/requester.py"\n', 'REQUESTER = "{p}/fetch/requester.py"\n'),
    ("from {c}.urls import NormalizedUrl\n", "from {c}.urls import NormalizedUrl\n"),
]


def _spelt(text: str) -> str:
    return text.format(c="openlinx.crawl", p="openlinx/crawl")


@pytest.mark.parametrize(("old", "new"), REWRITES)
def test_a_name_of_an_old_module_is_rewritten_to_its_new_place(old: str, new: str) -> None:
    assert codemod.rewrite(_spelt(old)) == _spelt(new)


@pytest.mark.parametrize("new", [new for _, new in REWRITES])
def test_a_rewritten_source_is_left_as_it_is(new: str) -> None:
    assert codemod.rewrite(_spelt(new)) == _spelt(new)


def test_a_run_prints_each_file_it_changed_and_a_second_run_changes_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = tmp_path / "a.py"
    changed.write_bytes(_spelt("from {c}.hooks import Hooks\r\n").encode())
    (tmp_path / "b.py").write_bytes(_spelt("from {c}.urls import NormalizedUrl\n").encode())
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "c.py").write_bytes(_spelt("from {c}.hooks import Hooks\n").encode())

    codemod.main([str(tmp_path)])
    first = capsys.readouterr().out
    codemod.main([str(tmp_path)])

    assert (first, capsys.readouterr().out, changed.read_bytes()) == (
        f"{changed.as_posix()}\n",
        "",
        _spelt("from {c}.engine.hooks import Hooks\r\n").encode(),
    )


def test_the_map_leads_from_every_old_module_to_a_module_that_exists() -> None:
    new = {*codemod.MOVED.values(), *codemod.MOVED_NAMES.values()}
    left = sorted(path.stem for path in CRAWL.glob("*.py") if path.stem in codemod.MOVED)
    missing = sorted(m for m in new if not (CRAWL / f"{m.replace('.', '/')}.py").is_file())

    assert (left, missing) == ([], [])
