#!/usr/bin/env python3
"""导出所有 categories 含 'uncategorized' 的文章清单（标题/摘要/现有分类标签/正文前200字），
   供人工/模型判断新分类与标签。仅导出，不修改。"""
import os, re, glob, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = "C:/tmp/uncat.json"

FM = re.compile(r"^\+\+\+(.*?)^\+\+\+", re.S | re.M)
TITLE = re.compile(r'title\s*=\s*"([^"]*)"')
SLUG = re.compile(r'slug\s*=\s*"([^"]*)"')
CATS = re.compile(r'categories\s*=\s*\[(.*?)\]', re.S)
TAGS = re.compile(r'tags\s*=\s*\[(.*?)\]', re.S)
SUMM = re.compile(r'summary\s*=\s*"([^"]*)"')

def uniq_arr(rx, text):
    m = rx.search(text)
    if not m:
        return []
    return [x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()]

def plain_excerpt(body):
    # 去 markdown 标记，取前 200 字
    body = re.sub(r'```.*?```', ' ', body, flags=re.S)
    body = re.sub(r'<[^>]+>', ' ', body)
    body = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', body)
    body = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', body)
    body = re.sub(r'[#>*_`~\-]', ' ', body)
    body = re.sub(r'\s+', ' ', body).strip()
    return body[:200]

items = []
for f in glob.glob(os.path.join(ROOT, "content", "**", "*.md"), recursive=True):
    txt = open(f, encoding="utf-8", errors="ignore").read()
    m = FM.search(txt)
    if not m:
        continue
    fm = m.group(1)
    cats = [c.lower() for c in uniq_arr(CATS, fm)]
    if "uncategorized" not in cats:
        continue
    body = txt[m.end():]
    title = TITLE.search(fm)
    slug = SLUG.search(fm)
    summ = SUMM.search(fm)
    items.append({
        "file": os.path.relpath(f, ROOT),
        "slug": slug.group(1) if slug else "",
        "title": title.group(1) if title else os.path.basename(f),
        "cats": cats,
        "tags": [t.lower() for t in uniq_arr(TAGS, fm)],
        "summary": summ.group(1) if summ else "",
        "excerpt": plain_excerpt(body),
    })

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(items, fh, ensure_ascii=False, indent=1)

print(f"含 uncategorized 的文章数: {len(items)}")
print(f"已导出到 {OUT}")
# 当前 tags 为空的比例
no_tag = sum(1 for i in items if not i["tags"])
print(f"其中当前 tags 为空: {no_tag}")
