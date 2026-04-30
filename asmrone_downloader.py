import os
import hashlib
import logging
import configparser
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path, PurePosixPath
from threading import Lock, Thread
from queue import Queue, Empty
from dataclasses import dataclass
from typing import List, Tuple, Optional

import requests
import boto3
from tqdm import tqdm
from requests_toolbelt.adapters.host_header_ssl import HostHeaderSSLAdapter
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from asmrone_crawler.storage import database

# Configuration
RCLONE_CONFIG_PATH = Path(
    os.environ.get("RCLONE_CONFIG", "~/.config/rclone/rclone.conf")
).expanduser()
RCLONE_REMOTE_NAME = os.environ.get("RCLONE_REMOTE_NAME", "alioss")
OSS_BUCKET_NAME = os.environ.get("OSS_BUCKET_NAME", "sd-tokyo-ap")
OSS_PREFIX = os.environ.get("OSS_PREFIX", "datasets/speech_datasets/asmr").strip("/")
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB
RETRY_COUNT = 3
DOWNLOAD_TMP_DIR = Path(
    os.environ.get("DOWNLOAD_TMP_DIR", "/data/asmrone/tmp")
).expanduser()

NUM_WORKERS = 10
NUM_LARGE_FILE_WORKERS = 4  # Number of workers dedicated to large files
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB threshold for large files
NO_EFFECT_RE = re.compile(
    r"(効果音\s*(?:なし|無し|ナシ|無|抜き)|SE\s*(?:カット|Cut|無し|なし)|効果音カット)",
    re.IGNORECASE,
)
WITH_EFFECT_RE = re.compile(
    r"(効果音\s*(?:あり|有り|アリ|入り|入|大|小)|SE\s*(?:あり|有り|入り))",
    re.IGNORECASE,
)

logging.basicConfig(
    filename="error.log",
    level=logging.ERROR,
    format="%(asctime)s:%(levelname)s:%(message)s",
)

# Initialize constants
transfer_config = TransferConfig(
    multipart_threshold=UPLOAD_CHUNK_SIZE,
    max_concurrency=10,
    multipart_chunksize=UPLOAD_CHUNK_SIZE,
    max_io_queue=100,
    io_chunksize=262144,
    use_threads=True,
)
session = requests.Session()
adapter = HostHeaderSSLAdapter()
session.mount("https://", adapter)


@dataclass
class FileInfo:
    uuid: str
    work_id: str
    source_id: str
    file_path: str
    download_url: str
    cloudflare_etag: str
    size: int


@dataclass(frozen=True)
class OssConfig:
    access_key_id: str
    secret_access_key: str
    endpoint_url: str


class DownloadQueueManager:
    def __init__(self, file_info_list: List[Tuple]):
        self.small_files_queue = Queue()
        self.large_files_queue = Queue()
        self.lock = Lock()
        self.total_size = sum(file_info[6] for file_info in file_info_list)

        # Sort and split files into small and large
        sorted_files = sorted(file_info_list, key=lambda x: x[6])
        for file_info in sorted_files:
            file_size = file_info[6]
            if file_size >= LARGE_FILE_THRESHOLD:
                self.large_files_queue.put(FileInfo(*file_info))
            else:
                self.small_files_queue.put(FileInfo(*file_info))

    def get_file_for_worker(self, worker_id: int) -> Optional[FileInfo]:
        """Get next file for worker based on dynamic allocation"""
        with self.lock:
            # Dedicated large file workers
            if worker_id < NUM_LARGE_FILE_WORKERS:
                if not self.large_files_queue.empty():
                    return self.large_files_queue.get(block=False)
                elif not self.small_files_queue.empty():
                    return self.small_files_queue.get(block=False)
            else:
                # Small file workers
                if not self.small_files_queue.empty():
                    return self.small_files_queue.get(block=False)
                elif not self.large_files_queue.empty():
                    return self.large_files_queue.get(block=False)

            return None

    def is_empty(self) -> bool:
        """Check if both queues are empty"""
        return self.small_files_queue.empty() and self.large_files_queue.empty()


def _sound_effect_variant(file_path: str) -> str:
    no_effect = bool(NO_EFFECT_RE.search(file_path or ""))
    with_effect = bool(WITH_EFFECT_RE.search(file_path or ""))
    if no_effect and not with_effect:
        return "no_effect"
    if with_effect and not no_effect:
        return "with_effect"
    if no_effect and with_effect:
        return "no_effect"
    return "unmarked"


def _filter_sound_effect_variants(file_info_list: List[Tuple]):
    variants_by_source = {}
    for file_info in file_info_list:
        source_id = file_info[2]
        variant = _sound_effect_variant(file_info[3])
        variants = variants_by_source.setdefault(
            source_id,
            {"no_effect": False, "with_effect": False},
        )
        if variant == "no_effect":
            variants["no_effect"] = True
        elif variant == "with_effect":
            variants["with_effect"] = True

    selected = []
    skipped = []
    for file_info in file_info_list:
        variants = variants_by_source[file_info[2]]
        variant = _sound_effect_variant(file_info[3])
        if variants["no_effect"] and variants["with_effect"] and variant == "with_effect":
            skipped.append(file_info)
        else:
            selected.append(file_info)
    return selected, skipped


_oss_config = None
_oss_config_lock = Lock()


def _endpoint_url(endpoint: str) -> str:
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    return f"https://{endpoint}"


def _load_oss_config() -> OssConfig:
    parser = configparser.ConfigParser()
    if not parser.read(RCLONE_CONFIG_PATH):
        raise FileNotFoundError(f"rclone config not found: {RCLONE_CONFIG_PATH}")
    if RCLONE_REMOTE_NAME not in parser:
        raise ValueError(f"rclone remote not found: {RCLONE_REMOTE_NAME}")

    remote = parser[RCLONE_REMOTE_NAME]
    missing = [
        key
        for key in ("access_key_id", "secret_access_key", "endpoint")
        if not remote.get(key)
    ]
    if missing:
        raise ValueError(
            f"rclone remote {RCLONE_REMOTE_NAME} missing keys: {', '.join(missing)}"
        )

    return OssConfig(
        access_key_id=remote["access_key_id"],
        secret_access_key=remote["secret_access_key"],
        endpoint_url=_endpoint_url(remote["endpoint"]),
    )


def get_oss_config() -> OssConfig:
    global _oss_config
    if _oss_config is None:
        with _oss_config_lock:
            if _oss_config is None:
                _oss_config = _load_oss_config()
    return _oss_config


def get_s3_client():
    oss_config = get_oss_config()
    return boto3.client(
        "s3",
        endpoint_url=oss_config.endpoint_url,
        aws_access_key_id=oss_config.access_key_id,
        aws_secret_access_key=oss_config.secret_access_key,
        config=Config(
            signature_version="s3v4",
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            s3={
                "addressing_style": "virtual",
                "payload_signing_enabled": False,
            },
        ),
    )


def _is_wav_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() == ".wav"


def _safe_object_path(file_path: str) -> str:
    path = PurePosixPath(file_path.replace("\\", "/"))
    parts = [part for part in path.parts if part not in ("", ".", "..")]
    if not parts:
        return "file"
    return str(PurePosixPath(*parts))


def _object_key(source_id: str, file_path: str) -> str:
    object_path = _safe_object_path(file_path)
    if _is_wav_file(object_path):
        object_path = str(PurePosixPath(object_path).with_suffix(".flac"))

    object_name = str(PurePosixPath(str(source_id), object_path))
    return f"{OSS_PREFIX}/{object_name}" if OSS_PREFIX else object_name


def _convert_wav_to_flac(input_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to convert WAV files to FLAC")

    output_path = input_path.with_suffix(".flac")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-vn",
            "-compression_level",
            "8",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def upload_to_bucket(file_path, object_key, expected_size):
    try:
        s3_client = get_s3_client()
        s3_client.upload_file(
            file_path, OSS_BUCKET_NAME, object_key, Config=transfer_config
        )

        response = s3_client.head_object(Bucket=OSS_BUCKET_NAME, Key=object_key)
        uploaded_size = response["ContentLength"]

        if expected_size == 0 or uploaded_size == expected_size:
            return True
        else:
            s3_client.delete_object(Bucket=OSS_BUCKET_NAME, Key=object_key)
            error_message = "File size mismatch when uploading to OSS."
            logging.error(f"{object_key}: {error_message}\n")
            return False
    except Exception as e:
        error_message = "Failed to upload to OSS. " + str(e)
        logging.error(f"{object_key}: {error_message}\n")
        return False


def copy_existing_object(source_source_id, source_path, target_source_id, target_path):
    try:
        s3_client = get_s3_client()
        s3_client.copy(
            Bucket=OSS_BUCKET_NAME,
            CopySource={
                "Bucket": OSS_BUCKET_NAME,
                "Key": _object_key(source_source_id, source_path),
            },
            Key=_object_key(target_source_id, target_path),
        )
        return True
    except Exception as e:
        logging.error(f"Failed to copy existing OSS object for {target_source_id}: {e}")
        return False


def _try_dedup_by_hash(file_info: FileInfo):
    """下载前用 tracks hash + size 查找已下载的相同文件，命中则 S3 copy 跳过下载。"""
    hash_val = file_info.cloudflare_etag
    if not hash_val:
        return False
    try:
        with database() as conn:
            cur = conn.execute(
                """
                SELECT COALESCE(w.source_id, f.work_id), f.path
                FROM t_file f
                LEFT JOIN t_work w ON w.work_id = f.work_id
                WHERE f.cloudflare_etag = ?
                    AND f.size = ?
                    AND f.download_date IS NOT NULL
                    AND f.uuid != ?
                LIMIT 1
                """,
                (hash_val, file_info.size, file_info.uuid),
            )
            dup = cur.fetchone()
            if not dup:
                return False
            if not copy_existing_object(
                dup[0], dup[1], file_info.source_id, file_info.file_path
            ):
                return False
            conn.execute(
                "UPDATE t_file SET download_date = ? WHERE uuid = ?",
                (date.today().isoformat(), file_info.uuid),
            )
            return True
    except Exception as e:
        logging.error(f"Pre-download dedup failed for {file_info.uuid}: {e}")
        return False


def download_file_and_upload_oss(file_info: FileInfo):
    uuid = file_info.uuid
    file_path = file_info.file_path
    url = file_info.download_url
    expected_size = file_info.size

    if _try_dedup_by_hash(file_info):
        return True

    DOWNLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_filepath = DOWNLOAD_TMP_DIR / uuid

    for attempt in range(RETRY_COUNT):
        converted_filepath = None
        try:
            with open(temp_filepath, "wb") as temp_file:
                response = session.get(url, stream=True, timeout=30)
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)

            with open(temp_filepath, "rb") as f:
                file_md5 = hashlib.md5(f.read()).hexdigest()
            file_size = os.path.getsize(temp_filepath)

            with database() as connection:
                cursor = connection.execute(
                    """
                    SELECT COALESCE(w.source_id, f.work_id), f.path
                    FROM t_file f
                    LEFT JOIN t_work w ON w.work_id = f.work_id
                    WHERE f.md5 = ?
                        AND f.uuid != ?
                        AND f.download_date IS NOT NULL
                    LIMIT 1
                    """,
                    (file_md5, uuid),
                )
                results = cursor.fetchall()

                if len(results) > 0 and copy_existing_object(
                    results[0][0], results[0][1], file_info.source_id, file_path
                ):
                    pass
                else:
                    if (
                        not file_path.lower().endswith(".txt")
                        and file_size != expected_size
                    ):
                        error_message = "File size mismatch."
                        continue

                    upload_path = temp_filepath
                    if _is_wav_file(file_path):
                        converted_filepath = _convert_wav_to_flac(temp_filepath)
                        upload_path = converted_filepath

                    upload_size = os.path.getsize(upload_path)
                    if not upload_to_bucket(
                        str(upload_path),
                        _object_key(file_info.source_id, file_path),
                        upload_size,
                    ):
                        error_message = "Failed to upload to OSS."
                        continue

                connection.execute(
                    "UPDATE t_file SET md5 = ?, download_date = ?, size = ? WHERE uuid = ?",
                    (file_md5, date.today().isoformat(), file_size, uuid),
                )

            os.remove(temp_filepath)
            return True

        except Exception as e:
            error_message = str(e)

        finally:
            if temp_filepath.exists():
                try:
                    temp_filepath.unlink()
                except:
                    pass
            if converted_filepath and converted_filepath.exists():
                try:
                    converted_filepath.unlink()
                except:
                    pass

    logging.error(f"All retries failed for {url}: {error_message}\n")
    return False


def worker_thread(worker_id, queue_manager, pbar):
    """Worker thread that processes files from the queue"""
    while True:
        try:
            # Get next file from queue
            file_info = queue_manager.get_file_for_worker(worker_id)
            if file_info is None:
                # No more files to process
                break

            # Process the file
            if download_file_and_upload_oss(file_info):
                with pbar.get_lock():
                    pbar.update(file_info.size)

        except Empty:
            # Queue is empty
            break
        except Exception as e:
            logging.error(f"Worker {worker_id} encountered an error: {str(e)}")


def main():
    with database() as connection:
        cursor = connection.execute("""
            SELECT
                f.uuid,
                f.work_id,
                COALESCE(w.source_id, f.work_id) AS source_id,
                f.path,
                f.download_url,
                f.cloudflare_etag,
                f.size
            FROM t_file f
            LEFT JOIN t_work w ON w.work_id = f.work_id
            WHERE f.masked = 0 AND f.download_date IS NULL;
        """)
        file_info_list, skipped_effect_files = _filter_sound_effect_variants(
            cursor.fetchall()
        )

    if len(file_info_list) == 0:
        print("All files are up to date.")
        return

    if skipped_effect_files:
        skipped_size = sum(file_info[6] for file_info in skipped_effect_files)
        print(
            "Skipped sound-effect variants: "
            f"{len(skipped_effect_files)} files "
            f"({skipped_size / 1024**4:.2f} TiB)"
        )

    # Create queue manager
    queue_manager = DownloadQueueManager(file_info_list)
    total_size = queue_manager.total_size

    # Create and start worker threads
    with tqdm(
        total=total_size,
        desc="Overall Progress",
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        smoothing=0.05,
    ) as pbar:
        threads = []
        for worker_id in range(NUM_WORKERS):
            thread = Thread(target=worker_thread, args=(
                worker_id, queue_manager, pbar))
            thread.start()
            threads.append(thread)

        # Wait for all workers to finish
        for thread in threads:
            thread.join()

    print("Download completed!")


if __name__ == "__main__":
    main()

