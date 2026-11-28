# /// script
# requires-python = ">=3.12"
# dependencies = ["fonttools==4.61.1"]
# ///
"""Generate the bundled SERP advance and fallback tables.

Pass LiberationSans-Regular.ttf from the Liberation Fonts 2.1.5 TTF release:
https://github.com/liberationfonts/liberation-fonts/releases/tag/2.1.5

Use EastAsianWidth.txt and extracted/DerivedGeneralCategory.txt from:
https://www.unicode.org/Public/16.0.0/ucd/

Usage: uv run scripts/serp_widths.py <regular.ttf> <EastAsianWidth.txt> <DerivedGeneralCategory.txt>
"""

import hashlib
import sys
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from typing import cast

_OUT = Path(__file__).resolve().parent.parent / "src" / "openlinx" / "extract"
_FONT_SHA256 = "76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8"
_UNICODE_VERSION = "16.0.0"
# The D9 blocks: Basic Latin, Latin-1 Supplement, Latin Extended-A and -B,
# Greek and Coptic, Cyrillic, and General Punctuation.
_FONT_BLOCKS = (range(0x0250), range(0x0370, 0x0500), range(0x2000, 0x2070))


def _font_advances(path: Path) -> dict[int, int]:
    if hashlib.sha256(path.read_bytes()).hexdigest() != _FONT_SHA256:
        sys.exit("Use the unmodified LiberationSans-Regular.ttf from the 2.1.5 TTF release.")
    # fontTools is installed in the generator's script environment only.
    ttlib = import_module("fontTools.ttLib")
    with ttlib.TTFont(path) as font:
        if font["head"].unitsPerEm != 2048:
            sys.exit("The source font must use 2048 units per em.")
        cmap = cast("dict[int, str]", font.getBestCmap())
        metrics = cast("dict[str, tuple[int, int]]", font["hmtx"].metrics)
        return {
            point: metrics[cmap[point]][0]
            for block in _FONT_BLOCKS
            for point in block
            if point in cmap
        }


def _points(path: Path, name: str, properties: set[str]) -> Iterator[int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != f"# {name}-{_UNICODE_VERSION}.txt":
        sys.exit(f"Use {name}.txt from Unicode {_UNICODE_VERSION}.")
    for line in lines:
        record = line.split("#", 1)[0].strip()
        if record:
            span, value = map(str.strip, record.split(";"))
            if value in properties:
                first, _, last = span.partition("..")
                yield from range(int(first, 16), int(last or first, 16) + 1)


def _fallbacks(wide: Path, categories: Path, default_advance: int) -> Iterator[tuple[int, int]]:
    advances = dict.fromkeys(_points(wide, "EastAsianWidth", {"W", "F"}), 2048)
    advances.update(
        dict.fromkeys(_points(categories, "DerivedGeneralCategory", {"Mn", "Me", "Cf"}), 0)
    )
    previous = None
    for point in range(0x110000):
        advance = advances.get(point, default_advance)
        if advance != previous:
            yield point, advance
            previous = advance


def main(font: Path, wide: Path, categories: Path) -> None:
    advances = _font_advances(font)
    advance_rows = "".join(
        f"    0x{point:04X}: {advance},\n" for point, advance in advances.items()
    )
    fallback_rows = "".join(
        f"    (0x{point:04X}, {advance}),\n"
        for point, advance in _fallbacks(wide, categories, advances[ord("0")])
    )
    (_OUT / "serp_advances.py").write_text(
        '"""Generated from Liberation Sans Regular 2.1.5 by scripts/serp_widths.py."""\n'
        "\n"
        "# SPDX-License-Identifier: OFL-1.1-RFN\n"
        "# See licenses/serp-advances-OFL.txt for copyright and license notices.\n"
        f"ADVANCES = {{\n{advance_rows}}}\n",
        encoding="utf-8",
        newline="\n",
    )
    (_OUT / "serp_fallbacks.py").write_text(
        '"""Generated from the Unicode 16.0.0 UCD by scripts/serp_widths.py."""\n'
        "\n"
        "# SPDX-License-Identifier: Unicode-3.0\n"
        "# See licenses/serp-fallbacks-Unicode.txt for the copyright and license notices.\n"
        "# Each entry gives an advance that applies until the next entry.\n"
        f"FALLBACK_ADVANCES: tuple[tuple[int, int], ...] = (\n{fallback_rows})\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main(*(Path(argument) for argument in sys.argv[1:]))
