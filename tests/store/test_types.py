"""Verify the Store's column types when SQLite statements share a compiled cache."""

from pathlib import Path

import pytest
from sqlalchemy import bindparam, select
from sqlalchemy.exc import StatementError

from openlinx.store.connections import opening
from openlinx.store.schema import crawl


@pytest.mark.parametrize("first", ["scope", "config"], ids=["scope-first", "config-first"])
def test_crawl_config_and_scope_keep_their_own_json_encoders(tmp_path: Path, first: str) -> None:
    statements = {
        column: select(bindparam("document", type_=crawl.c[column].type))
        for column in ("scope", "config")
    }
    wide = {"document": {"threshold": 18446744073709551617}}
    path = tmp_path / "crawl.sqlite"
    path.touch()

    with opening(path, role="create") as engine, engine.connect() as connection:
        assert connection.scalar(statements[first], {"document": {"threshold": 70}}) == (
            '{"threshold":70}'
        )
        assert connection.scalar(statements["config"], wide) == '{"threshold":18446744073709551617}'
        with pytest.raises(StatementError) as rejected:
            connection.scalar(statements["scope"], wide)
        assert isinstance(rejected.value.orig, TypeError)
