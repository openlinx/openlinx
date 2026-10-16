"""What crosses a parse worker's result pipe for a Page (design D3 of 026-add-parse-pool)."""

import pickle
from contextlib import suppress
from typing import Any

import msgspec

from spider.crawl.pages import PreparedPage

# The PreparedPage, or the exception prepare_page raised, which in-process reaches the engine.
type Outcome = PreparedPage | BaseException
# What crosses for a PreparedPage: the Page without its outputs, and each output's pickle.
type _Sent = tuple[PreparedPage, tuple[tuple[str, bytes], ...]]


def encode_outcome(outcome: Outcome) -> bytes:
    """What a worker sends: whatever cannot cross to the crawl process costs only itself."""
    if isinstance(outcome, PreparedPage):
        try:
            return pickle.dumps(_sendable(outcome), pickle.HIGHEST_PROTOCOL)
        # That one Page's failure, as a record the crawl process cannot read is (design D3).
        except Exception as error:
            message = f"The parse worker could not send the Page's record: {type(error).__name__}"
            crashed: _Sent = (crashed_page(message), ())
            return pickle.dumps(crashed, pickle.HIGHEST_PROTOCOL)
    with suppress(Exception):
        return pickle.dumps(outcome, pickle.HIGHEST_PROTOCOL)
    return pickle.dumps(RuntimeError(f"{type(outcome).__name__}: {outcome}"))


def _sendable(page: PreparedPage) -> _Sent:
    """The Page without its outputs, and each output pickled by itself (design D3)."""
    outputs: list[tuple[str, bytes]] = []
    failures: list[str] = []
    for name, output in page.outputs:
        try:
            outputs.append((name, pickle.dumps(output, pickle.HIGHEST_PROTOCOL)))
        except Exception as error:
            failures.append(f"{name}: {type(error).__name__}")
    return _with_failures(page, failures, ()), tuple(outputs)


def decode_outcome(message: bytes) -> Outcome:
    try:
        return _received(message)
    # A Page whose own record this process cannot read is that one Page's failure (design D3).
    except Exception as error:
        return crashed_page(
            "The Page's record from its parse worker could not be read: "
            f"{type(error).__name__}: {error}"
        )


def crashed_page(message: str) -> PreparedPage:
    """Nothing came out of the Page's preparation: 020 records it with parsed = 0."""
    return PreparedPage(parse_error="worker_crashed", parse_error_message=message)


def _received(message: bytes) -> Outcome:
    # From our own worker over a pipe of its own, as multiprocessing's recv() would unpickle it.
    sent: _Sent | BaseException = pickle.loads(message)  # noqa: S301
    if isinstance(sent, BaseException):
        return sent
    page, outputs = sent
    kept: list[tuple[str, msgspec.Struct]] = []
    failures: list[str] = []
    for name, data in outputs:
        try:
            kept.append((name, pickle.loads(data)))  # noqa: S301
        # Such as an output whose class cannot be rebuilt in this process.
        except Exception as error:
            failures.append(f"{name}: {type(error).__name__}")
    return _with_failures(page, failures, tuple(kept))


def _with_failures(
    page: PreparedPage, failures: list[str], outputs: tuple[tuple[str, Any], ...]
) -> PreparedPage:
    """In process an output would reach its handler; one that cannot cross fails as its
    extractor would (020 D16), and the Page keeps its Links."""
    if not failures:
        return msgspec.structs.replace(page, outputs=outputs)
    messages = [page.parse_error_message] if page.parse_error_message else []
    return msgspec.structs.replace(
        page,
        outputs=outputs,
        parse_error="extractor_error",
        parse_error_message="; ".join([*messages, *failures]),
    )
