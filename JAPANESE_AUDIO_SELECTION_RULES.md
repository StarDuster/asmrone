# 日语语音筛选规则

本文档定义如何根据 ASMR.one 元数据判断一个作品是否属于“日语语音资源”，并说明 `t_work.keep_japanese_audio` 字段的含义。字段来源可参考 `WEBSITE_METADATA_FORMAT.md` 中的作品表和轨道树说明。

## 目标

只保留日语语音资源。对于命中的作品，下载器后续应能把它的源文件保存到 OSS；对于不命中的作品，不应进入 OSS 下载范围。

这里的“日语语音”指音频内容主要是日语。中文字幕、英文字幕、中文台本、多语言台本、翻译标题都不能单独证明音频不是日语。

## 决策字段

在 `t_work` 上使用 `keep_japanese_audio` 表示作品级保留决策：

- `1`：按当前规则判断为日语语音资源，应保留并上传到 OSS。
- `0`：按当前规则判断不是日语语音资源，不应保留。
- `NULL`：尚未计算，或证据冲突，需要复核。

该字段是规则计算结果，不是人工备注。人工复核只用于处理 `NULL` 或明显误判的样本。

字段放在 `t_work`，不放在 `t_file`。语音语言通常是作品级判断；具体文件仍然由已有文件级规则处理，例如无音效优先、WAV 转 FLAC、字幕或台本是否下载等。

## 字段边界

`work_attributes`

这是最重要的语言标签来源之一。它是逗号分隔的混合属性编码，可能同时包含社团编号、作品类型、受众、语言和内容标签。常见语言 token 包括 `JPN`、`CHI`、`CHI_HANS`、`CHI_HANT`、`ENG`、`KO_KR`。

`JPN` 是日语语音的重要正向证据，但不是唯一证据。作品也可能同时带中文或英文台本，因此出现多个语言 token 时不能只按非日语 token 排除。

`language_editions`

这是多语言版本族信息。应优先检查当前作品的 `source_id` 是否等于某个 `language_editions[].workno`，再读取对应项的 `lang` 和 `label`。

`label` 比 `lang` 更能说明版本性质。比如 `日本語`、`日本語音声 多言語字幕付き` 是正向证据；`中文配音版`、`簡体字幕版`、`英語（公式翻訳）`、`中文（簡・繁）（公式翻訳）` 则需要按后面的规则处理。

`translation_info`

`translation_info.lang` 只表示翻译子版本语言，不表示音频语言。`translation_info.is_child = true` 通常表示当前条目是翻译版本，应谨慎处理。

不要把 `translation_info.lang = CHI_HANS` 或 `CHI_HANT` 直接理解为中文音频。很多这种条目只是中文标题、中文字幕、中文台本或翻译版商品。

`has_subtitle` 和文件路径

`has_subtitle`、`.vtt`、`.srt`、`.lrc`、`.txt`、`.pdf`、路径里的 `字幕`、`台本`、`script`、`Translated script` 只说明存在字幕、歌词或台本。它们不能单独决定音频语言。

`tags`

`tags` 主要是内容标签，例如 ASMR、双声道、舔耳、淫语等。不要把 `tags` 当作语种判断依据。

## 判定顺序

按以下顺序计算 `keep_japanese_audio`。

1. 先检查明确的非日语语音证据。

   如果标题或当前 `language_editions` 的 `label` 明确包含非日语配音或非日语音声，例如 `中文音声`、`中文音聲`、`中文配音`、`粤语配音`、`粵語配音`、`English Voice`、`English audio`、`韓国語音声`、`한국어음성`，则写 `keep_japanese_audio = 0`。

2. 再检查明确的日语语音证据。

   如果当前 `language_editions` 匹配项的 `label` 是 `日本語`，或标题、label 明确包含 `日本語音声`、`日语音声`、`日文版`、`日本語版`，并且没有第 1 步中的非日语音声证据，则写 `keep_japanese_audio = 1`。

3. 使用 `work_attributes` 判断主语言。

   如果 `work_attributes` 包含 `JPN`，并且标题、label 没有明确写成非日语配音，则写 `keep_japanese_audio = 1`。

4. 排除明确的翻译子版本。

   如果 `translation_info.is_child = true`，且 `translation_info.lang` 是 `CHI_HANS`、`CHI_HANT`、`ENG`、`KO_KR` 等非日语翻译语言，同时没有明确的 `日本語音声` 证据，则写 `keep_japanese_audio = 0`。

5. 排除只有非日语语言标签的作品。

   如果 `work_attributes` 不包含 `JPN`，但包含 `CHI`、`CHI_HANS`、`CHI_HANT`、`ENG`、`KO_KR` 等非日语语言 token，并且标题或 label 没有明确表示日语音声，则写 `keep_japanese_audio = 0`。

6. 保留不确定项。

   如果多语言同捆、标题与属性冲突、`language_editions` 无法匹配当前 `source_id`，或只看到 `中文版`、`英語版` 但无法判断是字幕、台本还是配音，则保持 `keep_japanese_audio = NULL`，后续抽样复核。

## 常见误判

- `translation_info.lang = CHI_HANS` 不等于中文音频。它经常只是中文翻译版本。
- `has_subtitle = 1` 不等于非日语音频。很多日语音频也有字幕或 `.lrc`。
- 标题包含 `中文版` 不一定是中文配音，可能只是字幕版、台本版或翻译版。
- `work_attributes` 同时包含 `JPN` 和 `CHI_HANS` 时，不要直接排除。需要结合标题、`language_editions.label` 和文件路径判断中文是字幕、台本还是配音。
- `tags` 中的中文名称只是界面本地化，不代表作品语言。

## 下载器使用方式

后续下载器筛选时，应通过 `t_file.work_id = t_work.work_id` 关联作品表，只选择 `t_work.keep_japanese_audio = 1` 的作品文件。

`keep_japanese_audio IS NULL` 的作品不应默认下载到 OSS，除非当前运行是专门用于复核或补样。

## 推荐复核查询

复核未决作品：

```sql
SELECT work_id, source_id, title, work_attributes, has_subtitle
FROM t_work
WHERE keep_japanese_audio IS NULL
ORDER BY CAST(work_id AS INTEGER) DESC;
```

检查将进入 OSS 的作品：

```sql
SELECT work_id, source_id, title, work_attributes
FROM t_work
WHERE keep_japanese_audio = 1
ORDER BY CAST(work_id AS INTEGER) DESC;
```

检查被排除的翻译版本：

```sql
SELECT work_id, source_id, title, work_attributes
FROM t_work
WHERE keep_japanese_audio = 0
  AND raw_json LIKE '%"is_child": true%';
```
