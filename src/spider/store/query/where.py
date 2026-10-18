"""The --where language compiled to SQLAlchemy Core (050-add-query-and-segments D1)."""

import operator
import sqlite3
from collections.abc import Callable
from typing import Any

from sqlalchemy import Boolean, Column, ColumnElement, Table, Text, and_, cast
from sqlalchemy.sql.functions import Function

from spider.query.where import And, Comparison, Contains, Expression, IsNull

# Registered on a connection and called by compiled expressions under the one name.
_CONTAINS = "spider_contains"
_COMPARE: dict[str, Callable[[Any, Any], ColumnElement[bool]]] = {
    "=": operator.eq,
    "!=": operator.ne,
    "<>": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


def register_where_functions(connection: sqlite3.Connection, _: Any = None) -> None:
    """Give a connection the functions that compiled expressions call (design D3); its
    signature is that of sqlalchemy's connect event."""
    connection.create_function(_CONTAINS, 2, _contains, deterministic=True)


def _contains(value: str | None, needle: str) -> int:
    return int(value is not None and needle.casefold() in value.casefold())


def compile_where(expression: Expression, table: Table) -> ColumnElement[bool]:
    """The expression as a condition on `table`, every value bound as a parameter."""
    match expression:
        case And(operands):
            return and_(*(compile_where(operand, table) for operand in operands))
        case Comparison(column, compare, value):
            return _COMPARE[compare](_column(table, column), value)
        case IsNull(column, negated):
            found = _column(table, column)
            return found.is_not(None) if negated else found.is_(None)
        case Contains(column, needle):
            return Function(_CONTAINS, cast(_column(table, column), Text), needle, type_=Boolean)


def _column(table: Table, name: str) -> Column[Any]:
    return {column.name.lower(): column for column in table.columns}[name.lower()]
