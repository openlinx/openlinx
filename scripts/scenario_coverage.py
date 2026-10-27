"""Checks that every scenario of a spec has exactly one test named after it (docs/testing.md).

A check that is run, never a test, since a scenario of a later version has no test yet:

    uv run python scripts/scenario_coverage.py openspec/changes/<change>/specs/<capability>/spec.md

A scenario's test is `test_` and its title in snake case, so "A cookie value is not stored" is
`test_a_cookie_value_is_not_stored`; the tests are the ids of `pytest --collect-only`. A
scenario is waiting, not missing, when its requirement opens with **(vX.Y)**, or when the
change's tasks.md names it in a group whose heading carries (vX.Y). It prints each scenario as
`covered`, `waiting`, `missing` or `twice`, with the task of tasks.md that names it in quotes,
or `-`; a missing one also gets any test whose name is close to it, as a renamed scenario leaves
behind. Then a count of each. It exits 1 when a scenario is missing or has more than one test.
"""

import argparse
import difflib
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

SCENARIO = re.compile(r"^#### Scenario: (.+?)\s*$")
REQUIREMENT = re.compile(r"^### Requirement: ")
# A requirement of a later version opens with its version in bold.
LATER_REQUIREMENT = re.compile(r"^\*\*\(v\d+\.\d+\)\*\*")
LATER_GROUP = re.compile(r"^## .*\(v\d+\.\d+\)")
TASK_GROUP = re.compile(r"^## ")
TASK = re.compile(r"^- \[[ x]\] (\d+\.\d+[a-z]?) ")
QUOTED = re.compile(r'"([^"]+)"')
CLOSE = 0.8


@dataclass(frozen=True)
class Scenario:
    title: str
    later: bool

    @property
    def test_name(self) -> str:
        return "test_" + snake_case(self.title)


def snake_case(title: str) -> str:
    # Every run of other characters is one _, an apostrophe too: "image's" is image_s.
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def scenarios(spec: Path) -> list[Scenario]:
    found: list[Scenario] = []
    later = False
    expecting_body = False
    for line in spec.read_text(encoding="utf-8").splitlines():
        if REQUIREMENT.match(line):
            later, expecting_body = False, True
            continue
        if expecting_body and line.strip():
            later, expecting_body = bool(LATER_REQUIREMENT.match(line)), False
        if match := SCENARIO.match(line):
            found.append(Scenario(match.group(1), later))
    return found


@dataclass(frozen=True)
class Tasks:
    # The first task that names each title in quotes.
    task_of: dict[str, str]
    # The titles that a later-version group names.
    later: set[str]


def tasks_of(spec: Path) -> Tasks:
    # openspec/changes/<change>/specs/<capability>/spec.md
    tasks = spec.parents[2] / "tasks.md"
    found = Tasks({}, set())
    if not tasks.is_file():
        return found
    in_later, task = False, None
    for line in tasks.read_text(encoding="utf-8").splitlines():
        if TASK_GROUP.match(line):
            in_later, task = bool(LATER_GROUP.match(line)), None
            continue
        if match := TASK.match(line):
            task = match.group(1)
        # An indented line belongs to the task above it.
        elif not line.startswith(" "):
            task = None
        if task is None:
            continue
        for title in QUOTED.findall(line):
            found.task_of.setdefault(title, task)
            if in_later:
                found.later.add(title)
    return found


def test_names(root: Path) -> list[str]:
    """Each test function once per module, parametrised ones too."""
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-cov"]
    collected = subprocess.run(
        [*command, "-p", "no:cacheprovider"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    ids = {line.split("[")[0] for line in collected.splitlines() if "::" in line}
    return [test_id.rsplit("::", 1)[1] for test_id in sorted(ids)]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, help="a spec.md with #### Scenario: headings")
    spec = parser.parse_args(argv).spec.resolve()
    root = Path(__file__).resolve().parents[1]
    tasks = tasks_of(spec)
    names = test_names(root)
    counts = Counter(names)
    totals: Counter[str] = Counter()
    for scenario in scenarios(spec):
        count = counts[scenario.test_name]
        if count == 1:
            state = "covered"
        elif count > 1:
            state = "twice"
        elif scenario.later or scenario.title in tasks.later:
            state = "waiting"
        else:
            state = "missing"
        totals[state] += 1
        line = f"{state:<8} {tasks.task_of.get(scenario.title, '-'):<6} {scenario.title}"
        if state == "missing":
            close = difflib.get_close_matches(scenario.test_name, names, n=3, cutoff=CLOSE)
            line += f"  (close: {', '.join(close)})" if close else ""
        print(line)
    states = ("covered", "waiting", "missing", "twice")
    print(", ".join(f"{totals[state]} {state}" for state in states))
    return 1 if totals["missing"] or totals["twice"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
