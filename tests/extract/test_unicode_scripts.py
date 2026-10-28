"""The generated character tables against this interpreter's Unicode (030-add-page-data D8)."""

import sys
import unicodedata

from spider.extract.unicode_scripts import (
    HAN_AND_KANA,
    KEPT_ENCODED,
    MARKS,
    UNICODE_VERSION,
    WORD_CHARACTERS,
)

# Characters whose general category Unicode changed after it assigned them, by code point,
# with the Unicode version that changed it: an older interpreter disagrees with the tables
# there. None changed class between Unicode 15.0 (Python 3.12) and 16.0.
_RECLASSIFIED: dict[int, str] = {}


def _points(ranges: tuple[tuple[int, int], ...]) -> frozenset[int]:
    return frozenset(point for first, last in ranges for point in range(first, last + 1))


def test_the_tables_agree_with_this_pythons_unicode() -> None:
    # A character this interpreter does not assign yet is the only other difference allowed, so
    # a Python of a newer Unicode than the tables fails here until they are regenerated.
    words, marks, kana, kept = map(_points, (WORD_CHARACTERS, MARKS, HAN_AND_KANA, KEPT_ENCODED))
    disagreeing = []
    for point in range(sys.maxunicode + 1):
        category = unicodedata.category(chr(point))
        if category == "Cn" or point in _RECLASSIFIED:
            continue
        if (
            (point in words) != (category[0] in "LMN" and point not in kana)
            or (point in marks) != (category[0] == "M")
            or (point in kept) != (category in {"Cc", "Cf", "Zs", "Zl", "Zp"})
        ):
            disagreeing.append(f"U+{point:04X} {category}")

    versions = f"tables of Unicode {UNICODE_VERSION}, Python's {unicodedata.unidata_version}"
    assert disagreeing == [], versions
