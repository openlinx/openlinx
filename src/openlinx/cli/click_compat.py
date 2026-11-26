"""Isolate Typer's private vendored Click API behind one compatibility module."""

# Typer 0.27 vendors Click as the private typer._click, and re-exports neither error below.
# The minor-version cap in pyproject.toml lets us review these private imports at each upgrade.
from typer._click.core import Command, Context, Parameter, ParameterSource  # noqa: TID251
from typer._click.exceptions import MissingParameter, UsageError  # noqa: TID251

__all__ = [
    "Command",
    "Context",
    "MissingParameter",
    "Parameter",
    "ParameterSource",
    "UsageError",
]
