"""Qualify native Ctrl+Break on the dispatch-only Windows verification branch."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
MODULE = "tests.crawl.test_parse_process_tree"
BOOTSTRAP = "test_ctrl_break_ends_the_parse_tree_during_windows_bootstrap"
NO_WINDOW = "test_parse_workers_open_no_console_window"
CASES = (
    "worker-targeted",
    "worker-broadcast",
    "replacement-targeted",
    "replacement-broadcast",
    "guardian-targeted",
    "guardian-broadcast",
    "no-window",
)
LAUNCH = Path("src/openlinx/crawl/pages/parse_launch.py")
POOL = Path("src/openlinx/crawl/pages/parse_pool.py")
FIXTURE = Path("tests/crawl/parse_process_fixture.py")
TEST = Path("tests/crawl/test_parse_process_tree.py")
INTERRUPT_DEADLINE_NS = 14_000_000_000
CONSOLE_KILLED = 0xC000013A
WAIT_TIMEOUT = 0x102


class ProofError(RuntimeError):
    """A required observation was missing or did not match the expected outcome."""


def require(value: bool, reason: str) -> None:
    if not value:
        raise ProofError(reason)


def junit_check(report: Path, name: str, expected_failure: str | None) -> None:
    # pytest creates this file from our own synthetic fixtures in this step's temp directory.
    root = ElementTree.parse(report).getroot()  # noqa: S314
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
    require(len(suites) == 1 and suites[0].tag == "testsuite", "junit-suite")
    suite = suites[0]
    counts = {
        "tests": "1",
        "errors": "0",
        "skipped": "0",
        "failures": "1" if expected_failure else "0",
    }
    require(all(suite.get(key) == value for key, value in counts.items()), "junit-counts")
    cases = suite.findall("testcase")
    require(len(cases) == 1, "junit-case-count")
    case = cases[0]
    require(case.get("classname") == MODULE and case.get("name") == name, "junit-case")
    outcomes = [child for child in case if child.tag in {"failure", "skipped", "error"}]
    if expected_failure is None:
        require(not outcomes, "junit-outcome")
    else:
        require(
            len(outcomes) == 1
            and outcomes[0].tag == "failure"
            and outcomes[0].get("message", "").partition("\n")[0]
            == f"AssertionError: {expected_failure}",
            "junit-failure-reason",
        )


def run_case(source: Path, attempt: Path, case: str, expected_failure: str | None = None) -> Path:
    attempt.mkdir()
    report = attempt / "result.xml"
    fixtures = attempt / "test"
    name = NO_WINDOW if case == "no-window" else f"{BOOTSTRAP}[{case}]"
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTHONOPTIMIZE", None)
    env["PYTHONPATH"] = os.pathsep.join((str(source / "src"), str(source)))
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--no-cov",
            "--tb=short",
            "-o",
            "junit_family=xunit2",
            f"--junitxml={report}",
            f"--basetemp={fixtures}",
            f"{TEST.as_posix()}::{name}",
        ],
        cwd=source,
        env=env,
        timeout=75,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    require(completed.returncode == (1 if expected_failure else 0), "pytest-exit")
    junit_check(report, name, expected_failure)
    if case == "no-window":
        return fixtures
    folders = [
        path
        for path in fixtures.iterdir()
        if not path.name.endswith("current") and (path / "owner_pid").is_file()
    ]
    require(len(folders) == 1, "fixture-count")
    return folders[0]


def read(folder: Path, name: str) -> str:
    return (folder / name).read_text(encoding="ascii")


def observation(folder: Path, name: str) -> Any:
    return json.loads(read(folder, name))


def console_observation(
    folder: Path, case: str, *, inherited: bool = False
) -> tuple[int, int, int]:
    owner = int(read(folder, "owner_pid"))
    worker_role = "parse-worker-1" if case.startswith("replacement") else "parse-worker-0"
    probe = observation(folder, worker_role)
    worker = int(probe["pid"])
    guardian = int(observation(folder, "parse-worker-guard")["pid"])
    members = set(observation(folder, "console_pids"))
    require(
        (folder / "send_break").is_file() and read(folder, "stopping") == "interrupt",
        "interrupt-not-observed",
    )
    require(
        len({owner, worker, guardian}) == 3 and owner in members and guardian not in members,
        "console-identities",
    )
    if inherited:
        require(
            len(members) == 3 and worker in members and members == set(probe["console_pids"]),
            "worker-did-not-inherit-console",
        )
    else:
        require(
            len(members) == 2
            and worker not in members
            and not members.intersection(probe["console_pids"]),
            "worker-console-isolation",
        )
    return owner, worker, guardian


def exit_code(folder: Path, pid: int) -> int:
    return int(read(folder, f"exit-{pid}"), 16)


def positive(source: Path, attempt: Path, case: str, *, label: str) -> None:
    folder = run_case(source, attempt, case)
    if case == "no-window":
        print(f"PASS {label} junit=pass visible_descendant_windows=0 parsed_pages=31", flush=True)
        return
    owner, worker, guardian = console_observation(folder, case)
    statuses = exit_code(folder, owner), exit_code(folder, worker), exit_code(folder, guardian)
    require(statuses[0] == 130 and statuses[1] in (0x10000, 15) and statuses[2] == 0, "exit-codes")
    print(
        f"PASS {label} junit=pass members=2 owner={statuses[0]:#x} "
        f"worker={statuses[1]:#x} guardian={statuses[2]:#x}",
        flush=True,
    )


def replace_once(source: Path, file: Path, before: str, after: str) -> None:
    target = source / file
    content = target.read_bytes()
    old = before.encode()
    new = after.encode()
    # Preserve the checked-out newline convention.
    if b"\r\n" in content:
        old, new = old.replace(b"\n", b"\r\n"), new.replace(b"\n", b"\r\n")
    require(content.count(old) == 1, "mutation-anchor")
    target.write_bytes(content.replace(old, new, 1))


def make_worker_inherit_console(source: Path) -> None:
    replace_once(
        source,
        LAUNCH,
        "                    subprocess.CREATE_NO_WINDOW,",
        '                    0 if process_obj.name == "parse-worker-0"'
        " else subprocess.CREATE_NO_WINDOW,",
    )
    # Hold the synthetic owner's stopping callback until the native handle is signaled,
    # so application cleanup cannot win the race against console termination.
    note = '            (self.folder / "stopping").write_text(data["reason"], encoding="ascii")'
    replace_once(
        source,
        FIXTURE,
        note,
        note + '\n            _await_observer(self.folder / "native_kill_seen")',
    )
    anchor = '            (folder / "send_break").touch()'
    replace_once(
        source,
        TEST,
        anchor,
        anchor + "\n            console.exit_status(worker_handle, 5)"
        '\n            (folder / "native_kill_seen").touch()',
    )


def inherit_console(source: Path, attempt: Path) -> None:
    make_worker_inherit_console(source)
    case = "worker-broadcast"
    folder = run_case(source, attempt, case, f"worker exited with {CONSOLE_KILLED:#x}")
    owner, worker, _ = console_observation(folder, case, inherited=True)
    status = exit_code(folder, worker)
    require(
        (folder / "native_kill_seen").is_file()
        and exit_code(folder, owner) == 130
        and status == CONSOLE_KILLED,
        "native-console-kill",
    )
    print(
        f"CONFIRMED inherit-console {case} junit=expected-failure "
        f"members=3 worker_in_console=1 owner=0x82 worker={status:#x}",
        flush=True,
    )


def omit_early_kill(source: Path) -> None:
    anchor = (
        "                    # The engine has already abandoned the Page "
        "or its wait for readiness.\n"
        "                    worker.process.kill()"
    )
    replace_once(source, POOL, "import multiprocessing\n", "import multiprocessing\nimport os\n")
    replace_once(
        source,
        POOL,
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\nfrom pathlib import Path\n",
    )
    replace_once(
        source,
        POOL,
        anchor,
        '                    folder = Path(os.environ["OPENLINX_TEST_SPAWN_FOLDER"])\n'
        '                    (folder / "early_kill_omitted").write_text(\n'
        '                        str(worker.process.pid), encoding="ascii"\n'
        "                    )",
    )


def missed_kill(source: Path, work: Path) -> None:
    case = "worker-targeted"
    # The production fallback starts at 10 s, inside the fixture's 14 s deadline.
    # Move it beyond that deadline in both arms so only the immediate kill differs.
    replace_once(source, POOL, "_SHUTDOWN_GRACE = 10.0", "_SHUTDOWN_GRACE = 20.0")
    positive(source, work / "grace", case, label="extended-grace-control worker-targeted")
    omit_early_kill(source)
    folder = run_case(source, work / "kill", case, "Crawl did not exit after one interrupt")
    _, worker, _ = console_observation(folder, case)
    require(int(read(folder, "early_kill_omitted")) == worker, "early-kill-branch")
    wait, elapsed = deadline_sample(folder, worker)
    print(
        f"CONFIRMED no-early-kill {case} junit=expected-failure "
        f"members=2 same_worker=1 stopping=interrupt wait={wait:#x} "
        f"elapsed_ns={elapsed} deadline_ns={INTERRUPT_DEADLINE_NS}",
        flush=True,
    )


def deadline_sample(folder: Path, worker: int) -> tuple[int, int]:
    sample = observation(folder, "interrupt_timeout.json")
    wait: int = sample["worker_wait"]
    elapsed = int(sample["worker_wait_started_ns"]) - int(sample["stopping_observed_ns"])
    require(
        sample["worker_pid"] == worker
        and sample["stopping"] == "interrupt"
        and wait == WAIT_TIMEOUT
        and elapsed >= INTERRUPT_DEADLINE_NS,
        "worker-deadline-sample",
    )
    return wait, elapsed


def index_copy(target: Path) -> None:
    git = shutil.which("git")
    if git is None:
        raise ProofError("git-unavailable")
    subprocess.run(
        [git, "checkout-index", "--all", f"--prefix={target.as_posix()}/"],
        cwd=ROOT,
        check=True,
        timeout=45,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    label = "environment"
    try:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        require(
            sys.platform == "win32"
            and version in {"3.12", "3.13", "3.14"}
            and version == os.environ.get("EXPECTED_PYTHON"),
            "runner-mismatch",
        )
        sha = os.environ.get("GITHUB_SHA", "")
        require(re.fullmatch(r"[a-f0-9]{40}", sha) is not None, "candidate-sha")
        print(f"PROOF python={version} commit={sha}", flush=True)
        with TemporaryDirectory(prefix="linx-proof-") as temp:
            work = Path(temp)
            for case in CASES:
                label = case
                positive(ROOT, work / case, case, label=label)
            label = "inherit-console"
            index_copy(work / "inherit-src")
            inherit_console(work / "inherit-src", work / "inherit")
            label = "no-early-kill"
            index_copy(work / "kill-src")
            missed_kill(work / "kill-src", work)
        print("PASS windows-interrupt-proof positives=7 matched_control=1 negatives=2", flush=True)
    except ProofError as error:
        print(f"FAIL {label} reason={error}", flush=True)
        return 1
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        ElementTree.ParseError,
        subprocess.SubprocessError,
    ):
        print(f"FAIL {label} reason=probe-or-runner-error", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
