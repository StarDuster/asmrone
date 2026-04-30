from collections import Counter

from asmrone_crawler.file_rules import tts_skip_reason
from asmrone_crawler.storage import database


BATCH_SIZE = 10000


def main():
    reason_counts = Counter()
    updated = 0
    scanned = 0

    with database() as connection:
        rows = connection.execute(
            """
            SELECT uuid, path, file_type, duration, tts_skip_reason
            FROM t_file
            """
        )

        pending_updates = []
        for uuid, path, file_type, duration, old_reason in rows:
            scanned += 1
            new_reason = tts_skip_reason(path, file_type, duration)
            if new_reason:
                reason_counts[new_reason] += 1

            if old_reason != new_reason:
                pending_updates.append((new_reason, uuid))

            if len(pending_updates) >= BATCH_SIZE:
                connection.executemany(
                    "UPDATE t_file SET tts_skip_reason = ? WHERE uuid = ?",
                    pending_updates,
                )
                updated += len(pending_updates)
                pending_updates.clear()
                connection.commit()

        if pending_updates:
            connection.executemany(
                "UPDATE t_file SET tts_skip_reason = ? WHERE uuid = ?",
                pending_updates,
            )
            updated += len(pending_updates)

    print(f"scanned={scanned}")
    print(f"updated={updated}")
    print(f"marked={sum(reason_counts.values())}")
    for reason, count in reason_counts.most_common():
        print(f"{reason}={count}")


if __name__ == "__main__":
    main()
