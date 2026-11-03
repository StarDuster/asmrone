# 目录数据快照

本仓库同时存放抓取器代码与一份只读的 SQLite 元数据快照。快照走 Git LFS，不含任何音频/媒体文件。

| 项 | 值 |
| --- | --- |
| 文件 | `asmrone-20260810.db.zst` |
| 原始大小 | 5,717,127,168 字节（5.32 GiB） |
| 归档大小 | 344,843,975 字节（328.9 MiB，6.03%） |
| 压缩 | `zstd -19 -T0 --long=27` |
| SHA-256（归档） | `0a3b871a50d1d6a24c0ab21f5a17fd261147d2e94ae054d7ec623eeb761db253` |
| SHA-256（原始库） | `54ec1ba1f838410f7ce9253fa64041f94a621ec7f2f062d331383b42b61a5765` |
| 数据库最后写入 | 2026-08-10 14:50:27 +0800 |

## 内容

SQLite 3，`journal_mode=wal`，页大小 4096，1,395,783 页。

| 表 | 行数 |
| --- | --- |
| `t_file` | 1,760,301（其中已有 `download_date` 的 1,298,064） |
| `t_work` | 60,542 |
| `t_va` | 5,461 |
| `t_tag` | 418 |
| `crawl_state` | 1 |

`t_file.created_at` 覆盖 2026-04-28 19:03:23 至 2026-04-30 06:18:16。`t_file` 约占总数据量 4.65 GB，主要是 `path`、`download_url`、`media_stream_url`、`raw_json` 等文本字段，因此压缩比很高。

## 恢复

```sh
git lfs pull
shasum -a 256 asmrone-20260810.db.zst   # 期望 0a3b871a…
zstd -d asmrone-20260810.db.zst -o asmrone.db
shasum -a 256 asmrone.db                # 期望 54ec1ba1…
```

## 说明

- 运行库本身被 `.gitignore` 的 `asmrone.db*` 排除，仓库里只有压缩归档。
- 归档 328.9 MiB 低于 GitHub 单文件 2 GB 的 LFS 上限；私有仓库的 LFS 存储与下载带宽计入仓库 owner 的配额。
- 更新快照请新增文件而不是覆盖同名文件，否则旧 LFS 对象仍会占用配额。
