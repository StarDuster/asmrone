import scrapy
import os
import pymongo
from itertools import cycle
from asmrone_crawler.items import VoiceWorksItem


class VoiceFilesSpider(scrapy.Spider):
    name = "voice_files"
    custom_settings = {
        "ITEM_PIPELINES": {"asmrone_crawler.pipelines.VoiceFilesDBPipeline": 300},
    }

    file_info = []
    failed_urls = []

    def __init__(self, crawl_uuid=None, *args, **kwargs):
        super(VoiceFilesSpider, self).__init__(*args, **kwargs)
        self.crawl_uuid = crawl_uuid

        domains = self.settings.getlist("API_DOMAINS", ["api.asmr-200.com"])
        self.allowed_domains = [*domains, "kiko-play-niptan.one"]
        self._domain_cycle = cycle(domains)

        mongo_user = os.environ.get("MONGO_USER")
        mongo_password = os.environ.get("MONGO_PASS")
        mongo_host = os.environ.get("MONGO_HOST", "localhost")
        mongo_port = os.environ.get("MONGO_PORT", "27017")
        mongo_db = os.environ.get("MONGO_DB", "asmrone_crawler")

        mongo_uri = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}:{mongo_port}/{mongo_db}"
        self.mongo_client = pymongo.MongoClient(
            mongo_uri, authMechanism="SCRAM-SHA-256"
        )
        self.db = self.mongo_client[mongo_db]

    def _api_url(self, path):
        domain = next(self._domain_cycle)
        return f"https://{domain}{path}"

    def fetch_work_ids(self):
        work_ids = []
        works_collection = self.db["works"]
        for work in works_collection.find(
            {"crawl_uuid": str(self.crawl_uuid)}, {"_id": 0, "id": 1}
        ):
            work_ids.append(work["id"])
        return work_ids

    def start_requests(self):
        work_ids = self.fetch_work_ids()
        for work_id in work_ids:
            yield scrapy.Request(
                url=self._api_url(f"/api/tracks/{work_id}"),
                meta={"work_id": work_id},
            )

    def process_folder(self, folder, work_id, folder_path=""):
        current_folder_path = os.path.join(folder_path, folder["title"])

        for item in folder["children"]:
            if item["type"] != "folder":
                file_path = os.path.join(current_folder_path, item["title"])
                download_url = item["mediaDownloadUrl"]
                yield self.fetch_etag(download_url, work_id, file_path)
            else:
                for request in self.process_folder(item, work_id, current_folder_path):
                    yield request

    def fetch_etag(self, download_url, work_id, file_path):
        return scrapy.Request(
            url=download_url,
            method="HEAD",
            meta={"work_id": work_id, "file_path": file_path},
            callback=self.process_etag,
            headers={"Accept-Encoding": "gzip, br"},
        )

    def process_etag(self, response):
        item = VoiceWorksItem()
        item["work_id"] = response.meta["work_id"]
        item["path"] = response.meta["file_path"]
        item["download_url"] = response.url
        item["cloudflare_etag"] = response.headers.get(
            "ETag", "").decode("utf-8").replace('"', "")
        item["size"] = int(response.headers.get(
            "Content-Length", "").decode("utf-8"))
        yield item

    def parse(self, response):
        work_id = response.meta["work_id"]
        if response.status == 200:
            data = response.json()
            for item in data:
                if item["type"] != "folder":
                    file_path = item["title"]
                    download_url = item["mediaDownloadUrl"]
                    yield self.fetch_etag(download_url, work_id, file_path)
                elif item["type"] == "folder":
                    for request in self.process_folder(item, work_id, ""):
                        yield request
