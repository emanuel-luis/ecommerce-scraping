from typing import Callable, Iterable, Union
from scrapy.http import HtmlResponse
from scrapy_splash import SplashRequest
from scrapy.linkextractors import LinkExtractor
import scrapy


class BaseSpider(scrapy.Spider):
    name: str
    start_urls: Iterable[str]
    custom_settings: dict[str, Union[str, dict]]
    xlink: LinkExtractor
    next_page: tuple[Callable, str]

    def start_requests(self):
        for url in self.start_urls:
            yield SplashRequest(
                url=url,
                callback=self.parse_result,
                args={'wait': 2.5},
            )

    def parse_result(self, response: HtmlResponse):
        for link in self.xlink.extract_links(response):
            yield SplashRequest(
                url=link.url,
                callback=self.parse,
                args={'wait': 5},
            )

        if getattr(self, 'next_page', False):
            method, query = self.next_page
            result = method(response, query).extract_first()
            if result:
                url = response.urljoin(result)
                yield SplashRequest(
                    url=url,
                    callback=self.parse_result,
                    args={'wait': 2.5}
                )
