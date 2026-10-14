"""What the Page extractor loads in a parse-pool worker (030-add-page-data D1; seam 4)."""

import os
import subprocess
import sys

from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT

_LIST_MODULES = "import sys, spider.extract.page_data; sys.stderr.write(chr(10).join(sys.modules))"


def test_the_page_extractor_loads_no_sqlalchemy() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _LIST_MODULES],
        cwd=REPO_ROOT,
        # Coverage would measure the child and load its own modules into it.
        env={k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_PROCESS_")},
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=True,
        text=True,
    )

    assert [name for name in completed.stderr.split() if name.startswith("sqlalchemy")] == []
