"""Measures TLS handshake time with truststore and with certifi's bundle (022-add-fetch-policy D5).

A one-off measurement against public hosts, never a test and never part of the gate:

    uv run python scripts/tls_handshake_speed.py [--rounds 20] [host ...]

For each host it connects once to find an address that answers, then makes `rounds` fresh TCP
connections per trust store, alternating them, and times the TLS handshake alone, certificate
verification included. It prints the platform and versions, the time to build each context, and
per host and over all hosts the median and 90th percentile handshake in milliseconds for each
trust store, with the median difference, truststore minus certifi. A host it cannot reach is
named and skipped.
"""

import argparse
import platform
import socket
import ssl
import statistics
import sys
import time
from collections.abc import Callable

import certifi
import truststore

HOSTS = ("www.python.org", "github.com", "www.wikipedia.org", "www.cloudflare.com", "pypi.org")
TIMEOUT_SECONDS = 10


def _truststore() -> ssl.SSLContext:
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def _certifi() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


STORES: dict[str, Callable[[], ssl.SSLContext]] = {"truststore": _truststore, "certifi": _certifi}


def _built(make: Callable[[], ssl.SSLContext]) -> tuple[ssl.SSLContext, float]:
    started = time.perf_counter()
    context = make()
    return context, (time.perf_counter() - started) * 1000


def _answering_address(host: str) -> tuple[str, int]:
    # The first resolved address may be one this network cannot route, such as IPv6.
    with socket.create_connection((host, 443), timeout=TIMEOUT_SECONDS) as probe:
        peer: tuple[str, int] = probe.getpeername()[:2]
        return peer


def _handshake_ms(context: ssl.SSLContext, host: str, address: tuple[str, int]) -> float:
    with socket.create_connection(address, timeout=TIMEOUT_SECONDS) as raw:
        started = time.perf_counter()
        with context.wrap_socket(raw, server_hostname=host):
            return (time.perf_counter() - started) * 1000


def _summary(samples: list[float]) -> tuple[float, float]:
    return statistics.median(samples), statistics.quantiles(samples, n=10)[-1]


def _row(label: str, samples: dict[str, list[float]]) -> None:
    t_median, t_p90 = _summary(samples["truststore"])
    c_median, c_p90 = _summary(samples["certifi"])
    truststore_cell = f"{t_median:.1f} / {t_p90:.1f} ms"
    certifi_cell = f"{c_median:.1f} / {c_p90:.1f} ms"
    print(f"{label:<22}{truststore_cell:>24}{certifi_cell:>22}{t_median - c_median:>+7.1f} ms")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("hosts", nargs="*", default=list(HOSTS))
    arguments = parser.parse_args(argv)
    if arguments.rounds < 2:
        parser.error("--rounds takes at least 2, for a 90th percentile")

    contexts = {name: _built(make) for name, make in STORES.items()}
    print(
        f"{platform.platform()}, Python {platform.python_version()}, "
        f"truststore {truststore.__version__}, certifi {certifi.__version__}, "
        f"{arguments.rounds} handshakes per host and store"
    )
    print("context build: " + ", ".join(f"{n} {ms:.1f} ms" for n, (_, ms) in contexts.items()))
    print(f"{'host':<22}{'truststore median/p90':>24}{'certifi median/p90':>22}{'diff':>10}")
    every: dict[str, list[float]] = {name: [] for name in STORES}
    for host in arguments.hosts:
        samples: dict[str, list[float]] = {name: [] for name in STORES}
        try:
            address = _answering_address(host)
            for _ in range(arguments.rounds):
                for name, (context, _) in contexts.items():
                    samples[name].append(_handshake_ms(context, host, address))
        except OSError as error:
            print(f"{host:<22}unreachable: {error}")
            continue
        for name in STORES:
            every[name].extend(samples[name])
        _row(host, samples)
    if every["truststore"]:
        _row("all hosts", every)


if __name__ == "__main__":
    main(sys.argv[1:])
