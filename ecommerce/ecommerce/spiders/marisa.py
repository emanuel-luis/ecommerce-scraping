import scrapy
from .base import BaseSpider as Base
from .util import *
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
import re

BASE_URL = 'https://www.marisa.com.br/'
PATH_DICT: dict[str, tuple[str]] = {
    'roupas-m/masculino/c/':
        ('polos-m', 'bermudas-shorts-m', 'blusa-masculina-com-capuz',
         'blusa-masculina-sem-capuz', 'calcas-m', 'camisas-m', 'camisetas-m',
         'casacos-jaquetas-m', 'sueter-masculino', 'moletons-sueteres-m'),
    'roupas/feminino/c/': ('bermudas', 'blusas', 'calcas', 'camisas',
                           'casacos-jaquetas', 'shorts'),
    'meninos/infantil/c/': ('roupas-meninos',),
    'meninas/infantil/c/': ('roupas-meninas',)
}
QUERY = '?q=%3AnewOnStore%3Abrand%3Amarisa&text=#' # Filtrar apenas roupas da marca Marisa
PATHS = (
    path + subpath + QUERY
    for path, subpaths in PATH_DICT.items()
    for subpath in subpaths
)

NEXT_BUTTON_SELECTOR = '//button[@class="js-loadButton loadButton" and @data-label-load="Carregar Mais" and not (@disabled)]'
DIV_LOADER = '//div[@id="loader" and @class="bgLoader"]'
LINK_SELECTOR = '//div[@class="js-product-column col-xs-12 col-sm-4 m-t-20 col-md-4"]//a'

NAME_SELECTOR = '//input[@class="productName"]/@value'
PRICE_SELECTOR = '//input[@class="productPrice"]/@value'
CATEGORIES_SELECTOR = '//input[@class="productCategories"]/@value'
MATERIAL_SELECTOR = '//div[contains(text(), "Material:")]/text()'
COMPOSITION_SELECTOR = '//div[contains(text(), "Composição:")]/text()'
DESCRIPTION_SELECTOR = '//div[@id="description-tab-desktop"]//text()'
IMG_URL_SELECTOR = '//img[@class="product--image img-responsive"]//@src'
ATTRIBUTES = ['name', 'price', 'material', 'composition', 'gender', 'category',
              'subcategory', 'description', 'img_url']
SELECTORS = get_selectors(ATTRIBUTES, globals())


class MarisaSpider(Base):
    name = 'marisa'
    allowed_domains = ['www.marisa.com.br']
    start_urls = get_start_urls(BASE_URL, PATHS)
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)

    def start_requests(self):
        handler = Selenium()
        for url in self.start_urls:
            response = handler.load_on_button(
                url, NEXT_BUTTON_SELECTOR, loader=DIV_LOADER)
            yield from self.parse_result(response)

    def parse(self, response: HtmlResponse):
        extracted = response.xpath(DESCRIPTION_SELECTOR).extract()
        joined_text = ' '.join(extracted)
        cleaned_text = re.sub(r'[\n\t]', ' ', joined_text)
        cleaned_text = cleaned_text.replace(u'\xa0', u' ')
        while '  ' in cleaned_text:
            cleaned_text = cleaned_text.replace('  ', ' ').strip()
        description = cleaned_text

        extracted = response.xpath(COMPOSITION_SELECTOR).extract_first(EMPTY)
        cleaned = re.sub('Composição:', '', extracted).strip()
        sorted_values = sorted(map(str.strip, cleaned.split(',')))
        joined_values = ', '.join(sorted_values)
        composition = joined_values
        
        extracted = response.xpath(MATERIAL_SELECTOR).extract_first(EMPTY)
        cleaned = re.sub('Material:', '', extracted).strip()
        sorted_values = sorted(re.findall('\w{2,}', cleaned))
        joined_values = ', '.join(sorted_values)
        material = joined_values
        
        gender, * \
            _, category, subcategory = map(str.strip, response.xpath(
                CATEGORIES_SELECTOR).extract_first(EMPTY).split('-'))

        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
            'material': material,
            'description': description,
            'composition': composition,
            'gender': gender,
            'category': category,
            'subcategory': subcategory
        }
        pass
