"""Measure a real HTTP Crawl of the seeded local site and verify its stored Pages."""

import argparse
import json
import os
import subprocess
import tempfile
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path

import psutil

from tests.fixture_site.synthetic.accounting import accounted_urls
from tests.fixture_site.synthetic.serve import SiteProcess
from tests.fixture_site.synthetic.site import (
    DEFAULT_SHARES,
    Fault,
    SyntheticSite,
)
from tests.support.processes import python_command


def _crawl(workspace: Path, seed: str) -> tuple[Path, int]:
    command = python_command("-m", "openlinx", "crawl", seed, "--workspace", str(workspace))
    env = {**(command.env or os.environ), "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}
    peak = 0
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        with subprocess.Popen(command.argv, stdout=out, stderr=err, env=env) as process:
            try:
                identity = psutil.Process(process.pid)
                while process.poll() is None:
                    with suppress(psutil.NoSuchProcess):
                        peak = max(peak, identity.memory_info().rss)
                    with suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=0.2)
            finally:
                if process.poll() is None:
                    process.kill()
            if process.returncode:
                err.seek(max(0, err.tell() - 4096))
                raise RuntimeError(
                    f"Crawl exited {process.returncode}: {err.read().decode(errors='replace')}"
                )
        out.seek(0)
        return Path(json.load(out)["crawl_file"]), peak


def _run(site: SyntheticSite, workspace: Path) -> dict[str, object]:
    command = python_command("-m", "openlinx", "init", "--workspace", str(workspace))
    subprocess.run(command.argv, env=command.env, stdout=subprocess.DEVNULL, check=True)
    with SiteProcess(site) as fixture:
        origin = fixture.base_url.rstrip("/")
        crawl_file, peak = _crawl(workspace, origin + "/")
        tally = fixture.stop()
    stored, page_rows = accounted_urls(crawl_file, site, origin)
    if tally.pages_requested != site.pages:
        raise ValueError(
            f"The site received requests for {tally.pages_requested} of {site.pages} Pages"
        )
    return {
        "seed": site.seed,
        "pages_requested": site.pages,
        "pages_stored": page_rows,
        "stored_urls": stored,
        "crawl_peak_rss_bytes": peak,
        "site": asdict(tally),
        "crawl_file": str(crawl_file),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=500_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--keep", type=Path, help="retain the Crawl in a new Workspace here")
    args = parser.parse_args()
    if args.pages < 1:
        parser.error("--pages must be positive")
    # The in-process baseline cannot contain faults that require an isolated worker.
    shares: dict[Fault, float] = {
        k: v for k, v in DEFAULT_SHARES.items() if k not in (Fault.NESTED_DIVS, Fault.ENDS_WORKER)
    }
    site = SyntheticSite(pages=args.pages, seed=args.seed, shares=shares)
    with tempfile.TemporaryDirectory() as scratch:
        workspace = Path(scratch) / "crawl" if args.keep is None else args.keep.resolve()
        if workspace.exists():
            parser.error(f"Workspace path already exists: {workspace}")
        report = _run(site, workspace)
        if args.keep is None:
            report["crawl_file"] = None
        print(json.dumps(report))


if __name__ == "__main__":
    main()
