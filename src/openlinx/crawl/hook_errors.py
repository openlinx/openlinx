"""What a hook's failure says: its error's text and where in the hook it was raised
(023-fix-code-audit D3)."""

import sys
import traceback
from collections.abc import Callable
from functools import partial
from pathlib import Path
from types import ModuleType

import msgspec

# The warning keeps one error's text; a long repr would fill the result.
TEXT_LIMIT = 300


class HookError(msgspec.Struct, frozen=True, kw_only=True):
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


def hook_error(hook: str, function: Callable[..., object], error: BaseException) -> HookError:
    return HookError(
        hook=hook,
        error_type=type(error).__name__,
        text=str(error)[:TEXT_LIMIT],
        at=_raised_at(function, error),
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
    return f"{_shown_file(function.__module__, Path(code.co_filename))}:{lines[-1]}"


def _shown_file(module: str, file: Path) -> str:
    """Relative to the folder that holds the module's top-level package, with `/` on every OS,
    so the warning reads the same on every machine; the module's name outside it."""
    top = sys.modules.get(module.partition(".")[0])
    root = _root_of(top)
    if root is None:
        return module
    try:
        return file.resolve().relative_to(root).as_posix()
    except ValueError:
        return module


def _root_of(top: ModuleType | None) -> Path | None:
    if top is None:
        return None
    package_path = getattr(top, "__path__", None)
    if package_path:
        return Path(next(iter(package_path))).resolve().parent
    module_file = getattr(top, "__file__", None)
    return None if module_file is None else Path(module_file).resolve().parent
