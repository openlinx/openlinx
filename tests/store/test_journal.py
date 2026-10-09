"""Choosing the journal mode (015-add-crawl-store, crawl-store)."""

from pathlib import PurePosixPath, PureWindowsPath

from spider.store.journal import choose_journal_mode


def test_unc_path() -> None:
    choice = choose_journal_mode("auto", PureWindowsPath(r"\\fileserver\share\site\.spider"))

    assert (choice.mode, choice.warning and choice.warning.code) == (
        "delete",
        "store_wal_unavailable",
    )


def test_local_path() -> None:
    choice = choose_journal_mode("auto", PureWindowsPath(r"C:\site\.spider"))

    assert (choice.mode, choice.warning) == ("wal", None)


def test_forced_wal_on_a_unc_path() -> None:
    choice = choose_journal_mode("wal", PureWindowsPath(r"\\fileserver\share\site\.spider"))

    assert (choice.mode, choice.warning) == ("wal", None)


def test_forced_rollback_journal_on_a_local_path() -> None:
    choice = choose_journal_mode("delete", PurePosixPath("/home/ann/site/.spider"))

    assert (choice.mode, choice.warning) == ("delete", None)
