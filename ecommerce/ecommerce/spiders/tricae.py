from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from .util import *
from .base import BaseSpider as Base
import re
import js2py

BASE_URL = 'https://www.tricae.com.br/'
CATEGORIES = 'casacos', 'bodies-e-culotes', 'macacoes', 'pijamas-camisolas', 'conjuntos'
PATHS = map(lambda x: f'{x}/tricae/', CATEGORIES)

LINK_SELECTOR = '//div[@class="product-list-col-3 col-md-9 main-list"]/div[@class="product-box"]'
NEXT_PAGE_SELECTOR = '//link[@rel="next"]/@href'
NAME_SELECTOR = '//h1[@class="product-name product-name-full" and @itemprop="name"]/text()'
PRICE_SELECTOR = '//span[@class="catalog-detail-price-value" and @itemprop="price"]/@content'
MATERIAL_SELECTOR = '//table[@class="product-informations"]/tbody/tr[3]/td[2]/text()'
COMPOSITION_SELECTOR = '//table[@class="product-informations"]/tbody/tr[4]/td[2]/text()'
DESCRIPTION_1_SELECTOR = '//div[@class="box-description"]//text()'
DESCRIPTION_2_SELECTOR = '//table[@class="product-informations"]/tbody//text()'
SCRIPT_SELECTOR = '//script[contains(text(), "dataLayer = [{")]/text()'
IMG_URL_SELECTOR = '//div[@class="gallery-preview"]/img[@class="gallery-preview-img product-image"]/@href'
ATTRIBUTES = ['name', 'price', 'material', 'composition', 'gender', 'category', 'is_kit', 'qt_pieces', 'description', 'img_url']
SELECTORS = get_selectors(ATTRIBUTES, globals())

class TricaeSpider(Base):
    name = 'tricae'
    allowed_domains = ['www.tricae.com.br']
    start_urls = get_start_urls(BASE_URL, PATHS)
    custom_settings = get_custom_settings(name)
    xlink = LinkExtractor(restrict_xpaths=LINK_SELECTOR)
    next_page = HtmlResponse.xpath, NEXT_PAGE_SELECTOR
    
    def parse(self, response: HtmlResponse):
        data_layer:dict
        
        extracted1 = response.xpath(DESCRIPTION_1_SELECTOR).extract()
        extracted2 = response.xpath(DESCRIPTION_2_SELECTOR).extract()
        extracted = extracted1 + extracted2
        joined_text = ' '.join(extracted)
        cleaned_text = re.sub(r'[\n\t]', ' ', joined_text).strip()
        while '  ' in cleaned_text:
            cleaned_text = cleaned_text.replace('  ', ' ').strip()
        
        script = response.xpath(SCRIPT_SELECTOR).extract_first(EMPTY)
        data_layer, *_ = js2py.eval_js(script) or [{}, ]
        gender = data_layer.get('gender', str())
        img_url = data_layer.get('image', response.xpath(IMG_URL_SELECTOR).extract_first(EMPTY)) or str()
        name:str = response.xpath(NAME_SELECTOR).extract_first(EMPTY) or data_layer.get('productName', str())
        category = data_layer.get('subCategory', name.split()[0])
        price = response.xpath(PRICE_SELECTOR).extract_first(EMPTY) or data_layer.get('price', str())
        description = cleaned_text
        is_kit = 'kit' in description.lower()
        qt_piece = re.sub(r'\D', '', name) if is_kit else 1
        
        yield {
            **get_attributes(ATTRIBUTES, SELECTORS, response),
            'gender': gender,
            'img_url': img_url,
            'category': category,
            'price': price,
            'name': name,
            'description': description,
            'is_kit': is_kit,
            'qt_pieces': qt_piece
        }
        
