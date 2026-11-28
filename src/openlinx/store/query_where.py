"""Compile parsed ``--where`` filters against a known Store table."""

import operator
import sqlite3
from collections.abc import Callable
from difflib import get_close_matches
from typing import Any
from typing import cast as type_cast

from sqlalchemy import (
    Boolean,
    Column,
    ColumnElement,
    Connection,
    Float,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    and_,
    cast,
)
from sqlalchemy.sql.functions import Function
from sqlalchemy.types import TypeDecorator

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import INVALID_WHERE, UNKNOWN_COLUMN
from openlinx.output.diagnostics import OpenLinxError
from openlinx.query.where import And, Contains, Expression, IsNull, Value
from openlinx.store.types import Flag

_CONTAINS = "openlinx_contains"
_SQLITE_INTEGER_MIN = -(2**63)
_SQLITE_INTEGER_MAX = 2**63 - 1
_COMPARE: dict[str, Callable[[Column[Any], Value], ColumnElement[bool]]] = {
    "=": operator.eq,
    "!=": operator.ne,
    "<>": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


def register_where_functions(connection: Connection) -> None:
    """Register Unicode case folding because SQLite's LIKE folds only ASCII."""
    driver = type_cast(sqlite3.Connection, connection.connection.driver_connection)
    driver.create_function(_CONTAINS, 2, _contains, deterministic=True)


def _contains(value: str | None, needle: str) -> int:
    return int(value is not None and needle.casefold() in value.casefold())


def compile_where(expression: Expression, table: Table) -> ColumnElement[bool]:
    """Build a condition whose literals are bound by SQLAlchemy as parameters."""
    if isinstance(expression, And):
        return and_(*(compile_where(operand, table) for operand in expression.operands))
    columns = {column.name.lower(): column for column in table.columns}
    name = expression.column.lower()
    column = columns.get(name)
    if column is None:
        matches = get_close_matches(name, list(columns), n=5)
        raise OpenLinxError(
            UNKNOWN_COLUMN,
            f"The queried view has no column {expression.column!r}.",
            hint=f"Use {COMMAND_NAME} schema to list available columns.",
            details={"suggestions": [columns[match].name for match in matches]},
        )
    if isinstance(expression, IsNull):
        return column.is_not(None) if expression.negated else column.is_(None)
    predicate: ColumnElement[bool]
    if isinstance(expression, Contains):
        predicate = Function(_CONTAINS, cast(column, Text), expression.needle, type_=Boolean)
    else:
        value = expression.value
        _require_comparison_type(column, value)
        if isinstance(value, int) and not _SQLITE_INTEGER_MIN <= value <= _SQLITE_INTEGER_MAX:
            raise OpenLinxError(
                INVALID_WHERE,
                f"The --where integer for {column.name!r} is outside the SQLite INTEGER range.",
                hint=f"Use an integer from {_SQLITE_INTEGER_MIN} to {_SQLITE_INTEGER_MAX}.",
            )
        predicate = _COMPARE[expression.operator](column, value)
    return and_(column.is_not(None), predicate)


def _require_comparison_type(column: Column[Any], value: Value) -> None:
    declared = column.type
    storage = declared.impl if isinstance(declared, TypeDecorator) else declared
    # A Flag uses INTEGER storage, but it is the only column type that takes a boolean literal.
    if isinstance(value, bool):
        mismatch = not isinstance(declared, Flag)
    elif isinstance(value, str):
        mismatch = isinstance(storage, (Integer, Float, Numeric))
    else:
        mismatch = isinstance(storage, String)
    if mismatch:
        raise OpenLinxError(
            INVALID_WHERE,
            f"The --where literal does not match the {storage} type of {column.name!r}.",
            hint=f"Check the column type with {COMMAND_NAME} schema and use a matching literal.",
        )
