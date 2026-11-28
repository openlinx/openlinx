"""Parse a ``--where`` filter into a syntax tree independent of the Store."""

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import NoReturn

from openlinx.output.codes import INVALID_WHERE
from openlinx.output.diagnostics import OpenLinxError

type Value = int | float | str | bool


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


type Predicate = Comparison | Contains | IsNull


@dataclass(frozen=True, slots=True)
class And:
    operands: tuple[Predicate, ...]


type Expression = Predicate | And

_TOKENS = re.compile(
    r"(?P<space>\s+)"
    r"|(?P<number>-?[0-9]+(?:\.[0-9]+)?)"
    r"|(?P<name>[A-Za-z][A-Za-z0-9_]*)"
    r"|(?P<string>'(?:[^']|'')*'"
    r'|"(?:[^"]|"")*")'
    r"|(?P<compare><=|>=|!=|<>|=|<|>)"
    r"|(?P<unexpected>.)"
)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str
    position: int


def parse(text: str) -> Expression:
    """Consume the whole expression so trailing text cannot reach the compiler."""
    tokens = _tokenize(text)
    operands = [_predicate(tokens)]
    for token in tokens:
        if token.kind == "end":
            break
        if token.kind != "name" or token.text.lower() != "and":
            _fail(token, f"unexpected {token.text!r}")
        operands.append(_predicate(tokens))
    return operands[0] if len(operands) == 1 else And(tuple(operands))


def _tokenize(text: str) -> Iterator[_Token]:
    for match in _TOKENS.finditer(text):
        kind = match.lastgroup
        if kind is None:
            raise RuntimeError("a --where token has no kind")
        if kind != "space":
            yield _Token(kind, match.group(), match.start() + 1)
    yield _Token("end", "", len(text) + 1)


def _predicate(tokens: Iterator[_Token]) -> Predicate:
    column = _take(tokens, "name", "a column name").text
    operator = next(tokens)
    if operator.kind == "name":
        word = operator.text.lower()
        if word == "contains":
            needle = _unquote(_take(tokens, "string", "a string").text)
            return Contains(column, needle)
        if word == "is":
            null = _take(tokens, "name", "null")
            negated = null.text.lower() == "not"
            if negated:
                null = _take(tokens, "name", "null")
            if null.text.lower() != "null":
                _fail(null, "expected null")
            return IsNull(column, negated)
    if operator.kind != "compare":
        _fail(operator, "expected a comparison operator")
    return Comparison(column, operator.text, _value(next(tokens)))


def _value(token: _Token) -> Value:
    if token.kind == "string":
        return _unquote(token.text)
    if token.kind == "number":
        try:
            number = float(token.text) if "." in token.text else int(token.text)
        except ValueError:
            _fail(token, "number is too large")
        if isinstance(number, float) and not math.isfinite(number):
            _fail(token, "number is too large")
        return number
    if token.kind == "name" and token.text.lower() in {"true", "false"}:
        return token.text.lower() == "true"
    _fail(token, "expected a value")


def _unquote(text: str) -> str:
    quote = text[0]
    return text[1:-1].replace(quote * 2, quote)


def _take(tokens: Iterator[_Token], kind: str, expected: str) -> _Token:
    token = next(tokens)
    if token.kind != kind:
        _fail(token, f"expected {expected}")
    return token


def _fail(token: _Token, problem: str) -> NoReturn:
    raise OpenLinxError(
        INVALID_WHERE,
        f"The --where expression is invalid at position {token.position}: {problem}.",
        hint="Join comparisons, contains or is [not] null with and. Quote text in single quotes.",
    )
