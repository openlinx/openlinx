"""Declare the response-code Rules over Internal URLs."""

from openlinx.rules.model import Rule, Threshold

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
WHERE is_internal = 1
  AND (fetch_state IN ('fetched', 'error') OR blocked_by_robots_txt = 1)
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
WHERE is_internal = 1
  AND (fetch_state IN ('fetched', 'error') OR blocked_by_robots_txt = 1)
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
WHERE is_internal = 1
  AND (fetch_state IN ('fetched', 'error') OR blocked_by_robots_txt = 1)
  AND fetch_state = 'error'
  -- With record_failed the Crawl received a response but could not write it.
  -- The record_failed warning reports that failure.
  AND fetch_error <> 'record_failed'""",
)

INTERNAL_BLOCKED_BY_ROBOTS_TXT = Rule(
    id="internal-blocked-by-robots-txt",
    category="response_codes",
    issue_type="warning",
    priority="medium",
    applies_to="internal_urls",
    description="robots.txt disallows an Internal URL for the Crawl's robots user-agent token.",
    why_it_matters=(
        "Crawlers that obey the matching directive cannot fetch the URL. If the block is "
        "unintentional, they can miss content or updates."
    ),
    how_to_fix=(
        "Check the URL against the matching user-agent group in robots.txt. If crawlers "
        "should be able to fetch it, adjust the group's Allow and Disallow directives."
    ),
    reproduce_sql="""\
SELECT id AS url_id, NULL AS detail
FROM urls
WHERE is_internal = 1
  AND (fetch_state IN ('fetched', 'error') OR blocked_by_robots_txt = 1)
  AND blocked_by_robots_txt = 1""",
)

INTERNAL_3XX = Rule(
    id="internal-3xx",
    category="response_codes",
    issue_type="warning",
    priority="low",
    applies_to="internal_urls",
    description="An Internal URL responded with a status code from 300 to 399.",
    why_it_matters=(
        "A redirect adds a request before visitors or search engines reach the destination. "
        "A missing target can leave them without a URL to follow."
    ),
    how_to_fix=(
        "For a redirect that should stay, update its Inlinks to point directly to the "
        "destination in detail.redirect_url. If that field is null and a redirect is intended, "
        "check the status code and Location header."
    ),
    reproduce_sql="""\
SELECT source.id AS url_id,
       json_object('status_code', source.status_code, 'redirect_url', target.url) AS detail
FROM urls AS source
LEFT JOIN urls AS target ON target.id = source.redirect_url_id
WHERE source.is_internal = 1
  AND (source.fetch_state IN ('fetched', 'error') OR source.blocked_by_robots_txt = 1)
  AND source.status_code BETWEEN 300 AND 399""",
)

REDIRECT_CHAIN = Rule(
    id="redirect-chain",
    category="response_codes",
    issue_type="warning",
    priority="medium",
    applies_to="internal_urls",
    description="An Internal URL has a Redirect Chain longer than max_hops.",
    why_it_matters="Each redirect adds a request before visitors or search engines can continue.",
    how_to_fix=(
        "Update Inlinks and redirects to point directly to the intended destination. "
        "Check that detail.final_url is the intended destination and returns the expected response."
    ),
    reproduce_sql="""\
WITH RECURSIVE
    redirects AS NOT MATERIALIZED (
        SELECT id, redirect_url_id
        FROM urls
        WHERE fetch_state IN ('fetched', 'error') AND status_code BETWEEN 300 AND 399
    ),
    -- Walk back from terminal URLs so shared suffixes are counted only once.
    finished(url_id, final_id, hops) AS MATERIALIZED (
        SELECT source.id, coalesce(source.redirect_url_id, source.id), 1
        FROM redirects AS source
        LEFT JOIN redirects AS target ON target.id = source.redirect_url_id
        WHERE target.id IS NULL
        UNION ALL
        SELECT source.id, finished.final_id, finished.hops + 1
        FROM finished
        JOIN redirects AS source ON source.redirect_url_id = finished.url_id
    ),
    -- Every cycle has a local minimum id. Queue those candidates only in the part of the
    -- graph that did not reach a terminal URL. ORDER BY gives visits priority over new
    -- candidates, so one forward walk finishes before another begins.
    -- The equal-width walk and step keys store the candidate id and step after a NUL.
    -- SQLite's NOCASE comparison stops there, so UNION deduplicates by (url_id, is_candidate)
    -- and retains the first visit's walk and step. BLOB casts below read past the NUL.
    walk(url_id, is_candidate, walk_key, step_key) AS (
        SELECT source.id, 1, (char(0) || printf('%020lld', source.id)) COLLATE NOCASE,
               (char(0) || printf('%019lld', 0)) COLLATE NOCASE
        FROM redirects AS source
        LEFT JOIN finished ON finished.url_id = source.id
        WHERE finished.url_id IS NULL
          AND source.redirect_url_id >= source.id
          AND EXISTS (
              SELECT 1 FROM redirects AS predecessor
              WHERE predecessor.redirect_url_id = source.id AND predecessor.id >= source.id
          )
        UNION
        SELECT CASE WHEN walk.is_candidate THEN walk.url_id ELSE source.redirect_url_id END,
               0, walk.walk_key,
               char(0) || printf('%019lld', 1 + CAST(substr(CAST(walk.step_key AS BLOB),
                   1 + length(CAST(char(0) AS BLOB))) AS INTEGER))
        FROM walk
        JOIN redirects AS source ON source.id = walk.url_id
        -- An unlimited LIMIT keeps older SQLite planners from removing the queue order.
        ORDER BY 2
        LIMIT -1
    ),
    visits AS MATERIALIZED (
        SELECT url_id, CAST(walk_key AS BLOB) AS walk_key,
               CAST(substr(CAST(step_key AS BLOB), 1 + length(CAST(char(0) AS BLOB)))
                    AS INTEGER) AS step
        FROM walk WHERE is_candidate = 0
    ),
    -- An edge to an earlier visit in the same walk closes a cycle. An edge to a
    -- different walk only joins a suffix that was already visited.
    cycles(root_id, hops) AS (
        SELECT target.url_id, origin.step - target.step + 1
        FROM visits AS origin
        -- Keep origin outside the lookup of source, so each visit looks up its URL by
        -- primary key instead of letting SQLite put a scan of urls in the outer loop.
        CROSS JOIN urls AS source ON source.id = origin.url_id
        JOIN visits AS target ON target.url_id = source.redirect_url_id
        WHERE target.walk_key = origin.walk_key AND target.step <= origin.step
    ),
    -- Visit each cycle once more to give every member its length and identify its incoming edge.
    cycle_members(url_id, predecessor_id, root_id, hops) AS (
        SELECT source.redirect_url_id, source.id, source.id, cycles.hops
        FROM cycles
        JOIN redirects AS source ON source.id = cycles.root_id
        UNION ALL
        SELECT source.redirect_url_id, source.id, member.root_id, member.hops
        FROM cycle_members AS member
        JOIN redirects AS source ON source.id = member.url_id
        WHERE member.url_id != member.root_id
    ),
    -- A chain entering a cycle repeats the entry URL first. Walk back towards its starts,
    -- skipping the incoming edge from inside the cycle so each predecessor is counted once.
    looping(url_id, final_id, hops, cycle_predecessor_id) AS (
        SELECT url_id, url_id, hops, predecessor_id FROM cycle_members
        UNION ALL
        SELECT source.id, looping.final_id, looping.hops + 1, NULL
        FROM looping
        JOIN redirects AS source ON source.redirect_url_id = looping.url_id
        WHERE source.id IS NOT looping.cycle_predecessor_id
    ),
    chains(url_id, final_id, hops) AS (
        SELECT url_id, final_id, hops FROM finished
        UNION ALL
        SELECT url_id, final_id, hops FROM looping
    )
SELECT chains.url_id, json_object('hops', chains.hops, 'final_url', final.url) AS detail
FROM chains
JOIN urls AS source ON source.id = chains.url_id
JOIN urls AS final ON final.id = chains.final_id
WHERE source.is_internal = 1 AND chains.hops > (
    SELECT json_extract(thresholds, '$.max_hops') FROM rules WHERE id = 'redirect-chain'
)""",
    thresholds=(Threshold("max_hops", 1, "hops"),),
)

REDIRECT_LOOP = Rule(
    id="redirect-loop",
    category="response_codes",
    issue_type="issue",
    priority="high",
    applies_to="internal_urls",
    description="An Internal URL is part of a redirect loop.",
    why_it_matters=(
        "Visitors and search engines following the redirects return to a URL they have "
        "already requested and cannot reach the intended content."
    ),
    how_to_fix=(
        "Trace the Location headers to find the redirects that close the loop. "
        "Point them and any Inlinks directly to the intended URL that serves the content."
    ),
    reproduce_sql="""\
WITH RECURSIVE
    -- The Store flags every member when it closes a loop. Unflagged URLs can lead into
    -- a loop or form an unmarked cycle, so follow only flagged members.
    -- Each loop has an id no greater than its target's id, including a self-redirect.
    -- Give visits priority over candidates so the first walk labels the whole loop.
    -- NOCASE compares the equal-width root keys only up to the NUL. UNION therefore
    -- keeps the first visit to each URL even when another candidate would give it a new root.
    walk(url_id, redirect_url_id, is_candidate, root_key) AS (
        SELECT id, redirect_url_id, 1, (char(0) || printf('%020lld', id)) COLLATE NOCASE
        FROM urls
        WHERE in_redirect_loop = 1 AND redirect_url_id >= id
        UNION
        SELECT target.id, target.redirect_url_id, 0, walk.root_key
        FROM walk
        JOIN urls AS target ON target.id = CASE WHEN walk.is_candidate THEN walk.url_id
                                               ELSE walk.redirect_url_id END
        WHERE target.in_redirect_loop = 1
        -- An unlimited LIMIT keeps older SQLite planners from removing the queue order.
        ORDER BY 3
        LIMIT -1
    ),
    sizes AS (
        SELECT url_id, count(*) OVER (PARTITION BY CAST(root_key AS BLOB)) AS hops
        FROM walk
        WHERE is_candidate = 0
    )
-- External URLs count toward the size of a loop. Report only the Internal URLs.
SELECT sizes.url_id, json_object('hops', sizes.hops) AS detail
FROM sizes
JOIN urls AS source ON source.id = sizes.url_id
WHERE source.is_internal = 1
  AND (source.fetch_state IN ('fetched', 'error') OR source.blocked_by_robots_txt = 1)""",
)

RULES = (
    INTERNAL_4XX,
    INTERNAL_5XX,
    INTERNAL_NO_RESPONSE,
    INTERNAL_BLOCKED_BY_ROBOTS_TXT,
    INTERNAL_3XX,
    REDIRECT_CHAIN,
    REDIRECT_LOOP,
)
