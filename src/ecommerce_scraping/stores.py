"""The store registry and the URL patterns shared by every store."""

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

PRODUCT_SITEMAP_RE = r"/sitemap/product-\d+\.xml$"
PRODUCT_URL_RE = r"/p$"


@dataclass(frozen=True)
class Store:
    name: str
    base_url: str

    @property
    def sitemap_url(self) -> str:
        return f"{self.base_url}/sitemap.xml"

    @property
    def allowed_domains(self) -> list[str]:
        return [urlparse(self.base_url).hostname or ""]


STORES: dict[str, Store] = {
    s.name: s
    for s in (
        Store("hering", "https://www.hering.com.br"),
        Store("levi", "https://www.levi.com.br"),
        Store("tng", "https://www.tng.com.br"),
    )
}


def resolve_store(name: str, overrides: Mapping[str, str]) -> Store:
    if name not in STORES:
        raise ValueError(f"unknown store {name!r}; known: {', '.join(STORES)}")
    base_url = overrides.get(name, STORES[name].base_url)
    return Store(name, base_url.rstrip("/"))
