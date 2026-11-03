"""Restore local aliases to the canonical development skills from CONTRIBUTING."""

import os
import shutil
import subprocess
from pathlib import Path


def _link(source: Path, alias: Path) -> None:
    if os.name == "nt":
        command = shutil.which("cmd.exe")
        if command is None:
            raise RuntimeError("cmd.exe is required to create Windows junctions")
        # Environment expansion keeps shell metacharacters in checkout paths quoted.
        subprocess.run(
            f'"{command}" /d /v:off /c mklink /J "%SKILL_ALIAS%" "%SKILL_SOURCE%"',
            env={**os.environ, "SKILL_ALIAS": str(alias), "SKILL_SOURCE": str(source)},
            capture_output=True,
            check=True,
        )
    else:
        alias.symlink_to(os.path.relpath(source, alias.parent), target_is_directory=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    library = root / ".agents" / "skills"
    aliases = root / ".claude" / "skills"
    for parent in (aliases.parent, aliases):
        if parent.is_symlink() or parent.is_junction() or (parent.exists() and not parent.is_dir()):
            raise SystemExit(f"Conflicting path: {parent}. Move it aside and rerun setup.")
    skills = sorted(library.glob("*/SKILL.md"))
    if not skills:
        raise SystemExit(f"No canonical skills: {library}")
    pending: list[tuple[Path, Path]] = []
    for skill in skills:
        source = skill.parent
        alias = aliases / source.name
        if alias.exists() and alias.samefile(source):
            continue
        if alias.exists() or alias.is_symlink() or alias.is_junction():
            raise SystemExit(f"Conflicting path: {alias}. Move it aside and rerun setup.")
        pending.append((source, alias))
    aliases.mkdir(parents=True, exist_ok=True)
    for source, alias in pending:
        _link(source, alias)


if __name__ == "__main__":
    main()
