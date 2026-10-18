"""The --where language: its tokens, parser and syntax tree (050-add-query-and-segments D1)."""

import re
from dataclasses import dataclass
from typing import Literal, NoReturn

from spider.output.codes import INVALID_WHERE
from spider.output.diagnostics import SpiderError

type Value = int | float | str | bool
type Compare = Literal["=", "!=", "<", "<=", ">", ">="]


@dataclass(frozen=True, slots=True)
class Comparison:
    column: str
    operator: Compare
    value: Value


@dataclass(frozen=True, slots=True)
class Contains:
    column: str
    needle: str


@dataclass(frozen=True, slots=True)
class IsNull:
    column: str
    negated: bool


@dataclass(frozen=True, slots=True)
class And:
    operands: tuple["Expression", ...]


type Expression = Comparison | Contains | IsNull | And

_TOKENS = re.compile(
    r"\s*(?:"
    r"(?P<number>-?[0-9]+(?:\.[0-9]+)?)"
    r"|(?P<name>[A-Za-z][A-Za-z0-9_]*)"
    r"|(?P<string>'(?:[^']|'')*'"
    r'|"(?:[^"]|"")*")'
    r"|(?P<compare><=|>=|!=|<>|=|<|>)"
    r")"
)

# <> is another spelling of !=, so the syntax tree has one.
_COMPARES: dict[str, Compare] = {
    "=": "=",
    "!=": "!=",
    "<>": "!=",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
}


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str


def parse(text: str) -> Expression:
    tokens = _Tokens(_tokenize(text))
    operands = [_predicate(tokens)]
    while tokens.accept("and"):
        operands.append(_predicate(tokens))
    tokens.expect_end()
    return operands[0] if len(operands) == 1 else And(tuple(operands))


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

    def peek(self, kind: str) -> bool:
        current = self._current()
        return current is not None and current.kind == kind

    def take(self, kind: str, expected: str) -> str:
        if not self.peek(kind):
            _fail(f"expected {expected}")
        self._next += 1
        return self._tokens[self._next - 1].text

    def accept(self, word: str) -> bool:
        current = self._current()
        if current is None or current.kind != "name" or current.text.lower() != word:
            return False
        self._next += 1
        return True

    def expect_end(self) -> None:
        current = self._current()
        if current is not None:
            _fail(f"unexpected {current.text!r}")

    def _current(self) -> _Token | None:
        return self._tokens[self._next] if self._next < len(self._tokens) else None


def _predicate(tokens: _Tokens) -> Comparison | Contains | IsNull:
    column = tokens.take("name", "a column name")
    if tokens.accept("is"):
        negated = tokens.accept("not")
        if not tokens.accept("null"):
            _fail("expected null")
        return IsNull(column, negated)
    if tokens.accept("contains"):
        return Contains(column, _unquoted(tokens.take("string", "a string")))
    compare = _COMPARES[tokens.take("compare", "a comparison")]
    return Comparison(column, compare, _value(tokens))


def _value(tokens: _Tokens) -> Value:
    for word, value in (("true", True), ("false", False)):
        if tokens.accept(word):
            return value
    if tokens.peek("string"):
        return _unquoted(tokens.take("string", "a value"))
    number = tokens.take("number", "a value")
    return float(number) if "." in number else int(number)


def _unquoted(string: str) -> str:
    # A quote inside a string is written twice; backslashes mean nothing.
    quote = string[0]
    return string[1:-1].replace(quote * 2, quote)


def _fail(problem: str) -> NoReturn:
    raise SpiderError(
        INVALID_WHERE,
        f"The --where expression is not valid: {problem}.",
        hint="Join predicates with and: column compare value, column contains 'text' "
        "or column is [not] null; quote text in single quotes.",
    )
