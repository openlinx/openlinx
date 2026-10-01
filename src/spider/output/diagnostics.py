"""Errors, each bound to its exit code (design D5 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Mapping
from typing import Any


class SpiderError(Exception):
    exit_code: int

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = dict(details or {})


class UsageError(SpiderError):
    exit_code = 2
