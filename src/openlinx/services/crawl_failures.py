"""The errors that a failed Crawl ends with (020-add-crawl-core D16)."""

from collections.abc import Callable, Mapping

from openlinx.crawl.engine.outcomes import RecordingFailedError
from openlinx.crawl.engine.pause import pause_after
from openlinx.crawl.settings import CrawlSettings
from openlinx.crawl.urls import NormalizedUrl, url_origin
from openlinx.naming import COMMAND_NAME, PRODUCT_NAME
from openlinx.output.codes import (
    CRAWL_WRITE_FAILED,
    INTERRUPTED,
    SEED_UNREACHABLE,
    SITE_UNREACHABLE,
)
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.failures import write_failure_cause
from openlinx.store.records import CrawlFile, StopReason


def _seed_unreachable(
    seed: NormalizedUrl, settings: CrawlSettings, crawl_file: CrawlFile
) -> OpenLinxError:
    wait = settings.network_wait
    return OpenLinxError(
        SEED_UNREACHABLE,
        f"The Seed {seed} got no HTTP response, and its origin did not answer within "
        f"--network-wait {wait}, so the Crawl ended failed.",
        hint=f"The Crawl waited {wait} seconds. Check that this machine can reach "
        f"{url_origin(seed)}: an agent's sandbox often blocks network access, so allow it, or "
        "run the Command outside the sandbox. Raise --network-wait for a network that is still "
        f"coming up. Then continue it with: {_resume(crawl_file)}",
        details={"seed": seed, "network_wait": wait},
    )


def _site_unreachable(
    _seed: NormalizedUrl, settings: CrawlSettings, crawl_file: CrawlFile
) -> OpenLinxError:
    wait = settings.network_wait
    return OpenLinxError(
        SITE_UNREACHABLE,
        f"{pause_after(settings.concurrency)} requests in a row to the site got no HTTP "
        f"response, and it did not answer within --network-wait {wait}, so the Crawl ended "
        "failed.",
        hint=f"The Crawl waited {wait} seconds. Check the network access to the site, then "
        f"continue it with: {_resume(crawl_file)}",
        details={"network_wait": wait},
    )


# The network's stop reasons, which end the Crawl through its own writer.
NETWORK_FAILURES: Mapping[
    StopReason, Callable[[NormalizedUrl, CrawlSettings, CrawlFile], OpenLinxError]
] = {
    "seed_unreachable": _seed_unreachable,
    "site_unreachable": _site_unreachable,
}


def write_failed(crawl_file: CrawlFile, cause: BaseException | None) -> OpenLinxError:
    # A file another connection holds is reported as the writer raised it (exit 5).
    if isinstance(cause, OpenLinxError):
        return cause
    if cause is not None:
        cause = write_failure_cause(cause)
    error = f"{type(cause).__name__}: {cause}"
    details = {"crawl_file": str(crawl_file.path), "error": error}
    if isinstance(cause, RecordingFailedError):
        # Rows that fail for one URL after another are a bug, which free space would not fix.
        return OpenLinxError(
            CRAWL_WRITE_FAILED,
            f"{cause}, so the Crawl ended failed.",
            hint="Rows that fail for one URL after another come from a bug in a handler or in "
            f"{PRODUCT_NAME} itself: the record_failed warning names the first URL. Once it is "
            f"fixed, continue the Crawl with: {_resume(crawl_file)}",
            details=details,
        )
    return OpenLinxError(
        CRAWL_WRITE_FAILED,
        f"Writing the crawl file failed, so the Crawl ended failed: {error.rstrip('.')}.",
        hint="Free disk space or fix the file system, then continue it with: "
        f"{_resume(crawl_file)}",
        details=details,
    )


def interrupted(crawl_file: CrawlFile) -> OpenLinxError:
    # 010's own text names Ctrl+C, which is wrong for Ctrl+Break and SIGTERM, and no way on.
    return OpenLinxError(
        INTERRUPTED,
        "The Crawl stopped on an interrupt; what it recorded is kept.",
        hint=f"Continue it with: {_resume(crawl_file)}",
        details={"crawl_file": str(crawl_file.path)},
    )


def _resume(crawl_file: CrawlFile) -> str:
    return f"{COMMAND_NAME} resume --crawl {crawl_file.id}"
