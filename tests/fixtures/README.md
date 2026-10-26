# Test fixtures

Every test runs offline against these files. CI never contacts a store.

## `pages/`: redacted real product pages

| File | Source page | What it exercises |
| --- | --- | --- |
| `levi.html` | `https://www.levi.com.br/camiseta-levi-s-perfect-graphic-tee-lb0010208/p` | single `Offer`; HTML entities (`&apos;`) inside JSON strings |
| `tng.html` | `https://www.tng.com.br/cinto-social-giratorio-bnmcis30950/p` | `@graph` and navigation noise; two `Product` blocks for one product (hosts and SKUs differ); `AggregateOffer` with nested offers |
| `hering.html` | `https://www.hering.com.br/calca-basica-feminina-jogger-em-moletom-peluciado-05v2n10en/p` | `offers` as a list of `AggregateOffer` typed with `type` instead of `@type`; entity-encoded category; out of stock |
| `damyller.html` | `https://www.damyller.com.br/jaqueta-trucker-jeans-feminina-6i0sz14/p` | `http://schema.org/...` availability; integer price; store not in the live set (parser fixture only) |

Each page was fetched once on 2026-10-26 during the target probe (robots.txt checked first,
identifying User-Agent, at most four requests per site). It was then reduced to what the
pipeline reads:

1. `ecommerce_scraping.jsonld.redact_page`: canonical link and JSON-LD blocks only, every
   `review` / `reviews` key removed (customer names), body dropped. This is the same function
   the crawler applies before anything reaches the raw layer.
2. Every `description` value replaced with a placeholder (third-party marketing copy the
   pipeline does not use), corporate contact keys (`contactPoint`, `address`, `telephone`,
   `email`) dropped, navigation `ItemList`s cut to three entries.
3. `redact_page` again, so the file is in the canonical redacted format.

Prices, SKUs and availability are a snapshot of that day and will not match the live sites.
Do not refresh these files by crawling; if a store changes its markup, save one page by hand
under the same rules and record it here.
