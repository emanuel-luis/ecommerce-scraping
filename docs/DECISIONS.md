# Decisions

Low-impact decisions follow the recommended option of the refactor brief; high-impact ones
(history rewrite, licensing, paid services, anything irreversible or outward-facing) need the
owner's answer.

| # | Date | Decision | Choice | Why |
| --- | --- | --- | --- | --- |
| 1 | 2026-10-26 | Rewrite history to drop `products/` and `geckodriver.exe` | No rewrite | Only size is at stake (17 MB of 2022 CSV/JSON and a 3.2 MB driver); nothing secret was committed. A rewrite would break every clone for little gain. |
| 2 | 2026-10-26 | `README.md` / `readme.md` case collision | Keep `README.md`, drop `readme.md` (2022, pt-BR) from the index | Case-insensitive checkouts wrote one file over the other, so git reported `README.md` as modified. The old text stays in history. |
| 3 | 2026-10-26 | Tracked run output and binaries | Untrack `products/` and `ecommerce/bin/geckodriver.exe`; ignore them | They are crawl output and a vendored Windows binary, not source. |
| 4 | 2026-10-26 | Default branch | `main` (renamed on GitHub and locally before this refactor) | Program-wide decision. |
| 5 | 2026-10-26 | Which targets stay | Live: Hering, Levi's, TNG. Damyller: one saved page kept as a parser fixture only. Dropped: Afabula, Alphabeto, Daksul, Lupo, Marisa, Mormaii, Tricae | A polite probe on 2026-10-26 (robots.txt first, at most 4 requests per site, 3 s apart, identifying User-Agent) found that Hering, Levi's, TNG and Damyller allow their sitemaps and product pages and serve schema.org `Product` JSON-LD. The brief caps the live set at 2-3 stores; Damyller is the fourth. Daksul answers `robots.txt` with 403, Lupo moved to Shopify and answered 429 on the fourth request, Tricae now redirects to Dafiti, Mormaii disallows every URL with a query string and lists no sitemap, Marisa's product sitemap timed out, Afabula's product page has no structured data, and Alphabeto's sampled product redirected to the home page. Nothing is ever fetched against robots.txt or past an anti-bot response. |
| 6 | 2026-10-26 | Product discovery | The sitemaps listed in each store's `robots.txt` (`/sitemap.xml` -> `product-N.xml`) instead of category listings | The 2022 listing URLs use query parameters (`?PS=`, `?page=`) that several stores now disallow, and sitemaps are the crawl entry point the sites publish for bots. |
| 7 | 2026-10-26 | Extraction | schema.org `Product` JSON-LD instead of XPath on CSS classes | Server-rendered on every kept store, stable across theme changes, and typed (price, currency, availability, SKU, GTIN). The 2022 class-based selectors no longer match. |
| 8 | 2026-10-26 | JavaScript rendering | None: Splash, Selenium, the geckodriver and js2py are removed; scrapy-playwright is not added | The data the pipeline needs is in the server-rendered HTML of every kept store. |
| 9 | 2026-10-26 | Personal data in pages | Customer reviews (author names, review text) are never extracted or stored; saved fixtures have them removed | Hering's JSON-LD embeds reviews with customers' names. The pipeline only needs catalog data. |
