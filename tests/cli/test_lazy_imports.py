"""Guard: importing the CLI loads no heavy library (design D6 of 000-scaffold-project)."""

import subprocess
import sys

HEAVY_LIBRARIES = {"aiohttp", "sqlalchemy", "alembic", "numpy", "selectolax", "lxml", "pydantic"}
LIST_MODULES_AFTER_IMPORT = "import sys, spider.cli.app; print('\\n'.join(sys.modules))"


def test_importing_the_cli_app_loads_no_heavy_library() -> None:
    listing = subprocess.run(
        [sys.executable, "-c", LIST_MODULES_AFTER_IMPORT],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    top_level_modules = {name.partition(".")[0] for name in listing.split()}

    assert top_level_modules & HEAVY_LIBRARIES == set()
