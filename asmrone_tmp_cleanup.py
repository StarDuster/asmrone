import os
import time
from pathlib import Path


TMP_DIR = Path(
    os.environ.get("DOWNLOAD_TMP_DIR", "~/.local/share/asmrone/tmp")
).expanduser()
MIN_AGE_HOURS = float(os.environ.get("TMP_CLEANUP_MIN_AGE_HOURS", "6"))


def _open_paths_under(root: Path) -> set[Path]:
    open_paths = set()
    proc = Path("/proc")
    root = root.resolve()

    for pid_dir in proc.iterdir():
        if not pid_dir.name.isdigit():
            continue
        fd_dir = pid_dir / "fd"
        if not fd_dir.exists():
            continue
        try:
            fds = list(fd_dir.iterdir())
        except (FileNotFoundError, PermissionError, OSError):
            continue
        for fd in fds:
            try:
                target = Path(os.readlink(fd))
            except (FileNotFoundError, PermissionError, OSError):
                continue
            try:
                resolved = target.resolve()
            except OSError:
                continue
            if resolved == root or root in resolved.parents:
                open_paths.add(resolved)

    return open_paths


def main():
    if not TMP_DIR.exists():
        print(f"tmp_dir_missing={TMP_DIR}")
        return

    cutoff = time.time() - MIN_AGE_HOURS * 3600
    open_paths = _open_paths_under(TMP_DIR)
    removed_count = 0
    removed_size = 0
    skipped_open = 0

    for path in TMP_DIR.iterdir():
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if stat.st_mtime >= cutoff:
            continue

        resolved = path.resolve()
        if resolved in open_paths:
            skipped_open += 1
            continue

        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed_count += 1
        removed_size += stat.st_size

    print(
        f"tmp_dir={TMP_DIR} min_age_hours={MIN_AGE_HOURS:g} "
        f"removed_files={removed_count} "
        f"removed_size_gib={removed_size / 1024**3:.4f} "
        f"skipped_open_files={skipped_open}"
    )


if __name__ == "__main__":
    main()
