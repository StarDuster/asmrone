import scrapy
import json
from itertools import cycle
from scrapy.utils.reactor import install_reactor


class VoiceWorksSpider(scrapy.Spider):
    name = "voice_works"
    custom_settings = {
        "ITEM_PIPELINES": {"asmrone_crawler.pipelines.VoiceWorksMangoPipeline": 300},
    }
    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

    def __init__(self, crawl_uuid=None, *args, **kwargs):
        super(VoiceWorksSpider, self).__init__(*args, **kwargs)
        self.crawl_uuid = crawl_uuid
        domains = self.settings.getlist("API_DOMAINS", ["api.asmr-200.com"])
        self.allowed_domains = [*domains, "kiko-play-niptan.one"]
        self._domain_cycle = cycle(domains)

    def _api_url(self, path):
        domain = next(self._domain_cycle)
        return f"https://{domain}{path}"

    def start_requests(self):
        yield scrapy.Request(
            url=self._api_url("/api/works?order=id&sort=asc&page=1"),
            callback=self.parse,
        )

    def parse(self, response):
        data = json.loads(response.text)
        total_count = data["pagination"]["totalCount"]
        page_size = data["pagination"]["pageSize"]
        total_pages = total_count // page_size + (1 if total_count % page_size else 0)

        for page in range(1, total_pages + 1):
            yield scrapy.Request(
                url=self._api_url(f"/api/works?order=id&sort=asc&page={page}"),
                callback=self.parse_page,
                cb_kwargs={"crawl_uuid": str(self.crawl_uuid)},
            )

    def parse_page(self, response, crawl_uuid):
        data = json.loads(response.text)
        works = data["works"]
        for work in works:
            yield {
                "crawl_uuid": str(crawl_uuid),
                **work,
            }
