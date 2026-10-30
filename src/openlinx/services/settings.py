"""The tool's settings tables, by reference, so nothing loads until the settings do
(023-fix-code-audit D9)."""

from openlinx.workspace.tables import SettingsTables


def default_tables() -> SettingsTables:
    """Every built-in settings table: a change that adds a table registers it here. A new
    registry on each call, since build_app registers its extra tables on it."""
    tables = SettingsTables()
    tables.register("crawl", "openlinx.crawl.settings:CrawlSettings")
    tables.register("store", "openlinx.store.settings:StoreSettings")
    tables.register("content_area", "openlinx.extract.settings:ContentAreaSettings")
    return tables
