"""A scripted random source, the randomness double of docs/testing.md (015-add-crawl-store)."""

from collections.abc import Sequence

from spider.store.ids import Choice


def scripted_choice(characters: str) -> Choice:
    remaining = iter(characters)

    def choice(_: Sequence[str]) -> str:
        return next(remaining)

    return choice
