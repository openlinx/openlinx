"""Choosing a crawl file's journal mode, with no system call (design D3 of 015-add-crawl-store)."""

from dataclasses import dataclass
from pathlib import PurePath

from spider.naming import SETTINGS_FILE_NAME
from spider.output.codes import STORE_WAL_UNAVAILABLE
from spider.output.diagnostics import Diagnostic
from spider.store.records import JournalMode, JournalSetting


@dataclass(frozen=True)
class JournalChoice:
    mode: JournalMode
    warning: Diagnostic | None = None


def choose_journal_mode(setting: JournalSetting, location: PurePath) -> JournalChoice:
    if setting != "auto":
        return JournalChoice(setting)
    if not _is_unc(location):
        return JournalChoice("wal")
    return JournalChoice(
        "delete",
        Diagnostic.of(
            STORE_WAL_UNAVAILABLE,
            f"{location} is a UNC path, where WAL is unsafe, so the crawl file uses a rollback "
            "journal.",
            hint=f'Set journal_mode = "wal" under [store] in {SETTINGS_FILE_NAME} only if the '
            "share supports WAL safely.",
            details={"path": str(location)},
        ),
    )


def _is_unc(location: PurePath) -> bool:
    path = str(location).replace("/", "\\")
    # The extended-length and device prefixes name a share only as \\?\UNC\; \\?\C:\ is local,
    # and a false UNC answer would cost a local user WAL (design D3).
    if path.startswith(("\\\\?\\", "\\\\.\\")):
        return path[4:].upper().startswith("UNC\\")
    return path.startswith("\\\\")


def confirm_journal_mode(choice: JournalChoice, granted: str, location: PurePath) -> JournalChoice:
    if choice.mode != "wal" or granted == "wal":
        return choice
    return JournalChoice(
        "delete",
        Diagnostic.of(
            STORE_WAL_UNAVAILABLE,
            f"SQLite refused WAL in {location} and gave {granted!r}, so the crawl file uses a "
            "rollback journal.",
            details={"path": str(location)},
        ),
    )
