import re
from scrapy.http import HtmlResponse
from .util import *
from scrapy.linkextractors import LinkExtractor
from .base import BaseSpider as Base

START_URLS = ['https://www.hering.com.br/store/pt/search?'
              'q=%3Arelevance%3Agender%3Ababy.FEMALE%3Agender'
              '%3Ababy.MALE%3Agender%3AFEMALE%3Agender%3AMALE'
              '%3Agender%3Akids.FEMALE%3Agender%3Akids.MALE'
              '%3Acategory%3A041%3Acategory%3A089%3Acategory'
              '%3A798%3Acategory%3A016%3Acategory%3A045%3Acategory'
              '%3A028%3Acategory%3A043%3Acategory%3A021%3Acategory'
              '%3A038%3Acategory%3A018%3Acategory%3A049%3Acategory'
              '%3A796%3Acategory%3A064%3Acategory%3A755%3Acategory'
              '%3A030%3Acategory%3A054%3Acategory%3A795%3Acategory'
              '%3A055%3Acategory%3A051%3Acategory%3A084%3Acategory'
              '%3A025%3Acategory%3A022']
LINK_SELECTOR = '//section[@class="section-carousel"]/div/div[@class="box-product__footer"]/p/a'
NEXT_PAGE_SELECTOR = '//ul[@class="pagination"]/li[@class="next"]/a/@href'
NAME_SELECTOR = '//li[@class="breadcrumb-item active"]/span/text()'
PRICE_SELECTOR = '//div[@class="product-price"]/meta[@itemprop="price"]/@content'
GENDER_SELECTOR = '//li[@itemprop="itemListElement"][1]/a/span/text()'
CATEGORY_SELECTOR = '//li[@itemprop="itemListElement"][3]/a/span/text()'
DESCRIPTION_SELECTOR = '//div[@id="tab1"]/div[@class="text"]/text()'
COMPOSITION_SELECTOR = '//ul[@class="features"]/li[3]/span[2]/text()'
IMG_URL_SELECTOR = '//div[@class="main-image"]/img/@src'
COLOR_SELECTOR = '//div[@class="box-colors"]/span[@class="title"]/span[@class="font-weight-normal"]/text()'
ATTRIBUTES = ('name', 'price', 'gender', 'composition',
              'category', 'color', 'description', 'img_url')
SELECTORS = get_selectors(ATTRIBUTES, globals())


class HeringSpider(Base):
    name = 'hering'
    start_urls = START_URLS
    custom_settings = get_custom_settings(name)
    next_page = HtmlResponse.xpath, NEXT_PAGE_SELECTOR
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)

    def parse(self, response: HtmlResponse):
        _composition: str = response.xpath(
            COMPOSITION_SELECTOR).extract_first(EMPTY)
        _composition = re.sub(r'[^\w\d%,\. ]', EMPTY, _composition).strip()
        _description = response.xpath(
            DESCRIPTION_SELECTOR).extract_first(EMPTY)

        composition = ' '.join(sorted(_composition.split('+'))).strip().lower()
        description = re.sub(r'[^\w ]', EMPTY, _description).strip()

        while any('  ' in value for value in (composition, description)):
            composition = composition.replace('  ', ' ')
            description = description.replace('  ', ' ')

        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
            'composition': composition,
            'description': description,
        }
