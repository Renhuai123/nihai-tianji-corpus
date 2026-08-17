#!/usr/bin/env python3
"""
天纪学习产品 · 静态站生成器

从 data/entries.jsonl + data/sections/ 生成一个零依赖的静态站：
    site/index.html          总览（十一册书架 + 五学科课程入口 + 全局检索）
    site/book-XX.html        册页（轴 A：按体系查）
    site/unit-{bvid}-pNN.html 单元页（轴 B：按课程学，语义段时间轴）
    site/data/*.json         前端检索用的分片数据

设计要点见 docs/学习产品设计说明.md。核心是「判语卡」：
引文 + 出处徽章（一键回放 B 站原视频那一秒）+ 归属面包屑 + 考据标注。

用法：python3 tools/build_site.py
"""
import json, os, re, glob, html, collections, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site")

BOOKS = [
    ("01-stars", "01", "主星", "十四主星与辅煞星的定性、性情、格局"),
    ("02-palaces", "02", "十二宫", "命宫至父母宫、三方四正、借星"),
    ("03-patterns", "03", "格局", "吉格 / 凶格 / 结构性警示"),
    ("04-sihua", "04", "四化", "化科 / 化权 / 化禄 / 化忌"),
    ("05-illness", "05", "疾厄", "十二地支宫配脏腑、病灾判断"),
    ("07-methodology", "07", "方法论", "天纪总纲、批命顺序、面相手相、阳宅化命"),
    ("08-yili", "08", "易理总纲", "象 / 序卦通义 / 三道 / 卦爻通论"),
    ("09-hexagrams", "09", "六十四卦", "逐卦：卦象 / 序卦 / 爻辞 / 卜筮 / 人间道"),
    ("10-divination", "10", "占断", "金钱卦 / 测字 / 六神 / 小六壬"),
    ("11-fengshui", "11", "堪舆", "峦头理气 / 罗经坐山来龙 / 宅法"),
    ("12-tieban", "12", "铁板神数", "铁板神数 / 皇极经世 / 卦数批命"),
]
BOOK_NAME = {b[0]: f"{b[1]} {b[2]}" for b in BOOKS}

SUBJECTS = [
    ("紫微斗数", "BV1KJsLekEfA", [3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29]),
    ("易经序卦", "BV1KJsLekEfA", [1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42]),
    ("六十四卦", "BV1q7BZYcEZP", list(range(4, 68))),
    ("堪舆", "BV1KJsLekEfA", [31, 33, 35, 37]),
    ("铁板神数", "BV1KJsLekEfA", [39, 41, 43, 44, 45, 46, 47, 48]),
]

# 互链词表：引文中出现即成为可点标签
LINK_TERMS = ("紫微 天机 太阳 武曲 天同 廉贞 天府 太阴 贪狼 巨门 天相 天梁 七杀 破军 "
              "左辅 右弼 文昌 文曲 禄存 天马 擎羊 陀罗 火星 铃星 天魁 天钺 红鸾 天喜 "
              "命宫 兄弟宫 夫妻宫 子女宫 财帛宫 疾厄宫 迁移宫 官禄宫 田宅宫 福德宫 父母宫 "
              "化禄 化权 化科 化忌 三方四正 大限 流年").split()

CSS = """
:root{--bg:#faf8f4;--card:#fff;--ink:#1a1d21;--muted:#6b7480;--line:#e3ded3;
--accent:#b04a3e;--accent2:#2e7d5b;--gold:#8a7a63;--chip:#f0ece3}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--card:#1c1f23;--ink:#e8e6e1;
--muted:#9aa3ad;--line:#2c3037;--chip:#24282e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans SC",sans-serif;
line-height:1.75;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
header{border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:10}
header .wrap{display:flex;align-items:center;gap:18px;height:58px}
.logo{font-weight:700;font-size:17px;letter-spacing:.5px}
.logo span{color:var(--accent)}
nav{display:flex;gap:16px;font-size:14px;color:var(--muted);margin-left:auto;flex-wrap:wrap}
nav a:hover{color:var(--accent)}
h1{font-size:26px;margin:28px 0 6px;letter-spacing:.5px}
h2{font-size:19px;margin:32px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h3{font-size:15px;margin:22px 0 10px;color:var(--gold);font-weight:600}
.sub{color:var(--muted);font-size:14px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;
transition:.15s;display:block}
.tile:hover{border-color:var(--accent);transform:translateY(-1px)}
.tile .n{font-size:12px;color:var(--muted);letter-spacing:1px}
.tile .t{font-size:16px;font-weight:600;margin:3px 0 5px}
.tile .d{font-size:12.5px;color:var(--muted);line-height:1.5}
.tile .c{font-size:12px;color:var(--accent);margin-top:8px;font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--gold);
border-radius:8px;padding:14px 16px;margin:10px 0}
.card .q{font-size:15.5px;line-height:1.95;letter-spacing:.2px}
.card .meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px;font-size:12px}
.badge{background:var(--chip);color:var(--muted);border-radius:5px;padding:3px 8px}
.play{background:var(--accent);color:#fff!important;border-radius:5px;padding:3px 10px;font-weight:600}
.play:hover{opacity:.85}
.crumb{color:var(--muted);font-size:12px}
.note{color:var(--accent2);font-size:11.5px;background:var(--chip);border-radius:5px;padding:3px 8px}
.chip{display:inline-block;background:var(--chip);border-radius:4px;padding:1px 5px;
font-size:13px;color:var(--accent);cursor:pointer;margin:0 1px}
.chip:hover{background:var(--accent);color:#fff}
.seg{border-left:2px solid var(--line);padding:2px 0 2px 16px;margin:22px 0}
.seg .st{font-size:14px;font-weight:600;margin-bottom:2px}
.seg .stime{font-size:12px;color:var(--muted)}
#q{width:100%;padding:11px 14px;font-size:15px;border:1px solid var(--line);border-radius:8px;
background:var(--card);color:var(--ink);font-family:inherit}
#q:focus{outline:none;border-color:var(--accent)}
.stat{display:flex;gap:26px;flex-wrap:wrap;margin:14px 0 6px;font-size:13px;color:var(--muted)}
.stat b{color:var(--ink);font-size:19px;font-weight:700;display:block}
footer{margin:60px 0 30px;padding-top:20px;border-top:1px solid var(--line);
color:var(--muted);font-size:12.5px;line-height:1.9}
mark{background:#ffe9a8;color:#1a1d21;border-radius:2px}
"""

JS_SEARCH = """
let IDX=null;
async function boot(){
  const r=await fetch('data/search-index.json');IDX=await r.json();
  const q=document.getElementById('q');
  q.addEventListener('input',()=>run(q.value.trim()));
  q.disabled=false;q.placeholder='检索 4886 条判语（星曜 / 宫位 / 卦名 / 关键词）…';
}
function run(k){
  const box=document.getElementById('res');
  if(k.length<1){box.innerHTML='';return}
  const hit=IDX.filter(e=>e.q.includes(k)).slice(0,60);
  box.innerHTML=hit.length?hit.map(e=>card(e,k)).join(''):
    '<p class="sub">没有匹配的判语。</p>';
}
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function card(e,k){
  const q=esc(e.q).replace(new RegExp(esc(k).replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&'),'g'),m=>'<mark>'+m+'</mark>');
  return `<div class="card"><div class="q">${q}</div><div class="meta">
  <a class="play" href="${e.u}" target="_blank" rel="noopener">▶ ${e.t}</a>
  <span class="badge">${e.b}</span><span class="crumb">${esc(e.h)}</span></div></div>`;
}
boot();
"""

JS_CHIP = """
document.addEventListener('click',e=>{
  if(e.target.classList.contains('chip')){
    location.href='index.html#s='+encodeURIComponent(e.target.textContent);
  }
});
if(location.hash.startsWith('#s=')){
  const k=decodeURIComponent(location.hash.slice(3));
  const q=document.getElementById('q');
  if(q){const t=setInterval(()=>{if(!q.disabled){q.value=k;q.dispatchEvent(new Event('input'));
    clearInterval(t);q.scrollIntoView({behavior:'smooth'})}},100)}
}
"""


def esc(s):
    return html.escape(s or "")


def secs(t_hms):
    h, m, s = map(int, t_hms.split(":"))
    return h * 3600 + m * 60 + s


def url(e):
    return f"https://www.bilibili.com/video/{e['bvid']}?p={e['part']}&t={secs(e['t_hms'])}"


def linkify(q):
    """引文中的术语变可点 chip（最长优先，避免嵌套）"""
    spans = []
    for term in sorted(LINK_TERMS, key=len, reverse=True):
        for m in re.finditer(re.escape(term), q):
            if not any(s <= m.start() < e_ for s, e_ in spans):
                spans.append((m.start(), m.end()))
    out, last = [], 0
    for s, e_ in sorted(spans):
        out.append(esc(q[last:s]))
        out.append(f'<span class="chip">{esc(q[s:e_])}</span>')
        last = e_
    out.append(esc(q[last:]))
    return "".join(out)


def card(e, crumb=True):
    note = f'<span class="note">{esc(e["note"])}</span>' if e.get("note") else ""
    cite = f"{'卦' + str(e['part'] - 3).zfill(2) if e['bvid'] == 'BV1q7BZYcEZP' else 'p' + str(e['part']).zfill(2)} §{e['section']}"
    cb = (f'<span class="crumb">{esc(BOOK_NAME.get(e["book"], e["book"]))} › '
          f'{esc(e.get("h2", ""))}{" › " + esc(e["h3"]) if e.get("h3") else ""}</span>') if crumb else ""
    return f"""<div class="card"><div class="q">{linkify(e['quote'])}</div>
<div class="meta"><a class="play" href="{url(e)}" target="_blank" rel="noopener">▶ {e['t_hms']}</a>
<span class="badge">{cite}</span>{note}{cb}</div></div>"""


def page(title, body, depth=0, extra_js=""):
    p = "" if depth == 0 else "../" * depth
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · 天纪</title><style>{CSS}</style></head><body>
<header><div class="wrap"><a class="logo" href="{p}index.html">天<span>纪</span>·倪海厦讲课judgment库</a>
<nav><a href="{p}index.html">总览</a><a href="{p}index.html#books">十一册</a>
<a href="{p}index.html#units">课程</a>
<a href="https://github.com/Renhuai123/nihai-tianji-corpus" target="_blank" rel="noopener">GitHub</a></nav>
</div></header><div class="wrap">{body}
<footer>本站内容为倪海厦先生《天纪》课程判语的结构化整理，每条均可回放原视频核对。<br>
课程内容著作权归倪海厦先生及其权利继承人所有；字幕整理致谢 B 站 UP 主程心学。<br>
内容属文化研究与学习资料，不构成医疗、投资或人生决策建议。语料 CC BY-NC-SA 4.0。</footer>
</div><script>{JS_CHIP}{extra_js}</script></body></html>"""


def build():
    E = [json.loads(l) for l in open(os.path.join(ROOT, "data/entries.jsonl"), encoding="utf-8") if l.strip()]
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(f"{OUT}/data", exist_ok=True)

    by_book = collections.defaultdict(list)
    by_unit = collections.defaultdict(list)
    for e in E:
        by_book[e["book"]].append(e)
        by_unit[(e["bvid"], e["part"])].append(e)

    # —— 检索索引 ——
    idx = [{"q": e["quote"], "u": url(e), "t": e["t_hms"],
            "b": BOOK_NAME.get(e["book"], e["book"]),
            "h": (e.get("h2") or "") + (" › " + e["h3"] if e.get("h3") else "")} for e in E]
    json.dump(idx, open(f"{OUT}/data/search-index.json", "w"), ensure_ascii=False, separators=(",", ":"))

    # —— 首页 ——
    units_html = []
    for name, bvid, parts in SUBJECTS:
        got = [(bvid, p) for p in parts if (bvid, p) in by_unit]
        tiles = "".join(
            f'<a class="tile" href="unit-{b}-p{p:02d}.html"><div class="n">'
            f'{"卦" + str(p - 3).zfill(2) if b == "BV1q7BZYcEZP" else "p" + str(p).zfill(2)}</div>'
            f'<div class="t">{esc(unit_title(by_unit[(b, p)]))}</div>'
            f'<div class="c">{len(by_unit[(b, p)])} 条</div></a>' for b, p in got)
        units_html.append(f'<h3>{esc(name)}（{len(got)} 单元）</h3><div class="grid">{tiles}</div>')

    books_html = "".join(
        f'<a class="tile" href="book-{num}.html"><div class="n">{num}</div>'
        f'<div class="t">{esc(nm)}</div><div class="d">{esc(desc)}</div>'
        f'<div class="c">{len(by_book[key])} 条</div></a>'
        for key, num, nm, desc in BOOKS)

    home = f"""<h1>倪海厦《天纪》判语库</h1>
<p class="sub">每一句都可回放验证 · 点任意出处直达 B 站原视频那一秒</p>
<div class="stat"><div><b>{len(E)}</b>判语条目</div><div><b>11</b>册体系</div>
<div><b>{len(by_unit)}</b>课程单元</div><div><b>约 61</b>小时讲课</div></div>
<h2 id="search">检索</h2>
<input id="q" disabled placeholder="索引加载中…"><div id="res"></div>
<h2 id="books">按体系查 · 十一册</h2><div class="grid">{books_html}</div>
<h2 id="units">按课程学 · {len(by_unit)} 单元</h2>{''.join(units_html)}"""
    open(f"{OUT}/index.html", "w", encoding="utf-8").write(page("总览", home, 0, JS_SEARCH))

    # —— 册页（轴 A）——
    for key, num, nm, desc in BOOKS:
        items = by_book[key]
        groups = collections.OrderedDict()
        for e in items:
            groups.setdefault(e.get("h2", "未分类"), collections.OrderedDict()) \
                  .setdefault(e.get("h3", ""), []).append(e)
        body = [f'<h1>{num} {esc(nm)}</h1><p class="sub">{esc(desc)} · 共 {len(items)} 条</p>']
        for h2, subs in groups.items():
            body.append(f"<h2>{esc(h2)}</h2>")
            for h3, es in subs.items():
                if h3:
                    body.append(f"<h3>{esc(h3)}</h3>")
                body += [card(e, crumb=False) for e in es]
        open(f"{OUT}/book-{num}.html", "w", encoding="utf-8").write(
            page(f"{num} {nm}", "".join(body)))

    # —— 单元页（轴 B）——
    for (bvid, part), es in by_unit.items():
        sf = os.path.join(ROOT, f"data/sections/{bvid}_p{part:02d}.json")
        sections = json.load(open(sf)) if os.path.exists(sf) else []
        bysec = collections.defaultdict(list)
        for e in es:
            bysec[e["section"]].append(e)
        tag = f"卦{part - 3:02d}" if bvid == "BV1q7BZYcEZP" else f"p{part:02d}"
        body = [f'<h1>{esc(unit_title(es))}</h1>'
                f'<p class="sub">{tag} · {len(es)} 条判语 · {len(sections)} 个语义段 · '
                f'<a href="https://www.bilibili.com/video/{bvid}?p={part}" target="_blank" '
                f'rel="noopener" style="color:var(--accent)">B 站原片 ↗</a></p>']
        for s in sections:
            t = s["t_start_ms"] // 1000
            hh = f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"
            body.append(f'<div class="seg"><div class="st">§{s["section"]} {esc(s.get("topic", ""))}</div>'
                        f'<div class="stime"><a class="play" href="https://www.bilibili.com/video/'
                        f'{bvid}?p={part}&t={t}" target="_blank" rel="noopener">▶ {hh}</a></div></div>')
            body += [card(e) for e in bysec.get(s["section"], [])]
        rest = [e for e in es if e["section"] not in {s["section"] for s in sections}]
        if rest:
            body.append("<h2>其他</h2>")
            body += [card(e) for e in rest]
        open(f"{OUT}/unit-{bvid}-p{part:02d}.html", "w", encoding="utf-8").write(
            page(unit_title(es), "".join(body)))

    n = len(glob.glob(f"{OUT}/*.html"))
    size = sum(os.path.getsize(p) for p in glob.glob(f"{OUT}/**/*", recursive=True) if os.path.isfile(p))
    print(f"生成 {n} 个页面（1 总览 + {len(BOOKS)} 册页 + {len(by_unit)} 单元页）")
    print(f"检索索引 {len(idx)} 条 · 站点体积 {size / 1048576:.1f} MB → site/")


def unit_title(es):
    """从条目的 h2 推单元标题：09 册用卦名，其余用最常见的 h2"""
    c = collections.Counter(e.get("h2", "") for e in es if e.get("h2"))
    return (c.most_common(1)[0][0] if c else "未命名")[:24]


if __name__ == "__main__":
    build()
