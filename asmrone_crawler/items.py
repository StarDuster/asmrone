import scrapy


class VoiceWorksItem(scrapy.Item):
    work_id = scrapy.Field()
    path = scrapy.Field()
    download_url = scrapy.Field()
    hash = scrapy.Field()
    size = scrapy.Field()
