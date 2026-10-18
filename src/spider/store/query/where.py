"""The --where language compiled to SQLAlchemy Core (050-add-query-and-segments D1)."""

import operator
import sqlite3
from collections.abc import Callable
from typing import Any

from sqlalchemy import Boolean, Column, ColumnElement, Table, Text, and_, cast
from sqlalchemy.sql.functions import Function

from spider.query.where import And, Compare, Comparison, Contains, Expression, IsNull

# Registered on a connection and called by compiled expressions under the one name.
_CONTAINS = "spider_contains"
_COMPARE: dict[Compare, Callable[[Any, Any], ColumnElement[bool]]] = {
    "=": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


def register_where_functions(connection: sqlite3.Connection, connection_record: object) -> None:
    """Takes the arguments of sqlalchemy's connect event, so an engine registers it with
    event.listen (design D3)."""
    connection.create_function(_CONTAINS, 2, _contains, deterministic=True)


def _contains(value: str | None, needle: str) -> int:
    return int(value is not None and needle.casefold() in value.casefold())


def compile_where(expression: Expression, table: Table) -> ColumnElement[bool]:
    """The expression as a condition on `table`, every value bound as a parameter."""
    match expression:
        case And(operands):
            return and_(*(compile_where(operand, table) for operand in operands))
        case Comparison(name, compare, value):
            return _COMPARE[compare](_column(table, name), value)
        case IsNull(name, negated):
            column = _column(table, name)
            return column.is_not(None) if negated else column.is_(None)
        case Contains(name, needle):
            return Function(_CONTAINS, cast(_column(table, name), Text), needle, type_=Boolean)


def _column(table: Table, name: str) -> Column[Any]:
    return {column.name.lower(): column for column in table.columns}[name.lower()]
