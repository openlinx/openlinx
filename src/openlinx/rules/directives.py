"""Declare the Rules for Page directives."""

from openlinx.rules.model import Rule

NOINDEX = Rule(
    id="noindex",
    category="directives",
    issue_type="warning",
    priority="high",
    applies_to="internal_pages",
    description="An analysed Page has a noindex directive in meta robots or X-Robots-Tag.",
    why_it_matters="The directive asks search engines to exclude the Page from search results.",
    how_to_fix=(
        "If the Page should be Indexable, remove the indexing restriction from each source "
        "listed in detail.sources."
    ),
    reproduce_sql="""\
SELECT pages.url_id,
       json_object('sources', CASE
           WHEN pages.meta_robots_noindex = 1 AND pages.x_robots_tag_noindex = 1
               THEN json_array('meta_robots', 'x_robots_tag')
           WHEN pages.meta_robots_noindex = 1 THEN json_array('meta_robots')
           ELSE json_array('x_robots_tag')
       END) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  AND (pages.meta_robots_noindex = 1 OR pages.x_robots_tag_noindex = 1)""",
)

NOFOLLOW = Rule(
    id="nofollow",
    category="directives",
    issue_type="warning",
    priority="medium",
    applies_to="internal_pages",
    description="An analysed Page has a nofollow directive in meta robots or X-Robots-Tag.",
    why_it_matters="The directive asks search engines to avoid following Links from this Page.",
    how_to_fix=(
        "If search engines should follow Links from the Page, remove nofollow from each "
        "source listed in detail.sources."
    ),
    reproduce_sql="""\
SELECT pages.url_id,
       json_object('sources', CASE
           WHEN pages.meta_robots_nofollow = 1 AND pages.x_robots_tag_nofollow = 1
               THEN json_array('meta_robots', 'x_robots_tag')
           WHEN pages.meta_robots_nofollow = 1 THEN json_array('meta_robots')
           ELSE json_array('x_robots_tag')
       END) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  AND (pages.meta_robots_nofollow = 1 OR pages.x_robots_tag_nofollow = 1)""",
)

META_REFRESH = Rule(
    id="meta-refresh",
    category="directives",
    issue_type="warning",
    priority="low",
    applies_to="internal_pages",
    description="An analysed Page has an HTML meta refresh directive.",
    why_it_matters="Timed redirects and reloads can interrupt people reading or interacting.",
    how_to_fix="Use an HTTP redirect for moved content. Remove an unnecessary timed reload.",
    reproduce_sql="""\
SELECT pages.url_id,
       json_object('meta_refresh', pages.meta_refresh, 'redirect_url', pages.redirect_url) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.meta_refresh IS NOT NULL""",
)

RULES = (NOINDEX, NOFOLLOW, META_REFRESH)
