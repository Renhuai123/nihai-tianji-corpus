#!/usr/bin/env python3
"""
格局重绘图批量生成器

依据 03 格局册的判语数据，用 SVG 重新绘制紫微盘面 —— 不复制原视频任何像素。
每张图标注该格局的成格条件与判语出处，可回原视频核对。

输入：_work/chart_specs.json（由判语抽取的盘面规格）
输出：docs/charts/*.svg + docs/charts/README.md

用法：python3 tools/draw_charts.py
"""
import json, os, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs/charts")

# 十二宫按紫微盘传统布局（四方形，地支固定位置）
POS = {"巳": (0, 0), "午": (1, 0), "未": (2, 0), "申": (3, 0),
       "辰": (0, 1), "酉": (3, 1),
       "卯": (0, 2), "戌": (3, 2),
       "寅": (0, 3), "丑": (1, 3), "子": (2, 3), "亥": (3, 3)}

CELL, M = 150, 12
W = M * 2 + CELL * 4
H = W + 132  # 底部留图注

LINK_STYLE = {
    "对宫": ("#b04a3e", "none", 2.4),
    "三合": ("#8a7a63", "7 5", 2.0),
    "会照": ("#8a7a63", "3 4", 1.8),
    "夹":   ("#2e7d5b", "2 4", 2.0),
}


def xy(z):
    c, r = POS[z]
    return M + c * CELL, M + r * CELL


def ctr(z):
    x, y = xy(z)
    return x + CELL / 2, y + CELL / 2


def esc(s):
    return html.escape(s or "")


def draw(spec):
    cells = {c["branch"]: c for c in spec["cells"] if c["branch"] in POS}
    S = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'font-family="PingFang SC, Noto Sans SC, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#faf8f4"/>']

    # 关系连线（先画，压在格线下层）
    for lk in spec["links"]:
        if lk["from"] not in POS or lk["to"] not in POS:
            continue
        color, dash, wd = LINK_STYLE.get(lk["type"], ("#8a7a63", "4 4", 1.8))
        x1, y1 = ctr(lk["from"])
        x2, y2 = ctr(lk["to"])
        S.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
                 f'stroke-width="{wd}" stroke-dasharray="{dash}" opacity="0.5"/>')

    # 十二宫格
    for z, (c, r) in POS.items():
        x, y = xy(z)
        cell = cells.get(z)
        fill = "#f3ddc4" if (cell and cell["emphasis"]) else ("#f7f2e8" if cell else "#ffffff")
        S.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" fill="{fill}" '
                 f'stroke="#8a7a63" stroke-width="1.3" fill-opacity="0.92"/>')
        S.append(f'<text x="{x + 9}" y="{y + 22}" font-size="14" fill="#8a7a63">{z}</text>')
        if not cell:
            continue
        stars = cell["stars"][:4]
        for i, st in enumerate(stars):
            fs = 25 if (cell["emphasis"] and len(stars) <= 2) else 19
            S.append(f'<text x="{x + CELL / 2}" y="{y + 56 + i * (fs + 5)}" font-size="{fs}" '
                     f'text-anchor="middle" fill="#1a1d21" font-weight="bold">{esc(st)}</text>')
        if cell["role"]:
            S.append(f'<text x="{x + CELL / 2}" y="{y + CELL - 16}" font-size="13" '
                     f'text-anchor="middle" fill="#b04a3e">{esc(cell["role"])}</text>')

    # 中宫：格局名 + 类型 + 图例
    cx = M + CELL
    S.append(f'<rect x="{cx}" y="{cx}" width="{CELL * 2}" height="{CELL * 2}" '
             f'fill="#faf8f4" stroke="#8a7a63" stroke-width="1.3" fill-opacity="0.9"/>')
    mid = W / 2
    S.append(f'<text x="{mid}" y="{mid - 22}" font-size="27" text-anchor="middle" '
             f'fill="#1a1d21" font-weight="bold">{esc(spec["name"])}</text>')
    kc = "#2e7d5b" if spec["kind"] == "吉格" else ("#b04a3e" if spec["kind"] == "凶格" else "#8a7a63")
    S.append(f'<text x="{mid}" y="{mid + 10}" font-size="17" text-anchor="middle" '
             f'fill="{kc}">{esc(spec["kind"])}</text>')
    seen, legend = [], []
    for lk in spec["links"]:
        if lk["type"] not in seen:
            seen.append(lk["type"])
            legend.append(lk["type"])
    if legend:
        txt = " · ".join(f"{t}" for t in legend)
        S.append(f'<text x="{mid}" y="{mid + 42}" font-size="12" text-anchor="middle" '
                 f'fill="#6b7480">连线：{esc(txt)}</text>')

    # 图注
    y0 = W + 24
    g = spec["gist"]
    lines = [g[i:i + 34] for i in range(0, len(g), 34)][:3]
    for i, ln in enumerate(lines):
        S.append(f'<text x="{M + 2}" y="{y0 + i * 22}" font-size="13.5" fill="#1a1d21">{esc(ln)}</text>')
    S.append(f'<text x="{M + 2}" y="{y0 + len(lines) * 22 + 8}" font-size="11.5" fill="#6b7480">'
             f'—— 倪海厦《天纪》{esc(spec["cite"])}</text>')
    S.append(f'<text x="{M + 2}" y="{y0 + len(lines) * 22 + 28}" font-size="11" fill="#a8b0ba">'
             f'本图依判语数据重绘（非原板书复制）· nihai-tianji-corpus · MIT</text>')
    S.append("</svg>")
    return "\n".join(S)


def main():
    specs = json.load(open(os.path.join(ROOT, "_work/chart_specs.json"), encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".svg") and f != "破军居子午-英星入庙.svg":
            os.remove(os.path.join(OUT, f))

    made, skipped = [], []
    for s in specs:
        if not s["drawable"] or not s["cells"]:
            skipped.append(s)
            continue
        name = s["name"].replace("/", "-").replace("（", "-").replace("）", "")
        p = os.path.join(OUT, f"{name}.svg")
        open(p, "w", encoding="utf-8").write(draw(s))
        made.append((name, s))

    rows = "\n".join(f"| [{n}]({n}.svg) | {s['kind']} | {s['gist'][:36]} | `{s['cite']}` |"
                     for n, s in made)
    skip = "、".join(s["name"] for s in skipped)
    open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write(f"""# charts/ · 格局重绘图

倪师板书上的盘面，**依 03 格局册的判语数据用 SVG 重新绘制** —— 不复制原视频任何像素。
每张图的成格条件与出处均来自真实判语，可按出处回原视频核对。

## 图例

- 实线红：**对宫**（相冲）· 虚线金：**三合** · 点线绿：**夹**
- 深底格：成格核心宫 · 浅底格：涉及宫位

## 已绘（{len(made)} 图）

| 格局 | 类型 | 成格条件与主断 | 出处 |
|---|---|---|---|
{rows}

## 未绘（{len(skipped)} 个）

{skip}

这些格局的判语只讲现象与结果、未言盘面结构（星曜落宫、宫位关系），
**据实不画** —— 宁可缺图，不凭空补盘。

---

重绘图为本仓库原创作品，按 MIT 发布。生成器见 [`tools/draw_charts.py`](../../tools/draw_charts.py)。
""")
    print(f"生成 {len(made)} 张重绘图 → docs/charts/")
    for n, s in made:
        print(f"  {n}.svg  ({s['kind']}, {len(s['cells'])}宫 {len(s['links'])}线)")
    print(f"据实未绘 {len(skipped)} 个：{skip}")


if __name__ == "__main__":
    main()
