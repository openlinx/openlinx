"""Locate settings in declaration order for diagnostics after TOML validation."""

import re
import tomllib
from collections import deque
from collections.abc import Iterator

type Key = tuple[str | int, ...]

# Keep strings opaque, including a multiline string's optional one or two closing quotes.
# Comments and strings can contain every delimiter used by an assignment or table header.
_TOKEN = re.compile(
    r'"""(?:[^"\\]++|\\[\s\S]|"(?!""))*+"{3,5}'
    r"|'''(?:[^']++|'(?!''))*+'{3,5}"
    r'|"(?:[^"\\]++|\\.)*+"'
    r"|'[^']*'|\#[^\n]*|[\[\]{},=.\n]|[^\s\[\]{},=.\"'\#]+"
)


def _key(tokens: deque[str], end: str) -> Iterator[str]:
    while (part := tokens.popleft()) != end:
        if part != ".":
            # Let the settings decoder interpret escapes and literal dots in quoted names.
            yield tomllib.loads(f"k = {part}")["k"] if part.startswith(('"', "'")) else part


def _value_keys(tokens: deque[str], path: Key) -> Iterator[Key]:
    yield path
    first = tokens.popleft()
    if first in ("{", "["):
        index = 0
        while tokens[0] not in ("}", "]"):
            if tokens[0] in (",", "\n"):
                tokens.popleft()
            elif first == "{":
                yield from _value_keys(tokens, (*path, *_key(tokens, "=")))
            else:
                yield from _value_keys(tokens, (*path, index))
                index += 1
        tokens.popleft()
    else:
        # A scalar may span tokens (a fraction or a date with a time). Its value is irrelevant.
        while tokens and tokens[0] not in (",", "\n", "}", "]"):
            tokens.popleft()


def _declarations(source: str) -> Iterator[Key]:
    tokens = deque(m[0] for m in _TOKEN.finditer(source) if not m[0].startswith("#"))
    table: Key = ()
    array_indices: dict[Key, int] = {}
    while tokens:
        if tokens[0] == "\n":
            tokens.popleft()
        elif tokens[0] == "[":
            tokens.popleft()
            array = tokens[0] == "["
            if array:
                tokens.popleft()
            names = tuple(_key(tokens, "]"))
            table = ()
            for index, name in enumerate(names):
                table += (name,)
                if array and index == len(names) - 1:
                    array_indices[table] = array_indices.get(table, -1) + 1
                if table in array_indices:
                    table += (array_indices[table],)
            if array:
                tokens.popleft()
            yield table
        else:
            yield from _value_keys(tokens, (*table, *_key(tokens, "=")))


def file_positions(source: str) -> dict[Key, int]:
    """Index each setting and its implicit parents at their first appearance in valid TOML."""
    positions: dict[Key, int] = {}
    for index, key in enumerate(_declarations(source)):
        for size in range(1, len(key) + 1):
            positions.setdefault(key[:size], index)
    return positions
