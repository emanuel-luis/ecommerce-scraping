# This package will contain the spiders of your Scrapy project
#
# Please refer to the documentation for information on how to create and manage
# your spiders.

from .marisa import MarisaSpider
from .afabula import AfabulaSpider
from .alphabeto import AlphabetoSpider
from .daksul import DaksulSpider
from .damyller import DamyllerSpider
from .hering import HeringSpider
from .lupo import LupoSpider
from .mormaii import MormaiiSpider
from .tricae import TricaeSpider
from .tng import TngSpider
from .levi import LeviSpider


SPIDERS = (
    AfabulaSpider, AlphabetoSpider, DaksulSpider, DamyllerSpider, HeringSpider,
    LupoSpider, MormaiiSpider, MarisaSpider, TricaeSpider, TngSpider, LeviSpider
)

__all__ = ['SPIDERS']