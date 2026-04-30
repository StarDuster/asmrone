import subprocess
from pathlib import Path

from asmrone_crawler.storage import database
from asmrone_downloader import DOWNLOAD_TMP_DIR, _filter_sound_effect_variants


LOG_PATH = Path("logs/downloader.log")


def _tib(size):
    return size / 1024**4


def _percent(done, total):
    if total == 0:
        return 100.0
    return done / total * 100


def _service_state():
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "asmrone-downloader.service"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _latest_progress_line():
    if not LOG_PATH.exists():
        return None

    with LOG_PATH.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 1024 * 1024))
        text = f.read().decode("utf-8", errors="replace")

    lines = text.replace("\r", "\n").splitlines()
    for line in reversed(lines):
        if "Overall Progress:" in line:
            return line.strip()
    return None


def _tmp_usage():
    if not DOWNLOAD_TMP_DIR.exists():
        return 0, 0

    count = 0
    total_size = 0
    for path in DOWNLOAD_TMP_DIR.iterdir():
        if path.is_file():
            count += 1
            total_size += path.stat().st_size
    return count, total_size


def main():
    with database() as conn:
        rows = conn.execute(
            """
            SELECT
                f.uuid,
                f.work_id,
                COALESCE(w.source_id, f.work_id) AS source_id,
                f.path,
                f.download_url,
                f.cloudflare_etag,
                f.size,
                f.download_date
            FROM t_file f
            JOIN t_work w ON w.work_id = f.work_id
            WHERE
                f.masked = 0
                AND w.keep_japanese_audio = 1
                AND f.tts_skip_reason IS NULL
            """
        ).fetchall()
        skipped_tts_rows = conn.execute(
            """
            SELECT f.tts_skip_reason, COUNT(*) AS file_count, SUM(f.size) AS total_size
            FROM t_file f
            JOIN t_work w ON w.work_id = f.work_id
            WHERE
                f.masked = 0
                AND w.keep_japanese_audio = 1
                AND f.tts_skip_reason IS NOT NULL
            GROUP BY f.tts_skip_reason
            ORDER BY file_count DESC
            """
        ).fetchall()

    queue_rows, skipped_effect_rows = _filter_sound_effect_variants(rows)

    done_files = sum(1 for row in queue_rows if row[7] is not None)
    done_size = sum(row[6] for row in queue_rows if row[7] is not None)
    total_files = len(queue_rows)
    total_size = sum(row[6] for row in queue_rows)
    pending_files = total_files - done_files
    pending_size = total_size - done_size
    skipped_size = sum(row[6] for row in skipped_effect_rows)
    skipped_tts_count = sum(row[1] for row in skipped_tts_rows)
    skipped_tts_size = sum(row[2] or 0 for row in skipped_tts_rows)
    tmp_count, tmp_size = _tmp_usage()

    print(f"service={_service_state()}")
    print("scope=keep_japanese_audio=1, after sound-effect variant filtering")
    print(
        f"done_files={done_files}/{total_files} "
        f"({_percent(done_files, total_files):.2f}%)"
    )
    print(
        f"done_size={_tib(done_size):.2f}/{_tib(total_size):.2f} TiB "
        f"({_percent(done_size, total_size):.2f}%)"
    )
    print(f"pending_files={pending_files}")
    print(f"pending_size={_tib(pending_size):.2f} TiB")
    print(
        f"skipped_effect_variants={len(skipped_effect_rows)} "
        f"({_tib(skipped_size):.2f} TiB)"
    )
    print(
        f"skipped_tts_unusable={skipped_tts_count} "
        f"({_tib(skipped_tts_size):.2f} TiB)"
    )
    for row in skipped_tts_rows:
        print(
            f"skipped_tts_{row[0]}={row[1]} "
            f"({_tib(row[2] or 0):.2f} TiB)"
        )
    print(f"tmp_files={tmp_count}")
    print(f"tmp_size={_tib(tmp_size):.4f} TiB")

    latest_progress = _latest_progress_line()
    if latest_progress:
        print(f"latest_log_progress={latest_progress}")


if __name__ == "__main__":
    main()
