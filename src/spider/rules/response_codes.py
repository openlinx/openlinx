"""The response_codes Rules (040-add-rules D3, D4)."""

from spider.rules.model import Rule

_INTERNAL_4XX_SQL = """SELECT id AS url_id, json_object('status_code', status_code) AS detail
FROM urls JOIN internal_urls ON internal_urls.url_id = urls.id
WHERE fetch_state = 'fetched' AND status_code BETWEEN 400 AND 499"""
_INTERNAL_5XX_SQL = """SELECT id AS url_id, json_object('status_code', status_code) AS detail
FROM urls JOIN internal_urls ON internal_urls.url_id = urls.id
WHERE fetch_state = 'fetched' AND status_code BETWEEN 500 AND 599"""
_INTERNAL_NO_RESPONSE_SQL = """SELECT id AS url_id, json_object('error', fetch_error) AS detail
FROM urls JOIN internal_urls ON internal_urls.url_id = urls.id
WHERE fetch_state = 'error'
  -- record_failed: the Crawl got a response and failed to record it. That is the tool's
  -- failure, which the record_failed warning reports, not the site's.
  AND fetch_error <> 'record_failed'"""

_INTERNAL_BLOCKED_BY_ROBOTS_TXT_SQL = """SELECT id AS url_id, NULL AS detail
FROM urls JOIN internal_urls ON internal_urls.url_id = urls.id
WHERE blocked_by_robots_txt = 1"""

INTERNAL_4XX = Rule(
    id="internal-4xx",
    category="response_codes",
    issue_type="issue",
    priority="high",
    population="internal_urls",
    description="An Internal URL responded with a client error, a status code from 400 to 499.",
    why_it_matters=(
        "Visitors and search engines that follow a link to the URL reach an error instead of "
        "content, and the links that point to it lead nowhere."
    ),
    how_to_fix=(
        "Restore the content, redirect the URL with a 301 to the closest equivalent page, or "
        "change the links that point to it. Answer 410 only for content that is gone for good."
    ),
    reproduce_sql=_INTERNAL_4XX_SQL,
)
INTERNAL_5XX = Rule(
    id="internal-5xx",
    category="response_codes",
    issue_type="issue",
    priority="high",
    population="internal_urls",
    description="An Internal URL responded with a server error, a status code from 500 to 599.",
    why_it_matters=(
        "The server failed to deliver the page. Search engines crawl a site that answers with "
        "server errors more slowly, and drop pages that keep failing from their index."
    ),
    how_to_fix=(
        "Find the failure in the server's error log for the URL, fix it, then request the URL "
        "again. A 503 during maintenance should carry a Retry-After header."
    ),
    reproduce_sql=_INTERNAL_5XX_SQL,
)
INTERNAL_NO_RESPONSE = Rule(
    id="internal-no-response",
    category="response_codes",
    issue_type="issue",
    priority="high",
    population="internal_urls",
    description=(
        "An Internal URL got no HTTP response: a timeout, a DNS, connection or TLS error, an "
        "answer that was no valid HTTP, or its site's robots.txt got no response so it was "
        "not requested."
    ),
    why_it_matters=(
        "Visitors and search engines that follow a link to the URL get nothing at all, and a "
        "site that often fails to answer is crawled less."
    ),
    how_to_fix=(
        "Look up the reason in detail.error: timeout or watchdog points to a slow page or "
        "server, connection_refused or connection_error to a server that is down, dns_error or "
        "tls_error to the domain's set-up, invalid_response to a broken server. Fix it, then "
        "request the URL again."
    ),
    reproduce_sql=_INTERNAL_NO_RESPONSE_SQL,
)

INTERNAL_BLOCKED_BY_ROBOTS_TXT = Rule(
    id="internal-blocked-by-robots-txt",
    category="response_codes",
    issue_type="warning",
    priority="medium",
    population="internal_urls",
    description="robots.txt disallows an Internal URL, whether or not the Crawl fetched it anyway.",
    why_it_matters=(
        "Search engines that obey robots.txt do not crawl the URL, so they cannot read "
        "its content, and a page they cannot read rarely ranks."
    ),
    how_to_fix=(
        "If the URL should be found in search, remove the Disallow rule that matches it "
        "from robots.txt. If it should not, keep the rule and stop linking to it."
    ),
    reproduce_sql=_INTERNAL_BLOCKED_BY_ROBOTS_TXT_SQL,
)

RULES = (INTERNAL_4XX, INTERNAL_5XX, INTERNAL_NO_RESPONSE, INTERNAL_BLOCKED_BY_ROBOTS_TXT)
