import os
from uuid_extensions import uuid7

from asmrone_crawler.storage import connect, init_db

DEDUP_EXTENSIONS = {
    ".aac",
    ".avi",
    ".flac",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".pdf",
    ".png",
    ".rar",
    ".wav",
    ".webm",
    ".webp",
    ".wma",
    ".zip",
}


class VoiceFilesDBPipeline:
    def open_spider(self, spider=None):
        self.connection = connect()
        init_db(self.connection)

    def close_spider(self, spider=None):
        self.connection.close()

    def process_item(self, item, spider=None):
        voice_file = item
        create_pg_record = False

        try:
            file_extension = os.path.splitext(voice_file["path"])[1].lower()
            if file_extension in DEDUP_EXTENSIONS:
                existing_files = self.connection.execute(
                    """
                    SELECT uuid, size FROM t_file
                    WHERE work_id = ? AND path = ?
                    """,
                    (voice_file["work_id"], voice_file["path"]),
                ).fetchall()

                file_uuid = None
                for existing_file in existing_files:
                    if existing_file[1] == voice_file["size"]:
                        file_uuid = existing_file[0]
                        break

                if file_uuid is None:
                    file_uuid = uuid7().hex
                    create_pg_record = True
            else:
                file_uuid = uuid7().hex
                create_pg_record = True

            if create_pg_record:
                self.connection.execute(
                    """
                    INSERT INTO t_file (
                        uuid,
                        work_id,
                        path,
                        download_url,
                        cloudflare_etag,
                        size
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_uuid,
                        voice_file["work_id"],
                        voice_file["path"],
                        voice_file["download_url"],
                        voice_file.get("hash"),
                        voice_file["size"],
                    ),
                )
                self.connection.commit()

        except Exception as e:
            self.connection.rollback()
            if spider:
                spider.logger.error(f"Error processing item: {e}")
            else:
                raise

        return item
