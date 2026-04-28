import scrapy
import json
from itertools import cycle
from scrapy.utils.reactor import install_reactor
from asmrone_crawler.storage import get_crawl_state, set_crawl_state

PAGE_SIZE = 500


class VoiceWorksSpider(scrapy.Spider):
    name = "voice_works"
    latest_work_ids = []
    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

    def __init__(self, crawl_uuid=None, full=None, *args, **kwargs):
        super(VoiceWorksSpider, self).__init__(*args, **kwargs)
        self.crawl_uuid = crawl_uuid
        self.full_mode = bool(full)
        self._max_create_date = None
        self.work_ids = []
        type(self).latest_work_ids = self.work_ids

        domains = self.settings.getlist("API_DOMAINS", ["api.asmr-200.com"])
        self.allowed_domains = [*domains, "kiko-play-niptan.one"]
        self._domain_cycle = cycle(domains)

        self._checkpoint = None
        if not self.full_mode:
            self._checkpoint = get_crawl_state("max_create_date")

    def _api_url(self, path):
        domain = next(self._domain_cycle)
        return f"https://{domain}{path}"

    def _make_item(self, work):
        work_id = work.get("id")
        if work_id is not None:
            self.work_ids.append(work_id)
        return {"crawl_uuid": str(self.crawl_uuid), **work}

    def start_requests(self):
        yield scrapy.Request(
            url=self._api_url(f"/api/works?order=create_date&sort=desc&page=1&pageSize={PAGE_SIZE}"),
            callback=self.parse,
        )

    def _process_page(self, data):
        """处理一页 works，返回 (items, has_new)。"""
        items = []
        has_new = False
        for work in data["works"]:
            create_date = work.get("create_date", "")
            if not self._max_create_date or create_date > self._max_create_date:
                self._max_create_date = create_date
            if self._checkpoint and create_date <= self._checkpoint:
                continue
            has_new = True
            items.append(self._make_item(work))
        return items, has_new

    def parse(self, response):
        data = json.loads(response.text)
        total_count = data["pagination"]["totalCount"]
        total_pages = -(-total_count // PAGE_SIZE)

        items, has_new = self._process_page(data)
        yield from items

        if self.full_mode or (self._checkpoint is None):
            for page in range(2, total_pages + 1):
                yield scrapy.Request(
                    url=self._api_url(f"/api/works?order=create_date&sort=desc&page={page}&pageSize={PAGE_SIZE}"),
                    callback=self.parse_page,
                    cb_kwargs={"crawl_uuid": str(self.crawl_uuid)},
                )
        elif has_new and total_pages >= 2:
            yield scrapy.Request(
                url=self._api_url(f"/api/works?order=create_date&sort=desc&page=2&pageSize={PAGE_SIZE}"),
                callback=self.parse_next,
                cb_kwargs={"page": 2, "total_pages": total_pages},
            )

    def parse_page(self, response, crawl_uuid):
        data = json.loads(response.text)
        for work in data["works"]:
            create_date = work.get("create_date", "")
            if not self._max_create_date or create_date > self._max_create_date:
                self._max_create_date = create_date
            yield self._make_item(work)

    def parse_next(self, response, page, total_pages):
        """增量模式的串行分页：遇到全部旧数据停止。"""
        data = json.loads(response.text)
        items, has_new = self._process_page(data)
        yield from items

        if has_new and page + 1 <= total_pages:
            yield scrapy.Request(
                url=self._api_url(f"/api/works?order=create_date&sort=desc&page={page + 1}&pageSize={PAGE_SIZE}"),
                callback=self.parse_next,
                cb_kwargs={"page": page + 1, "total_pages": total_pages},
            )

    def closed(self, reason):
        if reason == "finished" and self._max_create_date:
            set_crawl_state("max_create_date", self._max_create_date)
