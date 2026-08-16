#!/usr/bin/env python3
"""
已批准字幕更正 · 幂等重放器

corrections-approved.jsonl 是唯一权威账本。本脚本把其中全部已批准的
「原字→正字」重放到 structured/ 的册文件与条目 jsonl 上，可重复执行，
结果一致（幂等）。

为什么存在：产出方会整本重渲染册文件，任何就地补丁都会被冲掉。
因此规矩是——**每次重渲染交付前，必须跑一遍本脚本**：

    python3 ~/Downloads/三纪源证库/tools/apply_corrections.py

实现要点：
- 先把 〔字幕疑误/已按裁决改正〕行内标注与 jsonl 的 "note" 字段挖成占位符，
  防止全局替换把标注里的原字也改掉（否则产生「命宫→命宫」自指涉垃圾）。
- 单字更正（如 已→巳）必须用其 quote 上下文锚定，防误伤「已经」等常用字。
- 应用完毕后，把命中已批对的「字幕疑误」标注升级为「已按裁决改正」。
"""
import json, os, re, glob, sys

R = os.path.expanduser("~/Downloads/三纪源证库/structured")
LEDGER = os.path.join(R, "corrections-approved.jsonl")

ANN_MD = re.compile(r"〔(?:字幕疑误|已按裁决改正)[：:][^〕]*〕")
ANN_NOTE = re.compile(r'"note":\s*"[^"]*"')
ARROW = re.compile(r"\s*(.+?)→(.+?)\s*$")


def load_pairs():
    """返回 [(查找串, 替换串)]，已去重；单字项做上下文锚定。"""
    pairs, seen = [], set()
    for line in open(LEDGER, encoding="utf-8"):
        if not line.strip():
            continue
        d = json.loads(line)
        if "audit" in d:
            continue
        cand = []
        if d.get("original") and d.get("suggested"):
            cand.append((d["original"], d["suggested"], d.get("quote", "")))
        elif d.get("note"):
            for seg in re.split(r"[；;]", d["note"]):
                m = ARROW.match(seg)
                if m:
                    cand.append((m.group(1).strip(), m.group(2).strip(),
                                 d.get("quote", "")))
        for o, s, q in cand:
            if len(o) == 1:                      # 单字：上下文锚定
                i = q.find(o)
                if i < 0:
                    continue
                a = q[max(0, i - 2):i + len(o) + 1]
                o, s = a, a.replace(o, s, 1) if o in a else (a, a)
                # 注：a 中首个原字即目标（quote 取自出错处）
            if o != s and (o, s) not in seen:
                seen.add((o, s))
                pairs.append((o, s))
    return pairs


def upgrade_ann(text, approved):
    """字幕疑误 → 已按裁决改正（仅命中已批对时）"""
    def fix_md(m):
        inner = m.group(0)
        am = re.search(r"[：:]\s*(.+?)→(.+?)〕", inner)
        if am and (am.group(1).strip(), am.group(2).strip()) in approved:
            return f"〔已按裁决改正：{am.group(1).strip()}→{am.group(2).strip()}〕"
        return inner
    text = ANN_MD.sub(fix_md, text)

    def fix_note(m):
        inner = m.group(0)
        am = re.search(r'"note":\s*"(?:字幕疑误[：:])?\s*(.+?)→(.+?)"', inner)
        if am and (am.group(1).strip(), am.group(2).strip()) in approved:
            return f'"note": "已按裁决改正：{am.group(1).strip()}→{am.group(2).strip()}"'
        return inner
    return ANN_NOTE.sub(fix_note, text)


def main():
    pairs = load_pairs()
    approved = set(pairs)
    # 标注升级用的原始对（未锚定形态也要认）
    for line in open(LEDGER, encoding="utf-8"):
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("original") and d.get("suggested"):
            approved.add((d["original"], d["suggested"]))
        elif d.get("note"):
            for seg in re.split(r"[；;]", d["note"]):
                m = ARROW.match(seg)
                if m:
                    approved.add((m.group(1).strip(), m.group(2).strip()))

    targets = sorted(set(glob.glob(f"{R}/0*-*.md") +
                         glob.glob(f"{R}/_p*_entries.jsonl")))
    total = 0
    per = {}
    for t in targets:
        txt = open(t, encoding="utf-8").read()
        orig = txt
        # 1) 挖占位符保护标注
        holes = []
        def stash(m):
            holes.append(m.group(0))
            return f"\x00H{len(holes)-1}\x00"
        txt = ANN_MD.sub(stash, txt)
        txt = ANN_NOTE.sub(stash, txt)
        # 2) 应用更正
        for o, s in pairs:
            c = txt.count(o)
            if c:
                txt = txt.replace(o, s)
                per[(o, s)] = per.get((o, s), 0) + c
                total += c
        # 3) 还原并升级标注
        for i, h in enumerate(holes):
            txt = txt.replace(f"\x00H{i}\x00", h)
        txt = upgrade_ann(txt, approved)
        if txt != orig:
            open(t, "w", encoding="utf-8").write(txt)
    print(f"账本更正对 {len(pairs)} 组，作用于 {len(targets)} 个文件，改动 {total} 处")
    for (o, s), c in sorted(per.items(), key=lambda x: -x[1]):
        print(f"  {o} → {s}: {c}")
    # 残留自查（标注/账本内的原字不算）
    left = 0
    for t in targets:
        txt = open(t, encoding="utf-8").read()
        txt = ANN_MD.sub("", txt)
        txt = ANN_NOTE.sub("", txt)
        for o, _ in pairs:
            if o in txt:
                left += txt.count(o)
                print(f"  ⚠ 残留「{o}」于 {os.path.basename(t)}")
    print("残留:", "零 ✓" if left == 0 else f"{left} 处")
    return 0 if left == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
