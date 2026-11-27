"""Locate settings and scalar literals in TOML source for diagnostics."""

import re
import tomllib
from collections import deque
from collections.abc import Iterable, Iterator

type Key = tuple[str | int, ...]
type Declaration = tuple[Key, re.Match[str] | None]

# Keep strings opaque, including a multiline string's optional one or two closing quotes.
# Comments and strings can contain every delimiter used by an assignment or table header.
_TOKEN = re.compile(
    r'"""(?:[^"\\]++|\\[\s\S]|"(?!""))*+"{3,5}'
    r"|'''(?:[^']++|'(?!''))*+'{3,5}"
    r'|"(?:[^"\\]++|\\.)*+"'
    r"|'[^']*'|\#[^\n]*|[\[\]{},=.\n]|[^\s\[\]{},=.\"'\#]+"
)
_DECIMAL_INTEGER = re.compile(r"[+-]?[1-9](?:[0-9]++|_[0-9])*+")
_FLOAT_SUFFIX = re.compile(r"\.[0-9]|[eE][+-]?[0-9]")


def oversized_decimals(source: str, maximum: int) -> Iterator[re.Match[str]]:
    """Locate decimal values that exceed Python's conversion limit.

    Match just the numeric prefix so a syntax error after it cannot hide the value.
    A collection opened in a value position differs from a table header.
    """
    if not maximum:
        return
    containers: list[str] = []
    expects_value = False
    for token in _TOKEN.finditer(source):
        text = token[0]
        if text == "\n" or text.startswith("#"):
            continue
        if expects_value:
            integer = _DECIMAL_INTEGER.match(source, token.start())
            if (
                integer is not None
                and decimal_digits(integer[0]) > maximum
                and _FLOAT_SUFFIX.match(source, integer.end()) is None
            ):
                yield integer
            if text in ("[", "{"):
                containers.append(text)
        if containers and text in ("]", "}"):
            containers.pop()
        expects_value = text == "=" or (
            bool(containers) and containers[-1] == "[" and text in ("[", ",")
        )


def decimal_digits(literal: str) -> int:
    return len(literal.lstrip("+-")) - literal.count("_")


def replace_literals(source: str, replacements: Iterable[tuple[re.Match[str], str]]) -> str:
    """Replace literals in source order, preserving diagnostic columns."""
    parts: list[str] = []
    end = 0
    for literal, replacement in replacements:
        parts.extend((source[end : literal.start()], replacement.ljust(len(literal[0]))))
        end = literal.end()
    parts.append(source[end:])
    return "".join(parts)


def _key(tokens: deque[re.Match[str]], end: str) -> Iterator[str]:
    while (part := tokens.popleft()[0]) != end:
        if part != ".":
            # Let the settings decoder interpret escapes and literal dots in quoted names.
            yield tomllib.loads(f"k = {part}")["k"] if part.startswith(('"', "'")) else part


def _values(tokens: deque[re.Match[str]], path: Key) -> Iterator[Declaration]:
    first = tokens.popleft()
    if first[0] in ("{", "["):
        yield path, None
        index = 0
        while tokens[0][0] not in ("}", "]"):
            if tokens[0][0] in (",", "\n"):
                tokens.popleft()
            elif first[0] == "{":
                yield from _values(tokens, (*path, *_key(tokens, "=")))
            else:
                yield from _values(tokens, (*path, index))
                index += 1
        tokens.popleft()
    else:
        # Only return a token if it represents the entire scalar, including any date or fraction.
        yield path, first if not tokens or tokens[0][0] in (",", "\n", "}", "]") else None
        while tokens and tokens[0][0] not in (",", "\n", "}", "]"):
            tokens.popleft()


def declarations(source: str) -> Iterator[Declaration]:
    """Yield keys and their single-token scalar literals in source order."""
    tokens = deque(match for match in _TOKEN.finditer(source) if not match[0].startswith("#"))
    table: Key = ()
    array_indices: dict[Key, int] = {}
    while tokens:
        if tokens[0][0] == "\n":
            tokens.popleft()
        elif tokens[0][0] == "[":
            tokens.popleft()
            array = tokens[0][0] == "["
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
            yield table, None
        else:
            yield from _values(tokens, (*table, *_key(tokens, "=")))


def file_positions(located: Iterable[Declaration]) -> dict[Key, int]:
    """Index each setting and its implicit parents at their first appearance."""
    positions: dict[Key, int] = {}
    for index, (key, _) in enumerate(located):
        for size in range(1, len(key) + 1):
            positions.setdefault(key[:size], index)
    return positions
