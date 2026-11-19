"""Verify Rule threshold bounds across Workspace-reading Commands."""

import re

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize(
    "notation",
    [
        pytest.param("_d", id="decimal"),
        pytest.param("#_x", id="hexadecimal"),
        pytest.param("#_o", id="octal"),
        pytest.param("#_b", id="binary"),
    ],
)
def test_largest_supported_threshold(temp_workspace: TempWorkspace, notation: str) -> None:
    largest = 10**4300 - 1
    (temp_workspace.root / "openlinx.toml").write_text(
        f"[rules.title-too-long]\nmax_chars = {largest:{notation}}\n", encoding="utf-8"
    )

    result = run_cli("rules", "show", "title-too-long")

    assert result.exit_code == 0, result.stderr
    assert result.json()["thresholds"]["max_chars"]["value"] == largest


@pytest.mark.parametrize(
    "setting",
    [
        pytest.param('[rules."title-too-long"]\nmax_chars = +1' + "_0" * 4300, id="decimal"),
        pytest.param(f"rules.title-too-long.max_chars = {10**4300:#_x}", id="hexadecimal"),
        pytest.param(f"[rules.title-too-long]\nmax_chars = {10**4300:#_o}", id="octal"),
        pytest.param(f"rules = {{title-too-long.max_chars = {10**4300:#_b}}}", id="binary"),
    ],
)
def test_first_threshold_above_the_limit(
    temp_workspace: TempWorkspace, fixture_site: StartSite, setting: str
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>A Page.</p>")}))
    settings_file = temp_workspace.root / "openlinx.toml"
    settings_file.write_text(f"{setting}\n", encoding="utf-8")

    initialized = run_cli("init")
    shown = run_cli("rules", "show", "title-too-long")
    crawl = run_cli("crawl", server.url("/"))

    assert (initialized.exit_code, shown.exit_code, crawl.exit_code, server.requests) == (
        3,
        3,
        3,
        (),
    )
    for result in (initialized, shown, crawl):
        (error,) = result.errors()
        assert error["code"] == "settings_invalid"
        assert error["details"]["file"] == str(settings_file.resolve())
        (problem,) = error["details"]["errors"]
        assert problem["key"] == "rules.title-too-long.max_chars"
        message = problem["message"].casefold()
        limit = re.search(r"\b(?:maximum is|must contain at most) 4300 decimal digits\b", message)
        assert limit is not None
        assert not re.search(r"\b(?:incorrect|not)\b", message[: limit.start()])


def test_an_oversized_negative_threshold_keeps_the_negative_diagnostic(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>A Page.</p>")}))
    settings_file = temp_workspace.root / "openlinx.toml"
    reasons = []
    for threshold in ("-5", "-1" + "0" * 4300):
        settings_file.write_text(
            f"[rules.low-word-count]\nmin_words = {threshold}\n", encoding="utf-8"
        )
        result = run_cli("crawl", server.url("/"))

        (error,) = result.errors()
        assert (result.exit_code, error["code"]) == (3, "settings_invalid")
        assert error["details"]["file"] == str(settings_file.resolve())
        (problem,) = error["details"]["errors"]
        assert problem["key"] == "rules.low-word-count.min_words"
        reasons.append(problem["message"])

    assert reasons[1] == reasons[0]
    assert server.requests == ()
