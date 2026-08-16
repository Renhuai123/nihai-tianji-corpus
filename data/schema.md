# 数据字段说明

## entries.jsonl（一行一条判语，共 1910 条）

```json
{
  "book": "02-palaces",
  "h2": "命宫",
  "h3": "命宫 vs 身宫",
  "quote": "我们看命宫的时候一定要同时兼看另外三个宫。",
  "part": 3,
  "section": 4,
  "t_hms": "00:12:58",
  "cue_from": 294,
  "cue_to": 296,
  "note": "已按裁决改正：命官→命宫"
}
```

| 字段 | 含义 |
|---|---|
| `book` | 所属册：`01-stars` / `02-palaces` / `03-patterns` / `04-sihua` / `05-illness` / `07-methodology` |
| `h2` / `h3` | 册内大类 / 子类（对应 docs/ 六册的二、三级标题） |
| `quote` | 倪师原话（仅删口语赘词、补标点，不改字；字幕错字经人工裁决改正并在 note 留痕） |
| `part` | B 站正片 BV1KJsLekEfA 的分P号 |
| `section` | 该讲内语义段号（对应 `sections/` 索引） |
| `t_hms` | 该判语在本讲内的起始时间 |
| `cue_from` / `cue_to` | 源字幕 cue 区间号（内部溯源用） |
| `note` | 考据标注；空串表示无 |

**回放 URL 拼法**：`https://www.bilibili.com/video/BV1KJsLekEfA?p={part}&t={t_hms换算秒}`

## sections/BV1KJsLekEfA_pNN.json（每讲语义段索引）

```json
{ "section": 4, "t_start_ms": 720000, "t_end_ms": 1150000,
  "topic": "三方四正与对宫借星", "cue_range": [280, 401] }
```

## 生产管线摘要（可复现性）

烧录字幕 OCR（人工校正字幕为真值）→ whisper large-v3-turbo 探针逐条交叉验证
→ 七道门禁（时长去重 / 探针覆盖≥95% / 一致率≥60% / 术语白名单 / 出处可回溯≥95% /
逐字命中≥90% / 归类抽查）→ 字幕错字人工裁决 + 幂等重放（`tools/apply_corrections.py`）。
门禁实现见 `tools/gate_check.py`（路径按各自环境调整）。
