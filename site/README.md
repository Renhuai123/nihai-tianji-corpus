# site/ · 学习站（静态，零依赖）

由 `tools/build_site.py` 从 `data/` 生成，**纯静态 HTML**，无需构建工具与后端。

## 本地预览

```bash
cd site && python3 -m http.server 8000
# 浏览器打开 http://localhost:8000
```

## 结构

| 页面 | 内容 |
|---|---|
| `index.html` | 总览：全库检索 + 十一册书架 + 112 单元课程入口 |
| `book-NN.html` | 册页（轴 A · 按体系查）：大类 → 子类 → 判语卡 |
| `unit-{bvid}-pNN.html` | 单元页（轴 B · 按课程学）：语义段时间轴 + 段内判语卡 |
| `data/search-index.json` | 前端检索索引（4886 条） |

## 判语卡

每张卡 = 倪师原话引文 + `▶ 时间码`（新窗打开 B 站原视频那一秒）+ 出处徽章 +
考据标注（若有）+ 归属面包屑。引文中的星曜／宫位／四化等术语自动成为可点标签，
点击回到检索页查该术语的全部判语。

## 接入自有站点

页面无框架依赖，取用方式二选一：
- 直接部署本目录（GitHub Pages / 任意静态托管）
- 参照 `tools/build_site.py` 中的 `card()` 与 `linkify()` 移植判语卡组件，
  数据源仍用 `data/entries.jsonl` + `data/sections/`
