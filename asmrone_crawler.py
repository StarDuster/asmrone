from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
from uuid_extensions import uuid7
from asmrone_crawler.spiders.voice_works import VoiceWorksSpider
from asmrone_crawler.spiders.voice_files import VoiceFilesSpider
from twisted.internet import reactor, defer

settings = get_project_settings()
configure_logging(settings)
runner = CrawlerRunner(settings)


@defer.inlineCallbacks
def run_spiders():
    crawl_uuid = uuid7()
    yield runner.crawl(VoiceWorksSpider, crawl_uuid=crawl_uuid)
    yield runner.crawl(VoiceFilesSpider, crawl_uuid=crawl_uuid)
    reactor.stop()


run_spiders()
reactor.run()
