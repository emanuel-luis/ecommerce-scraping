from .base import BaseSpider as Base
from .util import *
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor


BASE_URL = 'https://www.levi.com.br/'
path_pages = {'masculino': 15,
              'feminino': 15,
              'kids/infantil': 7}

PATH = [f'{path}#{index}'
        for path, total_pages in path_pages.items()
        for index in range(1, total_pages+1)]


LINK_SELECTOR = '//div[@class="main"]//a[@class="highlight"]'
NAME_SELECTOR = '//h1/div[starts-with(@class, "fn productName")]/text()'
PRICE_SELECTOR = '//strong[@class="skuBestPrice"]/text()'
DESCRIPTION_SELECTOR = '//div[@class="productDescription"]/text()'
COMPOSITION_SELECTOR = '//td[@class="value-field Composicao"]/text()'
COLOR_SELECTOR = '//td[@class="value-field Cor"]/text()'
GENDER_SELECTOR = '//td[@class="value-field Genero"]/text()'
IMG_URL_SELECTOR = '//img[@id="image-main"]/@src'


ATTRIBUTES = ['name', 'price', 'category', 'composition',
              'color', 'gender', 'description', 'img_url']
SELECTORS = get_selectors(ATTRIBUTES, globals())


class LeviSpider(Base):
    name = 'levi'
    allowed_domains = ['levi.com.br']
    start_urls = get_start_urls(BASE_URL, PATH)
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)

    def parse(self, response: HtmlResponse):
        extracted: str = response.xpath(NAME_SELECTOR).extract_first(EMPTY)
        category, *_ = extracted.split() or ['Indefinido']

        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
            'category': category
        }
