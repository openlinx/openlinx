"""Provide a scripted randomness boundary double."""

from collections.abc import Sequence

from openlinx.store.ids import Choice


def scripted_choice(characters: str) -> Choice:
    remaining = iter(characters)

    def choice(_: Sequence[str]) -> str:
        return next(remaining)

    return choice
