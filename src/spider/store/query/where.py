"""The --where language compiled to SQLAlchemy Core (050-add-query-and-segments D1)."""

import operator
from collections.abc import Callable
from typing import Any

from sqlalchemy import Column, ColumnElement, Table, and_

from spider.query.where import And, Comparison, Expression

_COMPARE: dict[str, Callable[[Any, Any], ColumnElement[bool]]] = {
    "=": operator.eq,
    "!=": operator.ne,
    "<>": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


def compile_where(expression: Expression, table: Table) -> ColumnElement[bool]:
    """The expression as a condition on `table`, every value bound as a parameter."""
    match expression:
        case And(operands):
            return and_(*(compile_where(operand, table) for operand in operands))
        case Comparison(column, compare, value):
            return _COMPARE[compare](_column(table, column), value)


def _column(table: Table, name: str) -> Column[Any]:
    return {column.name.lower(): column for column in table.columns}[name.lower()]
