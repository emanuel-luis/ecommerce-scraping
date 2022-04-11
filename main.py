from twisted.internet import reactor, defer
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
from ecommerce.ecommerce.spiders import SPIDERS
import os

settings_file_path = 'ecommerce.ecommerce.settings'
os.environ.setdefault('SCRAPY_SETTINGS_MODULE', settings_file_path)

configure_logging()
settings = get_project_settings()
runner = CrawlerRunner(settings)


@defer.inlineCallbacks
def crawl():
    yield from map(runner.crawl, SPIDERS)
    reactor.stop()


crawl()
reactor.run()
