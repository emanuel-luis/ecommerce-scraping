from operator import add
from threading import Thread
from typing import Any, Iterable, Union
from scrapy.http import HtmlResponse
from datetime import datetime
import re

try:
    from ecommerce.ecommerce.settings import LOG_LEVEL
except ModuleNotFoundError:
    from ecommerce.settings import LOG_LEVEL

EMPTY = str()


def get_custom_settings(name: str, *, log_level=LOG_LEVEL) -> dict[str, dict]:
    return {
        'LOG_LEVEL': log_level,
        'FEEDS': {
            f'./products/{name}.csv': {
                'format': 'csv',
                'encoding': 'utf-8',
            },
            f'./products/{name}.json': {
                'format': 'json',
                'encoding': 'utf-8',
            }
        },
    }


def get_current_date(_format: str = '%d-%m-%Y') -> str:
    dt_now = datetime.now()
    return dt_now.strftime(_format)


def get_start_urls(base_url: str, paths: Iterable[str]) -> tuple[str]:
    return tuple(add(base_url, path) for path in paths)


def get_selectors(attrs: Iterable[str], globals: dict[str, Any]):
    def get_selector(value: str) -> str:
        selector = f'{value.upper()}_SELECTOR'
        return globals.get(selector, '//*/html')

    return tuple(get_selector(attr) for attr in attrs)


def get_attributes(attrs: Iterable[str], selectors: Iterable[str],
                   response: HtmlResponse, *,
                   default=EMPTY) -> dict[str, Union[str, None]]:
    def get_attribute(selector: str):
        value: str = response.xpath(selector).extract_first(default)
        value = re.sub(r'[\n\t]', ' ', value).strip()
        while '  ' in value:
            value = value.replace('  ', ' ').strip()

        return value

    return {
        **dict(zip(attrs, map(get_attribute, selectors))),
        'url': response.url,
        'scrapped-at': get_current_date()
    }
