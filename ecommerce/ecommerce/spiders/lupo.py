from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from .util import *
from .base import BaseSpider as Base
import re

BASE_URL = 'https://www.lupo.com.br/'
PATHS = 'produtos',

LINK_SELECTOR = '//li[@class="produtos"]/span/span[@class="mx-product-image"]/figure/a[@class="product-image"]'
NAME_SELECTOR = '//div[starts-with(@class, "fn productName")]/h1/text()'
SUB_CATEGORY_SELECTOR = '//li[@class="last"]/a/span/text()'
CATEGORY_SELECTOR = '//li[@itemprop="itemListElement"][3]/a/span/text()'
PRICE_SELECTOR = '//strong[@class="skuBestPrice"]/text()'
IMG_URL_SELECTOR = '//img[@id="image-main"]/@src'
DESCRIPTION_SELECTOR = '//div[@class="productDescription"]//text()'
ATTRIBUTES = ('name', 'price', 'composition', 'material-sum',
              'age', 'category', 'sub_category', 'description', 'img_url')
SELECTORS = get_selectors(ATTRIBUTES, globals())


class LupoSpider(Base):
    name = 'lupo'
    start_urls = get_start_urls(BASE_URL, PATHS)
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)

    def start_requests(self):
        handler = Selenium()

        for url in self.start_urls:
            response = handler.load_page(url, 2.5)
            yield from self.parse_result(response)

        handler.quit()

    def parse(self, response: HtmlResponse):
        def get_composition(pattern):
            first_pattern = pattern == r'\d+[,\.]?\d*?%,? (?:de )?[A-zà-ÿ]+'
            matches = re.findall(pattern, _description.lower())
            cleared_de = map(lambda x: re.sub(r' de ', ' ', x), matches)
            cleared_commas = map(lambda x: re.sub('%,', '%', x), cleared_de)
            if first_pattern:
                non_empty_values = filter(lambda x: re.match(
                    r'\d+[,\.]?\d*?% [A-zà-ÿ]+', x), cleared_commas)
            else:
                non_empty_values = filter(lambda x: re.match(
                    r'[A-zà-ÿ]+ \d+[,\.]?\d*?%', x), cleared_commas)

            composition = set(non_empty_values)
            only_numbers = map(lambda x: re.sub(
                r'[^\d.]', ' ', x), composition)
            float_values = map(float, only_numbers)
            if not first_pattern:
                _composition = []
                for c in composition:
                    num, material = c.split()
                    _composition.append(f'{material} {num}')
                composition = _composition

            return ' '.join(sorted(composition)), sum(float_values) / 100

        _name: str = response.xpath(NAME_SELECTOR).extract_first(EMPTY)
        _price: str = response.xpath(PRICE_SELECTOR).extract_first(EMPTY)
        _description: str = response.xpath(DESCRIPTION_SELECTOR).extract()
        _description = ' '.join(_description)

        _description = re.sub(r'[^\d\w,%.:]', ' ', _description)
        while '  ' in _description:
            _description = _description.replace('  ', ' ').strip()

        pattern = r'\d+[,\.]?\d*?%,? (?:de )?[A-zà-ÿ]+'
        composition, _sum = get_composition(pattern)
        if not _sum.is_integer():
            pattern = r'[A-zà-ÿ]+ \d+[,\.]?\d*?%'
            composition, _sum = get_composition(pattern)

        age, *_ = re.findall(r'\((\w+)\)', _name)
        name = re.sub(rf'\({age}\)', EMPTY, _name).strip()
        if name.endswith('-'):
            name = name.replace('-', '').strip()

        price = re.sub(r'[^\d,]', EMPTY, _price).strip()
        description = _description

        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
            'name': name,
            'price': price,
            'age': age,
            'composition': composition,
            'description': description,
            'material-sum': _sum
        }
