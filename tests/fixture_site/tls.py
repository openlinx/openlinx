"""Distinct TLS trust failures behind the fixture resolver (022-add-fetch-policy D5, D9)."""

import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import trustme
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from tests.fixture_site.hosts import HTTP_PORT, OTHER_HOST, SITE_HOSTS, FixtureResolver
from tests.fixture_site.routes import Site
from tests.fixture_site.server import Serve, ServerHandle

HTTPS_PORT = 443
BADCERT_HOST = "badcert.test"
SELFSIGNED_HOST = "selfsigned.test"


@dataclass(frozen=True, kw_only=True)
class TlsHosts:
    # http://site.test and https://site.test, each for www.site.test too, serving the same Site.
    site: ServerHandle
    secure_site: ServerHandle
    # https://badcert.test, whose certificate names other.test.
    badcert: ServerHandle
    # https://other.test:{untrusted_port}, whose certificate a CA the Crawl never trusts signs.
    untrusted: ServerHandle
    untrusted_port: int
    selfsigned: ServerHandle
    resolver: FixtureResolver
    # The test CA's certificate, the extra trust anchor a Crawl is given.
    trust_anchors: str
    # The other CA's certificate, for a test of the listener itself.
    untrusted_anchors: str
    # Explicit trust for the listener's positive control, never a normal Crawl anchor.
    selfsigned_certificate: str


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
    selfsigned_context, selfsigned_certificate = _self_signed()
    selfsigned = serve(other, selfsigned_context)
    servers = {
        **{(name, HTTP_PORT): plain for name in SITE_HOSTS},
        **{(name, HTTPS_PORT): secure for name in SITE_HOSTS},
        (BADCERT_HOST, HTTPS_PORT): badcert,
        (OTHER_HOST, untrusted_port): untrusted,
        (SELFSIGNED_HOST, HTTPS_PORT): selfsigned,
    }
    return TlsHosts(
        site=plain,
        secure_site=secure,
        badcert=badcert,
        untrusted=untrusted,
        untrusted_port=untrusted_port,
        selfsigned=selfsigned,
        resolver=FixtureResolver(servers),
        trust_anchors=_pem(trusted_ca),
        untrusted_anchors=_pem(untrusted_ca),
        selfsigned_certificate=selfsigned_certificate,
    )


def _self_signed() -> tuple[ssl.SSLContext, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SELFSIGNED_HOST)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(SELFSIGNED_HOST)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    pem = certificate.public_bytes(serialization.Encoding.PEM)
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    with TemporaryDirectory() as directory:
        cert_file, key_file = Path(directory) / "cert.pem", Path(directory) / "key.pem"
        cert_file.write_bytes(pem)
        key_file.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        # Windows needs both files closed before OpenSSL opens them again.
        context.load_cert_chain(cert_file, key_file)
    return context, pem.decode("ascii")


def _listening(certificate: trustme.LeafCert) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    certificate.configure_cert(context)
    return context


def _pem(ca: trustme.CA) -> str:
    return ca.cert_pem.bytes().decode("ascii")
