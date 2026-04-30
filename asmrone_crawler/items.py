import scrapy


class VoiceWorksItem(scrapy.Item):
    work_id = scrapy.Field()
    path = scrapy.Field()
    download_url = scrapy.Field()
    hash = scrapy.Field()
    size = scrapy.Field()
    file_type = scrapy.Field()
    title = scrapy.Field()
    duration = scrapy.Field()
    media_stream_url = scrapy.Field()
    stream_low_quality_url = scrapy.Field()
    work_title = scrapy.Field()
    raw_json = scrapy.Field()
