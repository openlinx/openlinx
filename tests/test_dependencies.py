"""Every runtime dependency is reviewed (design D14 of 000-scaffold-project)."""

from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ALLOWLIST = Path(__file__).with_name("dependency_allowlist.txt")


def runtime_dependencies() -> set[str]:
    found: set[str] = set()
    to_walk = ["spider"]
    while to_walk:
        for line in metadata.requires(to_walk.pop()) or []:
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            name = canonicalize_name(requirement.name)
            if name not in found:
                found.add(name)
                to_walk.append(name)
    return found


def allowlisted() -> set[str]:
    lines = ALLOWLIST.read_text(encoding="utf-8").splitlines()
    names = (line.partition("#")[0].strip() for line in lines)
    return {canonicalize_name(name) for name in names if name}


def test_every_runtime_dependency_is_allowlisted() -> None:
    assert sorted(runtime_dependencies() - allowlisted()) == []
