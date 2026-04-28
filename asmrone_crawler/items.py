# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class AsmroneCrawlerItem(scrapy.Item):
    # define the fields for your item here like:
    # name = scrapy.Field()
    pass

class VoiceWorksItem(scrapy.Item):
    work_id = scrapy.Field()
    path = scrapy.Field()
    download_url = scrapy.Field()
    cloudflare_etag = scrapy.Field()
    size = scrapy.Field()