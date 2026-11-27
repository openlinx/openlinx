"""Resolve settings from registered tables, the settings file and flag overrides."""

import difflib
import re
import sys
import tomllib
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
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

# Bound recovery even for literals that are not in a field with its own digit limit.
_DECIMAL_RECOVERY_LIMIT = 4300


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
        file_values, positions, unrecovered = _read_toml(source, fields)
    except UnicodeDecodeError as error:
        problem: dict[str, Any] = {"key": None, "message": "The file is not UTF-8.", "line": None}
        raise _invalid(settings_file, "is not UTF-8", [problem]) from error
    except tomllib.TOMLDecodeError as error:
        problem = {"key": None, "message": str(error), "line": _line(error)}
        raise _invalid(settings_file, "is not valid TOML", [problem]) from error
    root_model = create_model("OpenLinxSettings", __base__=_sources(file_values), **fields)
    problems: list[tuple[Key, str]] = []
    toml_keys: dict[Key, str] = {}
    validation_error = None
    hint = None
    try:
        settings = Settings(root_model(**values))
    except ValidationError as error:
        refused = refused_given_value(error, values)
        if refused is not None:
            raise refused from error
        settings = None
        validation_error = error
        for detail in error.errors():
            location = detail["loc"]
            problems.append((location, detail["msg"]))
            if isinstance(toml_key := detail.get("ctx", {}).get("toml_key"), str):
                toml_keys[location] = toml_key
        hint = _suggestion(error, root_model)
    if len(problems) > 1 or unrecovered:
        # Use the same normalization and table choice as the settings source.
        source_roots = InitSettingsSource(root_model, {key: key for key in file_values})()
        if unrecovered:
            overrides = InitSettingsSource(root_model, values)()
            diagnosed = tuple(key for key, _ in problems)
            problems.extend(
                (key, "The decimal integer exceeds this Python process's conversion limit.")
                for key in _selected_file_paths(unrecovered, source_roots, overrides)
                if not any(key[: len(location)] == location for location in diagnosed)
            )
        if len(problems) > 1:
            if positions is None:
                positions = file_positions(declarations(source))
            problems.sort(key=lambda problem: _position(problem[0], positions, source_roots))
    if problems:
        raise _invalid(
            settings_file,
            "is invalid",
            [
                {"key": toml_keys.get(key, ".".join(map(str, key))), "message": message}
                for key, message in problems
            ],
            hint=hint,
        ) from validation_error
    if settings is None:
        raise RuntimeError("settings validation must return settings or report an error")
    return settings


def _selected_file_paths(
    keys: Iterable[Key], source_roots: Mapping[str, str], overrides: dict[str, Any]
) -> Iterator[Key]:
    canonical_roots = {original: canonical for canonical, original in source_roots.items()}
    for root, *children in keys:
        if not isinstance(root, str) or root not in canonical_roots:
            continue
        key = (canonical_roots[root], *children)
        # The sources merge dictionaries. An explicit scalar or collection replaces its subtree.
        override: object = overrides
        for part in key:
            if not isinstance(override, dict):
                break
            if part not in override:
                yield key
                break
            override = override[part]


def _read_toml(
    source: str, fields: Mapping[str, tuple[Table, Any]]
) -> tuple[dict[str, Any], dict[Key, int] | None, tuple[Key, ...]]:
    try:
        return tomllib.loads(source), None, ()
    except tomllib.TOMLDecodeError:
        raise
    except ValueError:
        recovered = _recover_decimal_overflow(source, fields)
        if recovered is None:
            raise
        return recovered


def _recover_decimal_overflow(
    source: str, fields: Mapping[str, tuple[Table, Any]]
) -> tuple[dict[str, Any], dict[Key, int], tuple[Key, ...]] | None:
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
        decoded = tomllib.loads(probe)
    except tomllib.TOMLDecodeError:
        raise
    except ValueError:
        return None

    # Restore each confirmed integer in the parsed document. Keeping the original shape lets
    # the same model reject unknown keys and wrong types, including integers inside collections.
    located = list(declarations(probe))
    unrecovered: list[Key] = []
    for key, token in located:
        if token is None or (literal := overflows.pop(token.start(), None)) is None:
            continue
        limit = _decimal_limit(key, fields)
        maximum = _DECIMAL_RECOVERY_LIMIT if limit is None else limit
        if decimal_digits(literal[0]) <= maximum:
            number = int(Decimal(literal[0]))
        elif limit is not None:
            number = -1 if literal[0].startswith("-") else 10**limit
        else:
            # Preserve the integer type, sign and large magnitude for validation. If the model
            # accepts the placeholder, refuse only a value that survives source precedence.
            number = 10**maximum
            if literal[0].startswith("-"):
                number = -number
            unrecovered.append(key)
        container: Any = decoded
        for part in key[:-1]:
            container = container[part]
        container[key[-1]] = number
    if overflows:
        return None
    return decoded, file_positions(located), tuple(unrecovered)


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
