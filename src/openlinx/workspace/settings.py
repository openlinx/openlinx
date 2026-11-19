"""Resolve settings from registered tables, the settings file and flag overrides."""

import difflib
import re
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import AfterValidator, BaseModel, ValidationError, create_model
from pydantic.fields import FieldInfo
from pydantic_core import PydanticCustomError
from pydantic_settings import (
    BaseSettings,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import INVALID_VALUE, SETTINGS_INVALID
from openlinx.output.diagnostics import OpenLinxError
from openlinx.workspace.discovery import Workspace
from openlinx.workspace.tables import SettingsTables, Table, keyed_entry
from openlinx.workspace.toml_order import (
    Key,
    decimal_digits,
    declarations,
    file_positions,
    oversized_decimals,
    replace_literals,
)


@dataclass(frozen=True)
class NonNegativeDecimalDigits:
    """Cap the decimal digits of a setting already constrained to non-negative integers."""

    maximum: int

    def __call__(self, value: int) -> int:
        if value >= 10**self.maximum:
            raise PydanticCustomError(
                "decimal_digits", f"Must contain at most {self.maximum} decimal digits."
            )
        return value


@dataclass(frozen=True)
class Settings:
    root: BaseSettings

    def table[M: BaseModel](self, model: type[M]) -> M:
        for value in vars(self.root).values():
            if isinstance(value, model):
                return value
        raise TypeError(
            f"the settings table {model.__name__} is not registered: register it in "
            "openlinx.services.settings.default_tables(), or an extra table in "
            "AppExtra.settings_tables"
        )


def load_settings(
    workspace: Workspace,
    tables: SettingsTables,
    flags: Mapping[str, Mapping[str, Any]] | None = None,
) -> Settings:
    fields: dict[str, Any] = {
        name: (table, {} if keyed_entry(table) is not None else table())
        for name, table in tables.items()
    }
    settings_file = workspace.settings_file
    if settings_file.exists() and not settings_file.is_file():
        raise _invalid(settings_file, "is not a file", [{"key": None, "message": "Not a file."}])
    values: dict[str, Any] = dict(flags or {})
    try:
        # Validate and order diagnostics from the same bytes even if the file is replaced.
        source = settings_file.read_bytes().decode("utf-8") if settings_file.is_file() else ""
        file_values, positions = _read_toml(source, fields)
    except UnicodeDecodeError as error:
        problem: dict[str, Any] = {"key": None, "message": "The file is not UTF-8.", "line": None}
        raise _invalid(settings_file, "is not UTF-8", [problem]) from error
    except tomllib.TOMLDecodeError as error:
        problem = {"key": None, "message": str(error), "line": _line(error)}
        raise _invalid(settings_file, "is not valid TOML", [problem]) from error
    root_model = create_model("OpenLinxSettings", __base__=_sources(file_values), **fields)
    try:
        return Settings(root_model(**values))
    except ValidationError as error:
        refused = refused_given_value(error, values)
        if refused is not None:
            raise refused from error
        problems = error.errors()
        if len(problems) > 1:
            if positions is None:
                positions = file_positions(declarations(source))
            # Ask the file's settings source which spelling supplied each canonical root.
            # Distinct TOML tables can have names that differ only in case.
            source_roots = InitSettingsSource(root_model, {key: key for key in file_values})()
            problems.sort(key=lambda problem: _position(problem["loc"], positions, source_roots))
        raise _invalid(
            settings_file,
            "is invalid",
            [
                {"key": ".".join(map(str, problem["loc"])), "message": problem["msg"]}
                for problem in problems
            ],
            hint=_suggestion(error, root_model),
        ) from error


def _read_toml(
    source: str, fields: Mapping[str, tuple[Table, Any]]
) -> tuple[dict[str, Any], dict[Key, int] | None]:
    try:
        return tomllib.loads(source), None
    except tomllib.TOMLDecodeError:
        raise
    except ValueError:
        recovered = _recover_decimal_overflow(source, fields)
        if recovered is None:
            raise
        return recovered


def _recover_decimal_overflow(
    source: str, fields: Mapping[str, tuple[Table, Any]]
) -> tuple[dict[str, Any], dict[Key, int]] | None:
    # Check syntax with neutral values before walking declarations. The walker assumes valid
    # TOML, while a conversion error can stop tomllib before it reaches malformed syntax.
    overflows = {
        literal.start(): literal
        for literal in oversized_decimals(source, sys.get_int_max_str_digits())
    }
    if not overflows:
        return None
    probe = replace_literals(source, ((literal, "0") for literal in overflows.values()))
    try:
        tomllib.loads(probe)
    except tomllib.TOMLDecodeError:
        raise
    except ValueError:
        return None

    # Reparse the original data with replacements only for confirmed bounded fields. The
    # probe's values must never reach settings, including on files with an unrelated overflow.
    located = list(declarations(probe))
    replacements: list[tuple[re.Match[str], str]] = []
    for key, token in located:
        if token is None or (literal := overflows.get(token.start())) is None:
            continue
        limit = _decimal_limit(key, fields)
        if limit is None or decimal_digits(literal[0]) <= limit:
            return None
        replacement = "-1" if literal[0].startswith("-") else hex(10**limit)
        replacements.append((literal, replacement))
    if len(replacements) != len(overflows):
        return None
    return tomllib.loads(replace_literals(source, replacements)), file_positions(located)


def _decimal_limit(key: Key, fields: Mapping[str, tuple[Table, Any]]) -> int | None:
    root, *children = key
    if not isinstance(root, str) or root.lower() not in fields:
        return None
    # The settings source normalizes the root name. Subtables use their declared aliases.
    model: object = fields[root.lower()][0]
    field: FieldInfo | None = None
    for name in children:
        if (
            not isinstance(name, str)
            or not isinstance(model, type)
            or not issubclass(model, BaseModel)
        ):
            return None
        field = _toml_fields(model).get(name)
        if field is None:
            return None
        model = field.annotation
    if field is None:
        return None
    return next(
        (
            validator.func.maximum
            for validator in field.metadata
            if isinstance(validator, AfterValidator)
            and isinstance(validator.func, NonNegativeDecimalDigits)
        ),
        None,
    )


def refused_given_value(
    error: ValidationError, given: Mapping[str, Mapping[str, Any]], table: str | None = None
) -> OpenLinxError | None:
    """invalid_value for the first error at a key the caller gave, or None when the file's
    values alone are refused: the call's own input is checked first, as Click checks flags
    (023-fix-code-audit D9). `table` names the table of an error from one table's model."""
    keys, tables = _given_paths(given)
    for problem in error.errors():
        parts = ([] if table is None else [table]) + [str(part) for part in problem["loc"]]
        # A list's item is located below its key, as crawl.exclude.1.
        prefixes = (".".join(parts[:size]) for size in range(len(parts), 0, -1))
        key = next((prefix for prefix in prefixes if prefix in keys), None)
        located = ".".join(parts)
        if key is None and located in tables:
            key = located
        if key is not None:
            # pydantic words a validator's ValueError as "Value error, <its text>".
            reason = problem["msg"].removeprefix("Value error, ")
            return OpenLinxError(
                INVALID_VALUE,
                f"Invalid value for {key}: {reason}.",
                hint=f"Change the value given for {key}; {COMMAND_NAME} commands lists the "
                "type and bounds of each option that gives a setting.",
                details={"key": key},
            )
    return None


def _given_paths(given: Mapping[str, Any], prefix: str = "") -> tuple[set[str], set[str]]:
    # Empty tables have no leaf keys; keep their paths for exact table-error attribution.
    keys: set[str] = set()
    tables: set[str] = set()
    for name, value in given.items():
        key = f"{prefix}{name}"
        if isinstance(value, Mapping):
            tables.add(key)
            child_keys, child_tables = _given_paths(value, f"{key}.")
            keys.update(child_keys)
            tables.update(child_tables)
        else:
            keys.add(key)
    return keys, tables


def _invalid(
    settings_file: Path, what: str, errors: list[dict[str, Any]], hint: str | None = None
) -> OpenLinxError:
    return OpenLinxError(
        SETTINGS_INVALID,
        f"The settings file {settings_file} {what}.",
        hint=hint,
        details={"file": str(settings_file), "errors": errors},
    )


def _position(key: Key, positions: Mapping[Key, int], source_roots: Mapping[str, str]) -> int:
    if key and isinstance(key[0], str):
        key = (source_roots.get(key[0], key[0]), *key[1:])
    # Validators can report a child of a value assigned as a whole.
    while key and key not in positions:
        key = key[:-1]
    return positions.get(key, len(positions))


def _line(error: tomllib.TOMLDecodeError) -> int | None:
    # Python 3.14 added lineno; 3.12 and 3.13 only put it in the message.
    lineno: int | None = getattr(error, "lineno", None)
    if lineno is not None:
        return lineno
    match = re.search(r"at line (\d+)", str(error))
    return int(match.group(1)) if match else None


def _suggestion(error: ValidationError, root_model: type[BaseModel]) -> str | None:
    for problem in error.errors():
        if problem["type"] != "extra_forbidden":
            continue
        *parents, unknown = (str(part) for part in problem["loc"])
        model: Any = root_model
        for part in parents:
            # A keyed table's part is an entry's name: the next level is the entry model.
            entry = keyed_entry(model)
            model = entry if entry is not None else _toml_fields(model)[part].annotation
        matches = difflib.get_close_matches(unknown, list(_toml_fields(model)), n=1)
        if matches:
            return f"Did you mean {'.'.join([*parents, matches[0]])}?"
    return None


def _toml_fields(model: type[BaseModel]) -> dict[str, FieldInfo]:
    return {field.alias or key: field for key, field in model.model_fields.items()}


def _sources(file_values: dict[str, Any]) -> type[BaseSettings]:
    class Root(BaseSettings):
        model_config = SettingsConfigDict(extra="forbid")

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            # No env, .env or secrets source: settings come only from flags and the settings file.
            return (init_settings, InitSettingsSource(settings_cls, file_values))

    return Root
