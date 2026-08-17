# 数据字段说明 v2.0

## entries.jsonl（一行一条判语，共 4886 条）

```json
{
  "book": "09-hexagrams",
  "h2": "水雷屯（卦03）",
  "h3": "爻辞断诀",
  "quote": "倪师原话短引文",
  "bvid": "BV1q7BZYcEZP",
  "part": 6,
  "gua": 3,
  "section": 4,
  "t_hms": "00:12:58",
  "note": ""
}
```

| 字段 | 含义 |
|---|---|
| `book` | 所属册：`01-stars` `02-palaces` `03-patterns` `04-sihua` `05-illness` `07-methodology` `08-yili` `09-hexagrams` `10-divination` `11-fengshui` `12-tieban` |
| `h2` / `h3` | 册内大类 / 子类（对应 docs/ 各册的二、三级标题） |
| `quote` | 倪师原话（仅删口语赘词与 OCR 噪声、补标点，不改字；字幕错字经人工裁决改正并在 note 留痕） |
| `bvid` | 视频号：`BV1KJsLekEfA`（正片）或 `BV1q7BZYcEZP`（六十四卦） |
| `part` | 该视频的分P号 |
| `gua` | 仅六十四卦条目有：卦序号（1–64），`part = gua + 3` |
| `section` | 该单元内语义段号（对应 `sections/`） |
| `t_hms` | 该判语在本单元内的起始时间 |
| `note` | 考据标注（如 `已按裁决改正：X→Y`）；空串表示无 |

**回放 URL**：`https://www.bilibili.com/video/{bvid}?p={part}&t={t_hms换算秒}`

## sections/{bvid}_pNN.json（每单元语义段索引，共 112 个）

```json
{ "section": 4, "t_start_ms": 720000, "t_end_ms": 1150000,
  "topic": "三方四正与对宫借星", "cue_range": [280, 401] }
```

## 生产管线摘要

人工校正字幕逐帧 OCR（主源）→ whisper large-v3-turbo + FunASR paraformer 双引擎独立转写
交叉验证 → 七道门禁（空批次防线 / 秒级去重 / 探针覆盖≥95% / 一致率≥60% / 术语白名单 /
出处可回溯≥95% / 逐字命中≥90%）→ 全库语义清扫（只删不改，程序验证子序列）→
字幕错字人工裁决 + 幂等重放 → 三轮独立抽样审查（封库终裁 0.0% 问题率）。

门禁与重放器实现见 `tools/`，复现步骤见 `tools/REPRODUCE.md`。
