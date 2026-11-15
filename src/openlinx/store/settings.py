"""Define the store settings table and its validation bounds."""

from pydantic import BaseModel, ConfigDict, Field

from openlinx.store.records import JournalSetting


class StoreSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journal_mode: JournalSetting = Field(
        "auto",
        description='Journal mode of new crawl files: "auto" (a rollback journal on UNC paths), '
        '"wal" or "delete".',
    )
