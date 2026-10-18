"""The security Rule (040-add-rules D3, D4)."""

from spider.rules.model import Rule

_HTTP_URL_SQL = """SELECT id AS url_id, json_object('status_code', status_code) AS detail
FROM urls JOIN internal_urls ON internal_urls.url_id = urls.id
WHERE url LIKE 'http://%' AND status_code BETWEEN 200 AND 299"""

# A Warning: a site may mean to serve plain HTTP, and only definite defects lower the Health
# Score (D3).
HTTP_URL = Rule(
    id="http-url",
    category="security",
    issue_type="warning",
    priority="high",
    population="internal_urls",
    description="An Internal URL serves its content over plain HTTP.",
    why_it_matters=(
        "Anyone on the network path can read or change what plain HTTP carries, browsers mark "
        "such pages as not secure, and search engines prefer the HTTPS version of a page."
    ),
    how_to_fix=(
        "Serve the site over HTTPS, redirect every HTTP URL to its HTTPS URL with a 301, and "
        "link to the HTTPS URLs."
    ),
    reproduce_sql=_HTTP_URL_SQL,
)

RULES = (HTTP_URL,)
