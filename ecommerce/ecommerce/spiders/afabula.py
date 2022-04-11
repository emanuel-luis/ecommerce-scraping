from .base import BaseSpider as Base
from .util import *
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor

query = '?PS=50&pg={}'
pages = {
    'bebes': 3,
    'meninos': 3,
    'meninas': 8,
    'admin': 18
}
BASE_URL = 'https://www.afabula.com.br/'
PATHS = (path + query.format(index)
         for path, index in pages.items())

LINK_SELECTOR = '//div[@class="prateleira n24colunas"]'
NAME_SELECTOR = '//div/h1/span[@class="product-name"]/text()'
PRICE_SELECTOR = '//p/em/strong[@class="skuBestPrice"]/text()'
COMPOSITION_SELECTOR = '//div/div[@class="productComposition"]/text()'
DESCRIPTION_SELECTOR = '//div/div[@class="productDescription"]//text()'
GENDER_SELECTOR = '//div[@class="bread-crumb"]/ul/li[2]/a/span/text()'
CATEGORY_SELECTOR = '//li[@class="last"]/a/span/text()'
IMG_URL_SELECTOR = '//img[@id="thumb0"]/@src'

ATTRIBUTES = ('name', 'price', 'composition', 'gender',
              'category', 'description', 'img_url')
SELECTORS = get_selectors(ATTRIBUTES, globals())


class AfabulaSpider(Base):
    name = 'afabula'
    start_urls = get_start_urls(BASE_URL, PATHS)
    allowed_domains = ['afabula.com.br']
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)

    def parse(self, response: HtmlResponse):
        _description = response.xpath(DESCRIPTION_SELECTOR).extract()
        _description = ' '.join(_description).strip()
        while '  ' in _description:
            _description = _description.replace('  ', ' ').strip()

        description = _description

        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
            'description': description,
        }
