
# ecommerce-scrapping

> A data-ingestion crawler for e-commerce pages using **Scrapy** with **scrapy-splash** and
> **Selenium** for JavaScript-rendered content.

![python](https://img.shields.io/badge/python-3.9.6+-blue)
![Scrapy](https://img.shields.io/badge/Scrapy-60A839?logo=scrapy&logoColor=white)

## What this demonstrates

- **Web data ingestion** — extracting structured data from dynamic, JavaScript-heavy pages.
- **JS rendering at scale** — using a Splash render service (via Docker) alongside Scrapy.
- **Tooling fit** — choosing Splash/Selenium where plain HTTP scraping fails.

## Tech stack

Python 3.9.6+ · Scrapy · scrapy-splash · Selenium · js2py · Docker (Splash).

## Quickstart

```bash
pip install -r requirements.txt

# start the Splash render service (Docker) for JavaScript pages:
docker run -it -p 8050:8050 scrapinghub/splash --disable-private-mode

# run the crawler:
python main.py
```

## How it works

Scrapy drives the crawl; pages needing JavaScript are routed through Splash (`:8050`) so the
rendered DOM is available to selectors. Selenium handles flows Splash can't.

## Notes

- This is an early portfolio project; it's framed here as a **data-ingestion** demo.
- Respect target sites' `robots.txt` and terms of use; throttle requests.

## License

MIT (add a `LICENSE` file).
