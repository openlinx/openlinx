"""HTTPS listeners with a test CA, behind the DNS resolver hook (022-add-fetch-policy D5)."""

import asyncio
import ssl
from datetime import UTC, datetime, timedelta

import aiohttp
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from tests.fixture_site.routes import Page, Site
from tests.fixture_site.tls import StartTlsHosts

SITE = Site(routes={"/": Page(body="<p>Site</p>")})
OTHER = Site(routes={"/": Page(body="<p>Other</p>")})


async def test_self_signed_listener_serves_a_valid_leaf_that_can_be_explicitly_trusted(
    fixture_tls_hosts: StartTlsHosts,
) -> None:
    hosts = fixture_tls_hosts(SITE, OTHER)
    context = ssl.create_default_context(cadata=hosts.selfsigned_certificate)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    address = (await hosts.resolver.resolve("selfsigned.test", 443))[0]
    _, writer = await asyncio.open_connection(
        address["host"], address["port"], ssl=context, server_hostname="selfsigned.test"
    )
    try:
        connection: ssl.SSLObject = writer.get_extra_info("ssl_object")
        der = connection.getpeercert(binary_form=True)
        assert der is not None
    finally:
        writer.close()
        await writer.wait_closed()

    certificate = x509.load_der_x509_certificate(der)
    assert certificate.subject == certificate.issuer
    assert certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == (
        "selfsigned.test"
    )
    assert certificate.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName) == ["selfsigned.test"]
    constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert (constraints.ca, constraints.path_length) == (False, None)
    now = datetime.now(UTC)
    assert certificate.not_valid_before_utc <= now - timedelta(hours=1)
    assert certificate.not_valid_after_utc >= now + timedelta(days=1)
    key = certificate.public_key()
    assert isinstance(key, rsa.RSAPublicKey)
    assert isinstance(certificate.signature_hash_algorithm, hashes.SHA256)
    key.verify(
        certificate.signature,
        certificate.tbs_certificate_bytes,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    connector = aiohttp.TCPConnector(resolver=hosts.resolver)
    async with (
        aiohttp.ClientSession(connector=connector) as session,
        session.get("https://selfsigned.test/", ssl=context) as response,
    ):
        assert (response.status, await response.text()) == (200, "<p>Other</p>")
    assert [request.path for request in hosts.selfsigned.requests] == ["/"]


async def test_each_https_listener_serves_the_certificate_it_is_named_for(
    fixture_tls_hosts: StartTlsHosts,
) -> None:
    hosts = fixture_tls_hosts(SITE, OTHER)
    trusted = ssl.create_default_context(cadata=hosts.trust_anchors)
    untrusted = ssl.create_default_context(cadata=hosts.untrusted_anchors)
    connector = aiohttp.TCPConnector(resolver=hosts.resolver)

    async with aiohttp.ClientSession(connector=connector) as session:
        for url, context, certificate_name in (
            ("http://site.test/", True, None),
            ("https://site.test/", trusted, None),
            ("https://www.site.test/", trusted, None),
            ("https://badcert.test/", trusted, "other.test"),
            (f"https://other.test:{hosts.untrusted_port}/", untrusted, None),
        ):
            async with session.get(url, ssl=context, server_hostname=certificate_name) as response:
                assert response.status == 200

    assert [
        len(server.requests)
        for server in (hosts.site, hosts.secure_site, hosts.badcert, hosts.untrusted)
    ] == [1, 2, 1, 1]


async def test_a_name_is_resolved_only_on_the_ports_it_listens_on(
    fixture_tls_hosts: StartTlsHosts,
) -> None:
    hosts = fixture_tls_hosts(SITE, OTHER)
    connector = aiohttp.TCPConnector(resolver=hosts.resolver)

    async with aiohttp.ClientSession(connector=connector) as session:
        for url in ("http://badcert.test/", "https://other.test/", "http://site.test:8080/"):
            with pytest.raises(aiohttp.ClientConnectorDNSError):
                await session.get(url)
