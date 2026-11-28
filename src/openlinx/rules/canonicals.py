"""Declare the Rules for Page canonicals."""

from openlinx.rules.model import Rule

CANONICAL_MISSING = Rule(
    id="canonical-missing",
    category="canonicals",
    issue_type="warning",
    priority="medium",
    applies_to="internal_pages",
    description="An analysed Page has no canonical declaration and no noindex directive.",
    why_it_matters="A canonical declaration tells search engines which URL you prefer to index.",
    how_to_fix="Declare the preferred, Indexable URL, using this Page's URL if it is preferred.",
    reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  AND pages.canonical_count = 0
  -- A Page already marked noindex does not need to name a preferred URL.
  AND pages.meta_robots_noindex = 0
  AND pages.x_robots_tag_noindex = 0""",
)

CANONICALISED = Rule(
    id="canonicalised",
    category="canonicals",
    issue_type="warning",
    priority="medium",
    applies_to="internal_pages",
    description="An analysed Page is Non-Indexable because it declares another URL as canonical.",
    why_it_matters=(
        "Search engines are directed to consider the other URL for indexing in place of this Page."
    ),
    how_to_fix="Confirm the preferred URL. If this Page should be indexed, make it self-canonical.",
    reproduce_sql="""\
SELECT pages.url_id, json_object('canonical_url', pages.canonical_url) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  -- The recorded reason already excludes self-canonicals and higher-priority reasons.
  AND pages.indexability_status = 'canonicalised'
  AND pages.canonical_url IS NOT NULL""",
)

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

CANONICAL_CONFLICTING = Rule(
    id="canonical-conflicting",
    category="canonicals",
    issue_type="issue",
    priority="high",
    applies_to="internal_pages",
    description="An analysed Page declares two or more conflicting canonicals.",
    why_it_matters="Conflicting declarations make the preferred URL ambiguous for search engines.",
    how_to_fix="Choose one preferred, Indexable URL and make the HTML and HTTP declarations agree.",
    reproduce_sql="""\
SELECT pages.url_id,
       json_object('canonical_link_element_1', pages.canonical_link_element_1,
                   'canonical_link_element_2', pages.canonical_link_element_2,
                   'http_canonical', pages.http_canonical) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  -- Two or more declarations leave the preferred URL NULL when their targets disagree.
  AND pages.canonical_count >= 2
  AND pages.canonical_url IS NULL""",
)

CANONICAL_RELATIVE = Rule(
    id="canonical-relative",
    category="canonicals",
    issue_type="warning",
    priority="low",
    applies_to="internal_pages",
    description="An analysed Page declares a canonical using a relative URL.",
    why_it_matters="A relative canonical can resolve to the wrong URL if the Page's base changes.",
    how_to_fix="Use an absolute URL with the scheme and host of the preferred URL.",
    reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.canonical_relative = 1""",
)

RULES = (
    CANONICAL_MISSING,
    CANONICALISED,
    CANONICAL_TO_NON_INDEXABLE,
    CANONICAL_CONFLICTING,
    CANONICAL_RELATIVE,
)
