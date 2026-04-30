# ASMR One 网站元数据格式

本文档总结当前爬虫依赖的 ASMR One 网站接口元数据格式，以及本项目落库后的作品和文件元数据格式。

## 数据来源

作品列表来自：

```text
GET /api/works?order=create_date&sort=desc&page={page}&pageSize={pageSize}
```

作品文件列表来自：

```text
GET /api/tracks/{work_id}
```

当前代码会轮询这些 API 域名：

```text
api.asmr-300.com
api.asmr-200.com
api.asmr-100.com
```

## 作品列表响应

`/api/works` 返回一个对象，顶层包含 `works` 和 `pagination`：

```json
{
  "works": [
    {
      "id": 1563146,
      "title": "作品标题",
      "circle_id": 1060860,
      "name": "社团名",
      "nsfw": true,
      "release": "2026-02-27",
      "dl_count": 49,
      "price": 1980,
      "review_count": 0,
      "rate_count": 5,
      "rate_average_2dp": 5,
      "rate_count_detail": [],
      "rank": null,
      "has_subtitle": true,
      "create_date": "2026-04-04",
      "vas": [],
      "tags": [],
      "language_editions": [],
      "original_workno": null,
      "other_language_editions_in_db": [],
      "translation_info": {},
      "work_attributes": "RG01060860,adl,male,SOU,SND,JPN,DLP",
      "age_category_string": "adult",
      "duration": 7860,
      "source_type": "DLSITE",
      "source_id": "RJ01563146",
      "source_url": "https://www.dlsite.com/maniax/work/=/product_id/RJ01563146.html",
      "userRating": null,
      "circle": {},
      "samCoverUrl": "https://api.example/api/cover/1563146.jpg?type=sam",
      "thumbnailCoverUrl": "https://api.example/api/cover/1563146.jpg?type=240x240",
      "mainCoverUrl": "https://api.example/api/cover/1563146.jpg?type=main"
    }
  ],
  "pagination": {
    "currentPage": 1,
    "pageSize": 500,
    "totalCount": 60542
  }
}
```

主要字段说明：

- `id`：网站内部作品 ID，本项目后续作为 `work_id` 使用。
- `title`：作品标题。
- `circle_id`、`name`、`circle`：社团 ID、社团名和社团对象。
- `nsfw`：是否成人内容。
- `release`：发行日期，格式通常为 `YYYY-MM-DD`。
- `dl_count`、`price`、`review_count`、`rate_count`、`rate_average_2dp`：销量、价格和评分相关数据。
- `rate_count_detail`：各评分档位统计数组。
- `rank`：排名信息，可能为 `null`。
- `has_subtitle`：是否带字幕。
- `create_date`：网站收录日期，增量爬取用它作为检查点。
- `vas`：声优数组。
- `tags`：标签数组，包含多语言名称、投票数和状态。
- `language_editions`、`original_workno`、`other_language_editions_in_db`、`translation_info`：多语言版本和翻译相关信息。
- `work_attributes`：逗号分隔的属性编码字符串。
- `age_category_string`：年龄分级字符串，例如 `adult`。
- `duration`：作品总时长，单位为秒。
- `source_type`、`source_id`、`source_url`：来源站点类型、来源作品编号和来源 URL。
- `samCoverUrl`、`thumbnailCoverUrl`、`mainCoverUrl`：不同尺寸封面 URL。

### 嵌套对象

`vas` 元素格式：

```json
{
  "id": "5cb496f3-1c5e-5567-a654-e0784ba04b2c",
  "name": "声优名"
}
```

`tags` 元素格式：

```json
{
  "id": 415,
  "i18n": {
    "en-us": { "name": "Gal" },
    "ja-jp": { "name": "ギャル" },
    "zh-cn": {
      "name": "辣妹",
      "history": []
    }
  },
  "name": "辣妹",
  "upvote": null,
  "downvote": null,
  "voteRank": 15,
  "voteStatus": 1
}
```

`circle` 元素格式：

```json
{
  "id": 1060860,
  "name": "社团名",
  "source_id": "RG01060860",
  "source_type": "DLSITE"
}
```

## 轨道树响应

`/api/tracks/{work_id}` 返回数组，数组元素可以是文件夹，也可以是文件。

文件夹节点：

```json
{
  "type": "folder",
  "title": "効果音あり",
  "children": []
}
```

文件节点：

```json
{
  "type": "audio",
  "hash": "1563146/1799580",
  "title": "トラック01.wav",
  "work": {
    "id": 1563146,
    "source_id": "RJ01563146",
    "source_type": "DLSITE"
  },
  "workTitle": "作品标题",
  "mediaStreamUrl": "https://raw.example/media/stream/...",
  "mediaDownloadUrl": "https://raw.example/media/download/...",
  "streamLowQualityUrl": "https://fast.example/media/stream/...",
  "duration": 371.09998,
  "size": 106893570
}
```

文件节点字段说明：

- `type`：节点类型。常见值有 `audio`、`text`、`folder`。
- `hash`：网站返回的文件标识。本项目落库到 `cloudflare_etag` 字段，用于下载前去重。
- `title`：当前节点名称。递归遍历文件夹时会拼成相对路径。
- `work`：文件所属作品对象。
- `workTitle`：作品标题。
- `mediaStreamUrl`：在线播放地址。
- `mediaDownloadUrl`：下载地址。本项目下载文件时使用该字段。
- `streamLowQualityUrl`：低质量流地址，可能为空字符串，也可能不存在。
- `duration`：轨道时长，单位为秒。
- `size`：文件大小，单位为字节。

## 本项目落库格式

当前项目会把作品级元数据、声优、标签和文件级元数据写入 SQLite。`VoiceWorksSpider` 使用 `WorkMetadataPipeline` 保存作品相关表；`VoiceFilesSpider` 使用 `VoiceFilesDBPipeline` 保存文件表。

### 作品表

`t_work` 保存 `/api/works` 中每个作品的主要字段，并用 `raw_json` 保留原始作品 JSON。

```sql
CREATE TABLE IF NOT EXISTS t_work (
    work_id TEXT PRIMARY KEY,
    title TEXT,
    circle_id TEXT,
    circle_name TEXT,
    source_id TEXT,
    source_type TEXT,
    source_url TEXT,
    nsfw INTEGER,
    release_date TEXT,
    create_date TEXT,
    dl_count INTEGER,
    price INTEGER,
    review_count INTEGER,
    rate_count INTEGER,
    rate_average_2dp REAL,
    has_subtitle INTEGER,
    duration INTEGER,
    work_attributes TEXT,
    age_category_string TEXT,
    sam_cover_url TEXT,
    thumbnail_cover_url TEXT,
    main_cover_url TEXT,
    raw_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

字段来源：

- `work_id`：来自作品 `id`，统一转为字符串保存。
- `title`：来自作品 `title`。
- `circle_id`：优先来自 `circle_id`，为空时使用 `circle.id`。
- `circle_name`：优先来自 `name`，为空时使用 `circle.name`。
- `source_id`、`source_type`、`source_url`：来自同名字段。
- `nsfw`：来自作品 `nsfw`，保存为 `0` 或 `1`。
- `release_date`：来自作品 `release`。
- `create_date`：来自作品 `create_date`，也用于增量爬取检查点。
- `dl_count`、`price`、`review_count`、`rate_count`、`rate_average_2dp`：销量、价格和评分统计。
- `has_subtitle`：来自作品 `has_subtitle`，保存为 `0` 或 `1`。
- `duration`：作品总时长，单位为秒。
- `work_attributes`、`age_category_string`：来自同名字段。
- `sam_cover_url`、`thumbnail_cover_url`、`main_cover_url`：来自 `samCoverUrl`、`thumbnailCoverUrl`、`mainCoverUrl`。
- `raw_json`：完整作品 JSON 字符串。
- `updated_at`：本项目写入或更新记录时的 UTC 时间。

### 声优和作品关联表

`t_va` 保存声优，`t_work_va` 保存作品和声优的多对多关系。

```sql
CREATE TABLE IF NOT EXISTS t_va (
    va_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    raw_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_work_va (
    work_id TEXT NOT NULL,
    va_id TEXT NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (work_id, va_id)
);
```

字段来源：

- `va_id`：来自 `vas[].id`；如果缺失，则用 `name:{声优名}` 作为替代 ID。
- `name`：来自 `vas[].name`。
- `raw_json`：完整声优 JSON 字符串。
- `updated_at`：本项目写入或更新声优记录时的 UTC 时间。

### 标签和作品关联表

`t_tag` 保存标签，`t_work_tag` 保存作品和标签的多对多关系。

```sql
CREATE TABLE IF NOT EXISTS t_tag (
    tag_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    raw_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS t_work_tag (
    work_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (work_id, tag_id)
);
```

字段来源：

- `tag_id`：来自 `tags[].id`；如果缺失，则用 `name:{标签名}` 作为替代 ID。
- `name`：来自 `tags[].name`。
- `raw_json`：完整标签 JSON 字符串，包含 `i18n`、投票数和状态等网站字段。
- `updated_at`：本项目写入或更新标签记录时的 UTC 时间。

### 文件表

`t_file` 保存 `/api/tracks/{work_id}` 递归展开后的文件节点。旧库升级时会通过 `ALTER TABLE` 补齐新增列。

```sql
CREATE TABLE IF NOT EXISTS t_file (
    uuid TEXT PRIMARY KEY,
    work_id TEXT NOT NULL,
    path TEXT NOT NULL,
    download_url TEXT NOT NULL,
    cloudflare_etag TEXT,
    size INTEGER NOT NULL,
    md5 TEXT,
    download_date TEXT,
    masked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    file_type TEXT,
    title TEXT,
    duration REAL,
    media_stream_url TEXT,
    stream_low_quality_url TEXT,
    work_title TEXT,
    raw_json TEXT,
    tts_skip_reason TEXT
);
```

字段来源：

- `uuid`：本项目生成的 UUIDv7 hex，用作文件记录主键。
- `work_id`：来自作品 `id`，对应 `/api/tracks/{work_id}` 的路径参数。
- `path`：由轨道树文件夹名和文件名拼出的相对路径。
- `download_url`：来自文件节点 `mediaDownloadUrl`。
- `cloudflare_etag`：来自文件节点 `hash`。
- `size`：来自文件节点 `size`；下载完成后会按实际文件大小更新。
- `file_type`：来自文件节点 `type`，例如 `audio` 或 `text`。
- `title`：来自文件节点 `title`，只保存文件名，不包含父级文件夹路径。
- `duration`：来自文件节点 `duration`，单位为秒。
- `media_stream_url`：来自文件节点 `mediaStreamUrl`。
- `stream_low_quality_url`：来自文件节点 `streamLowQualityUrl`。
- `work_title`：来自文件节点 `workTitle`。
- `raw_json`：完整文件节点 JSON 字符串。
- `tts_skip_reason`：自动文件级 TTS 跳过原因。非 `NULL` 表示该文件不进入 TTS 下载队列。
- `md5`：下载后按文件内容计算。
- `download_date`：下载并上传成功后的日期，格式为 `YYYY-MM-DD`。
- `masked`：人工屏蔽标记。下载任务只处理 `masked = 0` 的记录。
- `created_at`：SQLite 写入记录时的时间戳。

### 文件级 TTS 跳过规则

`tts_skip_reason` 是自动规则字段，用来排除不适合 TTS 训练的音频文件。它和 `masked` 的职责不同：

- `masked`：人工屏蔽开关。当前代码不会把自动规则写入 `masked`。
- `tts_skip_reason`：自动规则结果。下载器会跳过所有 `tts_skip_reason IS NOT NULL` 的文件。

当前规则实现位于 `asmrone_crawler/file_rules.py`。只对音频文件生效；字幕、台本、图片等非音频文件不会因为这些规则被标记。

当前 reason 值：

- `no_dialogue`：无台词或无 voice 的音频，例如路径包含 `台詞レス`、`台詞なし`、`セリフレス`、`no dialogue`、`no voice`。
- `sound_only`：只有声音或音效的音频，例如 `効果音のみ`、`SEのみ`、`フェラ音のみ`、`耳舐め音のみ`、`環境音`。
- `sound_effect_material`：音效素材目录中的音频，例如路径目录包含 `効果音/`、`SE/`、`SFX/`、`SE素材/`、`行動系/`。
- `short_audio`：时长小于 3 秒的音频。

下载器实际队列条件包含：

```sql
FROM t_file f
JOIN t_work w ON w.work_id = f.work_id
WHERE f.masked = 0
  AND f.download_date IS NULL
  AND w.keep_japanese_audio = 1
  AND f.tts_skip_reason IS NULL;
```

如果修改了 `asmrone_crawler/file_rules.py`，需要重新扫描已有数据库：

```bash
uv run python asmrone_mark_tts_skip_reasons.py
```

如果下载器服务正在运行，先停服务、扫描、再重启：

```bash
systemctl --user stop asmrone-downloader.service
uv run python asmrone_mark_tts_skip_reasons.py
systemctl --user start asmrone-downloader.service
systemctl --user is-active asmrone-downloader.service
```

进度统计使用：

```bash
uv run python asmrone_progress.py
```

进度输出中的 `skipped_tts_unusable` 是所有 `tts_skip_reason IS NOT NULL` 文件的汇总，并会按 reason 继续展开显示。

### 查询能力

现在可以按声优、社团和标签聚合查询。

按声优统计作品数：

```sql
SELECT
    v.name,
    COUNT(DISTINCT wv.work_id) AS work_count
FROM t_work_va AS wv
JOIN t_va AS v ON v.va_id = wv.va_id
GROUP BY v.va_id, v.name
ORDER BY work_count DESC;
```

按社团统计作品数：

```sql
SELECT
    circle_name,
    COUNT(*) AS work_count
FROM t_work
WHERE circle_name IS NOT NULL
GROUP BY circle_name
ORDER BY work_count DESC;
```

按标签统计作品数：

```sql
SELECT
    t.name,
    COUNT(DISTINCT wt.work_id) AS work_count
FROM t_work_tag AS wt
JOIN t_tag AS t ON t.tag_id = wt.tag_id
GROUP BY t.tag_id, t.name
ORDER BY work_count DESC;
```

如果要把聚合结果限制到已下载文件，可以从关联表连接到 `t_file`，并过滤 `t_file.download_date IS NOT NULL`。

## 路径与上传规则

轨道树会递归展开为文件路径。例如：

```text
効果音あり/wav/トラック01.wav
```

上传对象 key 由 `OSS_PREFIX`、`work_id` 和 `path` 拼成：

```text
{OSS_PREFIX}/{work_id}/{path}
```

如果原文件扩展名是 `.wav`，下载器会先转换为 `.flac`，再把对象 key 的扩展名改为 `.flac`：

```text
datasets/speech_datasets/asmr/1563146/効果音あり/wav/トラック01.flac
```

## 增量爬取状态

增量爬取状态保存在 SQLite 表 `crawl_state`：

```sql
CREATE TABLE IF NOT EXISTS crawl_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

当前使用的 key：

- `max_create_date`：已完成爬取的最大 `create_date`。非全量模式会跳过 `create_date <= max_create_date` 的作品。

## 注意事项

- 网站 API 字段不是由本项目控制，新增字段应允许透传或忽略。
- `work_id` 在网站接口中是数字，但本项目数据库用 `TEXT` 存储。
- `path` 保留网站返回的原始标题字符，可能包含日文、空格和标点。
- `.wav` 上传后对象扩展名会变成 `.flac`，但数据库 `path` 仍保留原始 `.wav` 路径。
- 非音频文件也会进入 `t_file`，只要轨道树中存在 `mediaDownloadUrl`、`hash` 和 `size`。
