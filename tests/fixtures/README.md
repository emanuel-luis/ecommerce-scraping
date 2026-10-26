# Test fixtures

Every test runs offline against these files. CI never contacts a store.

`synthetic_*.html` pages are hand-written edge cases (no JSON-LD, invalid JSON, a Product only
inside `@graph`, reviews by the fake person "Zelda Synthetic"). `site/` holds the templates
of the offline fixture site the end-to-end test crawls (`{{BASE}}` is replaced with the local
server's address).

## `pages/`: redacted real product pages

| File | Source page | What it exercises |
| --- | --- | --- |
| `levi.html` | `https://www.levi.com.br/camiseta-levi-s-perfect-graphic-tee-lb0010208/p` | single `Offer`; HTML entities (`&apos;`) inside JSON strings |
| `tng.html` | `https://www.tng.com.br/cinto-social-giratorio-bnmcis30950/p` | two `Product` blocks for one product (hosts and SKUs differ); `AggregateOffer` with nested offers |
| `hering.html` | `https://www.hering.com.br/calca-basica-feminina-jogger-em-moletom-peluciado-05v2n10en/p` | `offers` as a list of `AggregateOffer` typed with `type` instead of `@type`; entity-encoded category; out of stock |
| `damyller.html` | `https://www.damyller.com.br/jaqueta-trucker-jeans-feminina-6i0sz14/p` | `http://schema.org/...` availability; integer price; store not in the live set (parser fixture only) |

Each page was fetched once on 2026-10-26 during the target probe (robots.txt checked first,
identifying User-Agent, at most four requests per site). It was then reduced to what the
pipeline reads:

1. `ecommerce_scraping.jsonld.redact_page`: the canonical link and one JSON-LD block per
   schema.org `Product` node; reviews, authors and any `Person` or `Review` node removed
   (customer names); breadcrumbs, organization and navigation blocks and the body dropped.
   This is the same function the crawler applies before anything reaches the raw layer.
2. Every `description` value replaced with a placeholder (third-party marketing copy the
   pipeline does not use).
3. `redact_page` again, so the file is in the canonical redacted format.

Prices, SKUs and availability are a snapshot of that day and will not match the live sites.
Do not refresh these files by crawling; if a store changes its markup, save one page by hand
under the same rules and record it here.
