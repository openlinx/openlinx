"""Share settings fixtures and diagnostic assertions across CLI and Workspace tests."""

import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UNKNOWN_SETTING_REASON = re.compile(
    r"(?:(?:unknown|unrecognized) (?:setting(?: key)?|key|table)"
    r"|(?:extra|unexpected) (?:inputs?|keys?|settings?) (?:is|are) not (?:permitted|allowed)"
    r"|this (?:setting|key|table) is not (?:permitted|allowed))[.!]?",
    re.IGNORECASE,
)
TABLE_REQUIRED_REASON = re.compile(
    r"(?:input should be a valid (?:dictionary|mapping|table)(?: or instance of [\w.]+)?"
    r"|(?:this (?:rule )?setting must be|expected) a (?:TOML )?table"
    r"|a (?:TOML )?table is required)[.!]?",
    re.IGNORECASE,
)


def assert_setting_problem(
    problem: Mapping[str, object], key: str, reason: re.Pattern[str]
) -> None:
    """Check the exact diagnostic path and the meaning of its whole message."""
    assert set(problem) == {"key", "message"}
    assert problem["key"] == key
    message = problem["message"]
    assert isinstance(message, str)
    assert reason.fullmatch(message.strip()), message


class ExampleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["low", "high"] = Field("low", description="How much the example does.")
    token: str | None = Field(
        None, description="The example's token.", json_schema_extra={"secret": True}
    )


class GroupSettings(BaseModel):
    """A named group of the example."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["low", "high"] = Field("low", description="How much the group does.")


GroupsTable = dict[str, GroupSettings]
