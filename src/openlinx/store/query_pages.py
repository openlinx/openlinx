"""Read Page projections within a selected Crawl snapshot."""

from typing import Any

from sqlalchemy import Connection, bindparam, func, select

from openlinx.query.where import Expression
from openlinx.store.query_where import compile_where, register_where_functions
from openlinx.store.schema import pages

_TOTAL = select(func.count()).select_from(pages)
_PAGE = select(pages.c.address).order_by(pages.c.address).limit(bindparam("limit"))
_PAGE_AFTER = _PAGE.where(pages.c.address > bindparam("after"))


def pages_in(
    connection: Connection,
    *,
    after: str | None,
    limit: int,
    fields: tuple[str, ...],
    where: Expression | None,
) -> tuple[int, list[dict[str, Any]]]:
    """Read the filtered total and one address-ordered window from the caller's snapshot."""
    conditions = () if where is None else (compile_where(where, pages),)
    if conditions:
        register_where_functions(connection)
    total: int = connection.execute(_TOTAL.where(*conditions)).scalar_one()
    if limit == 0:
        return total, []

    # Address is the cursor key even when the output projection leaves it out.
    columns = tuple(dict.fromkeys((*fields, "address")))
    window = _PAGE if after is None else _PAGE_AFTER
    parameters = {"limit": limit} if after is None else {"limit": limit, "after": after}
    selected = window.where(*conditions).with_only_columns(*(pages.c[name] for name in columns))
    rows = connection.execute(selected, parameters)
    return total, [{str(key): value for key, value in row.items()} for row in rows.mappings()]
