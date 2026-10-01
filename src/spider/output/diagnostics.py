"""Errors, each bound to its exit code (design D5 of 010-add-workspace-and-cli-contract)."""


class SpiderError(Exception):
    exit_code: int

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class UsageError(SpiderError):
    exit_code = 2
