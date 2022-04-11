from .util import *
from .base import BaseSpider as Base
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
import re

BASE_URL = 'https://www.mormaiishop.com.br/'
PAGES = {
    'roupas': 10,
    'mormaii': 51
}
PATHS = (
    f'{path}?PS=72#{index}'
    for path, page_count in PAGES.items()
    for index in range(1, page_count)
)

LINK_SELECTOR = '//div[@class="prateleira-padrao__item"]/a[@class="prateleira-padrao__item--link"]'
NEXT_PAGE_SELECTOR = '//'
NAME_SELECTOR = '//div[@class="product-info__content"]/h1/text()'
CATEGORY_SELECTOR = '//div[@class="bread-crumb"]/ul/li[3]/text()'
SUBCATEGORY_SELECTOR = '//li[@class="last" and @itemprop="itemListElement"]/a[@itemprop="item"]/span[@itemprop="name"]/text()'
PRICE_SELECTOR = '//em[@class="valor-por price-best-price"]/strong[@class="skuBestPrice"]/text()'
COMPOSITION_SELECTOR = '//td[@class="value-field CARACTERISTICA"]/text()'
GENDER_SELECTOR = '//td[@class="value-field Genero"]/text()'
AGE_SELECTOR = '//td[@class="value-field DIVISAO"]/text()'
DESCRIPTION_SELECTOR = '//div[@class="productDescription"]//text()'
IMG_URL_SELECTOR = '//img[@id="image-main"]/@src'

ATTRIBUTES = ('name', 'price', 'composition', 'gender', 'age',
              'category', 'subcategory', 'description', 'img_url')
SELECTORS = get_selectors(ATTRIBUTES, globals())


class MormaiiSpider(Base):
    name = 'mormaii'
    start_urls = get_start_urls(BASE_URL, PATHS)
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)

    def parse(self, response: HtmlResponse):
        # Composição / Material
        extracted_composition: str = response.xpath(
            COMPOSITION_SELECTOR).extract_first(EMPTY)
        matches = re.findall(
            r'\d+[,\.]?\d*?%(?: de)? [A-zà-ÿ]+', extracted_composition.lower())
        values = '|'.join(('da', 'das', 'dos', 'de'))
        filtered_values = filter(lambda x: not re.match(
            rf'\d+[,\.]?\d*?% ({values})', x), matches)
        unique_values = set(filtered_values)
        composition = ' '.join(sorted(unique_values))

        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
            'composition': composition or extracted_composition,
        }
