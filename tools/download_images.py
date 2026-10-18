#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
80shihua Hugo 工程：文章配图本地化
- 扫描 content/ 下所有 .md，提取指向 www.80shihua.com/wp-content/uploads/ 的图片 URL
  （覆盖 <img src>、srcset 各尺寸变体、<a href> 中的图片链接）
- 下载到 static/uploads/wp-content/uploads/<原相对路径>，保留 WP 原始目录结构
- 将 content 里的远程 URL 改写为本地 /uploads/wp-content/uploads/... 前缀

用法：
  python download_images.py        # 仅统计（默认，不下载不改动）
  python download_images.py run    # 下载全部图片 + 改写 content
"""
import os
import re
import sys
import time
import urllib.request
from urllib.parse import urlsplit, quote, urlunsplit


def enc_url(u):
    """对 URL 的 path/query 做百分号编码，使其可被 urllib 请求。
    仅编码非 ASCII 字符，已编码部分不受影响。"""
    p = urlsplit(u)
    path = quote(p.path, safe="/")
    q = quote(p.query, safe="=&")
    return urlunsplit((p.scheme, p.netloc, path, q, p.fragment))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")
STATIC_UPLOADS = os.path.join(ROOT, "static", "uploads", "wp-content", "uploads")
NEW_PREFIX = "/uploads/wp-content/uploads/"
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.80shihua.com/",
    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
}

# 抓取 80shihua 域名下 wp-content/uploads 的图片 URL（不含逗号/引号/空格/括号）
URL_RE = re.compile(r'https?://(?:www\.)?80shihua\.com/wp-content/uploads/[^"\s\',)>]+', re.I)
SRCSET_RE = re.compile(r'srcset="([^"]+)"', re.I)
REWRITE_RE = re.compile(r'(?:https?:)?//(?:www\.)?80shihua\.com/wp-content/uploads/')
CACHE = os.path.join(ROOT, ".image_urls_cache.txt")


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    return []


def save_cache(urls):
    with open(CACHE, "w", encoding="utf-8") as f:
        f.write("\n".join(urls) + "\n")


def collect_md():
    out = []
    for dp, _, fns in os.walk(CONTENT):
        for fn in fns:
            if fn.endswith(".md"):
                out.append(os.path.join(dp, fn))
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "stats"
    files = collect_md()
    print(f"[scan] markdown 文件: {len(files)}")

    url_files = {}      # url -> [files]
    for fp in files:
        txt = open(fp, encoding="utf-8").read()
        for m in URL_RE.finditer(txt):
            url_files.setdefault(m.group(0), []).append(os.path.basename(fp))
    # srcset 拆解：每张图还有 300w/768w 等尺寸变体 URL
    for fp in files:
        txt = open(fp, encoding="utf-8").read()
        for m in SRCSET_RE.finditer(txt):
            for part in m.group(1).split(","):
                u = part.strip().split(" ")[0]
                if "80shihua.com/wp-content/uploads/" in u:
                    url_files.setdefault(u, []).append(os.path.basename(fp))

    urls = sorted(url_files)
    print(f"[scan] 去重图片 URL 总数: {len(urls)}")

    # 按年份分布
    yr = {}
    for u in urls:
        seg = u.split("/wp-content/uploads/", 1)[1].split("/")
        y = seg[0] if seg and seg[0].isdigit() else "other"
        yr[y] = yr.get(y, 0) + 1
    print("[scan] 按年份分布:", dict(sorted(yr.items())))

    if mode != "run":
        print("[done] 仅统计模式。加 run 参数执行下载+改写。")
        return

    # run 模式：合并历史缓存 URL（content 改写后也能据此补下载）
    cached = load_cache()
    if cached:
        urls = sorted(set(urls) | set(cached))
        print(f"[run] 合并缓存后图片 URL 总数: {len(urls)}")
    save_cache(urls)

    # ---- 下载 ----
    os.makedirs(STATIC_UPLOADS, exist_ok=True)
    ok = fail = skip = 0
    fails = []
    for i, u in enumerate(urls, 1):
        rel = u.split("/wp-content/uploads/", 1)[1]
        dest = os.path.join(STATIC_UPLOADS, rel)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            skip += 1
        else:
            dl_url = enc_url(u.replace("http://", "https://"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            data = None
            last_err = None
            for attempt in range(4):  # 失败重试 4 次，指数退避
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
                fails.append((u, str(last_err)[:80]))
        if i % 100 == 0:
            print(f"  ...下载进度 {i}/{len(urls)}  ok={ok} fail={fail} skip={skip}")
        time.sleep(0.03)
    print(f"[download] ok={ok} fail={fail} skip={skip}")

    # ---- 改写 content ----
    replaced = 0
    for fp in files:
        txt = open(fp, encoding="utf-8").read()
        new = REWRITE_RE.sub(NEW_PREFIX, txt)
        if new != txt:
            open(fp, "w", encoding="utf-8").write(new)
            replaced += 1
    print(f"[rewrite] 改写文件数: {replaced}")

    if fails:
        print(f"[warn] 失败 {len(fails)} 个，示例:")
        for u, e in fails[:10]:
            print("   ", u, "->", e)


if __name__ == "__main__":
    main()
