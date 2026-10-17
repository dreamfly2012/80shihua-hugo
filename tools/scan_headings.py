#!/usr/bin/env python3
"""扫描 content/**/*.md 中残留的 HTML heading 标签（<h2>…</h2> 等），
评估「转成 markdown 标题」的规模与风险。

只读脚本：不修改任何文件。
用法：python tools/scan_headings.py [--json out.json]
"""
import re
import os
import sys
import glob
import json
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = sorted(glob.glob(os.path.join(ROOT, "content", "**", "*.md"), recursive=True))

FENCE_RE = re.compile(r"^(```|~~~)")
PRE_RE = re.compile(r"<pre\b[^>]*>.*?</pre>", re.I | re.S)
HEAD_RE = re.compile(r"<h([2-6])\b([^>]*)>(.*?)</h\1\s*>", re.I | re.S)
INLINE_RE = re.compile(r"<(strong|b|a|em|i|code|span|font|br|img|u|sup|sub)\b[^>]*>", re.I)
MD_HEAD_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s")
ATTR_RE = re.compile(r"\b(class|id|style|align|dir)\s*=", re.I)


def strip_code(text):
    """移除 pre 块与围栏代码块，返回可安全扫描的正文。"""
    t = PRE_RE.sub("\n", text)
    out, fence = [], None
    for line in t.split("\n"):
        s = line.strip()
        if fence is None:
            m = FENCE_RE.match(s)
            if m:
                fence = m.group(1)
                out.append("")
                continue
            out.append(line)
        else:
            if s.startswith(fence):
                fence = None
            out.append("")
    return "\n".join(out)


def strip_fm(raw):
    if raw.startswith("+++"):
        m = re.match(r"\+\+\+.*?\n\+\+\+\s*\n?", raw, re.S)
    elif raw.startswith("---"):
        m = re.match(r"---.*?\n---\s*\n?", raw, re.S)
    else:
        return raw
    return raw[m.end():] if m else raw


stats = collections.Counter()
per_level = collections.Counter()
samples = collections.defaultdict(list)
risk = collections.Counter()
new_toc_files = []
mixed_files = []

for p in FILES:
    raw = open(p, encoding="utf-8", errors="ignore").read()
    body = strip_fm(raw)
    clean = strip_code(body)

    raw_hits = len(HEAD_RE.findall(body))          # 含代码块内
    hs = HEAD_RE.findall(clean)                    # 排除代码块后
    if not hs:
        continue

    stats["files_with_html_heading"] += 1
    stats["headings_total"] += len(hs)
    if raw_hits != len(hs):
        stats["files_with_in_code"] += 1
        risk["excluded_in_codeblocks"] += raw_hits - len(hs)

    has_md = bool(MD_HEAD_RE.search(clean))
    if has_md:
        stats["files_mixed"] += 1
        mixed_files.append(os.path.relpath(p, ROOT))

    for lvl, attr, txt in hs:
        key = "h" + lvl.lower()
        per_level[key] += 1
        if attr.strip():
            risk["has_attribute"] += 1
        if ATTR_RE.search(attr):
            risk["attr_class_id_style"] += 1
        if "\n" in txt:
            risk["cross_line"] += 1
        if INLINE_RE.search(txt):
            risk["inline_html_in_text"] += 1
        if re.match(r"^\s*<h[2-6]\b", txt):
            risk["nested_heading"] += 1
        if len(samples[key]) < 3:
            samples[key].append(re.sub(r"\s+", " ", txt).strip()[:80])

    if len(hs) >= 2:
        stats["files_ge2"] += 1
        if not has_md:
            stats["net_new_toc_candidates"] += 1
            new_toc_files.append((os.path.relpath(p, ROOT), len(hs)))
    else:
        stats["files_only_1"] += 1

report = {
    "total_md_files": len(FILES),
    "stats": dict(stats),
    "by_level": dict(per_level),
    "risks": dict(risk),
    "samples": {k: v for k, v in samples.items()},
    "net_new_toc_sample": new_toc_files[:15],
}

if "--json" in sys.argv:
    out = sys.argv[sys.argv.index("--json") + 1]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("written", out)
else:
    print("MD 文件总数        :", report["total_md_files"])
    print("含 HTML heading    :", stats["files_with_html_heading"], "篇")
    print("heading 标签总数   :", stats["headings_total"])
    print("其中 ≥2 个标题     :", stats["files_ge2"], "篇")
    print("仅 1 个标题        :", stats["files_only_1"], "篇")
    print("与 markdown 标题混用:", stats["files_mixed"], "篇")
    print("净新增目录候选     :", stats["net_new_toc_candidates"], "篇")
    print("--- 级别分布 ---")
    for k, v in per_level.most_common():
        print(f"  {k}: {v}")
    print("--- 风险点 ---")
    for k, v in sorted(risk.items()):
        print(f"  {k}: {v}")
    print("--- 样例 ---")
    for k, v in samples.items():
        for s in v:
            print(f"  [{k}] {s}")
