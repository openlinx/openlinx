"""Require all native Windows bootstrap owner-death cases in a pytest JUnit report."""

from pathlib import Path
from sys import argv
from xml.etree import ElementTree

_MODULE = "tests.crawl.test_parse_process_tree"
_TEST = "test_a_second_ctrl_break_ends_the_parse_tree_during_windows_bootstrap"
_CASES = {
    f"{_TEST}[{phase}-{delivery}]"
    for phase in ("worker", "replacement", "guardian")
    for delivery in ("targeted", "broadcast")
}


def check_report(report: Path) -> None:
    # The CI test step writes this report from its own pytest run.
    root = ElementTree.parse(report).getroot()  # noqa: S314
    counts = dict.fromkeys(_CASES, 0)
    failed = set()
    observations = {}
    for case in root.iter("testcase"):
        name = case.get("name", "")
        if case.get("classname") != _MODULE or name not in counts:
            continue
        counts[name] += 1
        if any(child.tag in {"skipped", "failure", "error"} for child in case):
            failed.add(name)
        observation = case.find("properties/property[@name='windows_bootstrap_processes']")
        if observation is not None and (value := observation.get("value")):
            observations[name] = value

    problems = []
    for name in sorted(_CASES):
        snapshot = observations.get(name)
        if snapshot is not None:
            print(f"OBSERVED {name} {snapshot}")
        if counts[name] != 1 or name in failed or snapshot is None:
            status = "unsuccessful" if name in failed else "no error"
            presence = "present" if snapshot is not None else "missing"
            problems.append(f"{name}: {counts[name]} reports, {status}, snapshot {presence}")
        else:
            print(f"PASS {name} junit=pass")
    if problems:
        raise SystemExit(
            "Windows 4.2c requires one observed pass per case:\n" + "\n".join(problems)
        )
    print("PASS windows-bootstrap-owner-death cases=6")


if __name__ == "__main__":
    check_report(Path(argv[1]))
