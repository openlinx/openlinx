"""The Crawl's warning log (020-add-crawl-core D10; seam 2)."""

from spider.crawl.urls import NormalizedUrl
from spider.crawl.warning_log import WarningLog
from spider.output.codes import PARSE_FAILED, ROBOTS_UNREACHABLE
from spider.output.diagnostics import Diagnostic
from spider.output.reporter import Collected

_URL = NormalizedUrl("http://site.test/a")


def _unreachable(origin: str, host: str) -> Diagnostic:
    return Diagnostic.of(
        ROBOTS_UNREACHABLE, f"{origin} is unreachable.", details={"origin": origin, "host": host}
    )


def test_a_warning_is_written_once_per_code_and_host() -> None:
    reporter = Collected()
    log = WarningLog(reporter)

    for origin, host in [
        ("http://site.test", "site.test"),
        ("https://site.test", "site.test"),
        ("http://www.site.test", "www.site.test"),
    ]:
        log.warn(_unreachable(origin, host))

    assert (
        [warning.details["origin"] for warning in log.warnings],
        [warning.details["origin"] for warning in reporter.warnings],
    ) == (
        ["http://site.test", "http://www.site.test"],
        ["http://site.test", "http://www.site.test"],
    )


def test_a_counted_warning_of_a_code_already_written_counts_on_that_warning() -> None:
    log = WarningLog(Collected())
    log.warn(Diagnostic.of(PARSE_FAILED, "Preparing a Page gave nothing."))

    log.count(Diagnostic.of(PARSE_FAILED, "Preparing a Page gave nothing."), _URL)

    assert [(warning.code, warning.details["count"]) for warning in log.warnings] == [
        ("parse_failed", 1)
    ]
