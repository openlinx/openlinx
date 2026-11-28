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
    for case in root.iter("testcase"):
        name = case.get("name", "")
        if case.get("classname") != _MODULE or name not in counts:
            continue
        counts[name] += 1
        if any(child.tag in {"skipped", "failure", "error"} for child in case):
            failed.add(name)

    problems = [
        f"{name}: {counts[name]} reports, {'unsuccessful' if name in failed else 'no error'}"
        for name in sorted(_CASES)
        if counts[name] != 1 or name in failed
    ]
    if problems:
        raise SystemExit("Windows 4.2c requires one pass per case:\n" + "\n".join(problems))
    for name in sorted(_CASES):
        print(f"PASS {name} junit=pass")
    print("PASS windows-bootstrap-owner-death cases=6")


if __name__ == "__main__":
    check_report(Path(argv[1]))
