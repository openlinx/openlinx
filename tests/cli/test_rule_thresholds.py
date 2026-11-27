"""Verify Rule threshold bounds across Workspace-reading Commands."""

import json
import os
import re

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli, run_cli_process
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(("show", "title-too-long"), id="show-json"),
        pytest.param(("show", "title-too-long", "--format", "table"), id="show-table"),
        pytest.param(("list",), id="list-json"),
        pytest.param(("list", "--format", "jsonl"), id="list-jsonl"),
        pytest.param(("list", "--fields", "thresholds", "--format", "table"), id="list-table"),
    ],
)
@pytest.mark.parametrize("notation", ["d", "#x"], ids=["decimal", "hexadecimal"])
def test_wide_threshold_is_exact_under_a_lower_python_limit(
    temp_workspace: TempWorkspace, notation: str, args: tuple[str, ...]
) -> None:
    threshold = 10**700 - 1
    (temp_workspace.root / "openlinx.toml").write_text(
        f"[rules.title-too-long]\nmax_chars = {threshold:{notation}}\n", encoding="utf-8"
    )

    result = run_cli_process("rules", *args, env={**os.environ, "PYTHONINTMAXSTRDIGITS": "640"})

    assert result.exit_code == 0, result.stderr
    if "table" in args:
        text = re.sub(r"[\s│]+", "", result.stdout.decode())
        assert f'"value":{"9" * 700},"default":60,"unit":"characters"' in text
        return
    if "jsonl" in args:
        items = [json.loads(line) for line in result.stdout.splitlines()]
    elif args[0] == "list":
        items = result.json()["items"]
    else:
        items = [result.json()]
    (item,) = (item for item in items if item["id"] == "title-too-long")
    actual = item["thresholds"]["max_chars"]
    assert type(actual["value"]) is int
    assert actual == {"value": threshold, "default": 60, "unit": "characters"}


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

    result = run_cli_process(
        "rules", "show", "title-too-long", env={**os.environ, "PYTHONINTMAXSTRDIGITS": "640"}
    )

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

    env = {**os.environ, "PYTHONINTMAXSTRDIGITS": "640"}
    initialized = run_cli_process("init", env=env)
    shown = run_cli_process("rules", "show", "title-too-long", env=env)
    crawl = run_cli_process("crawl", server.url("/"), env=env)

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


@pytest.mark.parametrize(
    ("source", "key", "suggestion"),
    [
        pytest.param(
            "rules.title-to-long.max_chars = <value>",
            "rules.title-to-long",
            "rules.title-too-long",
            id="unknown-rule",
        ),
        pytest.param(
            "rules.h1-missing.max_chars = <value>",
            "rules.h1-missing.max_chars",
            None,
            id="unknown-key",
        ),
        pytest.param(
            "rules.title-missing.enabled = <value>",
            "rules.title-missing.enabled",
            None,
            id="numeric-enabled",
        ),
        pytest.param(
            "rules.title-too-long.max_chars = [70, # comment\n [<value>]]",
            "rules.title-too-long.max_chars",
            None,
            id="nested-array",
        ),
        pytest.param(
            "rules.title-too-long.max_chars = {x = <value>}",
            "rules.title-too-long.max_chars",
            None,
            id="inline-table",
        ),
        pytest.param(
            "rules.title-missing.enabled = [<value>]",
            "rules.title-missing.enabled",
            None,
            id="array-enabled",
        ),
    ],
)
def test_a_wide_integer_in_an_invalid_rule_setting_keeps_its_diagnostic(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    source: str,
    key: str,
    suggestion: str | None,
) -> None:
    settings = temp_workspace.root / "openlinx.toml"
    server = fixture_site(Site(routes={"/": Page(body="<p>A Page.</p>")}))
    invalid = source.replace("<value>", "9" * 700)
    settings.write_text(
        f"crawl.concurrency = 0\n{invalid}\nstore.journal_mode = 'unknown'\n",
        encoding="utf-8",
    )

    for command in (("rules", "list"), ("crawl", server.url("/"))):
        normal = run_cli_process(*command, env={**os.environ, "PYTHONINTMAXSTRDIGITS": "4300"})
        constrained = run_cli_process(*command, env={**os.environ, "PYTHONINTMAXSTRDIGITS": "640"})

        assert constrained.exit_code == normal.exit_code == 3, constrained.stderr
        (error,) = constrained.errors()
        assert error == normal.errors()[0]
        assert error["code"] == "settings_invalid"
        assert error["details"]["file"] == str(settings.resolve())
        assert [item["key"] for item in error["details"]["errors"]] == [
            "crawl.concurrency",
            key,
            "store.journal_mode",
        ]
        if suggestion is not None:
            assert suggestion in error["hint"]
    assert server.requests == ()


def test_an_unbounded_setting_refuses_an_unrestored_integer(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    settings = temp_workspace.root / "openlinx.toml"
    server = fixture_site(Site(routes={"/": Page(body="<p>A Page.</p>")}))
    env = {**os.environ, "PYTHONINTMAXSTRDIGITS": "640"}
    depth = f"max_depth = {'9' * 4301}\n"
    settings.write_text(f"[Crawl]\n{depth}", encoding="utf-8")

    result = run_cli_process("rules", "list", env=env)

    assert result.exit_code == 3
    (error,) = result.errors()
    assert error["code"] == "settings_invalid"
    (problem,) = error["details"]["errors"]
    assert problem == {
        "key": "crawl.max_depth",
        "message": "The decimal integer exceeds this Python process's conversion limit.",
    }

    settings.write_text(
        f"[Crawl]\nconcurrency = 0\n{depth}[store]\njournal_mode = 'unknown'\n",
        encoding="utf-8",
    )
    with_flag = run_cli_process("crawl", server.url("/"), "--max-depth", "0", env=env)
    without_flag = run_cli_process("crawl", server.url("/"), env=env)

    assert with_flag.exit_code == without_flag.exit_code == 3
    normal, combined = (result.errors()[0] for result in (with_flag, without_flag))
    assert normal["code"] == combined["code"] == "settings_invalid"
    assert normal["details"]["file"] == combined["details"]["file"] == str(settings.resolve())
    before, after = normal["details"]["errors"]
    assert (before["key"], after["key"]) == ("crawl.concurrency", "store.journal_mode")
    assert combined["details"]["errors"] == [before, problem, after]
    assert server.requests == ()


def test_a_boolean_setting_keeps_the_diagnostic_beyond_the_recovery_bound(
    temp_workspace: TempWorkspace,
) -> None:
    settings = temp_workspace.root / "openlinx.toml"
    env = {**os.environ, "PYTHONINTMAXSTRDIGITS": "640"}
    diagnostics = []
    for numeral in ("9" * 4301, f"{10**4301 - 1:#x}"):
        settings.write_text(f"rules.title-missing.enabled = {numeral}\n", encoding="utf-8")
        result = run_cli_process("rules", "list", env=env)

        assert result.exit_code == 3
        (error,) = result.errors()
        assert error["code"] == "settings_invalid"
        diagnostics.append(error)

    assert diagnostics[0] == diagnostics[1]


def test_an_oversized_negative_threshold_keeps_the_negative_diagnostic(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>A Page.</p>")}))
    settings_file = temp_workspace.root / "openlinx.toml"
    reasons = []
    for threshold in ("-5", "-1" + "0" * 4300):
        settings_file.write_text(
            f"[rules.title-too-long]\nmax_chars = {threshold}\n", encoding="utf-8"
        )
        result = run_cli("crawl", server.url("/"))

        (error,) = result.errors()
        assert (result.exit_code, error["code"]) == (3, "settings_invalid")
        assert error["details"]["file"] == str(settings_file.resolve())
        (problem,) = error["details"]["errors"]
        assert problem["key"] == "rules.title-too-long.max_chars"
        reasons.append(problem["message"])

    assert reasons[1] == reasons[0]
    assert server.requests == ()
