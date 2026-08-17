#!/usr/bin/env python3
"""
天纪语料工程 · 验收门禁校验

用法:
    python3 gate_check.py --batch <转写目录>          # 校验一批产出
    python3 gate_check.py --dedup BV1KJsLekEfA p03    # 单独跑 G1 去重前置
    python3 gate_check.py --build-lexicon             # 重建术语白名单

监督的形式是脚本而非人工意见：六项门禁全过才算交付，
任一失败即打回并列出具体失败条目。阈值可调，但调整须有实测依据。
"""
import os, re, json, sys, argparse, urllib.request, time, collections, difflib

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, "Downloads/三纪源证库")
CORPUS = os.path.join(HOME, "Downloads/ni-haisha-corpus")
LEXICON = os.path.join(ROOT, "术语白名单.json")

MAIN_BV = "BV1KJsLekEfA"          # 天纪正片，去重基准
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


# ---- 繁简归一：优先当前环境的 zhconv，缺则自举到 tools/.venv-gate 重执行 ----
def _boot_zhconv():
    try:
        from zhconv import convert
        return convert
    except ImportError:
        # venv 的 python3 是指向基解释器的软链，不能用 realpath 判断是否已在 venv 内；
        # 用环境变量防止 execv 死循环
        vp = os.path.join(ROOT, "tools", ".venv-gate", "bin", "python3")
        if os.path.exists(vp) and os.environ.get("GATE_ZH_BOOT") != "1":
            os.environ["GATE_ZH_BOOT"] = "1"
            os.execv(vp, [vp] + sys.argv)
        return None


_ZH = _boot_zhconv()
_PUNCT = re.compile(r'[\s，。、；：？！,\.\?!·…—\-「」『』()（）:;；]')


def norm_zh(s):
    s = _PUNCT.sub("", s or "")
    return _ZH(s, "zh-cn") if _ZH else s


def parse_srt(p):
    out = []
    for b in re.split(r"\n\s*\n", open(p, encoding="utf-8", errors="ignore").read()):
        m = re.search(r"(\d+):(\d+):(\d+)[,\.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,\.](\d+)", b)
        if not m:
            continue
        g = list(map(int, m.groups()))
        s = (g[0] * 3600 + g[1] * 60 + g[2]) * 1000 + g[3]
        e = (g[4] * 3600 + g[5] * 60 + g[6]) * 1000 + g[7]
        L = b.strip().split("\n")
        ti = [i for i, l in enumerate(L) if "-->" in l][0]
        t = norm_zh("".join(x.strip() for x in L[ti + 1:]))
        if t:
            out.append((s, e, t))
    out.sort(key=lambda x: x[0])
    return out


def _match_score(a, b):
    """互为子串（短侧≥4字，防琐碎误确认）记 1.0，否则字符相似度"""
    if not a or not b:
        return 0.0
    if (a in b or b in a) and min(len(a), len(b)) >= 4:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def contain_in(needle, hay):
    """needle 的字符按序出现在 hay 中的比例（G6 用）"""
    if not needle:
        return 1.0
    if not hay:
        return 0.0
    if needle in hay:
        return 1.0
    sm = difflib.SequenceMatcher(None, needle, hay, autojunk=False)
    return sum(bl.size for bl in sm.get_matching_blocks()) / len(needle)


def recompute_g3(jsonl_path, srt_path, asr2_path=None):
    """从 subtitle.jsonl + 自有 ASR 独立重算一致率与探针覆盖。
    口径（2026-08-15 裁定，2026-08-17 扩双探针）：whisper 与 FunASR 均为
    独立自有转写，任一引擎的时间重叠候选达 ≥0.62 即 strong / ≥0.35 review。
    不读任何自报数字。"""
    cues = [json.loads(l) for l in open(jsonl_path, encoding="utf-8") if l.strip()]
    cues.sort(key=lambda c: c["t_start_ms"])
    sources = [parse_srt(srt_path)]
    if asr2_path and os.path.exists(asr2_path):
        sources.append(parse_srt(asr2_path))
    n = len(cues)
    strong = review = nocand = 0
    ptrs = [0] * len(sources)
    for r in cues:
        s, e = r["t_start_ms"], r["t_end_ms"]
        nc = norm_zh(r["text"])
        best, found = 0.0, False
        for si, asr in enumerate(sources):
            j = ptrs[si]
            while j < len(asr) and asr[j][1] <= s:
                j += 1
            ptrs[si] = j
            k = max(j - 1, 0)
            while k < len(asr) and asr[k][0] < e:
                if min(e, asr[k][1]) > max(s, asr[k][0]):
                    found = True
                    sc = _match_score(nc, asr[k][2])
                    if sc > best:
                        best = sc
                k += 1
        if not found:
            nocand += 1
        elif best >= 0.62:
            strong += 1
        elif best >= 0.35:
            review += 1
    return {"n": n, "strong": strong, "review": review,
            "weak": n - strong - review - nocand, "nocand": nocand,
            "rate": strong / n if n else 0.0,
            "probe": 1 - nocand / n if n else 0.0}

# 阈值 —— 以实测标定，不得为了通过而下调
TH = {
    "usable_ratio": 0.60,          # G3 OCR↔ASR 一致率门槛
    "asr_share_max": 0.30,         # G2 ASR 作主源的占比上限
    "asr_probe_min": 0.95,         # G2 ASR 探针覆盖下限：必须有第二源
    "junk_share_max": 0.02,        # G4 疑似水印/噪声 cue 占比上限
    "citation_hit_min": 0.95,      # G5 出处可回溯率
    "phrase_hit_min": 0.90,        # G6 关键短语在源文中命中率
}


def hms(s):
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def api_pages(bv):
    req = urllib.request.Request(
        f"https://api.bilibili.com/x/web-interface/view?bvid={bv}", headers=UA)
    d = json.load(urllib.request.urlopen(req))["data"]
    return [{"p": p["page"], "title": p["part"], "dur": p["duration"]}
            for p in d["pages"]]


# ---------------------------------------------------------------- G1
def g1_dedup(bv, part=None):
    """去重前置：本批分P 的时长不得与正片精确匹配（正片自身除外）"""
    out = {"gate": "G1 去重前置", "pass": True, "detail": []}
    if bv == MAIN_BV:
        out["detail"].append("对象即正片本身，为去重基准，自动通过")
        return out
    try:
        main = {p["dur"]: p for p in api_pages(MAIN_BV)}
        time.sleep(0.8)
        pages = api_pages(bv)
    except Exception as e:
        out["pass"] = False
        out["detail"].append(f"接口查询失败，无法判定：{e}")
        return out
    if part:
        n = int(re.sub(r"\D", "", part))
        pages = [p for p in pages if p["p"] == n]
    for p in pages:
        m = main.get(p["dur"])
        near = None
        if not m:
            for dur, mp in main.items():
                if abs(dur - p["dur"]) <= 2:
                    near = mp
                    break
        if m:
            out["pass"] = False
            out["detail"].append(
                f"p{p['p']:02d}（{hms(p['dur'])}）与正片 p{m['p']:02d} 时长逐秒相同"
                f" → 重复内容，不应处理")
        elif near:
            out["pass"] = False
            out["detail"].append(
                f"p{p['p']:02d}（{hms(p['dur'])}）与正片 p{near['p']:02d} 时长差 ≤2s"
                f" → 疑似重复（转码漂移），须内容抽验后方可处理")
        else:
            out["detail"].append(f"p{p['p']:02d}（{hms(p['dur'])}）未匹配正片，可处理")
    return out


# ---------------------------------------------------------------- G2/G3
def g2_g3_route(batch):
    """主源正确 + 可用率"""
    g2 = {"gate": "G2 主源正确", "pass": True, "detail": []}
    g3 = {"gate": "G3 可用率", "pass": True, "detail": []}
    covs = []
    for root, _, files in os.walk(batch):
        for f in files:
            if f in ("coverage.json", "alignment_summary.json"):
                covs.append(os.path.join(root, f))
    if not covs:
        has_jsonl = any(f == "subtitle.jsonl"
                        for _, _, fs in os.walk(batch) for f in fs)
        for g in (g2, g3):
            if has_jsonl:
                g["pass"] = False
                g["detail"].append("有 subtitle.jsonl 却缺 coverage.json —— 转写批次不完整")
            else:
                g["detail"].append("本批无转写产物，跳过（第二层批次属正常）")
        return g2, g3
    for c in covs:
        try:
            d = json.load(open(c))
        except Exception as e:
            g2["pass"] = False; g2["detail"].append(f"{c} 解析失败：{e}"); continue
        tag = os.path.basename(os.path.dirname(c))

        route = str(d.get("selected_route", "")).lower()
        if route and route != "ocr":
            g2["pass"] = False
            g2["detail"].append(f"{tag}: selected_route = {route}，应为 ocr")
        share = d.get("asr_share")
        if share is None:
            cnt = d.get("source_counts") or {}
            tot = sum(cnt.values()) or 0
            share = (cnt.get("asr", 0) / tot) if tot else None
        if share is not None:
            ok = share <= TH["asr_share_max"]
            g2["pass"] &= ok
            g2["detail"].append(
                f"{tag}: ASR 作主源占比 {share:.1%}"
                f"（上限 {TH['asr_share_max']:.0%}）{'✓' if ok else '✗'}")
        # G2 探针覆盖 + G3 一致率：一律独立重算，不读任何自报字段
        ep_m = re.search(r"_p(\d+)$", tag)
        jsonl = os.path.join(os.path.dirname(c), "subtitle.jsonl")
        # 探针路径：新命名（按 BV 命名空间）优先，正片老命名兜底
        srt = ""
        if ep_m:
            for cand in (
                os.path.join(ROOT, f"_work_{tag}", "probe.wav.srt"),
                os.path.join(ROOT, f"_work_{tag}", f"{tag}.wav.srt"),
                os.path.join(ROOT, f"_work_p{ep_m.group(1)}",
                             f"p{ep_m.group(1)}.wav.srt"),
            ):
                if os.path.exists(cand):
                    srt = cand
                    break
            else:
                srt = os.path.join(ROOT, f"_work_{tag}", "probe.wav.srt")
        if not ep_m or not os.path.exists(jsonl):
            g3["pass"] = False
            g3["detail"].append(f"{tag}: ✗ 缺 subtitle.jsonl，无法独立重算")
            continue
        if not os.path.exists(srt):
            g3["pass"] = False
            g3["detail"].append(
                f"{tag}: ✗ 缺 ASR 原始探针 {os.path.basename(srt)}"
                f" —— _work_pNN 的 .wav.srt 是门禁复核依据，不得删除")
            continue
        if _ZH is None:
            g3["pass"] = False
            g3["detail"].append(
                f"{tag}: ✗ zhconv 不可用且 tools/.venv-gate 缺失，无法繁简归一")
            continue
        a2p = ""
        for cand2 in (os.path.join(ROOT, f"_work_{tag}", "asr2.srt"),
                      os.path.join(ROOT, f"_work_p{ep_m.group(1)}", "asr2.srt")):
            if os.path.exists(cand2):
                a2p = cand2
                break
        rc = recompute_g3(jsonl, srt, a2p)
        ok = rc["rate"] >= TH["usable_ratio"]
        g3["pass"] &= ok
        rep = d.get("counts") or {}
        rep_n = sum(rep.values()) or 0
        rep_s = (rep.get("strong", 0) / rep_n) if rep_n else None
        g3["detail"].append(
            f"{tag}: 复核一致率 {rc['rate']:.1%}"
            f"（strong {rc['strong']} / review {rc['review']} / weak {rc['weak']}"
            f" / 无探针 {rc['nocand']}，门槛 {TH['usable_ratio']:.0%}）{'✓' if ok else '✗'}"
            + (f"｜自报 {rep_s:.1%}" if rep_s is not None else "｜无自报"))
        pok = rc["probe"] >= TH["asr_probe_min"]
        g2["pass"] &= pok
        g2["detail"].append(
            f"{tag}: 复核探针覆盖 {rc['probe']:.1%}"
            f"（下限 {TH['asr_probe_min']:.0%}）{'✓' if pok else '✗'}")
    return g2, g3


# ---------------------------------------------------------------- G4
def build_lexicon():
    """从既有已核验条目与笔记中抽取专名，建立白名单"""
    terms = set()
    seed = """紫微 天机 太阳 武曲 天同 廉贞 天府 太阴 贪狼 巨门 天相 天梁 七杀 破军
    左辅 右弼 文昌 文曲 禄存 天马 擎羊 陀罗 火星 铃星 地空 地劫 天魁 天钺
    红鸾 天喜 孤辰 寡宿 天刑 天姚 化禄 化权 化科 化忌
    命宫 兄弟 夫妻 子女 财帛 疾厄 迁移 仆役 官禄 田宅 福德 父母 身宫
    乾 坤 震 巽 坎 离 艮 兑 堪舆 明堂 龙脉 罗经 大限 流年 三方四正
    杀破狼 紫府 日月反背 石中隐玉 日丽中天 巨日 孤鸾
    屯 蒙 需 讼 师 比 小畜 履 泰 否 同人 大有 谦 豫 随 蛊 临 观
    噬嗑 贲 剥 复 无妄 大畜 颐 大过 咸 恒 遯 大壮 晋 明夷 家人 睽
    蹇 解 损 益 夬 姤 萃 升 困 井 革 鼎 渐 归妹 丰 旅 涣 节
    中孚 小过 既济 未济 爻 卦辞 爻辞 序卦 上经 下经 占卜 测字 金钱卦
    峦头 九星 消砂 纳水 立向 阳宅 阴宅 点穴 龙砂穴水 二十八宿
    铁板神数 皇极经世 值年卦 先天卦 后天卦 六神 青龙 白虎 朱雀 勾陈 腾蛇 玄武"""
    terms |= {t for t in seed.split() if len(t) >= 1}
    vd = os.path.join(CORPUS, "verified")
    if os.path.isdir(vd):
        for f in os.listdir(vd):
            if not f.endswith(".md"):
                continue
            txt = open(os.path.join(vd, f), encoding="utf-8").read()
            for m in re.findall(r"^#{2,4}\s*(.+)$", txt, re.M):
                for w in re.split(r"[·（）()／/、,，\s]+", m.strip()):
                    if 2 <= len(w) <= 6 and re.fullmatch(r"[一-鿿]+", w):
                        terms.add(w)
    json.dump(sorted(terms), open(LEXICON, "w"), ensure_ascii=False, indent=1)
    return terms


def load_lexicon():
    if os.path.exists(LEXICON):
        return set(json.load(open(LEXICON)))
    return build_lexicon()


def g4_lexicon(batch):
    """术语白名单：拦截「堪舆学→看雨群」这类 ASR 崩坏"""
    out = {"gate": "G4 术语白名单", "pass": True, "detail": []}
    lex = load_lexicon()
    # 已知的崩坏样例，命中即硬失败
    KNOWN_BAD = ["看雨群", "天积", "字化", "蜂胸蜂蜜", "贪郎", "连真"]
    hits = collections.Counter()
    scanned = 0
    # 裁决/分流工作文件的用途就是承载坏字证物，不计入错词扫描
    WORKFILE = re.compile(
        r"corrections-pending|corrections-approved|corrections-ledger|"
        r"inventory\.jsonl$|resourcing-sample|resourcing-report|"
        r"recast-report|consensus-report")
    for root, dirs, files in os.walk(batch):
        dirs[:] = [d for d in dirs if not d.startswith("_") and d != "holds"]
        for f in files:
            if not f.endswith((".srt", ".md", ".jsonl", ".txt")):
                continue
            if WORKFILE.search(f):
                continue
            scanned += 1
            try:
                txt = open(os.path.join(root, f), encoding="utf-8",
                           errors="ignore").read()
            except Exception:
                continue
            # subtitle.jsonl 只扫正文 text 字段——asr_text 是内部探针数据，
            # 专名听崩本来就该出现在那里（被 OCR 纠正正是交叉验证的功能）
            if f == "subtitle.jsonl":
                try:
                    txt = "\n".join(json.loads(l).get("text", "")
                                    for l in txt.splitlines() if l.strip())
                except Exception:
                    pass
            for bad in KNOWN_BAD:
                n = txt.count(bad)
                if n:
                    hits[f"{os.path.basename(root)}/{f} :: {bad}"] += n
    # 模式检测：异常符号 / 超短 token / 水印残片
    JUNK = re.compile(r'[◎●○◆■□▲△※☆★♀♂]|[A-Za-z]{3,}')
    for root, _, files in os.walk(batch):
        for f in files:
            if f != "subtitle.jsonl":
                continue
            rows = []
            for line in open(os.path.join(root, f), encoding="utf-8",
                             errors="ignore"):
                line = line.strip()
                if line:
                    try: rows.append(json.loads(line))
                    except Exception: pass
            if not rows:
                continue
            tot = len(rows)
            def _isjunk(r):
                if JUNK.search(r.get("text", "")):
                    return True
                short = len(r.get("text", "").strip()) <= 4
                bb = r.get("bbox")
                if isinstance(bb, dict) and "x" in bb and "w" in bb:
                    cx = bb["x"] + bb["w"] / 2
                    # 有位置信息时：只有「又短又偏离字幕中轴」才算疑似水印
                    return short and not (0.25 <= cx <= 0.75)
                return short
            junk = [r for r in rows if _isjunk(r)]
            share = len(junk) / tot
            ok = share <= TH["junk_share_max"]
            out["pass"] &= ok
            out["detail"].append(
                f"{os.path.basename(root)}: 疑似水印/噪声 cue {len(junk)}/{tot}"
                f" = {share:.1%}（上限 {TH['junk_share_max']:.0%}）"
                f"{'✓' if ok else '✗'}")
            hi = [r for r in junk if (r.get("ocr_confidence") or 0) >= 1.0]
            if hi:
                out["detail"].append(
                    f"        其中 {len(hi)} 条噪声的 confidence = 1.0"
                    f" → 证明引擎自评不可作门禁指标")
    out["detail"].append(f"白名单 {len(lex)} 词，扫描 {scanned} 个文件")
    if hits:
        out["pass"] = False
        for k, n in hits.most_common(20):
            out["detail"].append(f"命中已知错词 ×{n}：{k}")
    else:
        out["detail"].append("未命中任何已知错词 ✓")
    return out


# ---------------------------------------------------------------- G5/G6
CITE_OLD = re.compile(
    r"[「『]([^」』]{4,})[」』]\s*(?:〔[^〕]*〕\s*)*\[(ep\d+)\s*§\s*\d+\]")
CITE_NEW = re.compile(
    r"[「『]([^」』]{2,})[」』]\s*(?:〔[^〕]*〕\s*)*"
    r"\[(p\d{2})\s*§\s*(\d+)\s*@(\d{1,2}):(\d{2}):(\d{2})\]")
CITE_GUA = re.compile(
    r"[「『]([^」』]{2,})[」』]\s*(?:〔[^〕]*〕\s*)*"
    r"\[卦(\d{1,2})\s*§\s*(\d+)\s*@(\d{1,2}):(\d{2}):(\d{2})\]")
GUA_BV = "BV1q7BZYcEZP"


def _load_cues(ep, bvid=None):
    bvid = bvid or MAIN_BV
    p = os.path.join(ROOT, "transcripts", f"{bvid}_{ep}", "subtitle.jsonl")
    if not os.path.exists(p):
        return None
    cues = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    cues.sort(key=lambda c: c["t_start_ms"])
    return cues


def _load_asr2(ep):
    """换源后 G6 校验窗 = 自有 FunASR 转写；无 asr2 时回退 OCR cue（过渡期）"""
    p = os.path.join(ROOT, f"_work_{ep}", "asr2.srt")
    if not os.path.exists(p):
        return None
    return parse_srt(p)


def _load_sections(ep, batch, bvid=None):
    bvid = bvid or MAIN_BV
    for base in (os.path.join(batch, "sections"),
                 os.path.join(ROOT, "structured", "sections")):
        p = os.path.join(base, f"{bvid}_{ep}.json")
        if os.path.exists(p):
            return {s["section"]: s for s in json.load(open(p))}
    return None


def g5_g6_citation(batch):
    """出处可回溯 + 无凭空新增（兼容新旧两种出处格式）"""
    g5 = {"gate": "G5 出处可回溯", "pass": True, "detail": []}
    g6 = {"gate": "G6 无凭空新增", "pass": True, "detail": []}
    srcs = {}
    rt = os.path.join(CORPUS, "raw-transcripts")
    if os.path.isdir(rt):
        for f in os.listdir(rt):
            if f.endswith(".txt"):
                srcs[f[:-4]] = re.sub(
                    r"[，。、；：？！\s]", "",
                    open(os.path.join(rt, f), encoding="utf-8",
                         errors="ignore").read())
    cue_cache, sec_cache = {}, {}
    for root, dirs, files in os.walk(batch):
        dirs[:] = [d for d in dirs if not d.startswith("_")]  # 跳过 _backup 等
        for f in files:
            if not f.endswith(".md"):
                continue
            txt = open(os.path.join(root, f), encoding="utf-8",
                       errors="ignore").read()
            # —— 新格式 [pNN §M @H:MM:SS]：对 transcripts + sections 校验 ——
            news = CITE_NEW.findall(txt)
            if news:
                a5 = b5 = c6 = 0
                tot = len(news)
                bad = []
                for q, ep, sec, hh, mm, ss in news:
                    t = (int(hh) * 3600 + int(mm) * 60 + int(ss)) * 1000
                    if ep not in cue_cache:
                        cue_cache[ep] = _load_cues(ep)
                        sec_cache[ep] = _load_sections(ep, batch)
                    cues, secs = cue_cache[ep], sec_cache[ep]
                    if cues is None:
                        bad.append(f"{ep} 转写缺失")
                        continue
                    okA = any(c["t_start_ms"] - 2000 <= t <= c["t_end_ms"] + 2000
                              for c in cues)
                    s_ = (secs or {}).get(int(sec))
                    okB = bool(s_) and \
                        s_["t_start_ms"] - 2000 <= t <= s_["t_end_ms"] + 2000
                    # G6 校验窗 = OCR 字幕 cue 文本（2026-08-17 路线 C 定案：
                    # 发布文本以校正字幕为源、已获校正者同意；asr2 仅作质检探针）
                    win = "".join(norm_zh(c["text"]) for c in cues
                                  if t - 60000 <= c["t_start_ms"] <= t + 60000)
                    cv = contain_in(norm_zh(q), win)
                    okC = cv >= TH["phrase_hit_min"]
                    a5 += okA; b5 += okB; c6 += okC
                    if not (okA and okB and okC) and len(bad) < 4:
                        bad.append(f"{ep}§{sec}@{hh}:{mm}:{ss} "
                                   f"时间码={okA} 段号={okB} 命中率={cv:.2f}"
                                   f"「{q[:16]}…」")
                r5 = min(a5, b5) / tot
                r6 = c6 / tot
                ok5 = r5 >= TH["citation_hit_min"]
                ok6 = r6 >= TH["phrase_hit_min"]
                g5["pass"] &= ok5
                g6["pass"] &= ok6
                g5["detail"].append(
                    f"{f}: 新格式 {tot} 条 · 时间码有效 {a5 / tot:.1%}"
                    f" · 段号有效 {b5 / tot:.1%}"
                    f"（门槛 {TH['citation_hit_min']:.0%}）{'✓' if ok5 else '✗'}")
                g6["detail"].append(
                    f"{f}: ±60s 窗逐字命中 {r6:.1%}"
                    f"（门槛 {TH['phrase_hit_min']:.0%}）{'✓' if ok6 else '✗'}")
                for b in bad:
                    g5["detail"].append(f"    异常：{b}")
            # —— 64 卦专讲 [卦NN §M @H:MM:SS]：BV1q7BZYcEZP p(NN+3) ——
            guas = CITE_GUA.findall(txt)
            if guas:
                a5 = b5 = c6 = 0
                tot = len(guas)
                bad = []
                for q, gua, sec, hh, mm, ss in guas:
                    gua_n = int(gua)
                    part = gua_n + 3
                    ep = f"p{part:02d}"
                    t = (int(hh) * 3600 + int(mm) * 60 + int(ss)) * 1000
                    key = f"gua:{ep}"
                    if key not in cue_cache:
                        cue_cache[key] = _load_cues(ep, GUA_BV)
                        sec_cache[key] = _load_sections(ep, batch, GUA_BV)
                    cues, secs = cue_cache[key], sec_cache[key]
                    if cues is None:
                        bad.append(f"卦{gua} 转写缺失")
                        continue
                    okA = any(c["t_start_ms"] - 2000 <= t <= c["t_end_ms"] + 2000
                              for c in cues)
                    s_ = (secs or {}).get(int(sec))
                    okB = bool(s_) and \
                        s_["t_start_ms"] - 2000 <= t <= s_["t_end_ms"] + 2000
                    win = "".join(norm_zh(c["text"]) for c in cues
                                  if t - 60000 <= c["t_start_ms"] <= t + 60000)
                    cv = contain_in(norm_zh(q), win)
                    okC = cv >= TH["phrase_hit_min"]
                    a5 += okA; b5 += okB; c6 += okC
                    if not (okA and okB and okC) and len(bad) < 4:
                        bad.append(f"卦{gua}§{sec}@{hh}:{mm}:{ss} "
                                   f"时间码={okA} 段号={okB} 命中率={cv:.2f}"
                                   f"「{q[:16]}…」")
                r5 = min(a5, b5) / tot
                r6 = c6 / tot
                ok5 = r5 >= TH["citation_hit_min"]
                ok6 = r6 >= TH["phrase_hit_min"]
                g5["pass"] &= ok5
                g6["pass"] &= ok6
                g5["detail"].append(
                    f"{f}: 卦格式 {tot} 条 · 时间码有效 {a5 / tot:.1%}"
                    f" · 段号有效 {b5 / tot:.1%}"
                    f"（门槛 {TH['citation_hit_min']:.0%}）{'✓' if ok5 else '✗'}")
                g6["detail"].append(
                    f"{f}: 卦±60s 窗逐字命中 {r6:.1%}"
                    f"（门槛 {TH['phrase_hit_min']:.0%}）{'✓' if ok6 else '✗'}")
                for b in bad:
                    g5["detail"].append(f"    异常：{b}")
            # —— 旧格式 [epNNN §M]：对 whisper 存量语料校验 ——
            olds = CITE_OLD.findall(txt)
            if olds:
                hit = sum(1 for q, ep in olds
                          if re.sub(r"[，。、；：？！\s]", "", q)[:12]
                          and re.sub(r"[，。、；：？！\s]", "", q)[:12]
                          in srcs.get(ep, ""))
                r = hit / len(olds)
                ok = r >= TH["citation_hit_min"]
                g5["pass"] &= ok
                g5["detail"].append(
                    f"{f}: 旧格式 {len(olds)} 条，whisper 源命中 {r:.1%}"
                    f" {'✓' if ok else '✗'}")
    if not g5["detail"]:
        g5["detail"].append("本批无结构化条目，跳过（第一层转写阶段属正常）")
        g6["detail"].append("本批无结构化条目，跳过")
    return g5, g6


# ---------------------------------------------------------------- main
def report(gates):
    print("\n" + "=" * 66)
    print("天纪语料工程 · 门禁校验报告")
    print("=" * 66)
    allp = True
    for g in gates:
        mark = "通过" if g["pass"] else "未通过"
        print(f"\n[{mark}] {g['gate']}")
        # 失败/异常行永不被截断：优先展示，再补通过行
        bad_lines = [d for d in g["detail"] if "✗" in d or "错词" in d or "异常" in d]
        ok_lines = [d for d in g["detail"] if d not in bad_lines]
        for d in bad_lines + ok_lines[:max(0, 200 - len(bad_lines))]:
            print(f"       {d}")
        allp &= g["pass"]
    print("\n" + "-" * 66)
    print(f"结论：{'全部通过，可采信' if allp else '存在未通过项，打回重做'}")
    print("-" * 66)
    return 0 if allp else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch")
    ap.add_argument("--dedup", nargs="+")
    ap.add_argument("--build-lexicon", action="store_true")
    a = ap.parse_args()

    if a.build_lexicon:
        t = build_lexicon()
        print(f"已重建术语白名单：{len(t)} 词 → {LEXICON}")
        return 0
    if a.dedup:
        bv = a.dedup[0]
        part = a.dedup[1] if len(a.dedup) > 1 else None
        return report([g1_dedup(bv, part)])
    if a.batch:
        b = os.path.expanduser(a.batch)
        if not os.path.isdir(b):
            print(f"目录不存在：{b}")
            return 2
        # G0 空批次防线：既无转写产物也无带出处条目 → 直接失败，绝不静默通过
        has_l1 = has_l2 = False
        for root, dirs, files in os.walk(b):
            dirs[:] = [d for d in dirs if not d.startswith("_")]
            for f in files:
                if f in ("subtitle.jsonl", "coverage.json"):
                    has_l1 = True
                elif f.endswith(".md"):
                    t = open(os.path.join(root, f), encoding="utf-8",
                             errors="ignore").read()
                    if CITE_NEW.search(t) or CITE_OLD.search(t) or CITE_GUA.search(t):
                        has_l2 = True
        if not (has_l1 or has_l2):
            return report([{"gate": "G0 空批次防线", "pass": False, "detail": [
                f"{b} 既无转写产物（subtitle.jsonl / coverage.json）"
                f"也无带出处的结构化条目 —— 空目录不得视为通过"]}])
        g2, g3 = g2_g3_route(b)
        g5, g6 = g5_g6_citation(b)
        return report([g2, g3, g4_lexicon(b), g5, g6])
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
