"""The `[store]` settings table (015-add-crawl-store, crawl-store)."""

from pathlib import Path

from tests.support.cli import run_cli


def test_the_store_setting_in_the_template(shop: Path) -> None:
    run_cli("init")

    lines = (shop / "spider.toml").read_text(encoding="utf-8").splitlines()

    assert lines.index("[store]") < lines.index('# journal_mode = "auto"')


def test_an_invalid_store_setting(shop: Path) -> None:
    (shop / "spider.toml").write_bytes(b'[store]\njournal_mode = "fast"\n')

    result = run_cli("init")
    error = result.stderr_json_lines()[-1]

    assert (result.exit_code, error["code"], error["details"]["errors"][0]["key"]) == (
        3,
        "settings_invalid",
        "store.journal_mode",
    )
