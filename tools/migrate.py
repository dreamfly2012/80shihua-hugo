#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
80shihua.com (WordPress) -> Hugo 迁移脚本
- 数据源：WordPress REST API (wp-json/wp/v2)
- URL 保留：文章 slug = 数字ID；分类/标签/作者 slug 解码为原始中文，
  由 Hugo 按 permalinks 重新编码，与 WP 语义 1:1 一致
- 正文：保留原始 HTML，最大化保真（Hugo goldmark unsafe=true 透传）
依赖：仅 Python 标准库
"""
import json
import os
import html
import urllib.request
from urllib.parse import unquote

BASE = "https://www.80shihua.com/wp-json/wp/v2"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")
POSTS_DIR = os.path.join(CONTENT, "posts")

UA = {"User-Agent": "80shihua-migrate/1.0"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def get_all(endpoint):
    items = {}
    page = 1
    while True:
        data = get(f"{BASE}/{endpoint}?per_page=100&page={page}")
        if not isinstance(data, list) or not data:
            break
        for d in data:
            items[d["id"]] = d
        if len(data) < 100:
            break
        page += 1
    return items


def tomlish(s):
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s + '"'


def main():
    print("[1/3] 拉取分类 / 标签 / 作者映射 ...")
    cats = get_all("categories")
    tags = get_all("tags")
    users = get_all("users")
    # 解码百分号编码的 slug（中文分类/标签在 REST API 里是 %XX 形式）
    cat_slug = {cid: unquote(c["slug"]) for cid, c in cats.items()}
    tag_slug = {tid: unquote(t["slug"]) for tid, t in tags.items()}
    user_slug = {uid: unquote(u["slug"]) for uid, u in users.items()}
    print(f"      分类 {len(cats)} 个, 标签 {len(tags)} 个, 作者 {len(users)} 个")

    print("[2/3] 迁移文章 posts ...")
    os.makedirs(POSTS_DIR, exist_ok=True)
    count = 0
    page = 1
    while True:
        posts = get(f"{BASE}/posts?per_page=100&page={page}&orderby=id&order=asc")
        if not isinstance(posts, list) or not posts:
            break
        for p in posts:
            pid = p["id"]
            title = html.unescape(p["title"]["rendered"])
            cslugs = [cat_slug[c] for c in p.get("categories", []) if c in cat_slug]
            tslugs = [tag_slug[t] for t in p.get("tags", []) if t in tag_slug]
            # 站点单一作者：所有文章统一归属 dreamfly
            aslug = "dreamfly"
            fm = [
                f"title = {tomlish(title)}",
                f'date = {tomlish(p["date"])}',
                f'slug = {tomlish(str(pid))}',
                f"categories = {json.dumps(cslugs, ensure_ascii=False)}",
                f"tags = {json.dumps(tslugs, ensure_ascii=False)}",
            ]
            if aslug:
                # Hugo 分类法 front matter 用复数键
                fm.append(f"authors = {json.dumps([aslug], ensure_ascii=False)}")
            fm.append(f'draft = {str(p.get("status") != "publish").lower()}')
            fm.append(f'original_link = {tomlish(p.get("link", ""))}')
            body = p["content"]["rendered"]
            text = "+++\n" + "\n".join(fm) + "\n+++\n\n" + body
            with open(os.path.join(POSTS_DIR, f"{pid}.md"), "w", encoding="utf-8") as f:
                f.write(text)
            count += 1
        print(f"      已处理 {count} 篇 (page {page})")
        if len(posts) < 100:
            break
        page += 1

    print("[3/3] 迁移独立页面 pages ...")
    os.makedirs(CONTENT, exist_ok=True)
    pcount = 0
    page = 1
    while True:
        pages = get(f"{BASE}/pages?per_page=100&page={page}")
        if not isinstance(pages, list) or not pages:
            break
        for pg in pages:
            slug = unquote(pg.get("slug") or str(pg["id"]))
            title = html.unescape(pg["title"]["rendered"])
            fm = [f"title = {tomlish(title)}", f'date = {tomlish(pg["date"])}', f'slug = {tomlish(slug)}']
            # 站点单一作者：所有页面统一归属 dreamfly
            fm.append(f"authors = {json.dumps(['dreamfly'], ensure_ascii=False)}")
            fm.append(f'draft = {str(pg.get("status") != "publish").lower()}')
            # 页面写到 content 根级，URL 即 /{slug}/ 对齐 WP 页面
            text = "+++\n" + "\n".join(fm) + "\n+++\n\n" + pg["content"]["rendered"]
            with open(os.path.join(CONTENT, f"{slug}.md"), "w", encoding="utf-8") as f:
                f.write(text)
            pcount += 1
        if len(pages) < 100:
            break
        page += 1
    print(f"      已处理 {pcount} 个页面")

    print("完成。")
    print(f"文章: {count}  页面: {pcount}")
    print(f"内容目录: {CONTENT}")


if __name__ == "__main__":
    main()
