"""Runs of blocking responses belong to the engine's warnings (020-add-crawl-core D7)."""

# Consecutive 403 and 429 responses of one host before the warning that it may be blocking.
BLOCKING_RUN = 10
_BLOCKING_STATUSES = frozenset({403, 429})


class BlockingRuns:
    """The run of consecutive 403 and 429 responses of each Internal host, in the order
    they complete."""

    def __init__(self) -> None:
        self._runs: dict[str, int] = {}

    def responded(self, host: str, status_code: int | None) -> bool:
        """Whether the host's run has just reached BLOCKING_RUN; a request without an HTTP
        response, None, leaves the run as it is."""
        if status_code is None:
            return False
        run = self._runs.get(host, 0) + 1 if status_code in _BLOCKING_STATUSES else 0
        self._runs[host] = run
        return run == BLOCKING_RUN
