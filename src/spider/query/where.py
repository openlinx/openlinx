"""The --where language: its tokens, parser and syntax tree (050-add-query-and-segments D1)."""

import re
from dataclasses import dataclass
from typing import NoReturn

type Value = int | float | str


@dataclass(frozen=True, slots=True)
class Comparison:
    column: str
    operator: str
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
    r"(?P<number>-?\d+(?:\.\d+)?)"
    r"|(?P<name>[A-Za-z][A-Za-z0-9_]*)"
    r"|(?P<string>'(?:[^']|'')*'"
    r'|"(?:[^"]|"")*")'
    r"|(?P<compare><=|>=|!=|<>|=|<|>)"
    r")"
)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str


def parse(text: str) -> Expression:
    tokens = _Tokens(_tokenize(text))
    operands = [_predicate(tokens)]
    while tokens.keyword("and"):
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

    def take(self, kind: str, expected: str) -> str:
        if self._next == len(self._tokens) or self._tokens[self._next].kind != kind:
            _fail(f"expected {expected}")
        self._next += 1
        return self._tokens[self._next - 1].text

    def peek(self, kind: str) -> bool:
        return self._next < len(self._tokens) and self._tokens[self._next].kind == kind

    def keyword(self, word: str) -> bool:
        """Whether the next token is the keyword `word`, in any case, which it then consumes."""
        if self._next == len(self._tokens):
            return False
        token = self._tokens[self._next]
        if token.kind != "name" or token.text.lower() != word:
            return False
        self._next += 1
        return True

    def expect_end(self) -> None:
        if self._next < len(self._tokens):
            _fail(f"unexpected {self._tokens[self._next].text!r}")


def _predicate(tokens: _Tokens) -> Comparison | Contains | IsNull:
    column = tokens.take("name", "a column name")
    if tokens.keyword("is"):
        negated = tokens.keyword("not")
        if not tokens.keyword("null"):
            _fail("expected null")
        return IsNull(column, negated)
    if tokens.keyword("contains"):
        return Contains(column, _unquoted(tokens.take("string", "a string")))
    compare = tokens.take("compare", "a comparison")
    return Comparison(column, compare, _value(tokens))


def _value(tokens: _Tokens) -> Value:
    if tokens.peek("string"):
        return _unquoted(tokens.take("string", "a value"))
    number = tokens.take("number", "a value")
    return float(number) if "." in number else int(number)


def _unquoted(string: str) -> str:
    # A quote inside a string is written twice; backslashes mean nothing.
    quote = string[0]
    return string[1:-1].replace(quote * 2, quote)


def _fail(problem: str) -> NoReturn:
    raise ValueError(problem)
