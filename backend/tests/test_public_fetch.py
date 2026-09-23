import asyncio
import gzip
import json
import zlib

import httpx
import pytest

from tianji_lab import public_fetch as pf


class RawStream(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = body

    async def __aiter__(self):
        for start in range(0, len(self.body), 128):
            yield self.body[start : start + 128]


def mock_network(monkeypatch, handler):
    original = httpx.AsyncClient
    seen = []

    async def resolve(host, port):
        return ["93.184.216.34"]

    def respond(request):
        seen.append(request)
        status, headers, body = handler(request)
        return httpx.Response(status, headers=headers, stream=RawStream(body))

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(pf, "resolve_public", resolve)
    monkeypatch.setattr(pf.httpx, "AsyncClient", client)
    return seen


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://[::1]/",
        "http://169.254.169.254/",
        "http://198.18.0.1/",
        "http://[::ffff:8.8.8.8]/",
        "http://224.0.0.1/",
        "http://user:secret@example.com/",
        "file:///etc/passwd",
        "https://example.com:8443/",
        "https://localhost/",
        "https://example.com\\@127.0.0.1/",
        "https://a.local/",
        "https://example.com/\nsecret",
        "http://[64:ff9b::7f00:1]/",
    ],
)
def test_unsafe_url(url):
    with pytest.raises(ValueError):
        pf.validate_public_url(url)


def test_dns_rejects_any_nonpublic_answer(monkeypatch):
    async def run():
        async def records(*args, **kwargs):
            return [(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("127.0.0.1", 443))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", records)
        with pytest.raises(pf.FetchError, match="unsafe_address"):
            await pf.resolve_public("example.com", 443)

    monkeypatch.delenv("TIANJI_RESEARCH_DNS", raising=False)
    asyncio.run(run())


def test_pinned_host_sni_no_credentials_and_robots(monkeypatch):
    def handler(request):
        if request.url.path == "/robots.txt":
            return (
                200,
                {"content-type": "text/plain", "set-cookie": "secret=value"},
                b"User-agent: *\nAllow: /",
            )
        assert "cookie" not in request.headers
        assert "authorization" not in request.headers
        return 200, {"content-type": "text/html"}, b"<p>Public body</p>"

    seen = mock_network(monkeypatch, handler)
    fetcher = pf.PublicFetcher(1024, 2048)
    result = asyncio.run(fetcher.fetch("https://example.com/article"))
    assert result.resolved_url == "https://example.com/article"
    assert len(seen) == 2
    assert all(request.url.host == "93.184.216.34" for request in seen)
    assert all(request.headers["host"] == "example.com" for request in seen)
    assert all(request.extensions["sni_hostname"] == "example.com" for request in seen)
    assert fetcher.fetched_bytes == len(b"User-agent: *\nAllow: /") + len(result.body)


def test_redirect_to_private_is_never_requested(monkeypatch):
    def handler(request):
        if request.url.path == "/robots.txt":
            return 404, {}, b""
        return 302, {"location": "http://127.0.0.1/private"}, b""

    seen = mock_network(monkeypatch, handler)
    with pytest.raises(pf.FetchError, match="unsafe_url"):
        asyncio.run(pf.PublicFetcher(1024, 2048).fetch("https://example.com/a"))
    assert len(seen) == 2


@pytest.mark.parametrize(
    "headers,body,code",
    [
        ({"content-type": "text/plain"}, b"a" * 1025, "fetch_byte_limit"),
        ({"content-encoding": "gzip"}, b"compressed", "unsupported_encoding"),
        ({"content-length": "99999"}, b"", "fetch_byte_limit"),
        ({"content-type": "application/pdf"}, b"%PDF", "unsupported_content"),
    ],
)
def test_limits_and_content(monkeypatch, headers, body, code):
    def handler(request):
        return (404, {}, b"") if request.url.path == "/robots.txt" else (200, headers, body)

    mock_network(monkeypatch, handler)
    fetcher = pf.PublicFetcher(1024, 1024)
    with pytest.raises(pf.FetchError, match=code):
        asyncio.run(fetcher.fetch("https://example.com/a"))
    assert fetcher.fetched_bytes <= 1024


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
@pytest.mark.parametrize("size", [1000, 1024, 65536])
def test_bounded_decompression(monkeypatch, encoding, compress, size):
    body = b"a" * size
    encoded = compress(body)

    def handler(request):
        if request.url.path == "/robots.txt":
            return 404, {}, b""
        return 200, {"content-type": "text/plain", "content-encoding": encoding}, encoded

    mock_network(monkeypatch, handler)
    counted = []
    fetcher = pf.PublicFetcher(1024, 2048, on_bytes=counted.append)
    if size > 1024:
        # Compressed input fits: rejection must come from the decoded-size cap.
        assert len(encoded) < 1024
        with pytest.raises(pf.FetchError, match="fetch_byte_limit"):
            asyncio.run(fetcher.fetch("https://example.com/a"))
    else:
        result = asyncio.run(fetcher.fetch("https://example.com/a"))
        assert result.body == body
        assert fetcher.fetched_bytes == len(encoded)
    assert fetcher.fetched_bytes == sum(counted)
    assert fetcher.fetched_bytes <= 1024


@pytest.mark.parametrize("malform", [lambda b: b[:-1], lambda b: b + b, lambda b: b + b"junk"])
def test_gzip_truncated_or_trailing_data_rejected(monkeypatch, malform):
    encoded = malform(gzip.compress(b"valid public content" * 10))
    mock_network(
        monkeypatch,
        lambda request: (
            (404, {}, b"")
            if request.url.path == "/robots.txt"
            else (200, {"content-encoding": "gzip", "content-type": "text/plain"}, encoded)
        ),
    )
    with pytest.raises(pf.FetchError, match="unsupported_encoding"):
        asyncio.run(pf.PublicFetcher(1024, 2048).fetch("https://example.com/a"))


def test_robots_denial_stops_before_page(monkeypatch):
    seen = mock_network(
        monkeypatch,
        lambda req: (200, {"content-type": "text/plain"}, b"User-agent: *\nDisallow: /"),
    )
    with pytest.raises(pf.FetchError, match="robots_denied"):
        asyncio.run(pf.PublicFetcher(1024, 2048).fetch("https://example.com/a"))
    assert len(seen) == 1


def test_cloudflare_fixed_endpoint_validates_answers(monkeypatch):
    original = httpx.AsyncClient
    seen = []

    def handler(request):
        seen.append(request)
        body = json.dumps({"Status": 0, "Answer": [{"type": 1, "data": "198.18.0.1"}]}).encode()
        return httpx.Response(200, stream=RawStream(body))

    monkeypatch.setenv("TIANJI_RESEARCH_DNS", "cloudflare")
    monkeypatch.setattr(
        pf.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    with pytest.raises(pf.FetchError, match="unsafe_address"):
        asyncio.run(pf.resolve_public("example.com", 443))
    assert len(seen) == 2
    assert all(r.url.host == "1.1.1.1" and r.headers["host"] == "cloudflare-dns.com" for r in seen)
    assert all(r.extensions["sni_hostname"] == "cloudflare-dns.com" for r in seen)
