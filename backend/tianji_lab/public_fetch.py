"""Small, credential-free public HTTP reader; no crawler or ambient proxy.

Only response body bytes (including robots/redirects) enter the fetch budget, not
DNS, TLS/header overhead or DDGS traffic. gzip/deflate are decoded incrementally
with a separate max_response_bytes decoded-size cap; fetched_bytes counts accepted
raw body bytes, not decoded bytes. Each connection pins a validated public IP.
"""

import asyncio
import ipaddress
import json
import os
import re
import socket
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "ContingentResearch/1.0"


class FetchError(Exception):
    """The code is safe to persist; never persist exception details."""

    def __init__(self, code: str = "fetch_failed"):
        self.code = code
        super().__init__(code)


def public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(
        ip.is_global
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_unspecified
        and not getattr(ip, "ipv4_mapped", None)
        and not getattr(ip, "sixtofour", None)
        and not getattr(ip, "teredo", None)
        # Translation prefixes can otherwise route to a private IPv4 destination.
        and not (ip.version == 6 and ip in ipaddress.ip_network("64:ff9b::/96"))
    )


def validate_public_url(url: str) -> str:
    """Syntax/literal checks only; DNS must still be checked immediately before IO."""
    if (
        not isinstance(url, str)
        or not url
        or len(url) > 2048
        or re.search(r"[\x00-\x20\x7f\\]", url)
    ):
        raise ValueError("invalid public URL")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if (
            parts.scheme not in {"http", "https"}
            or not host
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, 80 if parts.scheme == "http" else 443}
            or "%" in host
        ):
            raise ValueError("invalid public URL")
        host = host.encode("idna").decode("ascii").lower()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if (
                "." not in host.rstrip(".")
                or host.endswith((".localhost", ".local", ".internal", ".invalid"))
                or not all(
                    re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in host.rstrip(".").split(".")
                )
            ):
                raise ValueError("invalid public URL")
        else:
            if not public_ip(host):
                raise ValueError("non-public URL")
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid public URL") from exc
    return urlunsplit(parts._replace(fragment=""))


async def _cloudflare_addresses(host: str) -> list[str]:
    """Explicit opt-in fixed endpoint; neither configurable DoH URL nor proxy."""
    addresses: list[str] = []
    async with httpx.AsyncClient(trust_env=False, timeout=8, follow_redirects=False) as client:
        for record_type in ("A", "AAAA"):
            request = client.build_request(
                "GET",
                "https://1.1.1.1/dns-query",
                params={"name": host, "type": record_type},
                headers={"Host": "cloudflare-dns.com", "Accept": "application/dns-json"},
                extensions={"sni_hostname": "cloudflare-dns.com"},
            )
            response = await client.send(request, stream=True)
            try:
                if response.status_code != 200:
                    raise FetchError("dns_failed")
                raw = bytearray()
                async for chunk in response.aiter_raw():
                    if len(raw) + len(chunk) > 16384:
                        raise FetchError("dns_failed")
                    raw.extend(chunk)
                data = json.loads(raw)
                if data.get("Status") != 0:
                    raise FetchError("dns_failed")
                for answer in data.get("Answer", []):
                    if answer.get("type") in (1, 28):
                        addresses.append(answer["data"])
            finally:
                await response.aclose()
    return addresses


async def resolve_public(host: str, port: int) -> list[str]:
    try:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            mode = os.environ.get("TIANJI_RESEARCH_DNS", "system")
            if mode == "cloudflare":
                addresses = await _cloudflare_addresses(host)
            elif mode == "system":
                records = await asyncio.get_running_loop().getaddrinfo(
                    host, port, type=socket.SOCK_STREAM
                )
                addresses = [record[4][0] for record in records]
            else:
                raise FetchError("dns_failed")
        else:
            addresses = [host]
        if not addresses or not all(public_ip(ip) for ip in addresses):
            raise FetchError("unsafe_address")
        return list(dict.fromkeys(addresses))
    except (OSError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise FetchError("dns_failed") from exc


@dataclass(frozen=True)
class FetchResult:
    url: str
    resolved_url: str
    body: bytes
    content_type: str
    status_code: int = 200


class PublicFetcher:
    def __init__(
        self,
        max_response_bytes: int,
        max_total_bytes: int,
        on_bytes: Callable[[int], None] | None = None,
    ):
        self.max_response_bytes = max_response_bytes
        self.max_total_bytes = max_total_bytes
        self.fetched_bytes = 0
        self.on_bytes = on_bytes
        self._robots: dict[str, RobotFileParser | None] = {}

    async def _request(self, url: str) -> tuple[FetchResult, str | None]:
        try:
            url = validate_public_url(url)
        except ValueError as exc:
            raise FetchError("unsafe_url") from exc
        if self.fetched_bytes >= self.max_total_bytes:
            raise FetchError("fetch_byte_limit")
        parts = urlsplit(url)
        host = parts.hostname.encode("idna").decode("ascii")
        port = 443 if parts.scheme == "https" else 80
        addresses = await resolve_public(host, port)
        ip = addresses[0]
        authority = f"[{ip}]" if ":" in ip else ip
        pinned = urlunsplit((parts.scheme, authority, parts.path, parts.query, ""))
        host_header = f"[{host}]" if ":" in host else host
        headers = {"Host": host_header, "User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
        try:
            # A fresh client per hop prevents cookies and pooled DNS state crossing targets.
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=10
            ) as client:
                async with client.stream(
                    "GET", pinned, headers=headers, extensions={"sni_hostname": host}
                ) as response:
                    network = response.extensions.get("network_stream")
                    if network is not None:
                        peer = network.get_extra_info("server_addr")
                        if peer is not None and (
                            not public_ip(peer[0])
                            or ipaddress.ip_address(peer[0]) != ipaddress.ip_address(ip)
                        ):
                            raise FetchError("unsafe_address")
                    encoding = response.headers.get("content-encoding", "identity").lower()
                    if encoding not in {"identity", "gzip", "deflate"}:
                        raise FetchError("unsupported_encoding")
                    decoder = (
                        zlib.decompressobj(31 if encoding == "gzip" else 15)
                        if encoding != "identity"
                        else None
                    )
                    limit = min(self.max_response_bytes, self.max_total_bytes - self.fetched_bytes)
                    length = response.headers.get("content-length")
                    if length and (not length.isdigit() or int(length) > limit):
                        raise FetchError("fetch_byte_limit")
                    body = bytearray()
                    raw_count = 0
                    async for chunk in response.aiter_raw(chunk_size=min(8192, limit + 1)):
                        # Count accepted raw body bytes; a boundary-detection byte and
                        # transport buffers/headers are not an on-the-wire quota.
                        count = min(len(chunk), limit - raw_count)
                        raw_count += count
                        self.fetched_bytes += count
                        if self.on_bytes:
                            self.on_bytes(count)
                        if count != len(chunk):
                            raise FetchError("fetch_byte_limit")
                        decoded = (
                            decoder.decompress(chunk, self.max_response_bytes - len(body) + 1)
                            if decoder
                            else chunk
                        )
                        if len(body) + len(decoded) > self.max_response_bytes:
                            raise FetchError("fetch_byte_limit")
                        body.extend(decoded)
                        if decoder and (decoder.unconsumed_tail or decoder.unused_data):
                            raise FetchError("unsupported_encoding")
                    if decoder and not decoder.eof:
                        raise FetchError("unsupported_encoding")
                    return (
                        FetchResult(
                            url,
                            url,
                            bytes(body),
                            response.headers.get("content-type", "").split(";", 1)[0].lower(),
                            response.status_code,
                        ),
                        response.headers.get("location"),
                    )
        except zlib.error as exc:
            raise FetchError("unsupported_encoding") from exc
        except (httpx.HTTPError, OSError) as exc:
            raise FetchError("fetch_failed") from exc

    async def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        if origin not in self._robots:
            result, _ = await self._request(origin + "/robots.txt")
            if result.status_code in (404, 410):
                self._robots[origin] = None
            elif result.status_code == 200:
                # HTML challenge pages are not an empty allow-all robots file.
                if result.content_type not in {"text/plain", ""}:
                    raise FetchError("robots_unavailable")
                parser = RobotFileParser()
                parser.parse(result.body.decode("utf-8", errors="replace").splitlines())
                self._robots[origin] = parser
            else:
                raise FetchError("robots_unavailable")
        parser = self._robots[origin]
        if parser is not None and (
            not parser.can_fetch(USER_AGENT, url)
            or parser.crawl_delay(USER_AGENT)
            or parser.request_rate(USER_AGENT)
        ):
            # Do not pretend to honor pacing directives by fetching immediately.
            raise FetchError("robots_denied")

    async def fetch(self, url: str) -> FetchResult:
        try:
            original = validate_public_url(url)
        except ValueError as exc:
            raise FetchError("unsafe_url") from exc
        current = original
        seen: set[str] = set()
        for _ in range(4):
            if current in seen:
                raise FetchError("redirect_limit")
            seen.add(current)
            await self._check_robots(current)
            result, location = await self._request(current)
            if result.status_code in (301, 302, 303, 307, 308):
                if not location:
                    raise FetchError("fetch_failed")
                try:
                    target = validate_public_url(urljoin(current, location))
                except ValueError as exc:
                    raise FetchError("unsafe_url") from exc
                if current.startswith("https:") and target.startswith("http:"):
                    raise FetchError("unsafe_url")
                current = target
                continue
            if result.status_code != 200:
                raise FetchError("http_denied")
            if result.content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise FetchError("unsupported_content")
            return FetchResult(original, current, result.body, result.content_type)
        raise FetchError("redirect_limit")
