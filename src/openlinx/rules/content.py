"""Declare Rules for word count and Exact Duplicates in the Content Area."""

from openlinx.rules.model import Rule, Threshold

LOW_WORD_COUNT = Rule(
    id="low-word-count",
    category="content",
    issue_type="opportunity",
    priority="medium",
    applies_to="internal_pages",
    description="An Indexable Page's Content Area has fewer than min_words words.",
    why_it_matters="A Page with very little content may leave visitors' questions unanswered.",
    how_to_fix="Review whether the Page needs more information to meet its purpose.",
    reproduce_sql="""\
SELECT pages.url_id, json_object('word_count', pages.word_count) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  -- The word count check concerns Pages eligible for indexing.
  AND pages.indexability = 'indexable'
  AND pages.word_count < (
      SELECT json_extract(thresholds, '$.min_words') FROM rules WHERE id = 'low-word-count'
  )""",
    thresholds=(Threshold("min_words", 200, "words"),),
)

EXACT_DUPLICATE = Rule(
    id="exact-duplicate",
    category="content",
    issue_type="issue",
    priority="medium",
    applies_to="internal_pages",
    description="Indexable Pages share the same Content Area hash.",
    why_it_matters="Identical content at multiple Indexable URLs obscures the preferred Page.",
    how_to_fix=(
        "Consolidate identical Pages at a preferred URL or give each Page distinct content."
    ),
    reproduce_sql="""\
WITH duplicate_hashes AS (
    SELECT pages.content_hash, COUNT(*) AS page_count
    FROM pages
    JOIN urls ON urls.id = pages.url_id
    WHERE urls.parsed = 1
      -- Count only Pages competing for indexing.
      AND pages.indexability = 'indexable'
      -- Empty or unmeasured content has no hash to compare.
      AND pages.content_hash IS NOT NULL
    GROUP BY pages.content_hash
    HAVING COUNT(*) > 1
)
SELECT pages.url_id,
       json_object('content_hash', pages.content_hash,
                   'pages', duplicate_hashes.page_count) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
JOIN duplicate_hashes ON duplicate_hashes.content_hash = pages.content_hash
-- Keep the source on its Page and URL rows so a live URL filter can use their primary keys.
WHERE urls.parsed = 1
  AND pages.indexability = 'indexable'
  AND pages.content_hash IS NOT NULL""",
)

RULES = (LOW_WORD_COUNT, EXACT_DUPLICATE)
