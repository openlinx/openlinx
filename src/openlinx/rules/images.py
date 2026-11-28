"""Declare the Rules for image markup and the outcomes of requests to image targets."""

from openlinx.rules.model import Rule, Threshold

# Use the existing (type, target_url_id) index. EXISTS returns one result per target
# even when several Pages or several Links on one Page reference the same image.
_IMAGE_LINK = """\
EXISTS (
    SELECT 1 FROM links
    JOIN pages ON pages.url_id = links.source_url_id
    WHERE links.type = 'image' AND links.target_url_id = urls.id
)"""

IMAGE_MISSING_ALT_TEXT = Rule(
    id="image-missing-alt-text",
    category="images",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page has an image with an absent or empty alt attribute.",
    why_it_matters=(
        "Alt text conveys the image's purpose to assistive technology and helps when the "
        "image cannot load."
    ),
    how_to_fix=(
        "Review the Page's <img> elements. Describe informative images in alt text and "
        'leave alt="" on purely decorative images.'
    ),
    reproduce_sql="""\
SELECT links.source_url_id AS url_id,
       json_object('missing_alt_attribute', count(*) FILTER (WHERE links.alt_text IS NULL),
                   'empty_alt', count(*) FILTER (WHERE links.alt_text = '')) AS detail
FROM links
JOIN pages ON pages.url_id = links.source_url_id
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  -- A srcset Link is another candidate for the same image, not another alt attribute.
  AND links.type = 'image' AND links.element = 'img' AND links.attribute = 'src'
  -- A failed Link extractor also leaves alt_text NULL. link_position tells those rows apart.
  AND links.link_position IS NOT NULL AND (links.alt_text IS NULL OR links.alt_text = '')
GROUP BY links.source_url_id""",
)

IMAGE_TOO_LARGE = Rule(
    id="image-too-large",
    category="images",
    issue_type="opportunity",
    priority="medium",
    applies_to="resources",
    description="A checked image exceeds max_kb kilobytes, measured at 1024 bytes per kilobyte.",
    why_it_matters="Large image files increase transfer time and can slow down Pages.",
    how_to_fix=(
        "Resize the image to the dimensions needed and choose a suitable encoding. "
        "Check the result at the sizes where the image is displayed."
    ),
    reproduce_sql=f"""\
SELECT urls.id AS url_id, json_object('size_bytes', urls.size_bytes) AS detail
FROM urls
WHERE urls.fetch_state IN ('fetched', 'error') AND urls.attempt_count > 0
  AND urls.size_bytes > (
      SELECT json_extract(thresholds, '$.max_kb') * 1024 FROM rules WHERE id = 'image-too-large'
  )
  -- An image Link may point to HTML, even when the Crawl did not parse it.
  AND coalesce(
      lower(trim(substr(urls.content_type, 1, instr(urls.content_type || ';', ';') - 1),
                 char(9, 32))),
      ''
  ) NOT IN ('text/html', 'application/xhtml+xml')
  AND {_IMAGE_LINK}""",  # noqa: S608 - only fixed SQL fragments
    thresholds=(Threshold("max_kb", 100, "kilobytes"),),
)

IMAGE_BROKEN = Rule(
    id="image-broken",
    category="images",
    issue_type="issue",
    priority="medium",
    applies_to="resources",
    description="A checked image returned a 4xx or 5xx status or its request failed.",
    why_it_matters="Visitors can miss content when an image cannot be loaded.",
    how_to_fix=(
        "Restore the image at its URL, update the Page Links to the intended image, "
        "or remove the reference if the image is no longer needed."
    ),
    reproduce_sql=f"""\
SELECT urls.id AS url_id,
       CASE WHEN urls.status_code BETWEEN 400 AND 599
            THEN json_object('status_code', urls.status_code)
            ELSE json_object('error', urls.fetch_error) END AS detail
FROM urls
WHERE urls.fetch_state IN ('fetched', 'error')
  -- A robots.txt preflight failure can record an error without requesting this image.
  AND urls.attempt_count > 0
  -- record_failed is a Store write failure, reported by a Crawl warning.
  AND urls.fetch_error IS NOT 'record_failed'
  AND (urls.status_code BETWEEN 400 AND 599
       OR (urls.fetch_state = 'error' AND urls.fetch_error IS NOT NULL))
  AND {_IMAGE_LINK}""",  # noqa: S608 - only fixed SQL fragments
)

RULES = (IMAGE_MISSING_ALT_TEXT, IMAGE_TOO_LARGE, IMAGE_BROKEN)
