#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
80shihua Hugo 工程：补下载 UEditor 配图（download_images.py 当时只抓了 /wp-content/uploads/）
- 扫描 content/ 下所有 .md，提取 /ueditor/php/upload/ 路径的图片引用
  （兼容相对路径 /ueditor/... 与绝对 https://www.80shihua.com/ueditor/...）
- 下载到 static/uploads/ueditor/php/upload/<原相对路径>，保留原始目录结构
- 将 content 里的引用改写为本地 /uploads/ueditor/php/upload/... 前缀

用法：
  python download_ueditor.py        # 仅统计
  python download_ueditor.py run    # 下载 + 改写 content
"""
import os
import re
import sys
import time
import urllib.request
from urllib.parse import urlsplit, quote, urlunsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")
STATIC_UPLOADS = os.path.join(ROOT, "static", "uploads")          # -> 站点 /uploads/...
NEW_PREFIX = "/uploads/ueditor/php/upload/"
BASE = "https://www.80shihua.com"
CACHE = os.path.join(ROOT, ".ueditor_urls_cache.txt")
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": BASE + "/",
    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
}

# 匹配 /ueditor/php/upload/...（相对或绝对），不含引号/空格/括号
UE_RE = re.compile(r'(?:https?://(?:www\.)?80shihua\.com)?(/ueditor/php/upload/[^"\s\',)>]+)', re.I)
# 改写：把绝对或相对的 /ueditor/php/upload/ 都归一为 /uploads/ueditor/php/upload/
REWRITE_RE = re.compile(r'(?:https?://(?:www\.)?80shihua\.com)?(/ueditor/php/upload/[^"\s\',)>]+)')


def enc_url(u):
    p = urlsplit(u)
    path = quote(p.path, safe="/")
    q = quote(p.query, safe="=&")
    return urlunsplit((p.scheme, p.netloc, path, q, p.fragment))


def collect_md():
    out = []
    for dp, _, fns in os.walk(CONTENT):
        for fn in fns:
            if fn.endswith(".md"):
                out.append(os.path.join(dp, fn))
    return out


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    return []


def save_cache(urls):
    with open(CACHE, "w", encoding="utf-8") as f:
        f.write("\n".join(urls) + "\n")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "stats"
    files = collect_md()
    print(f"[scan] markdown 文件: {len(files)}")

    refs = {}          # 原始引用串 -> 相对路径(去域名)
    for fp in files:
        txt = open(fp, encoding="utf-8").read()
        for m in UE_RE.finditer(txt):
            rel = m.group(1)                      # /ueditor/php/upload/...
            refs.setdefault(m.group(0), rel)

    urls = sorted(set(refs.values()))
    print(f"[scan] 去重 ueditor 图片路径: {len(urls)}")

    yr = {}
    for u in urls:
        seg = u.split("/ueditor/php/upload/", 1)[1].split("/")
        y = seg[0] if seg and seg[0].isdigit() else "other"
        yr[y] = yr.get(y, 0) + 1
    print("[scan] 按年份分布:", dict(sorted(yr.items())))

    if mode != "run":
        print("[done] 仅统计模式。加 run 参数执行下载+改写。")
        return

    cached = load_cache()
    if cached:
        urls = sorted(set(urls) | set(cached))
        print(f"[run] 合并缓存后: {len(urls)}")
    save_cache(urls)

    ok = fail = skip = 0
    fails = []
    for i, rel in enumerate(urls, 1):
        dest = os.path.join(STATIC_UPLOADS, rel.lstrip("/"))
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            skip += 1
        else:
            dl_url = enc_url(BASE + rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            data = None
            last_err = None
            for attempt in range(4):
                try:
                    req = urllib.request.Request(dl_url, headers=UA)
                    with urllib.request.urlopen(req, timeout=60) as r:
                        data = r.read()
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(2 * (attempt + 1))
            if data:
                with open(dest, "wb") as f:
                    f.write(data)
                ok += 1
            else:
                fail += 1
                fails.append((BASE + rel, str(last_err)[:80]))
        if i % 50 == 0:
            print(f"  ...{i}/{len(urls)} ok={ok} fail={fail} skip={skip}")
        time.sleep(0.03)
    print(f"[download] ok={ok} fail={fail} skip={skip}")

    # 改写 content（相对/绝对 ueditor 引用 -> 本地 /uploads/ueditor/...）
    replaced = 0
    for fp in files:
        txt = open(fp, encoding="utf-8").read()
        new = REWRITE_RE.sub(lambda m: "/uploads" + m.group(1), txt)
        if new != txt:
            open(fp, "w", encoding="utf-8", newline="\n").write(new)
            replaced += 1
    print(f"[rewrite] 改写文件数: {replaced}")

    if fails:
        print(f"[warn] 失败 {len(fails)} 个，示例:")
        for u, e in fails[:10]:
            print("   ", u, "->", e)


if __name__ == "__main__":
    main()
