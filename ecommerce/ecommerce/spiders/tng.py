from .base import BaseSpider as Base
from .util import *
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor


BASE_URL = 'https://www.tng.com.br/'
query = '?PS=48'
path_pages = {
    'masculino' + query: 30,
    'feminino' + query: 13
}
PATH = [f'{path}#{index}'
        for path, total_pages in path_pages.items()
        for index in range(1, total_pages+1)]
LINK_SELECTOR = '//div[@data-product-id]'

NAME_SELECTOR = '//h1[@class="full-product__name"]/text()'
PRICE_SELECTOR = '//div[@class="productPrice"]//strong[@class="skuBestPrice"]/text()'
CATEGORY_SELECTOR = '//div[@class="bread-crumb"]/ul/li[not(@itemprop)]/text()'
SUBCATEGORY_SELECTOR = '//div[@class="bread-crumb"]/ul/li[@class="last"]/text()'
COMPOSITION_SELECTOR = '//td[@class="value-field Composicao"]/text()'
COLOR_SELECTOR = '//td[@class="value-field Cor"]/text()'
GENDER_SELECTOR = '//td[@class="value-field Genero"]/text()'
DESCRIPTION_SELECTOR = '//div[@class="productDescription"]/text()'
IMG_URL_SELECTOR = '//div[@id="include"]//img/@src'

ATTRIBUTES = ['name', 'price', 'category', 'subcategory',
              'composition', 'color', 'gender', 'description',
              'img_url']
SELECTORS = get_selectors(ATTRIBUTES, globals())

class TngSpider(Base):
    name = 'tng'
    allowed_domains = ['www.tng.com.br']
    start_urls = get_start_urls(BASE_URL, PATH)
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)

    def parse(self, response: HtmlResponse):
        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response)
        }
