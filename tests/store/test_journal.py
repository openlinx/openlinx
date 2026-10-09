"""Choosing the journal mode (015-add-crawl-store, crawl-store)."""

from pathlib import PureWindowsPath

from spider.store.journal import choose_journal_mode


def test_unc_path() -> None:
    choice = choose_journal_mode("auto", PureWindowsPath(r"\\fileserver\share\site\.spider"))

    assert (choice.mode, choice.warning and choice.warning.code) == (
        "delete",
        "store_wal_unavailable",
    )
