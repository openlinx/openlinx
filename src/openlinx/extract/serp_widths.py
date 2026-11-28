"""Estimate SERP text widths from bundled advances without applying kerning."""

from bisect import bisect_right

from openlinx.extract.serp_advances import ADVANCES
from openlinx.extract.serp_fallbacks import FALLBACK_ADVANCES

_FALLBACK_STARTS = tuple(point for point, _ in FALLBACK_ADVANCES)
_FALLBACK_WIDTHS = tuple(advance for _, advance in FALLBACK_ADVANCES)
_UNITS_PER_EM = 2048
_DESCRIPTION_SIZE_PX = 14


def _advance(character: str) -> int:
    point = ord(character)
    advance = ADVANCES.get(point)
    if advance is not None:
        return advance
    return _FALLBACK_WIDTHS[bisect_right(_FALLBACK_STARTS, point) - 1]


def meta_description_width_px(text: str | None) -> int | None:
    """Measure the stored description, distinguishing an empty value from a missing one."""
    if text is None:
        return None
    units = sum(map(_advance, text))
    return (units * _DESCRIPTION_SIZE_PX + _UNITS_PER_EM // 2) // _UNITS_PER_EM
