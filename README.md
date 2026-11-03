# asmrone

抓取 ASMR.one 的作品元数据，从中筛选日语语音文件，下载后转成 FLAC 并上传到 S3 兼容对象存储（OSS）。目标是构建干净的语音/TTS 语料，而不是整站镜像。

仓库同时提供一份只读的元数据快照，见 [DATA_SNAPSHOT.md](DATA_SNAPSHOT.md)。

## 流程

```text
/ api/works ──────────► VoiceWorksSpider ──┐
                                           ├─► pipelines ─► SQLite
/ api/tracks/{work_id} ► VoiceFilesSpider ─┘

SQLite ─► asmrone_downloader ─► 下载 ─► wav→flac ─► 上传 OSS ─► 回写 download_date
```

## 目录

| 路径 | 作用 |
| --- | --- |
| `asmrone_crawler.py` | 依次运行两个 spider，入口参数 `--full` 表示全量抓取 |
| `asmrone_crawler/spiders/voice_works.py` | 抓 `/api/works`，写作品级元数据 |
| `asmrone_crawler/spiders/voice_files.py` | 抓 `/api/tracks/{work_id}`，写递归文件树 |
| `asmrone_crawler/pipelines.py` | 把作品、声优、标签、文件写入 SQLite |
| `asmrone_crawler/storage.py` | SQLite 表结构与轻量迁移 |
| `asmrone_crawler/file_rules.py` | 音频判定、音效素材排除与 TTS 跳过原因规则 |
| `asmrone_downloader.py` | 选出待下载队列，多线程下载、转码、上传、回写 |
| `asmrone_progress.py` | 打印下载队列进度 |
| `asmrone_mark_tts_skip_reasons.py` | 给不适合 TTS 的文件打跳过原因 |
| `asmrone_tmp_cleanup.py` | 清理下载临时目录里过期的残留文件 |

## 环境要求

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- `ffmpeg`（`.wav` → `.flac` 转换需要，缺失时下载器会直接报错）

```sh
uv sync
```

## 配置

对象存储凭据不放在环境变量里，而是从 rclone 配置读取：

```ini
# ~/.config/rclone/rclone.conf
[alioss]                                  # 名字由 RCLONE_REMOTE_NAME 决定
type = s3
provider = Alibaba
access_key_id = ...
secret_access_key = ...
endpoint = oss-cn-....aliyuncs.com
```

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `SQLITE_PATH` | `$XDG_DATA_HOME/asmrone/asmrone.db`（通常是 `~/.local/share/asmrone/asmrone.db`） | SQLite 路径 |
| `DOWNLOAD_TMP_DIR` | `~/.local/share/asmrone/tmp` | 下载临时目录 |
| `OSS_BUCKET_NAME` | **无默认值，必填** | 上传目标 bucket |
| `OSS_PREFIX` | 空（bucket 根） | 对象键前缀 |
| `RCLONE_CONFIG` | `~/.config/rclone/rclone.conf` | 凭据来源 |
| `RCLONE_REMOTE_NAME` | `alioss` | rclone remote 名 |
| `NUM_WORKERS` | `24` | 下载线程数 |
| `NUM_LARGE_FILE_WORKERS` | `8` | 大文件（≥100 MB）线程数 |
| `DOWNLOAD_CHUNK_SIZE` | `4194304` | 下载分块字节数 |
| `FLAC_COMPRESSION_LEVEL` | `5` | ffmpeg FLAC 压缩级别 |
| `TQDM_MIN_INTERVAL` | `5` | 进度条最小刷新间隔（秒） |
| `TMP_CLEANUP_MIN_AGE_HOURS` | `6` | 清理脚本只删超过此时长的文件 |

`OSS_BUCKET_NAME` 未设置时，上传路径会以 `RuntimeError` 明确失败，不会回落到任何内置 bucket。

## 运行

```sh
export OSS_BUCKET_NAME=your-bucket
export OSS_PREFIX=asmr

python asmrone_crawler.py            # 增量；--full 为全量
python asmrone_mark_tts_skip_reasons.py
python asmrone_progress.py           # 看队列
python asmrone_downloader.py
python asmrone_tmp_cleanup.py
```

下载器只处理 `masked = 0`、`download_date IS NULL`、`keep_japanese_audio = 1` 且没有 `tts_skip_reason` 的文件；上传后用 `head_object` 校验对象大小，不一致则删除该对象并记录错误。

## 数据模型

| 表 | 内容 |
| --- | --- |
| `t_work` | 作品元数据，含 `keep_japanese_audio` 判定结果 |
| `t_file` | 递归文件树，含下载地址、大小、MD5、`download_date`、跳过原因 |
| `t_va` / `t_work_va` | 声优及关联 |
| `t_tag` / `t_work_tag` | 标签及关联 |
| `crawl_state` | 抓取进度 |

`t_file` 的字段含义与抓取口径见 [WEBSITE_METADATA_FORMAT.md](WEBSITE_METADATA_FORMAT.md)，日语语音的筛选规则见 [JAPANESE_AUDIO_SELECTION_RULES.md](JAPANESE_AUDIO_SELECTION_RULES.md)。

## 合规

仓库只包含抓取器代码与元数据，不包含任何音频文件。使用前请自行确认目标站点的服务条款与所在地区的版权要求，并控制请求频率。
