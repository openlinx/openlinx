"""Every runtime dependency is reviewed (design D14 of 000-scaffold-project)."""

from fnmatch import fnmatchcase
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ALLOWLIST = Path(__file__).with_name("dependency_allowlist.txt")
TELEMETRY_AND_LLM_SDKS = (
    "openai",
    "anthropic",
    "google-generativeai",
    "google-genai",
    "langchain*",
    "litellm",
    "sentry-sdk",
    "posthog",
    "mixpanel",
    "analytics-python",
    "segment-analytics-python",
    "amplitude-analytics",
    "opentelemetry-*",
    "datadog",
    "ddtrace",
    "newrelic",
    "rollbar",
    "bugsnag",
    "logfire",
)


def runtime_dependencies() -> set[str]:
    found: set[str] = set()
    to_walk = ["spider"]
    while to_walk:
        for line in metadata.requires(to_walk.pop()) or []:
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            name = canonicalize_name(requirement.name)
            if name not in found:
                found.add(name)
                to_walk.append(name)
    return found


def allowlisted() -> set[str]:
    lines = ALLOWLIST.read_text(encoding="utf-8").splitlines()
    names = (line.partition("#")[0].strip() for line in lines)
    return {canonicalize_name(name) for name in names if name}


def test_every_runtime_dependency_is_allowlisted() -> None:
    assert sorted(runtime_dependencies() - allowlisted()) == []


def test_no_telemetry_or_llm_sdk_is_a_runtime_dependency() -> None:
    denied = [
        name
        for name in runtime_dependencies()
        if any(fnmatchcase(name, pattern) for pattern in TELEMETRY_AND_LLM_SDKS)
    ]

    assert denied == []
