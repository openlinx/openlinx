"""The response_codes Rules (040-add-rules D3, D4)."""

from spider.rules.model import NO_ROWS, Rule

_INTERNAL_4XX_SQL = """SELECT id AS url_id, json_object('status_code', status_code) AS detail
FROM urls
WHERE status_code BETWEEN 400 AND 499"""

INTERNAL_4XX = Rule(
    id="internal-4xx",
    category="response_codes",
    issue_type="issue",
    priority="high",
    applies_to="internal_urls",
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
    applies_to="internal_urls",
    description="An Internal URL responded with a server error, a status code from 500 to 599.",
    why_it_matters=(
        "The server failed to deliver the page. Search engines crawl a site that answers with "
        "server errors more slowly, and drop pages that keep failing from their index."
    ),
    how_to_fix=(
        "Find the failure in the server's error log for the URL, fix it, then request the URL "
        "again. A 503 during maintenance should carry a Retry-After header."
    ),
    reproduce_sql=NO_ROWS,
)

RULES = (INTERNAL_4XX, INTERNAL_5XX)
