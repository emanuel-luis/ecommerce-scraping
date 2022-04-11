from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from .util import *
from .base import BaseSpider as Base
import re

BASE_URL = 'https://www.daksuljeans.com.br/'
PATHS = 'loja/busca.php?loja=1052366',

LINK_SELECTOR = '//li[@class="product col-sm-4"]/div/a'
NEXT_PAGE_SELECTOR = '//a[text()="Próxima Página"]/@href'
PRICE_SELECTOR = '//input[@id="preco_atual"]/@value'
GENDER_SELECTOR = '//div[@class="breadcrumb"]/span[3]/a/@title'
NAME_SELECTOR = '//div[@class="col-md-5"]/h1[@class="product-name" and @itemprop="name"]/text()'
IMG_URL_SELECTOR = '//img[@id="imgView"]/@src'
DESCRIPTION_SELECTOR = '//div[@class="board_htm description"]//text()'
ATTRIBUTES = ('name', 'price', 'composition', 'category',
              'gender', 'description', 'img_url')
SELECTORS = get_selectors(ATTRIBUTES, globals())


class DaksulSpider(Base):
    name = 'daksul'
    start_urls = get_start_urls(BASE_URL, PATHS)
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)
    next_page = HtmlResponse.xpath, NEXT_PAGE_SELECTOR

    def parse(self, response: HtmlResponse):
        _name = response.xpath(NAME_SELECTOR).extract_first(EMPTY)
        if _name:
            name = re.sub(r'[^\w ]', EMPTY, _name).strip()
            piece_type = name.split()[0]
        else:
            name = EMPTY
            piece_type = EMPTY
        _description = ' '.join(response
                                .xpath(DESCRIPTION_SELECTOR)
                                .extract())

        _description = _description.replace('\n', ' ')
        while '  ' in _description:
            _description = _description.replace('  ', ' ')

        _description = re.sub(r'[^\w,% .:]', EMPTY, _description)
        _composition = re.findall(r'\d+[,\.]?\d*?% \w+',
                                  _description, re.IGNORECASE)
        _composition.sort()

        composition = ' '.join(_composition).strip().lower()
        description = re.sub(r'Composição.+', EMPTY,
                             _description, re.IGNORECASE).strip()

        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
            'category': piece_type,
            'description': description,
            'composition': composition,
            'name': name,
        }
