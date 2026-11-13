"""Guard: package interfaces list cross-package imports from src (023 D13)."""

import ast
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT
from tests.support.processes import python_command

SRC = Path(__file__).resolve().parents[1] / "src"


def missing_interface_names(sources: Mapping[str, str]) -> list[str]:
    trees = {path: ast.parse(source) for path, source in sources.items()}
    interfaces = {
        path.removesuffix("/__init__.py").replace("/", "."): {
            (module, name)
            for module, names in re.findall(
                r"\b([a-z_]\w*):\s*([\w,\s]+)\.", ast.get_docstring(tree) or ""
            )
            for name in re.findall(r"\b\w+\b", names)
        }
        for path, tree in trees.items()
        if path.startswith("openlinx/crawl/") and path.endswith("/__init__.py")
    }
    missing = []
    for path, tree in trees.items():
        importer = path.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            parts = node.module.split(".")
            if parts[:2] != ["openlinx", "crawl"] or len(parts) < 4:
                continue
            package = ".".join(parts[:3])
            if importer == package or importer.startswith(f"{package}."):
                continue
            module = ".".join(parts[3:])
            doc_path = package.replace(".", "/") + "/__init__.py"
            for alias in node.names:
                if (module, alias.name) not in interfaces.get(package, set()):
                    missing.append(
                        f"{path}:{node.lineno} imports {node.module}.{alias.name}: "
                        f"list {alias.name} under {module} in {doc_path}'s docstring"
                    )
    return missing


def test_every_name_used_across_a_package_is_listed() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(SRC.rglob("*.py"))
    }

    assert missing_interface_names(sources) == [], (
        "every cross-package import from src is listed in its package interface: "
        "add each reported name under its module in the named __init__.py docstring"
    )


def test_an_unlisted_import_names_its_module_and_the_docstring_to_edit() -> None:
    sources = {
        "openlinx/crawl/pages/__init__.py": '"""Page preparation.\n\n'
        'preparation: PageInput. links: prepare_page.\n"""',
        "openlinx/extract/page.py": "def extract():\n"
        "    from openlinx.crawl.pages.preparation import prepare_page as prepare\n",
    }

    assert missing_interface_names(sources) == [
        "openlinx/extract/page.py:2 imports openlinx.crawl.pages.preparation.prepare_page: "
        "list prepare_page under preparation in openlinx/crawl/pages/__init__.py's docstring"
    ]


def test_listed_imports_and_imports_within_the_package_need_no_new_entry() -> None:
    sources = {
        "openlinx/crawl/pages/__init__.py": '"""Page preparation.\n\n'
        'preparation: PageInput,\nPageSettings. links: locate_links.\n"""',
        "openlinx/crawl/pages/headers.py": "from openlinx.crawl.pages.links import rel_tokens\n",
        "openlinx/crawl/pages/nested/__init__.py": (
            "from openlinx.crawl.pages.links import rel_tokens\n"
        ),
        "openlinx/extract/page.py": "from openlinx.crawl.pages.preparation import (\n"
        "    PageInput as Input,\n    PageSettings,\n)\n"
        "if TYPE_CHECKING:\n    from openlinx.crawl.pages.links import locate_links\n",
        "openlinx/crawl/scope.py": "from openlinx.store.records import LinkType\n",
    }

    assert missing_interface_names(sources) == []


@pytest.mark.parametrize(
    "references_first", [True, False], ids=["references first", "following first"]
)
def test_reference_resolution_and_redirects_import_cold_in_either_order(
    references_first: bool,
) -> None:
    imports = [
        "from openlinx.crawl.references import C0_OR_SPACE, resolve_base, resolve_reference\n",
        "from openlinx.crawl.following import redirect_target\n",
    ]
    command = python_command(
        "-c",
        "".join(imports if references_first else reversed(imports))
        + "from openlinx.crawl.urls import NormalizedUrl\n"
        + "url = NormalizedUrl('http://site.test/dir/page')\n"
        + "assert resolve_reference(url, '../next', None, None) == 'http://site.test/next'\n"
        + "assert resolve_base(url, '/base/', None) == 'http://site.test/base/'\n"
        + "assert redirect_target(url, 302, '../next', None) == 'http://site.test/next'\n",
    )
    completed = subprocess.run(
        command.argv,
        env=command.env,
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        text=True,
        check=False,
    )

    assert (completed.returncode, completed.stdout, completed.stderr) == (0, "", ""), (
        "reference resolution and redirects import cold in either order: keep shared URL "
        "resolution in a dependency leaf, with the existing named interfaces preserved"
    )
