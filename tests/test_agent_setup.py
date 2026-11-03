"""Development setup restores one physical skill library (CONTRIBUTING, seam 8)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout with spaces & %PATH% !"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    setup = ROOT / "scripts" / "setup_agents.py"
    if setup.exists():
        shutil.copyfile(setup, scripts / setup.name)
    for name in ("openspec-explore", "openspec-propose"):
        skill = root / ".agents" / "skills" / name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_bytes(b"canonical skill\r\n")
    return root


def setup_agents(root: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "setup_agents.py")],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_setup_from_another_folder_restores_shared_skills_and_is_idempotent(tmp_path: Path) -> None:
    root = checkout(tmp_path)
    first = setup_agents(root, tmp_path)
    assert first.returncode == 0, first.stderr
    for name in ("openspec-explore", "openspec-propose"):
        source = root / ".agents" / "skills" / name / "SKILL.md"
        alias = root / ".claude" / "skills" / name / "SKILL.md"
        assert source.samefile(alias)
        assert source.read_bytes() == b"canonical skill\r\n"
        alias.write_bytes(b"edited through alias\n")
        assert source.read_bytes() == b"edited through alias\n"
    second = setup_agents(root, tmp_path)
    assert second.returncode == 0, second.stderr
    assert (root / ".agents/skills/openspec-explore/SKILL.md").read_bytes() == (
        b"edited through alias\n"
    )


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_a_conflict_is_reported_before_any_alias_is_created(tmp_path: Path, kind: str) -> None:
    root = checkout(tmp_path)
    conflict = root / ".claude/skills/openspec-propose"
    conflict.parent.mkdir(parents=True)
    if kind == "directory":
        conflict.mkdir()
        contents = conflict / "SKILL.md"
    else:
        contents = conflict
    contents.write_bytes(b"keep my skill\r\n")

    result = setup_agents(root, tmp_path)

    assert result.returncode != 0
    assert "Conflicting path:" in result.stderr
    assert contents.read_bytes() == b"keep my skill\r\n"
    assert not (root / ".claude/skills/openspec-explore").exists()
    assert (root / ".agents/skills/openspec-propose/SKILL.md").read_bytes() == (
        b"canonical skill\r\n"
    )


def directory_link(target: Path, alias: Path) -> None:
    if os.name == "nt":
        command = shutil.which("cmd.exe")
        assert command is not None
        subprocess.run(
            f'"{command}" /d /v:off /c mklink /J "%TEST_ALIAS%" "%TEST_TARGET%"',
            env={**os.environ, "TEST_ALIAS": str(alias), "TEST_TARGET": str(target)},
            capture_output=True,
            check=True,
        )
    else:
        alias.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("parent", [".claude", ".claude/skills"])
def test_setup_refuses_a_redirected_alias_parent(tmp_path: Path, parent: str) -> None:
    root = checkout(tmp_path)
    outside = tmp_path / "other checkout"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_bytes(b"other checkout\n")
    redirect = root / parent
    redirect.parent.mkdir(parents=True, exist_ok=True)
    directory_link(outside, redirect)

    result = setup_agents(root, tmp_path)

    assert result.returncode != 0
    assert "Conflicting path:" in result.stderr
    assert sorted(path.name for path in outside.iterdir()) == ["keep.txt"]
    assert marker.read_bytes() == b"other checkout\n"


def test_setup_requires_a_canonical_skill_library(tmp_path: Path) -> None:
    root = checkout(tmp_path)
    for skill in (root / ".agents/skills").glob("*/SKILL.md"):
        skill.unlink()

    result = setup_agents(root, tmp_path)

    assert result.returncode != 0
    assert "No canonical skills:" in result.stderr
    assert not (root / ".claude").exists()


@pytest.mark.parametrize("dangling", [False, True])
def test_setup_preserves_an_alias_to_another_library(tmp_path: Path, dangling: bool) -> None:
    root = checkout(tmp_path)
    outside = tmp_path / "other skill"
    outside.mkdir()
    redirect = root / ".claude/skills/openspec-propose"
    redirect.parent.mkdir(parents=True)
    directory_link(outside, redirect)
    if dangling:
        outside.rmdir()
    else:
        (outside / "SKILL.md").write_bytes(b"other skill\n")

    result = setup_agents(root, tmp_path)

    assert result.returncode != 0
    assert "Conflicting path:" in result.stderr
    assert redirect.is_symlink() or redirect.is_junction()
    assert redirect.resolve() == outside
    assert not (root / ".claude/skills/openspec-explore").exists()
    if not dangling:
        assert (outside / "SKILL.md").read_bytes() == b"other skill\n"
