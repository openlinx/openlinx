"""A scripted random source, the randomness double of docs/testing.md (015-add-crawl-store)."""

from collections.abc import Callable, Sequence


def scripted_choice(characters: str) -> Callable[[Sequence[str]], str]:
    """Stands in for `secrets.choice`: each call returns the next of `characters`."""
    remaining = iter(characters)

    def choice(_: Sequence[str]) -> str:
        return next(remaining)

    return choice
