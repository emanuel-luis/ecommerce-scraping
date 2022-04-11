from .base import BaseSpider as Base
from .util import *
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
import re

BASE_URL = 'https://www.alphabeto.com/'
PAGES = (('meninas', 30), ('meninos', 30))
PATHS = (f'{path}?page={index}'
         for path, page_count in PAGES
         for index in range(1, page_count))

LINK_SELECTOR = '//div[@id="gallery-layout-container"]'
NAME_SELECTOR = '//h1/span[@class="vtex-store-components-3-x-productBrand vtex-store-components-3-x-productBrand--product "]/text()'
PRICE_SELECTOR = '//span[@class="vtex-product-price-1-x-sellingPriceValue vtex-product-price-1-x-sellingPriceValue--product"]//text()'
COMPOSITION_SELECTOR = '//td[@class="vtex-store-components-3-x-specificationItemSpecifications w-50 b--muted-4 bb pa5"]//text()'
DESCRIPTION_SELECTOR = '//div[@class="vtex-store-components-3-x-content h-auto"]//text()'
AGE_SELECTOR = '//a[@class="vtex-breadcrumb-1-x-link vtex-breadcrumb-1-x-link--2 dib pv1 link ph2 c-muted-2 hover-c-link"]/text()'
CATEGORY_SELECTOR = '//a[@class="vtex-breadcrumb-1-x-link vtex-breadcrumb-1-x-link--3 dib pv1 link ph2 c-muted-2 hover-c-link"]/text()'
GENDER_SELECTOR = '//a[@class="vtex-breadcrumb-1-x-link vtex-breadcrumb-1-x-link--1 dib pv1 link ph2 c-muted-2 hover-c-link"]/text()'
IMG_URL_SELECTOR = '//img[@class="vtex-store-components-3-x-productImageTag vtex-store-components-3-x-productImageTag--product vtex-store-components-3-x-productImageTag--main vtex-store-components-3-x-productImageTag--product--main"]/@href'
ATTRIBUTES = ('name', 'price', 'composition', 'age',
              'category', 'gender', 'description')
SELECTORS = get_selectors(ATTRIBUTES, globals())


class AlphabetoSpider(Base):
    name = 'alphabeto'
    start_urls = get_start_urls(BASE_URL, PATHS)
    allowed_domains = ['www.alphabeto.com']
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)

    def parse(self, response: HtmlResponse):
        _price = response.xpath(PRICE_SELECTOR).extract()
        _price = ''.join(_price)
        _price = re.sub(r'[^\d,\.]', EMPTY, _price)
        _description = response.xpath(DESCRIPTION_SELECTOR).extract()
        _description = ' '.join(_description)
        _description = re.sub(r'[\n\t]', EMPTY, _description)
        _composition = response.xpath(COMPOSITION_SELECTOR).extract()
        _composition = ' '.join(_composition)
        _composition = re.sub(
            r'[\n\t]|(\([\d, ea]+(anos|dias|meses|ano|dia|mes)\),? ?)*', EMPTY, _composition)
        _composition = re.sub(r'[^\dA-zÀ-ÿ%,\. /\\]', EMPTY, _composition).strip()
        price = _price
        composition = _composition

        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
            'composition': composition,
            'price': price,
        }
