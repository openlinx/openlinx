"""Declare the Rules for Page canonicals."""

from openlinx.rules.model import Rule

CANONICAL_TO_NON_INDEXABLE = Rule(
    id="canonical-to-non-indexable",
    category="canonicals",
    issue_type="issue",
    priority="high",
    applies_to="internal_pages",
    description="A Page declares a Non-Indexable canonical URL.",
    why_it_matters="Search engines cannot index that URL as the preferred version of the Page.",
    how_to_fix="Point the canonical declaration directly to the preferred, Indexable URL.",
    reproduce_sql="""\
WITH canonical_targets AS (
    SELECT source_page.url_id, source_page.canonical_url,
           CASE
               -- A Page already has its Indexability, including any directive reason.
               WHEN target_page.url_id IS NOT NULL THEN
                   CASE WHEN target_page.indexability = 'non_indexable'
                        THEN target_page.indexability_status END
               WHEN target_url.blocked_by_robots_txt = 1 THEN 'blocked_by_robots_txt'
               WHEN target_url.status_code BETWEEN 300 AND 399 THEN 'redirected'
               WHEN target_url.status_code BETWEEN 400 AND 499 OR target_url.status_code >= 600
                   THEN 'client_error'
               WHEN target_url.status_code BETWEEN 500 AND 599 THEN 'server_error'
               WHEN target_url.fetch_state = 'error'
                    -- A robots.txt preflight error leaves zero attempts on the target URL.
                    AND target_url.attempt_count > 0
                    -- record_failed describes a Store write failure even with real attempts.
                    AND target_url.fetch_error <> 'record_failed' THEN 'no_response'
           END AS target_reason
    FROM pages AS source_page
    JOIN urls AS source_url ON source_url.id = source_page.url_id
    JOIN urls AS target_url ON target_url.url = source_page.canonical_url
    LEFT JOIN pages AS target_page ON target_page.url_id = target_url.id
    WHERE source_url.parsed = 1
      -- A self-canonical identifies this Page as preferred. This Rule checks other URLs.
      AND source_page.canonical_url <> source_url.url
)
SELECT url_id, json_object('canonical_url', canonical_url, 'target_reason', target_reason) AS detail
FROM canonical_targets
WHERE target_reason IS NOT NULL""",
)

RULES = (CANONICAL_TO_NON_INDEXABLE,)
