"""The --where language: its tokens, parser and syntax tree (050-add-query-and-segments D1)."""

import re
from dataclasses import dataclass
from typing import NoReturn

type Value = int | float


@dataclass(frozen=True, slots=True)
class Comparison:
    column: str
    operator: str
    value: Value


type Expression = Comparison

_TOKENS = re.compile(
    r"\s*(?:(?P<number>-?\d+(?:\.\d+)?)|(?P<name>[A-Za-z][A-Za-z0-9_]*)|(?P<compare><=|>=|!=|<>|=|<|>))"
)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str


def parse(text: str) -> Expression:
    tokens = _Tokens(_tokenize(text))
    expression = _comparison(tokens)
    tokens.expect_end()
    return expression


def _tokenize(text: str) -> list[_Token]:
    found = []
    position = 0
    while text[position:].strip():
        match = _TOKENS.match(text, position)
        if match is None or match.lastgroup is None:
            _fail(f"unexpected {text[position:].lstrip()[0]!r}")
        found.append(_Token(match.lastgroup, match.group(match.lastgroup)))
        position = match.end()
    return found


class _Tokens:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._next = 0

    def take(self, kind: str, expected: str) -> str:
        if self._next == len(self._tokens) or self._tokens[self._next].kind != kind:
            _fail(f"expected {expected}")
        self._next += 1
        return self._tokens[self._next - 1].text

    def expect_end(self) -> None:
        if self._next < len(self._tokens):
            _fail(f"unexpected {self._tokens[self._next].text!r}")


def _comparison(tokens: _Tokens) -> Comparison:
    column = tokens.take("name", "a column name")
    compare = tokens.take("compare", "a comparison")
    number = tokens.take("number", "a value")
    return Comparison(column, compare, float(number) if "." in number else int(number))


def _fail(problem: str) -> NoReturn:
    raise ValueError(problem)
