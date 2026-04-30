# AGENTS.md

This repository crawls ASMR.one metadata and downloads selected Japanese audio files to OSS. It is currently optimized around building a clean ASMR/TTS-oriented audio corpus, not around mirroring the whole website blindly.

## Project Shape

- `asmrone_crawler.py` runs the Scrapy spiders in sequence.
- `asmrone_crawler/spiders/voice_works.py` crawls `/api/works` and records work-level metadata.
- `asmrone_crawler/spiders/voice_files.py` crawls `/api/tracks/{work_id}` and records the recursive file tree.
- `asmrone_crawler/pipelines.py` writes works, voice actors, tags, and files into SQLite.
- `asmrone_crawler/storage.py` owns the SQLite schema and lightweight migrations.
- `asmrone_downloader.py` selects queued files, downloads them, converts `.wav` to `.flac`, uploads to OSS, and updates `t_file.download_date`.
- `asmrone_progress.py` reports downloader queue progress.
- `asmrone_tmp_cleanup.py` cleans stale files from the download temp directory.

The default SQLite database is:

```text
~/.local/share/asmrone/asmrone.db
```

The default temporary download directory is:

```text
/data/asmrone/tmp
```

## Metadata Model

Important SQLite tables:

- `t_work`: one row per work. Includes title, circle, source IDs, R18 flag, subtitle flag, raw JSON, and `keep_japanese_audio`.
- `t_file`: one row per crawled file. Includes relative path, download URL, size, duration, file type, raw JSON, `masked`, `tts_skip_reason`, and `download_date`.
- `t_va` and `t_work_va`: voice actors and work-to-voice-actor links.
- `t_tag` and `t_work_tag`: tags and work-to-tag links.
- `crawl_state`: incremental crawl checkpoints.

`keep_japanese_audio` is a work-level decision. It means the work appears to be Japanese audio. It does not mean every file in that work is useful for TTS.

## Download Scope

The downloader currently selects rows roughly like this:

```sql
FROM t_file f
JOIN t_work w ON w.work_id = f.work_id
WHERE f.masked = 0
  AND f.download_date IS NULL
  AND w.keep_japanese_audio = 1
  AND f.tts_skip_reason IS NULL
```

Then it applies sound-effect version filtering:

- If both no-effect and with-effect versions are present for the same source, prefer the no-effect version.
- `.wav` files are converted to `.flac` before upload.
- The database `path` remains the original website path, even when the uploaded object uses `.flac`.

`tts_skip_reason` is a file-level automatic skip reason for audio that should not enter the TTS download queue. Current reason values include:

- `no_dialogue`: no-dialogue tracks such as `台詞レス`, `セリフなし`, `no voice`.
- `sound_only`: sound-only tracks such as `効果音のみ`, `SEのみ`, `フェラ音のみ`.
- `sound_effect_material`: sound effect material directories such as `効果音/`, `SE素材/`, `行動系/`.
- `short_audio`: audio shorter than 3 seconds.

`masked` is still a separate manual file-level block flag. Do not use it for automatic TTS classification.

## TTS-Relevant Caveats

For TTS work, distinguish these concepts:

- Japanese audio work: selected by `t_work.keep_japanese_audio`.
- Single-speaker candidate: usually `COUNT(t_work_va) = 1`.
- No-effect candidate: inferred from file paths such as `SEなし`, `SE無し`, `効果音なし`, `効果音カット`, `NOSE`, or similar.
- Text-aligned candidate: requires subtitle/script files or later alignment work. `has_subtitle` alone is not guaranteed alignment.
- Training-usable audio: requires file-level filtering and actual audio validation.

Known non-training audio patterns should not be treated as usable speech:

- `台詞レス`, `台詞なし`, `セリフレス`, `no dialogue`, `no voice`
- `音のみ`, `効果音のみ`, `SEのみ`, `SE素材`, `効果音素材`
- short sound effects such as paths under `効果音/`, `行動系/`, or tiny sub-second `.wav` files

These are marked in `t_file.tts_skip_reason` by `asmrone_crawler/file_rules.py` and are skipped by the downloader. This still does not make the queue a finished training set; downloaded audio still needs actual audio validation, segmentation, and text alignment.

## Useful Commands

Run the crawler:

```bash
uv run python asmrone_crawler.py
```

Run a full crawl:

```bash
uv run python asmrone_crawler.py --full
```

Run the downloader:

```bash
uv run python asmrone_downloader.py
```

Check downloader progress:

```bash
uv run python asmrone_progress.py
```

Recompute `t_file.tts_skip_reason` after changing file-level TTS rules:

```bash
uv run python asmrone_mark_tts_skip_reasons.py
```

When changing skip rules while the downloader service is running, stop it before scanning the full database and start it again afterwards:

```bash
systemctl --user stop asmrone-downloader.service
uv run python asmrone_mark_tts_skip_reasons.py
systemctl --user start asmrone-downloader.service
systemctl --user is-active asmrone-downloader.service
```

Clean old temp files:

```bash
uv run python asmrone_tmp_cleanup.py
```

Use `SQLITE_PATH` to point tools at a non-default database. Use `DOWNLOAD_TMP_DIR` to override the temporary download directory.

## Engineering Rules For Agents

- Keep imports at the top of Python files.
- Preserve existing user changes. This repository often has uncommitted crawl/download work.
- Do not run destructive git commands.
- Do not treat `masked` as an automatic classifier unless the user explicitly asks. It is safer to add runtime skip rules or explicit reason fields.
- Use `t_file.tts_skip_reason` for automatic file-level TTS skip rules. Keep the rule implementation in `asmrone_crawler/file_rules.py` so downloader, progress reporting, pipelines, and marking scripts share one source of truth.
- Avoid large schema redesigns. The project uses small SQLite migrations through `_ensure_column`.
- When adding download filters, update both `asmrone_downloader.py` and `asmrone_progress.py` so progress numbers match downloader behavior.
- After changing `asmrone_crawler/file_rules.py`, run `uv run python asmrone_mark_tts_skip_reasons.py` to refresh existing rows.
- When changing metadata fields, update `WEBSITE_METADATA_FORMAT.md` if it exists in the working tree.

## Validation Guidance

There is no formal test suite yet. For focused changes:

- Run the changed script with `uv run python ...` if it is safe.
- For SQL/schema changes, open the database through `asmrone_crawler.storage.database()` instead of hand-rolling connection setup.
- For downloader queue changes, compare queue counts before and after with a read-only SQL query or `asmrone_progress.py`.
- For WAV-to-FLAC behavior, inspect `/data/asmrone/tmp` only as a sample cache. It may contain partial files, stale files, or files already being cleaned.

## Related Docs

- `WEBSITE_METADATA_FORMAT.md`: website API and local metadata schema.
- `JAPANESE_AUDIO_SELECTION_RULES.md`: work-level Japanese audio selection policy.
