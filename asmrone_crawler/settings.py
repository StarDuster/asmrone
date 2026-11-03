# Settings for the asmrone_crawler Scrapy project.
# Reference: https://docs.scrapy.org/en/latest/topics/settings.html

BOT_NAME = "asmrone_crawler"

SPIDER_MODULES = ["asmrone_crawler.spiders"]
NEWSPIDER_MODULE = "asmrone_crawler.spiders"

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS = 8

AUTOTHROTTLE_ENABLED = False

# Set settings whose default value is deprecated to a future-proof value
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

RETRY_TIMES = 20
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 525, 408, 429]
LOG_LEVEL = "INFO"

API_DOMAINS = [
    "api.asmr-300.com",
    "api.asmr-200.com",
    "api.asmr-100.com",
]
