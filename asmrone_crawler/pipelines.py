import json
from datetime import datetime
from uuid_extensions import uuid7

from asmrone_crawler.storage import connect, init_db


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _now():
    return datetime.utcnow().isoformat()


class WorkMetadataPipeline:
    def open_spider(self, spider=None):
        self.connection = connect()
        init_db(self.connection)

    def close_spider(self, spider=None):
        self.connection.close()

    def process_item(self, item, spider=None):
        work = dict(item)
        work_id = work.get("id")
        if work_id is None:
            return item

        work_id = str(work_id)
        circle = work.get("circle") or {}
        circle_id = work.get("circle_id") or circle.get("id")
        circle_name = work.get("name") or circle.get("name")
        timestamp = _now()

        try:
            self.connection.execute(
                """
                INSERT INTO t_work (
                    work_id,
                    title,
                    circle_id,
                    circle_name,
                    source_id,
                    source_type,
                    source_url,
                    nsfw,
                    release_date,
                    create_date,
                    dl_count,
                    price,
                    review_count,
                    rate_count,
                    rate_average_2dp,
                    has_subtitle,
                    duration,
                    work_attributes,
                    age_category_string,
                    sam_cover_url,
                    thumbnail_cover_url,
                    main_cover_url,
                    raw_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_id) DO UPDATE SET
                    title = excluded.title,
                    circle_id = excluded.circle_id,
                    circle_name = excluded.circle_name,
                    source_id = excluded.source_id,
                    source_type = excluded.source_type,
                    source_url = excluded.source_url,
                    nsfw = excluded.nsfw,
                    release_date = excluded.release_date,
                    create_date = excluded.create_date,
                    dl_count = excluded.dl_count,
                    price = excluded.price,
                    review_count = excluded.review_count,
                    rate_count = excluded.rate_count,
                    rate_average_2dp = excluded.rate_average_2dp,
                    has_subtitle = excluded.has_subtitle,
                    duration = excluded.duration,
                    work_attributes = excluded.work_attributes,
                    age_category_string = excluded.age_category_string,
                    sam_cover_url = excluded.sam_cover_url,
                    thumbnail_cover_url = excluded.thumbnail_cover_url,
                    main_cover_url = excluded.main_cover_url,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    work_id,
                    work.get("title"),
                    str(circle_id) if circle_id is not None else None,
                    circle_name,
                    work.get("source_id"),
                    work.get("source_type"),
                    work.get("source_url"),
                    int(bool(work.get("nsfw"))) if work.get("nsfw") is not None else None,
                    work.get("release"),
                    work.get("create_date"),
                    work.get("dl_count"),
                    work.get("price"),
                    work.get("review_count"),
                    work.get("rate_count"),
                    work.get("rate_average_2dp"),
                    int(bool(work.get("has_subtitle")))
                    if work.get("has_subtitle") is not None
                    else None,
                    work.get("duration"),
                    work.get("work_attributes"),
                    work.get("age_category_string"),
                    work.get("samCoverUrl"),
                    work.get("thumbnailCoverUrl"),
                    work.get("mainCoverUrl"),
                    _json_dumps(work),
                    timestamp,
                ),
            )

            self.connection.execute("DELETE FROM t_work_va WHERE work_id = ?", (work_id,))
            for va in work.get("vas") or []:
                va_id = str(va.get("id") or f"name:{va.get('name', '')}")
                name = va.get("name") or ""
                self.connection.execute(
                    """
                    INSERT INTO t_va (va_id, name, raw_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(va_id) DO UPDATE SET
                        name = excluded.name,
                        raw_json = excluded.raw_json,
                        updated_at = excluded.updated_at
                    """,
                    (va_id, name, _json_dumps(va), timestamp),
                )
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO t_work_va (work_id, va_id, name)
                    VALUES (?, ?, ?)
                    """,
                    (work_id, va_id, name),
                )

            self.connection.execute("DELETE FROM t_work_tag WHERE work_id = ?", (work_id,))
            for tag in work.get("tags") or []:
                tag_id = str(tag.get("id") or f"name:{tag.get('name', '')}")
                name = tag.get("name") or ""
                self.connection.execute(
                    """
                    INSERT INTO t_tag (tag_id, name, raw_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(tag_id) DO UPDATE SET
                        name = excluded.name,
                        raw_json = excluded.raw_json,
                        updated_at = excluded.updated_at
                    """,
                    (tag_id, name, _json_dumps(tag), timestamp),
                )
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO t_work_tag (work_id, tag_id, name)
                    VALUES (?, ?, ?)
                    """,
                    (work_id, tag_id, name),
                )

            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            if spider:
                spider.logger.error(f"Error processing work metadata: {e}")
            else:
                raise

        return item


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

            if create_pg_record:
                self.connection.execute(
                    """
                    INSERT INTO t_file (
                        uuid,
                        work_id,
                        path,
                        download_url,
                        cloudflare_etag,
                        size,
                        file_type,
                        title,
                        duration,
                        media_stream_url,
                        stream_low_quality_url,
                        work_title,
                        raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_uuid,
                        voice_file["work_id"],
                        voice_file["path"],
                        voice_file["download_url"],
                        voice_file.get("hash"),
                        voice_file["size"],
                        voice_file.get("file_type"),
                        voice_file.get("title"),
                        voice_file.get("duration"),
                        voice_file.get("media_stream_url"),
                        voice_file.get("stream_low_quality_url"),
                        voice_file.get("work_title"),
                        _json_dumps(voice_file.get("raw_json")),
                    ),
                )
            else:
                self.connection.execute(
                    """
                    UPDATE t_file SET
                        download_url = ?,
                        cloudflare_etag = ?,
                        file_type = ?,
                        title = ?,
                        duration = ?,
                        media_stream_url = ?,
                        stream_low_quality_url = ?,
                        work_title = ?,
                        raw_json = ?
                    WHERE uuid = ?
                    """,
                    (
                        voice_file["download_url"],
                        voice_file.get("hash"),
                        voice_file.get("file_type"),
                        voice_file.get("title"),
                        voice_file.get("duration"),
                        voice_file.get("media_stream_url"),
                        voice_file.get("stream_low_quality_url"),
                        voice_file.get("work_title"),
                        _json_dumps(voice_file.get("raw_json")),
                        file_uuid,
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
