# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
import pymongo
import psycopg
import os
from datetime import datetime
from uuid_extensions import uuid7


class VoiceWorksMangoPipeline:
    def open_spider(self, spider):
        # Check if MONGO_URI is provided, otherwise build from individual components
        mongo_uri = os.environ.get("MONGO_URI")
        
        if not mongo_uri:
            # Fallback to building URI from individual components
            mongo_user = os.environ.get("MONGO_USER")
            mongo_password = os.environ.get("MONGO_PASS")
            mongo_host = os.environ.get("MONGO_HOST", "localhost")
            mongo_port = os.environ.get("MONGO_PORT", "27017")
            mongo_db = os.environ.get("MONGO_DB", "asmrone_crawler")
            
            # Create the MongoDB URI
            mongo_uri = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}:{mongo_port}/{mongo_db}"
        
        # Extract database name from URI if not provided separately
        mongo_db = os.environ.get("MONGO_DB", "asmrone_crawler")
        
        self.mongo_client = pymongo.MongoClient(
            mongo_uri, authMechanism="SCRAM-SHA-256"
        )
        self.db = self.mongo_client[mongo_db]
        self.works_collection = self.db["works"]
        self.crawls_collection = self.db["crawls"]
        self.files_collection = self.db["files"]

        crawl_record = {
            "crawl_uuid": str(spider.crawl_uuid),
            "crawl_date": datetime.utcnow(),
        }
        self.crawls_collection.insert_one(crawl_record)

    def close_spider(self, spider):
        self.mongo_client.close()

    def process_item(self, item, spider):
        self.works_collection.insert_one(item)
        return item


class VoiceFilesDBPipeline:
    def open_spider(self, spider):
        # Set up database connection
        # Check if POSTGRES_DSN is provided, otherwise build from individual components
        postgres_dsn = os.environ.get("POSTGRES_DSN")
        
        if postgres_dsn:
            self.connection = psycopg.connect(postgres_dsn)
        else:
            # Fallback to building DSN from individual components
            postgres_user = os.environ.get("POSTGRES_USER")
            postgres_password = os.environ.get("POSTGRES_PASS")
            postgres_host = os.environ.get("POSTGRES_HOST", "localhost")
            postgres_port = os.environ.get("POSTGRES_PORT", "5432")
            postgres_db = os.environ.get("POSTGRES_DB", "asmrone_crawler")
            self.connection = psycopg.connect(
                f"dbname={postgres_db} user={postgres_user} password={postgres_password} host={postgres_host} port={postgres_port}"
            )
        self.cursor = self.connection.cursor()

        # Set up MongoDB connection
        # Check if MONGO_URI is provided, otherwise build from individual components
        mongo_uri = os.environ.get("MONGO_URI")
        
        if not mongo_uri:
            # Fallback to building URI from individual components
            mongo_user = os.environ.get("MONGO_USER")
            mongo_password = os.environ.get("MONGO_PASS")
            mongo_host = os.environ.get("MONGO_HOST", "localhost")
            mongo_port = os.environ.get("MONGO_PORT", "27017")
            mongo_db = os.environ.get("MONGO_DB", "asmrone_crawler")
            
            # Create the MongoDB URI
            mongo_uri = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}:{mongo_port}/{mongo_db}"
        
        # Extract database name from URI if not provided separately
        mongo_db = os.environ.get("MONGO_DB", "asmrone_crawler")
        
        self.mongo_client = pymongo.MongoClient(
            mongo_uri, authMechanism="SCRAM-SHA-256"
        )
        self.db = self.mongo_client[mongo_db]
        self.files_collection = self.db["files"]

    def close_spider(self, spider):
        # Close database connection
        self.cursor.close()
        self.connection.close()

    def process_item(self, item, spider):
        crawl_uuid = spider.crawl_uuid
        voice_file = item
        file_uuid = None
        create_pg_record = False

        try:
            file_extension = os.path.splitext(voice_file["path"])[1].lower()
            if file_extension in [".wav", ".mp3", ".jpg", ".png", ".mp4", ".flac", ".pdf", ".ogg", ".m4a", ".avi", ".jpeg", ".wma", ".zip", ".aac", ".webm", ".webp", ".rar", ".opus"]:
                # Check if the voice file already exists in PostgreSQL from either same file in the past or other works
                self.cursor.execute(
                    "SELECT * FROM t_file WHERE work_id = %s and path = %s;",
                    (voice_file["work_id"], voice_file["path"],),
                )
                existing_files = self.cursor.fetchall()

                if existing_files:
                    for file in existing_files:
                        if (
                            file[6] == voice_file["size"]
                        ):  # Same file with the same size, assume it's the same file
                            # Found a matching file, use its UUID
                            file_uuid = file[0]
                            create_pg_record = False  # No need to create a new record
                            break  # Exit the loop early since we found a match
                    else:
                        # Files with this path exist, but NONE matched the size. Treat as new file.
                        file_uuid = uuid7()
                        create_pg_record = True

                else:
                    # New file, generate a new UUIDv7 for the file
                    file_uuid = uuid7()
                    create_pg_record = True
            else:
                # Force redownload for scripts and subtitles
                file_uuid = uuid7()
                create_pg_record = True

            if create_pg_record:
                # Insert the new voice file into PostgreSQL
                self.cursor.execute(
                    "INSERT INTO t_file (uuid, work_id, path, download_url, cloudflare_etag, size) VALUES (%s, %s, %s, %s, %s, %s);",
                    (
                        file_uuid.hex,
                        voice_file["work_id"],
                        voice_file["path"],
                        voice_file["download_url"],
                        voice_file["cloudflare_etag"],
                        voice_file["size"],
                    ),
                )
                self.connection.commit()

            # Insert or update the record in MongoDB
            voice_file_record = {
                "uuid": str(file_uuid),
                "crawl_uuid": str(crawl_uuid),
                **voice_file,
            }
            self.files_collection.insert_one(voice_file_record)

        except Exception as e:
            self.connection.rollback()
            spider.logger.error(f"Error processing item: {e}")

        return item
