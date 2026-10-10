"""Choosing the journal mode (015-add-crawl-store, crawl-store)."""

from pathlib import PurePosixPath, PureWindowsPath

from spider.store.journal import JournalChoice, choose_journal_mode, confirm_journal_mode


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


LOCAL = PureWindowsPath(r"C:\site\.spider")


def test_wal_refused_by_sqlite() -> None:
    choice = confirm_journal_mode(JournalChoice("wal"), "memory", LOCAL)

    assert (choice.mode, choice.warning and choice.warning.code) == (
        "delete",
        "store_wal_unavailable",
    )


def test_wal_granted_by_sqlite() -> None:
    choice = confirm_journal_mode(JournalChoice("wal"), "wal", LOCAL)

    assert (choice.mode, choice.warning) == ("wal", None)
