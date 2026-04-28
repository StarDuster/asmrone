import os
import hashlib
import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Thread
from queue import Queue, Empty
from dataclasses import dataclass
from typing import List, Tuple, Optional

import psycopg
import requests
import boto3
from tqdm import tqdm
from requests_toolbelt.adapters.host_header_ssl import HostHeaderSSLAdapter
from boto3.s3.transfer import TransferConfig
from urllib.parse import urlparse

# Configuration
OSS_ACCESS_KEY = ""
OSS_SECRET_KEY = ""
OSS_BUCKET_NAME = "voices"
OSS_ENDPOINT_URL = ""
RGW_ENDPOINTS = [
    "http://192.168.0.11:7480",
    "http://192.168.0.12:7480",
    "http://192.168.0.13:7480",
]
POSTGRES_USER = os.environ.get("POSTGRES_USER", "asmrone_crawler")
POSTGRES_PASSWORD = os.environ.get(
    "POSTGRES_PASS", ""
)
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "192.168.1.1")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "12345")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "asmrone_crawler")
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB
CHUNK_SIZE = 100000000
# CHUNK_SIZE = 33554432
RETRY_COUNT = 3

NUM_WORKERS = 10
NUM_LARGE_FILE_WORKERS = 4  # Number of workers dedicated to large files
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB threshold for large files

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
host_map = {
    "large.kiko-play-niptan.one": [
        "162.159.133.151",
        "104.19.167.40",
        "104.16.168.105",
        "104.17.221.182",
        "104.19.214.20",
    ],
    "raw.kiko-play-niptan.one": [
        "104.19.215.92",
        "198.41.195.70",
        "104.18.20.190",
        "104.19.238.35",
        "198.41.200.24",
    ],
}
session = requests.Session()
adapter = HostHeaderSSLAdapter()
session.mount("https://", adapter)


@dataclass
class FileInfo:
    uuid: str
    work_id: str
    file_path: str
    download_url: str
    cloudflare_etag: str
    size: int


class HostSelector:
    def __init__(self, host_map):
        self.host_map = host_map
        self.lock = Lock()
        self.assigned_ips = {}

    def assign_ip_to_worker(self, host, worker_id):
        with self.lock:
            if host in self.host_map:
                ip_list = self.host_map[host]
                # Assign an IP to a worker based on the worker_id
                assigned_ip = ip_list[worker_id % len(ip_list)]
                if worker_id not in self.assigned_ips:
                    self.assigned_ips[worker_id] = {}
                self.assigned_ips[worker_id][host] = assigned_ip

    def get_ip_for_worker(self, host, worker_id):
        if worker_id in self.assigned_ips and host in self.assigned_ips[worker_id]:
            return self.assigned_ips[worker_id][host]
        return None


class DownloadQueueManager:
    def __init__(self, file_info_list: List[Tuple]):
        self.small_files_queue = Queue()
        self.large_files_queue = Queue()
        self.lock = Lock()
        self.total_size = sum(file_info[5] for file_info in file_info_list)

        # Sort and split files into small and large
        sorted_files = sorted(file_info_list, key=lambda x: x[5])
        for file_info in sorted_files:
            file_size = file_info[5]
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


host_selector = HostSelector(host_map)


def get_s3_client():
    endpoint_url = RGW_ENDPOINTS[get_s3_client.endpoint_index]
    get_s3_client.endpoint_index = (get_s3_client.endpoint_index + 1) % len(
        RGW_ENDPOINTS
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=OSS_ACCESS_KEY,
        aws_secret_access_key=OSS_SECRET_KEY,
    )


get_s3_client.endpoint_index = 0


def calculate_s3_etag(file_path):
    md5s = []

    with open(file_path, "rb") as fp:
        while True:
            data = fp.read(CHUNK_SIZE)
            if not data:
                break
            md5s.append(hashlib.md5(data))

    if len(md5s) < 1:
        return "{}".format(hashlib.md5().hexdigest())

    if len(md5s) == 1:
        return "{}".format(md5s[0].hexdigest())

    digests = b"".join(m.digest() for m in md5s)
    digests_md5 = hashlib.md5(digests)
    return "{}-{}".format(digests_md5.hexdigest(), len(md5s))


def is_valid_md5(md5_str):
    parts = md5_str.split("-")

    if len(parts) == 1:
        return len(md5_str) == 32 and all(c in "0123456789abcdef" for c in md5_str)

    elif len(parts) == 2:
        md5_part, num_parts_str = parts
        return (
            len(md5_part) == 32
            and all(c in "0123456789abcdef" for c in md5_part)
            and num_parts_str.isdigit()
        )

    return False


def upload_to_bucket(file_path, object_name, expected_size):
    try:
        s3_client = get_s3_client()
        object_name = f"asmrone/{object_name}"
        s3_client.upload_file(
            file_path, OSS_BUCKET_NAME, object_name, Config=transfer_config
        )

        response = s3_client.head_object(
            Bucket=OSS_BUCKET_NAME, Key=object_name)
        uploaded_size = response["ContentLength"]

        if expected_size == 0 or uploaded_size == expected_size:
            return True
        else:
            s3_client.delete_object(Bucket=OSS_BUCKET_NAME, Key=object_name)
            error_message = "File size mismatch when uploading to OSS."
            logging.error(f"{object_name}: {error_message}\n")
            return False
    except Exception as e:
        error_message = "Failed to upload to OSS. " + str(e)
        logging.error(f"{object_name}: {error_message}\n")
        return False


def download_file_and_upload_oss(
    file_info: FileInfo, worker_id: int
):
    uuid = file_info.uuid
    work_id = file_info.work_id
    file_path = file_info.file_path
    url = file_info.download_url
    expected_etag = file_info.cloudflare_etag
    expected_size = file_info.size

    original_host = urlparse(url).hostname
    temp_filepath = f"/tmp/{uuid}"

    for attempt in range(RETRY_COUNT):
        try:

            with open(temp_filepath, "wb") as temp_file:
                response = session.get(
                    url, stream=True, timeout=30
                )
                response.raise_for_status()

                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)

            with open(temp_filepath, "rb") as f:
                file_md5 = hashlib.md5(f.read()).hexdigest()
            file_size = os.path.getsize(temp_filepath)

            with psycopg.connect(
                f"dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD} host={POSTGRES_HOST} port={POSTGRES_PORT}"
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT uuid, md5 FROM t_file WHERE md5 = %s AND uuid != %s AND download_date IS NOT NULL",
                        (file_md5, uuid),
                    )
                    results = cursor.fetchall()

                    if (len(results) > 0):
                        s3_client = get_s3_client()
                        s3_client.copy(
                            Bucket=OSS_BUCKET_NAME,
                            CopySource={'Bucket': f"{OSS_BUCKET_NAME}",
                                        'Key': f"asmrone/{results[0][0]}"},
                            Key=f"asmrone/{uuid}",
                        )
                    else:
                        if not file_path.lower().endswith(".txt") and file_size != expected_size:
                            error_message = "File size mismatch."
                            continue

                        if not upload_to_bucket(temp_filepath, str(uuid), expected_size):
                            error_message = "Failed to upload to OSS."
                            continue

                    cursor.execute(
                        "UPDATE t_file SET md5 = %s, download_date = %s, size = %s WHERE uuid = %s",
                        (file_md5, date.today(), file_size, uuid),
                    )

            os.remove(temp_filepath)
            return True

        except Exception as e:
            error_message = str(e)

        finally:
            if os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
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
            if download_file_and_upload_oss(file_info, worker_id):
                with pbar.get_lock():
                    pbar.update(file_info.size)

        except Empty:
            # Queue is empty
            break
        except Exception as e:
            logging.error(f"Worker {worker_id} encountered an error: {str(e)}")


def main():
    with psycopg.connect(
        f"dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD} host={POSTGRES_HOST} port={POSTGRES_PORT}"
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT uuid, work_id, path, download_url, cloudflare_etag, size
                FROM (
                    SELECT uuid, work_id, path, download_url, cloudflare_etag, size,
                           ROW_NUMBER() OVER (PARTITION BY uuid ORDER BY download_date DESC NULLS LAST) AS rn
                    FROM t_file
                    WHERE masked = FALSE AND download_date IS NULL
                ) t
                WHERE rn = 1;
            """)
            file_info_list = cursor.fetchall()

    if len(file_info_list) == 0:
        print("All files are up to date.")
        return

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

