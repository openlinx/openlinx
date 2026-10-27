"""The TLS context of every request of a Crawl (022-add-fetch-policy D5)."""

import ssl


def tls_context(trust_anchors: str | None = None) -> ssl.SSLContext:
    """A context that verifies each certificate and its host name; `trust_anchors`, PEM
    certificates, are trusted besides the default ones."""
    context = ssl.create_default_context()
    if trust_anchors is not None:
        context.load_verify_locations(cadata=trust_anchors)
    return context
