#!/usr/bin/env python3
"""一次性诊断脚本：复刻 Hugo [related] 的加权相似度算法，
   看当前配置下"相关文章"到底返回了什么。
   仅用于分析，不参与构建。"""
import os, re, glob, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS = os.path.join(ROOT, "content", "posts")

FM = re.compile(r"^\+\+\+(.*?)^\+\+\+", re.S | re.M)
TITLE = re.compile(r'title\s*=\s*"([^"]*)"')
SLUG = re.compile(r'slug\s*=\s*"([^"]*)"')
CATS = re.compile(r'categories\s*=\s*\[(.*?)\]', re.S)
TAGS = re.compile(r'tags\s*=\s*\[(.*?)\]', re.S)
DATE = re.compile(r'date\s*=\s*"([^"]*)"')

def parse(path):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    m = FM.search(txt)
    if not m:
        return None
    fm = m.group(1)
    def arr(rx):
        mm = rx.search(fm)
        if not mm:
            return []
        return [x.strip().strip('"').strip("'").lower() for x in mm.group(1).split(",") if x.strip()]
    title = TITLE.search(fm)
    slug = SLUG.search(fm)
    date = DATE.search(fm)
    return {
        "title": title.group(1) if title else os.path.basename(path),
        "slug": slug.group(1) if slug else "",
        "cats": arr(CATS),
        "tags": arr(TAGS),
        "date": date.group(1)[:10] if date else "",
        "path": path,
    }

def vector(p):
    """复刻 Hugo 当前配置：tags*100, categories*60（已移除 date 噪声维度）"""
    v = {}
    for c in p["cats"]:
        v["cat:" + c] = v.get("cat:" + c, 0) + 60
    for t in p["tags"]:
        v["tag:" + t] = v.get("tag:" + t, 0) + 100
    return v

def score(a, b):
    va, vb = vector(a), vector(b)
    keys = set(va) & set(vb)
    return sum(va[k] * vb[k] for k in keys)

pages = []
for f in glob.glob(os.path.join(POSTS, "*.md")):
    p = parse(f)
    if p:
        pages.append(p)

def show(target):
    peers = [p for p in pages if p["path"] != target["path"]]
    ranked = sorted(peers, key=lambda p: score(target, p), reverse=True)[:4]
    print(f"\n=== 目标: 《{target['title']}》 cat={target['cats']} tag={target['tags']} date={target['date']} ===")
    for i, p in enumerate(ranked, 1):
        s = score(target, p)
        print(f"  {i}. [{s:>5}] 《{p['title']}》 cat={p['cats']} tag={p['tags']} {p['date']}")

# 选代表：reprint / php / uncategorized / essay 各取第一篇
picked = {}
for p in pages:
    for key in ("reprint", "php", "uncategorized", "essay"):
        if key in p["cats"] and key not in picked:
            picked[key] = p
for key in ("reprint", "php", "uncategorized", "essay"):
    if key in picked:
        show(picked[key])

# 可选：指定 slug 分析
if len(sys.argv) > 1:
    slug = sys.argv[1]
    t = next((p for p in pages if p["slug"] == slug), None)
    if t:
        show(t)
