"""Open an HTTP CONNECT tunnel for the dedicated ALPN handshake."""

import asyncio
import re

import aiohttp
import yarl

_HEADER_END = b"\r\n\r\n"
# StreamReader.readuntil counts only the bytes before its separator.
CONNECT_STREAM_LIMIT = 65_536 - len(_HEADER_END)
_SUCCESS_STATUS = re.compile(rb"HTTP/1\.[01] 2[0-9]{2} [\t\x20-\x7e\x80-\xff]*")


async def establish_tunnel(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    proxy: yarl.URL,
    host: str,
    port: int,
) -> bool:
    authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
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
    return _SUCCESS_STATUS.fullmatch(head.split(b"\r\n", 1)[0]) is not None
