import scrapy
import os
from itertools import cycle
from asmrone_crawler.items import VoiceWorksItem


class VoiceFilesSpider(scrapy.Spider):
    name = "voice_files"
    custom_settings = {
        "ITEM_PIPELINES": {"asmrone_crawler.pipelines.VoiceFilesDBPipeline": 300},
    }

    def __init__(self, crawl_uuid=None, work_ids=None, *args, **kwargs):
        super(VoiceFilesSpider, self).__init__(*args, **kwargs)
        self.crawl_uuid = crawl_uuid
        self.work_ids = self._normalize_work_ids(work_ids)

        domains = ["api.asmr-200.com"]
        self.allowed_domains = [*domains, "kiko-play-niptan.one"]
        self._domain_cycle = cycle(domains)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider._configure_domains(crawler.settings)
        return spider

    def _configure_domains(self, settings):
        domains = settings.getlist("API_DOMAINS", ["api.asmr-200.com"])
        self.allowed_domains = [*domains, "kiko-play-niptan.one"]
        self._domain_cycle = cycle(domains)

    def _normalize_work_ids(self, work_ids):
        if work_ids is None:
            return []
        if isinstance(work_ids, str):
            return [work_id for work_id in work_ids.split(",") if work_id]
        return list(work_ids)

    def _api_url(self, path):
        domain = next(self._domain_cycle)
        return f"https://{domain}{path}"

    async def start(self):
        for work_id in self.work_ids:
            yield scrapy.Request(
                url=self._api_url(f"/api/tracks/{work_id}"),
                meta={"work_id": work_id},
            )

    def _make_item(self, track_item, work_id, file_path):
        item = VoiceWorksItem()
        item["work_id"] = work_id
        item["path"] = file_path
        item["download_url"] = track_item["mediaDownloadUrl"]
        item["hash"] = track_item["hash"]
        item["size"] = track_item["size"]
        return item

    def process_folder(self, folder, work_id, folder_path=""):
        current_folder_path = os.path.join(folder_path, folder["title"])
        for child in folder["children"]:
            if child["type"] == "folder":
                yield from self.process_folder(child, work_id, current_folder_path)
            else:
                file_path = os.path.join(current_folder_path, child["title"])
                yield self._make_item(child, work_id, file_path)

    def parse(self, response):
        work_id = response.meta["work_id"]
        if response.status != 200:
            return
        for item in response.json():
            if item["type"] == "folder":
                yield from self.process_folder(item, work_id, "")
            else:
                yield self._make_item(item, work_id, item["title"])
