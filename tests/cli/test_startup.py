"""What a fresh process loads (designs D2 and D10 of 010-add-workspace-and-cli-contract)."""

import os
import subprocess
import sys
import sysconfig
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT

# Each loaded module and where it came from: built-in, frozen, a file, or None.
LIST_MODULES = """
for name, module in list(sys.modules.items()):
    spec = getattr(module, "__spec__", None)
    origin = spec.origin if spec is not None else getattr(module, "__file__", None)
    sys.stderr.write(name + "\\t" + str(origin) + "\\n")
"""
# Runs an app as the console script does, then lists every loaded module on stderr.
LIST_MODULES_AFTER_RUN = f"""
import sys
from {{module}} import {{factory}}
try:
    {{factory}}()(sys.argv[1:])
except SystemExit:
    pass
{LIST_MODULES}
"""

STARTUP_ALLOWLIST = {
    "typer",
    # Typer's own dependencies; rich is one too, but Typer's rich help is off.
    "annotated_doc",
    "colorama",
    "shellingham",
    "orjson",
    "openlinx",
}


@dataclass(frozen=True)
class StandardLibrary:
    """Where an interpreter's standard modules live, and the site folders found inside them."""

    roots: tuple[Path, ...]
    site_dirs: tuple[Path, ...]

    def holds(self, name: str, origin: str | None) -> bool:
        # By where a module comes from, not by name: some standard modules have names the
        # platform makes, such as sysconfig's _sysconfigdata__linux_x86_64-linux-gnu.
        if origin == "built-in":
            return name in sys.stdlib_module_names
        if origin == "frozen":
            return True
        if origin is None:
            return False
        path = _real(origin)
        in_site = any(path.is_relative_to(_real(site)) for site in self.site_dirs) or not {
            "site-packages",
            "dist-packages",
        }.isdisjoint(path.parts)
        return not in_site and any(path.is_relative_to(_real(root)) for root in self.roots)


def _real(path: str | Path) -> Path:
    # Compared resolved: an installation may name one folder by several paths, as Homebrew's
    # opt/python@3.14 symlink into its Cellar does, and is_relative_to compares the text.
    return Path(os.path.realpath(path))


def this_standard_library() -> StandardLibrary:
    paths = sysconfig.get_paths()
    return StandardLibrary(
        # Windows keeps the standard extension modules in DLLs, which sysconfig names no path for.
        roots=(
            Path(paths["stdlib"]),
            Path(paths["platstdlib"]),
            Path(sys.base_exec_prefix, "DLLs"),
        ),
        # A base interpreter's site-packages lies inside its stdlib folder on Windows.
        site_dirs=(Path(paths["purelib"]), Path(paths["platlib"])),
    )


def outside_the_standard_library(
    loaded: Mapping[str, str | None], stdlib: StandardLibrary
) -> set[str]:
    """The top-level modules of `loaded`, by name with their origin, that are not standard."""
    return {
        name
        for name, origin in loaded.items()
        if "." not in name and not stdlib.holds(name, origin)
    }


def modules_loaded(module: str, factory: str, *args: str) -> dict[str, str | None]:
    return _child_modules(LIST_MODULES_AFTER_RUN.format(module=module, factory=factory), *args)


def interpreter_startup_modules() -> dict[str, str | None]:
    # Loaded before any code of ours: sitecustomize on some CI images, _virtualenv, __main__.
    return _child_modules(f"import sys\n{LIST_MODULES}")


def _child_modules(code: str, *args: str) -> dict[str, str | None]:
    completed = subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=REPO_ROOT,
        # Coverage would measure the child and load its own modules into it.
        env={k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_PROCESS_")},
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=True,
        text=True,
    )
    lines = (line.partition("\t") for line in completed.stderr.splitlines() if line)
    return {name: None if origin == "None" else origin for name, _, origin in lines}


def test_settings_tables_load_with_the_settings() -> None:
    loaded = modules_loaded("tests.support.app", "example_app", "--help")

    assert "tests.support.settings" not in loaded


def test_a_module_is_standard_by_where_it_comes_from() -> None:
    stdlib = StandardLibrary(
        roots=(Path("/py/lib/python3.14"), Path("/py/DLLs")),
        site_dirs=(Path("/venv/lib/python3.14/site-packages"),),
    )
    loaded = {
        "_sysconfigdata__linux_x86_64-linux-gnu": (
            "/py/lib/python3.14/_sysconfigdata__linux_x86_64-linux-gnu.py"
        ),
        "json": "/py/lib/python3.14/json/__init__.py",
        "_socket": "/py/DLLs/_socket.pyd",
        "_io": "built-in",
        "_frozen_importlib": "frozen",
        "pydantic": "/venv/lib/python3.14/site-packages/pydantic/__init__.py",
        "pydantic.main": "/venv/lib/python3.14/site-packages/pydantic/main.py",
        # On Windows the base interpreter's site-packages lies inside its stdlib folder.
        "in_base_site": "/py/lib/python3.14/site-packages/in_base_site/__init__.py",
        "a_namespace": None,
    }

    assert outside_the_standard_library(loaded, stdlib) == {
        "pydantic",
        "in_base_site",
        "a_namespace",
    }


def test_a_folder_reached_through_a_symlink_is_the_same_folder(tmp_path: Path) -> None:
    cellar = tmp_path / "Cellar"
    (cellar / "lib" / "json").mkdir(parents=True)
    opt = tmp_path / "opt"
    try:
        opt.symlink_to(cellar, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"this account cannot create a symlink: {error}")
    through_opt = StandardLibrary(roots=(opt / "lib",), site_dirs=())
    through_cellar = StandardLibrary(roots=(cellar / "lib",), site_dirs=())

    assert (
        outside_the_standard_library({"json": str(cellar / "lib" / "json" / "a.py")}, through_opt),
        outside_the_standard_library({"json": str(opt / "lib" / "json" / "a.py")}, through_cellar),
    ) == (set(), set())


def test_dot_dot_segments_name_the_folder_they_resolve_to() -> None:
    stdlib = StandardLibrary(
        roots=(Path("/py/lib/python3.14"), Path("/venv")),
        site_dirs=(Path("/venv/bin/../lib"),),
    )
    loaded = {
        "json": "/py/lib/other/../python3.14/json/__init__.py",
        "pkg": "/venv/lib/pkg/__init__.py",
    }

    assert outside_the_standard_library(loaded, stdlib) == {"pkg"}


# linx commands reads the inherited secret flag of an option's setting from the table's model,
# so it may load pydantic and pydantic's own dependencies (design D10 of 010).
SETTINGS_MODELS = {
    "pydantic",
    "pydantic_core",
    "annotated_types",
    "typing_inspection",
    "typing_extensions",
}


@pytest.mark.parametrize(
    ("command", "allowed"),
    [
        (["--help"], STARTUP_ALLOWLIST),
        (["commands"], STARTUP_ALLOWLIST | SETTINGS_MODELS),
        (["schema", "--help"], STARTUP_ALLOWLIST),
        (["crawl", "--help"], STARTUP_ALLOWLIST),
    ],
    ids=lambda value: " ".join(value) if isinstance(value, list) else "",
)
def test_startup_loads_only_the_allowlist(command: list[str], allowed: set[str]) -> None:
    startup = interpreter_startup_modules()
    loaded = {
        name: origin
        for name, origin in modules_loaded("openlinx.cli.app", "build_app", *command).items()
        if name not in startup
    }

    assert outside_the_standard_library(loaded, this_standard_library()) - allowed == set()
