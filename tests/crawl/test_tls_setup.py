"""The TLS setup's fallback to certifi (022-add-fetch-policy D5, seam 4)."""

import ssl
import sys

import certifi
import pytest
import trustme

from spider.crawl.fetch.tls import tls_context


def _subjects(context: ssl.SSLContext) -> set[object]:
    return {repr(certificate["subject"]) for certificate in context.get_ca_certs()}


def test_without_truststore_the_context_trusts_certifis_bundle_and_the_extra_anchors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # As on a Python or OpenSSL that truststore refuses: its import raises ImportError.
    monkeypatch.setitem(sys.modules, "truststore", None)
    ca = trustme.CA()
    bundle = ssl.create_default_context(cafile=certifi.where())
    anchors = ssl.create_default_context(cadata=ca.cert_pem.bytes().decode("ascii"))

    context = tls_context(ca.cert_pem.bytes().decode("ascii"))

    assert (context.verify_mode, context.check_hostname, _subjects(context)) == (
        ssl.CERT_REQUIRED,
        True,
        _subjects(bundle) | _subjects(anchors),
    )
