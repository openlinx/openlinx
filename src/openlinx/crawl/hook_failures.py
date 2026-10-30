"""What a hook's failure says: its error's text and where in the hook it was raised
(023-fix-code-audit D3)."""

import sys
import traceback
from collections.abc import Callable
from functools import lru_cache, partial
from pathlib import Path

import msgspec

# The warning keeps one error's text; a long repr would fill the result.
TEXT_LIMIT = 300


class HookFailure(msgspec.Struct, frozen=True, kw_only=True):
    """One hook's failure: a struct, so an extractor's crosses 026's process boundary."""

    hook: str
    error_type: str
    text: str
    # `<file>:<line>`; None when no frame of the error is in the hook's own file.
    at: str | None = None

    @property
    def details(self) -> dict[str, str]:
        """The warning's details of the first URL it failed on."""
        return {"error": self.text} | ({} if self.at is None else {"at": self.at})


def hook_failure(hook: str, function: Callable[..., object], error: BaseException) -> HookFailure:
    """Called inside the hook's except clause, so reading the error must never raise: a hook's
    failure costs only its rows or output (020-add-crawl-core D16)."""
    error_type = type(error).__name__
    try:
        text = str(error)
    except Exception:
        text = f"<{error_type} that cannot be printed>"
    return HookFailure(
        hook=hook, error_type=error_type, text=text[:TEXT_LIMIT], at=_raised_at(function, error)
    )


def _raised_at(function: Callable[..., object], error: BaseException) -> str | None:
    while isinstance(function, partial):
        function = function.func
    code = getattr(function, "__code__", None)
    if code is None:
        return None
    # The deepest frame in the hook's file, so an error that a library raises points at the
    # hook's line that called it.
    lines = [
        line
        for frame, line in traceback.walk_tb(error.__traceback__)
        if frame.f_code.co_filename == code.co_filename
    ]
    if not lines:
        return None
    return f"{_shown_file(function.__module__, code.co_filename)}:{lines[-1]}"


# A handler that fails on every URL asks for one file again and again, on the loop's thread.
@lru_cache(maxsize=256)
def _shown_file(module: str, filename: str) -> str:
    """Relative to the folder that holds the module's top-level package, with `/` on every OS,
    so the warning reads the same on every machine; the module's name outside it."""
    top = sys.modules.get(module.partition(".")[0])
    package_path = getattr(top, "__path__", None)
    top_file = package_path[0] if package_path else getattr(top, "__file__", None)
    if top_file is None:
        return module
    try:
        return Path(filename).resolve().relative_to(Path(top_file).resolve().parent).as_posix()
    # Another drive, or a path the file system cannot resolve.
    except (OSError, ValueError):
        return module
