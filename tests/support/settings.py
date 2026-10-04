"""The scenarios' settings tables (design D8 of 010-add-workspace-and-cli-contract)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExampleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["low", "high"] = Field("low", description="How much the example does.")
    token: str | None = Field(None, description="The example's token.")


class GroupSettings(BaseModel):
    """A named group of the example."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["low", "high"] = Field("low", description="How much the group does.")


GroupsTable = dict[str, GroupSettings]
