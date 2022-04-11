from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from .util import *
from .base import BaseSpider as Base


BASE_URL = 'https://www.damyller.com.br/'
PATHS = 'moda-feminina', 'moda-masculina'

LINK_SELECTOR = '//article[starts-with(@class, "vitrine__product")]/div[@class="vitrine__group"]/h2/a'
NAME_SELECTOR = '//h1[@class="productMain__name"]/div/text()'
PRICE_SELECTOR = '//div[@class="productMain__price--skuPrice"]/text()'
CATEGORY_SELECTOR = '//li[@class="last"]/a/span/text()'
DESCRIPTION_SELECTOR = '//div[@class="productDescription"]/text()'
IMG_URL_SELECTOR = '//a[@class="ON" and @id="botaoZoom"]/img/@src'
COMPOSITION_SELECTOR = '//td[@class="value-field Material"]/text()'
LEATHER_SELECTOR = '//td[@class="value-field Tecido"]/text()'
GENDER_SELECTOR = '//td[@class="value-field Genero"]/text()'
ATTRIBUTES = ('name', 'price', 'gender', 'category', 'composition',
              'leather', 'description', 'img_url')
SELECTORS = get_selectors(ATTRIBUTES, globals())


class DamyllerSpider(Base):
    name = 'damyller'
    start_urls = get_start_urls(BASE_URL, PATHS)
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)

    def start_requests(self):
        handler = Selenium()
        for url in self.start_urls:
            response = handler.load_page(url, 5)
            yield from self.parse_result(response)
        handler.quit()

    def parse(self, response: HtmlResponse):
        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
        }
