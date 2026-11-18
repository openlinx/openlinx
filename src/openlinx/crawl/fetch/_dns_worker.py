"""Run one blocking system DNS query in an isolated, disposable interpreter."""

import json
import os
import socket
import sys
from typing import cast


def _addresses(host: str, port: int) -> list[tuple[str, int, socket.AddressFamily, int]]:
    # Match aiohttp's threaded resolver, including the Winsock loopback fallback.
    flags = socket.AI_ADDRCONFIG & getattr(socket, "AI_MASK", socket.AI_ADDRCONFIG)
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM, flags=flags)
    except socket.gaierror:
        if sys.platform == "win32" and host.rstrip(".").casefold() == "localhost":
            infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        else:
            raise
    answers: list[tuple[str, int, socket.AddressFamily, int]] = []
    for family, _, proto, _, address in infos:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        endpoint = cast(tuple[str, int] | tuple[str, int, int, int], address)
        if family == socket.AF_INET6:
            if len(endpoint) != 4:
                continue
            if endpoint[3]:
                # Preserve the zone on link-local IPv6 addresses.
                ip, service = socket.getnameinfo(
                    endpoint, socket.NI_NUMERICHOST | socket.NI_NUMERICSERV
                )
                answers.append((ip, int(service), family, proto))
                continue
        answers.append((endpoint[0], endpoint[1], family, proto))
    return answers


def _run(host: str, port: int) -> int:
    try:
        answers = _addresses(host, port)
    except (OSError, UnicodeError):
        return 1
    # Descriptor 1 is the parent's private IPC pipe.
    with os.fdopen(1, "wb", closefd=False) as pipe:
        pipe.write(json.dumps(answers).encode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(_run(sys.argv[1], int(sys.argv[2])))
