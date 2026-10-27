"""The TLS setup: the OS trust store, or certifi without it (022-add-fetch-policy D5, seam 4)."""

import ssl
import sys
from typing import cast

import certifi
import pytest
import trustme
import truststore

from spider.crawl.fetch.tls import tls_context

# typeshed types every value of a certificate as a string or a tuple.
type _Subject = tuple[tuple[tuple[str, str], ...], ...]
PEM_BEGIN = "-----BEGIN CERTIFICATE-----"
# A root that certifi's bundle holds, as Mozilla's does.
ISRG_ROOT_X1 = {
    "countryName": "US",
    "organizationName": "Internet Security Research Group",
    "commonName": "ISRG Root X1",
}


def _subjects(context: ssl.SSLContext) -> list[dict[str, str]]:
    return [
        {key: value for part in cast(_Subject, certificate["subject"]) for key, value in part}
        for certificate in context.get_ca_certs()
    ]


def test_the_context_verifies_against_the_os_trust_store() -> None:
    context = tls_context()

    assert (type(context), context.verify_mode, context.check_hostname) == (
        truststore.SSLContext,
        ssl.CERT_REQUIRED,
        True,
    )


def test_without_truststore_the_context_trusts_certifis_bundle_and_the_extra_anchors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # As on a Python runtime that truststore refuses: its import raises ImportError.
    monkeypatch.setitem(sys.modules, "truststore", None)
    ca = trustme.CA()

    context = tls_context(ca.cert_pem.bytes().decode("ascii"))

    subjects = _subjects(context)
    test_cas = [s for s in subjects if s.get("organizationName", "").startswith("trustme v")]
    assert (
        context.verify_mode,
        context.check_hostname,
        len(subjects),
        ISRG_ROOT_X1 in subjects,
        len(test_cas),
    ) == (ssl.CERT_REQUIRED, True, certifi.contents().count(PEM_BEGIN) + 1, True, 1)
