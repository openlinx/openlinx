"""Typer's vendored Click in one place (design D10 of 010-add-workspace-and-cli-contract)."""

# Typer 0.27 vendors Click as the private typer._click, and re-exports neither error below.
# A Typer upgrade then touches this module and the pin in pyproject.toml only.
from typer._click.core import Command, Context, Parameter  # noqa: TID251
from typer._click.exceptions import MissingParameter, UsageError  # noqa: TID251

__all__ = ["Command", "Context", "MissingParameter", "Parameter", "UsageError"]
