"""Registering a Command with @command_meta (design D7 of 010-add-workspace-and-cli-contract)."""

import pytest

from spider.cli.meta import command_meta
from spider.output.writer import Format


def test_a_command_without_the_format_parameter_is_refused_when_it_is_declared() -> None:
    def no_format() -> dict[str, str]:
        return {}

    with pytest.raises(TypeError):
        command_meta(output="document", formats=[Format.JSON])(no_format)
