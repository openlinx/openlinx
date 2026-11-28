"""The v0.1 Rule IDs promised in the release roadmap."""

PREVIEW_NO_ROWS = "SELECT id AS url_id, NULL AS detail FROM urls WHERE 0"
PREVIEW_RULE_IDS = {"h2-missing", "low-word-count", "url-parameters"}

PREVIEW_LIVE_RULE_IDS = {
    "internal-4xx",
    "internal-5xx",
    "internal-no-response",
    "internal-3xx",
    "redirect-chain",
    "redirect-loop",
    "internal-blocked-by-robots-txt",
    "http-url",
    "title-missing",
    "title-duplicate",
    "title-too-long",
    "meta-description-missing",
    "h1-missing",
    "noindex",
    "canonical-to-non-indexable",
}

V01_RULE_IDS = PREVIEW_LIVE_RULE_IDS | {
    "title-too-short",
    "title-multiple",
    "title-same-as-h1",
    "meta-description-duplicate",
    "meta-description-too-long",
    "meta-description-too-short",
    "meta-description-multiple",
    "h1-duplicate",
    "h1-multiple",
    "h1-too-long",
    "h2-missing",
    "canonical-missing",
    "canonicalised",
    "canonical-conflicting",
    "canonical-relative",
    "nofollow",
    "meta-refresh",
    "low-word-count",
    "exact-duplicate",
    "url-uppercase",
    "url-underscores",
    "url-parameters",
    "url-too-long",
    "url-non-ascii",
    "image-missing-alt-text",
    "image-too-large",
    "image-broken",
}
