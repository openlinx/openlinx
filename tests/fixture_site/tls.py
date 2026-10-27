"""HTTPS listeners for the fixture site, certificates from a test CA (022-add-fetch-policy D5)."""

import ssl
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import trustme

from tests.fixture_site.hosts import HTTP_PORT, OTHER_HOST, SITE_HOSTS, FixtureResolver
from tests.fixture_site.routes import Site
from tests.fixture_site.server import Serve, ServerHandle

HTTPS_PORT = 443
BADCERT_HOST = "badcert.test"


@dataclass(frozen=True)
class TlsHosts:
    # http://site.test and https://site.test, each for www.site.test too, serving the same Site.
    site: ServerHandle
    secure_site: ServerHandle
    # https://badcert.test, whose certificate names other.test.
    badcert: ServerHandle
    # https://other.test:{untrusted_port}, whose certificate a CA the Crawl never trusts signs.
    untrusted: ServerHandle
    untrusted_port: int
    resolver: FixtureResolver
    # The test CA's certificate, the extra trust anchor a Crawl is given.
    trust_anchors: str
    # The other CA's certificate, for a test of the listener itself.
    untrusted_anchors: str


# A site, or a function that builds it from the untrusted listener's port, to link to it.
type SiteOrBuilder = Site | Callable[[int], Site]
StartTlsHosts = Callable[[SiteOrBuilder, Site], TlsHosts]


def tls_hosts_for(serve: Serve, site: SiteOrBuilder, other: Site) -> TlsHosts:
    trusted_ca, untrusted_ca = trustme.CA(), trustme.CA()
    untrusted = serve(other, _listening(untrusted_ca.issue_cert(OTHER_HOST)))
    untrusted_port = urlsplit(untrusted.base_url).port or 0
    if not isinstance(site, Site):
        site = site(untrusted_port)
    plain = serve(site)
    secure = serve(site, _listening(trusted_ca.issue_cert(*SITE_HOSTS)))
    badcert = serve(other, _listening(trusted_ca.issue_cert(OTHER_HOST)))
    servers = {
        **{(name, HTTP_PORT): plain for name in SITE_HOSTS},
        **{(name, HTTPS_PORT): secure for name in SITE_HOSTS},
        (BADCERT_HOST, HTTPS_PORT): badcert,
        (OTHER_HOST, untrusted_port): untrusted,
    }
    return TlsHosts(
        site=plain,
        secure_site=secure,
        badcert=badcert,
        untrusted=untrusted,
        untrusted_port=untrusted_port,
        resolver=FixtureResolver(servers),
        trust_anchors=_pem(trusted_ca),
        untrusted_anchors=_pem(untrusted_ca),
    )


def _listening(certificate: trustme.LeafCert) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    certificate.configure_cert(context)
    return context


def _pem(ca: trustme.CA) -> str:
    return ca.cert_pem.bytes().decode("ascii")
