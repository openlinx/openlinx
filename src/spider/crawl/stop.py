"""The stop flag of a Crawl: set once, with the stop_reason it ends with (020 D10)."""

from spider.store.records import StopReason


class StopSignal:
    def __init__(self) -> None:
        self._reason: StopReason | None = None
        self._cause: BaseException | None = None

    @property
    def is_set(self) -> bool:
        return self._reason is not None

    @property
    def reason(self) -> StopReason | None:
        return self._reason

    @property
    def cause(self) -> BaseException | None:
        """The error that set it, for write_failed."""
        return self._cause

    def set(self, reason: StopReason, cause: BaseException | None = None) -> None:
        """Only the first stop counts: the Crawl ends for that reason."""
        if self._reason is None:
            self._reason, self._cause = reason, cause
