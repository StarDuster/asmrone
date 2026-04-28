import argparse

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
def run_spiders(full=False):
    crawl_uuid = uuid7()
    yield runner.crawl(VoiceWorksSpider, crawl_uuid=crawl_uuid, full=full)
    work_ids = VoiceWorksSpider.latest_work_ids
    if work_ids:
        yield runner.crawl(
            VoiceFilesSpider,
            crawl_uuid=crawl_uuid,
            work_ids=work_ids,
        )
    reactor.stop()


parser = argparse.ArgumentParser()
parser.add_argument("--full", action="store_true", help="crawl all works")
args = parser.parse_args()

run_spiders(full=args.full)
reactor.run()
