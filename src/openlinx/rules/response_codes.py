"""Declare the Rules for HTTP response codes."""

from openlinx.rules.model import Rule

INTERNAL_4XX = Rule(
    id="internal-4xx",
    category="response_codes",
    issue_type="issue",
    priority="high",
    applies_to="internal_urls",
    description="An Internal URL responded with a client error, a status code from 400 to 499.",
    why_it_matters=(
        "Visitors and search engines that follow a Link to the URL reach an error instead of "
        "content, and the Links that point to it lead nowhere."
    ),
    how_to_fix=(
        "Restore the content, redirect the URL with a 301 to the closest equivalent Page, or "
        "change the Links that point to it. Answer 410 only for content that is gone for good."
    ),
    reproduce_sql="""\
SELECT id AS url_id, json_object('status_code', status_code) AS detail
FROM urls
WHERE is_internal = 1 AND fetch_state IN ('fetched', 'error')
  AND status_code BETWEEN 400 AND 499""",
)
INTERNAL_5XX = Rule(
    id="internal-5xx",
    category="response_codes",
    issue_type="issue",
    priority="high",
    applies_to="internal_urls",
    description="An Internal URL responded with a server error, a status code from 500 to 599.",
    why_it_matters=(
        "The server failed to deliver the requested content. Search engines crawl a site that "
        "answers with server errors more slowly, and drop URLs that keep failing from their index."
    ),
    how_to_fix=(
        "Find the failure in the server's error log for the URL, fix it, then request the URL "
        "again. A 503 during maintenance should carry a Retry-After header."
    ),
    reproduce_sql="""\
SELECT id AS url_id, json_object('status_code', status_code) AS detail
FROM urls
WHERE is_internal = 1 AND fetch_state IN ('fetched', 'error')
  AND status_code BETWEEN 500 AND 599""",
)

INTERNAL_NO_RESPONSE = Rule(
    id="internal-no-response",
    category="response_codes",
    issue_type="issue",
    priority="high",
    applies_to="internal_urls",
    description="An Internal URL got no HTTP response.",
    why_it_matters=(
        "Visitors and search engines cannot reach the content. Repeated failures can "
        "reduce how often a search engine crawls the site."
    ),
    how_to_fix=(
        "Check detail.error and the server logs. For a timeout, check response times. "
        "For DNS, connection or TLS errors, check the host and its network configuration."
    ),
    reproduce_sql="""\
SELECT id AS url_id, json_object('error', fetch_error) AS detail
FROM urls
WHERE is_internal = 1 AND fetch_state = 'error'""",
)

RULES = (INTERNAL_4XX, INTERNAL_5XX, INTERNAL_NO_RESPONSE)
