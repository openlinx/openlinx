"""Prove the controlled Windows tree guard by a reversible root-only cleanup mutation."""

import ast
import hashlib
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Never
from xml.parsers import expat

from tests.support.processes import python_command

GUARD = "test_a_console_timeout_ends_the_controlled_process_tree"
TEST_FILE = "tests/cli/test_encoding.py"
SOURCE_FILE = "tests/support/processes.py"
SURVIVOR_ASSERT = (
    "assert [identity.is_running() for identity in identities] == [False, False, False]"
)
MUTATION_FAILURE = "assert [False, True, True] == [False, False, False]"


def _mutated_source(original: bytes) -> bytes:
    tree = ast.parse(original.decode("utf-8"))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_end_console_tree"
    ]
    if len(functions) != 1:
        raise RuntimeError("expected exactly one _end_console_tree function")
    function = functions[0]
    if [arg.arg for arg in function.args.args] != ["process", "root", "timeout"]:
        raise RuntimeError("the cleanup signature changed: review the mutation")
    if function.end_lineno is None:
        raise RuntimeError("the cleanup body has no source extent")
    lines = original.splitlines(keepends=True)
    lines[function.body[0].lineno - 1 : function.end_lineno] = [
        b"    process.kill()\n",
        b"    process.wait(timeout=timeout)\n",
    ]
    mutated = b"".join(lines)
    compile(mutated, SOURCE_FILE, "exec")
    return mutated


def _run_guard(root: Path, report: Path, phase: str) -> subprocess.CompletedProcess[str]:
    command = python_command(
        "-m",
        "pytest",
        f"{TEST_FILE}::{GUARD}",
        "--no-cov",
        "--tb=short",
        "-q",
        "--color=no",
        f"--junitxml={report}",
    )
    completed = subprocess.run(
        command.argv,
        cwd=root,
        env={**os.environ, **(command.env or {}), "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    print(f"{phase}: exit {completed.returncode}\n{completed.stdout}", flush=True)
    return completed


def _case(report: Path) -> ET.Element:
    limit = 1024 * 1024
    with report.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise RuntimeError("the guard report exceeds 1 MiB")
    text = payload.decode("utf-8", errors="strict")
    if "\x00" in text:
        raise RuntimeError("the guard report must not contain NUL")
    upper_text = text.upper()
    if "<!DOCTYPE" in upper_text or "<!ENTITY" in upper_text:
        raise RuntimeError("the guard report must not contain DTD declarations or entities")

    def reject_declaration(*_args: object) -> Never:
        raise RuntimeError("the guard report must not contain DTD declarations or entities")

    builder = ET.TreeBuilder()
    parser = expat.ParserCreate("UTF-8", namespace_separator="}")
    if not parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER):
        raise RuntimeError("the guard parser could not disable parameter entities")
    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_declaration
    parser.SkippedEntityHandler = reject_declaration
    parser.StartElementHandler = builder.start
    parser.EndElementHandler = builder.end
    parser.CharacterDataHandler = builder.data
    parser.Parse(text, True)
    root = builder.close()
    cases = root.findall(".//testcase")
    if (
        len(cases) != 1
        or cases[0].get("name") != GUARD
        or cases[0].get("classname") != "tests.cli.test_encoding"
        or root.findall(".//error")
        or root.findall(".//skipped")
    ):
        raise RuntimeError("proof requires exactly the guard, with no errors or skips")
    return cases[0]


def _require_green(root: Path, report: Path, phase: str) -> None:
    completed = _run_guard(root, report, phase)
    case = _case(report)
    if completed.returncode != 0 or case.findall("failure"):
        raise RuntimeError(f"{phase}: the unmutated guard must pass")


def main() -> None:
    if not hasattr(subprocess, "CREATE_NEW_CONSOLE"):
        raise RuntimeError("Windows runtime is required; a Linux skip is not mutation proof")
    root = Path(__file__).resolve().parents[1]
    source = root / SOURCE_FILE
    original = source.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    assertion_lines = [
        number
        for number, line in enumerate(
            (root / TEST_FILE).read_text(encoding="utf-8").splitlines(), 1
        )
        if line.strip() == SURVIVOR_ASSERT
    ]
    if len(assertion_lines) != 1:
        raise RuntimeError("the survivor assertion changed: review the proof")
    with TemporaryDirectory(prefix="console-cleanup-proof-") as folder:
        reports = Path(folder)
        _require_green(root, reports / "before.xml", "original green")
        try:
            source.write_bytes(_mutated_source(original))
            report = reports / "mutation.xml"
            completed = _run_guard(root, report, "root-only mutation")
            failures = _case(report).findall("failure")
            if len(failures) != 1:
                raise RuntimeError("the mutation must produce exactly one assertion failure")
            failure = failures[0]
            traceback = (failure.text or "").replace("\\", "/")
            if (
                completed.returncode != 1
                or not failure.get("message", "").startswith(MUTATION_FAILURE)
                or f"{TEST_FILE}:{assertion_lines[0]}:" not in traceback
                or "the guard's independent cleanup left a process alive" in traceback
            ):
                raise RuntimeError("mutation did not fail solely at the survivor assertion")
        finally:
            source.write_bytes(original)
            if source.read_bytes() != original:
                raise RuntimeError("the cleanup source was not restored byte for byte")
            print(f"source restored: sha256 {digest}", flush=True)
            _require_green(root, reports / "after.xml", "restored green")
    if source.read_bytes() != original:
        raise RuntimeError("the restored guard run changed the cleanup source")
    print(f"Windows mutation proof passed; unchanged source sha256 {digest}", flush=True)


if __name__ == "__main__":
    main()
