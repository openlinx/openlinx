"""Declare the Rule for successful responses from Internal HTTP URLs."""

from openlinx.rules.model import Rule

HTTP_URL = Rule(
    id="http-url",
    category="security",
    issue_type="warning",
    priority="high",
    applies_to="internal_urls",
    description="An Internal URL using plain HTTP responded with a status code from 200 to 299.",
    why_it_matters=(
        "Plain HTTP leaves responses exposed to interception and modification in transit."
    ),
    how_to_fix=(
        "Serve the content over HTTPS with a valid certificate, redirect the HTTP URL "
        "to its HTTPS equivalent with a 301, and update Inlinks to point directly to HTTPS."
    ),
    reproduce_sql="""\
SELECT id AS url_id, json_object('status_code', status_code) AS detail
FROM urls
WHERE is_internal = 1
  AND (fetch_state IN ('fetched', 'error') OR blocked_by_robots_txt = 1)
  AND url GLOB 'http://*'
  AND status_code BETWEEN 200 AND 299""",
)

RULES = (HTTP_URL,)
