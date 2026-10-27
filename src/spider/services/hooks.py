"""A Crawl's hooks, composed here: the crawl core never imports them (020-add-crawl-core D9)."""

from spider.crawl.engine.hooks import Hooks, UrlResult, handler
from spider.crawl.pages.preparation import InProcessExecutor, PageExecutor
from spider.store.records import ResponseHeaders
from spider.store.response_headers import write_response_headers


def default_hooks() -> Hooks:
    """The built-in hooks, listed explicitly: 030 and 040 add theirs here."""
    return Hooks(handlers=(handler("response_headers", _response_headers, write_response_headers),))


def _response_headers(result: UrlResult) -> tuple[ResponseHeaders, ...]:
    """The headers of the URL's response; none for a URL that got no response."""
    if result.response is None:
        return ()
    return (ResponseHeaders(url_id=result.url_id, headers=result.response.headers),)


def default_page_executor() -> PageExecutor:
    """Where Pages are prepared: in process here, 026's process pool later."""
    return InProcessExecutor()
