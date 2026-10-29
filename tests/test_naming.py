"""Guard: one source for the product name (design D11 of 010-add-workspace-and-cli-contract)."""

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
NAMING = SRC / "openlinx" / "naming.py"
NAME_LITERALS = ("openlinx.toml", ".openlinx")


def test_name_derived_literals_appear_only_in_openlinx_naming() -> None:
    hits = [
        f"{path.relative_to(SRC).as_posix()}:{number}"
        for path in sorted(SRC.rglob("*.py"))
        if path != NAMING
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if any(literal in line for literal in NAME_LITERALS)
    ]

    assert hits == []
