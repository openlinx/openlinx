"""Open an HTTP CONNECT tunnel for the dedicated ALPN handshake."""

import asyncio
import re

import aiohttp
import yarl

_HEADER_END = b"\r\n\r\n"
# StreamReader.readuntil counts only the bytes before its separator.
CONNECT_STREAM_LIMIT = 65_536 - len(_HEADER_END)
_SUCCESS_STATUS = re.compile(rb"HTTP/1\.[01] 2[0-9]{2} [\t\x20-\x7e\x80-\xff]*")
_FIELD_LINE = re.compile(rb"[!#$%&'*+\-.^_`|~0-9A-Za-z]+:[\t\x20-\x7e\x80-\xff]*")


def connect_authority(url: yarl.URL) -> str:
    """Match aiohttp's CONNECT target, including DNS root dots and default ports."""
    host, port = url.host_subcomponent, url.port
    if host is None or port is None:
        raise RuntimeError("A tunnel request needs an origin host and port")
    return f"{host}:{port}"


async def establish_tunnel(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    proxy: yarl.URL,
    authority: str,
) -> bool:
    lines = [f"CONNECT {authority} HTTP/1.1", f"Host: {authority}"]
    if proxy.raw_user or proxy.raw_password:
        auth = aiohttp.encode_basic_auth(proxy.user or "", proxy.password or "", encoding="latin1")
        lines.append(f"Proxy-Authorization: {auth}")
    writer.write("\r\n".join(lines).encode("ascii") + _HEADER_END)
    await writer.drain()
    try:
        head = await reader.readuntil(_HEADER_END)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        return False
    status, *fields = head[: -len(_HEADER_END)].split(b"\r\n")
    return _SUCCESS_STATUS.fullmatch(status) is not None and all(
        _FIELD_LINE.fullmatch(field) is not None for field in fields
    )
