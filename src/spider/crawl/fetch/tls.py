"""The TLS context of every request of a Crawl (022-add-fetch-policy D5)."""

import ssl

import certifi


def tls_context(trust_anchors: str | None = None) -> ssl.SSLContext:
    """A context that verifies each certificate and its host name against the OS trust store,
    or certifi's bundle when truststore cannot be loaded; `trust_anchors`, PEM certificates,
    are trusted besides them."""
    context = _trust_store_context()
    if trust_anchors is not None:
        context.load_verify_locations(cadata=trust_anchors)
    return context


def _trust_store_context() -> ssl.SSLContext:
    try:
        # truststore refuses to load on a Python or OpenSSL it cannot verify with.
        import truststore
    except ImportError:
        return ssl.create_default_context(cafile=certifi.where())
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
