"""The scenarios' `example` settings table (design D8 of 010-add-workspace-and-cli-contract)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExampleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["low", "high"] = Field("low", description="How much the example does.")
