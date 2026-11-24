"""Keep secret-form metadata inherited while Command descriptions expose booleans."""

import json
from typing import Annotated, Any, cast

import typer
from pydantic import BaseModel, ConfigDict, Field
from typer.main import get_command

from openlinx.cli.app import AppExtra, build_app
from openlinx.cli.meta import command_meta
from openlinx.cli.options import FormatOpt, OptionMeta, secret_flags
from openlinx.cli.runner import OpenLinxGroup
from openlinx.output.reporter import Collected
from openlinx.output.writer import Format
from openlinx.services.crawling import CrawlRequest, plan_crawl
from openlinx.services.crawls import create_crawl
from openlinx.workspace.tables import SecretPolicy
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawls import crawl_row
from tests.support.workspace import TempWorkspace

WHOLE: SecretPolicy = "whole"


class FormSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: str = Field("", description="A credential.", json_schema_extra={"secret": "whole"})
    entries: list[str] = Field([], description="Headers.", json_schema_extra={"secret": "header"})
    endpoint: str = Field("", description="A URL.", json_schema_extra={"secret": "url"})
    visible: str = Field("", description="Visible text.", json_schema_extra={"secret": False})


@command_meta(output="document", formats=[Format.JSON])
def forms(
    output_format: FormatOpt = Format.JSON,
    credential: Annotated[str, typer.Option(), OptionMeta(setting="forms.credential")] = "",
    entries: Annotated[
        list[str] | None, typer.Option(), OptionMeta(setting="forms.entries")
    ] = None,
    endpoint: Annotated[str, typer.Option(), OptionMeta(setting="forms.endpoint")] = "",
    visible: Annotated[str, typer.Option(), OptionMeta(setting="forms.visible")] = "",
    standalone: Annotated[str, typer.Option(), OptionMeta(secret=WHOLE)] = "",
) -> dict[str, Any]:
    return {}


def _app() -> typer.Typer:
    return build_app(
        AppExtra(
            settings_tables={"forms": "tests.cli.test_secret_forms:FormSettings"}, commands=[forms]
        )
    )


def test_declared_forms_reach_crawl_recording_from_option_and_setting_metadata(
    temp_workspace: TempWorkspace,
) -> None:
    group = cast(OpenLinxGroup, get_command(_app()))
    request = CrawlRequest(
        seed="http://site.test/",
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        command_argv=[
            "linx",
            "forms",
            "--credential",
            "http://ann:s3cret@proxy.test",
            "--entries",
            "X-Token: abc123",
            "--endpoint=http://proxy.test:8080",
            "--visible=public",
            "--standalone=http://ann:other@proxy.test",
        ],
        flags={
            "forms": {
                "credential": "http://ann:s3cret@proxy.test",
                "entries": ["X-Env: staging", "X-Token: abc123"],
                "endpoint": "http://proxy.test:8080",
                "visible": "public",
            }
        },
        secret_flags=secret_flags(group.commands["forms"], group.settings_tables),
    )
    plan = plan_crawl(request, group.settings_tables)
    with create_crawl(plan.new_crawl, FakeClock(), Collected()) as crawl:
        pass
    row = crawl_row(crawl.path)

    assert json.loads(row["config"])["forms"] == {
        "credential": "***",
        "entries": ["X-Env: staging", "X-Token: ***"],
        "endpoint": "http://proxy.test:8080",
        "visible": "public",
    }
    assert json.loads(row["command_argv"]) == [
        "linx",
        "forms",
        "--credential",
        "***",
        "--entries",
        "X-Token: ***",
        "--endpoint=http://proxy.test:8080",
        "--visible=public",
        "--standalone=***",
    ]
    recorded = crawl.path.read_bytes()
    assert b"s3cret" not in recorded
    assert b"abc123" not in recorded
    assert b"ann:other" not in recorded


def test_command_secret_indicators_are_booleans_for_every_declared_form() -> None:
    entry = next(
        c for c in run_cli("commands", app=_app()).json()["commands"] if c["name"] == "forms"
    )
    options = {option["name"]: option for option in entry["options"]}

    assert {name: option["secret"] for name, option in options.items()} == {
        "--format": False,
        "--credential": True,
        "--entries": True,
        "--endpoint": True,
        "--visible": False,
        "--standalone": True,
    }
    assert all(type(option["secret"]) is bool for option in options.values())
