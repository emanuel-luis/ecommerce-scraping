"""Offline fixture site: one loopback HTTP server per store, serving tests/fixtures/site."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SITE = FIXTURES / "site"
PAGES = FIXTURES / "pages"

_PAGE_FOR_PATH = {  # lowercased path -> synthetic page; anything not listed is a store page
    "/no-jsonld-product/p": "synthetic_no_jsonld.html",
    "/renamed-product/p": "synthetic_graph_only.html",
}
_STORE_PAGE_PATHS = {"/fixture-product/p", "/second-sitemap-product/p", "/blocked-product/p"}
_TEMPLATES = {
    "/robots.txt": ("robots.txt", "text/plain"),
    "/sitemap.xml": ("sitemap.xml", "application/xml"),
    "/sitemap/product-0.xml": ("sitemap/product-0.xml", "application/xml"),
    "/sitemap/product-1.xml": ("sitemap/product-1.xml", "application/xml"),
}


@dataclass
class FixtureSite:
    store: str
    mode: str = "normal"  # "blocked" answers 403 to every path
    base: str = ""
    requests: list[tuple[str, str]] = field(default_factory=list)  # (path, User-Agent)
    server: ThreadingHTTPServer | None = None

    @property
    def paths(self) -> list[str]:
        return [path for path, _ua in self.requests]

    def _respond(self, path: str) -> tuple[int, str, bytes, dict[str, str]]:
        lowered = path.lower()
        if self.mode == "blocked":
            return 403, "text/plain", b"forbidden", {}
        if lowered in _TEMPLATES:
            name, ctype = _TEMPLATES[lowered]
            text = (SITE / name).read_text(encoding="utf-8").replace("{{BASE}}", self.base)
            return 200, ctype, text.encode(), {}
        if lowered == "/old-fixture-product/p":
            return 301, "text/plain", b"", {"Location": "/renamed-product/p"}
        page = _PAGE_FOR_PATH.get(lowered) or (
            f"{self.store}.html" if lowered in _STORE_PAGE_PATHS else None
        )
        if page is None:
            return 404, "text/plain", b"not found", {}
        return 200, "text/html; charset=utf-8", (PAGES / page).read_bytes(), {}


def _handler(site: FixtureSite) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            site.requests.append((self.path, self.headers.get("User-Agent", "")))
            status, ctype, body, headers = site._respond(self.path.split("?")[0])
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return Handler


@pytest.fixture
def start_site() -> Iterator[Callable[..., FixtureSite]]:
    """Factory: start_site("levi", mode="blocked") -> a running FixtureSite on 127.0.0.1."""
    sites: list[FixtureSite] = []

    def start(store: str, mode: str = "normal") -> FixtureSite:
        site = FixtureSite(store, mode)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(site))
        server.daemon_threads = True
        site.server = server
        site.base = f"http://127.0.0.1:{server.server_address[1]}"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        sites.append(site)
        return site

    yield start
    for site in sites:
        if site.server is not None:
            site.server.shutdown()
            site.server.server_close()
