#!/usr/bin/env python3
"""Scan all posts for image references, classify, and probe remote liveness."""
import os, re, json, sys
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS = os.path.join(ROOT, "content", "posts")
STATIC_UP = os.path.join(ROOT, "static", "uploads")

# Markdown image and HTML <img> src
IMG_MD = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
IMG_TAG = re.compile(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']', re.I)
IMG_TAG_ALT = re.compile(r'<img\b[^>]*\balt=["\']([^"\']*)["\']', re.I)

def local_exists(path):
    # path like /uploads/xxx -> static/uploads/xxx (Hugo serves static/ at site root)
    rel = path
    if rel.startswith("/"):
        rel = rel[1:]
    return os.path.exists(os.path.join(ROOT, "static", rel))

def classify(url):
    u = url.strip()
    if u.startswith("http://") or u.startswith("https://"):
        return ("remote", u)
    if u.startswith("//"):
        return ("remote", "https:" + u)
    if u.startswith("/"):
        return ("local", u)
    # relative
    return ("local_rel", u)

def probe(url):
    import urllib.request, ssl
    from urllib.error import HTTPError, URLError
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
           "Referer": "https://www.80shihua.com/"}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers=hdr, method="HEAD")
        with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
            return r.status
    except HTTPError as e:
        return e.code  # real HTTP status (e.g. 403/404/410)
    except Exception:
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
                return r.status
        except HTTPError as e:
            return e.code
        except URLError as e:
            return f"NETERR:{type(e.reason).__name__}"
        except Exception as e2:
            return f"ERR:{type(e2).__name__}"

results = {}
remote_urls = set()
for fn in sorted(os.listdir(POSTS)):
    if not fn.endswith(".md"):
        continue
    p = os.path.join(POSTS, fn)
    txt = open(p, encoding="utf-8", errors="replace").read()
    refs = []
    for m in IMG_MD.finditer(txt):
        refs.append((m.group(1), m.group(2)))
    for m in IMG_TAG.finditer(txt):
        alt = ""
        am = IMG_TAG_ALT.search(txt[max(0, m.start()-200):m.start()])
        refs.append((am.group(1) if am else "", m.group(1)))
    for alt, url in refs:
        kind, val = classify(url)
        if kind.startswith("remote"):
            remote_urls.add(val)
        else:
            exists = local_exists(val)
            key = ("local_missing" if not exists else "local_ok", val)
            results.setdefault(fn, []).append((alt, url, "local_missing" if not exists else "local_ok"))

# local missing summary
local_missing_files = set()
local_ok_count = 0
for fn, lst in results.items():
    for alt, url, st in lst:
        if st == "local_missing":
            local_missing_files.add(url)
        else:
            local_ok_count += 1

print(f"=== LOCAL image refs ===")
print(f"local OK refs: {local_ok_count}")
print(f"local MISSING (source-deleted) unique files: {len(local_missing_files)}")

# probe remote
print(f"\n=== REMOTE image refs ===")
print(f"unique remote URLs: {len(remote_urls)}")

# domain distribution
dom = {}
for u in remote_urls:
    d = urlparse(u).netloc
    dom[d] = dom.get(d, 0) + 1
dom_sorted = sorted(dom.items(), key=lambda x: -x[1])
print("domain distribution:")
for d, c in dom_sorted:
    print(f"  {c:4d}  {d}")

# probe liveness
alive = {}
dead = {}
blocked = {}   # 401/403/429 - protected but likely still serves to real browsers
unknown = {}
with ThreadPoolExecutor(max_workers=20) as ex:
    fut = {ex.submit(probe, u): u for u in remote_urls}
    done = 0
    for f in as_completed(fut):
        u = fut[f]
        st = f.result()
        if isinstance(st, int):
            if 200 <= st < 400:
                alive[u] = st
            elif st in (401, 403, 429):
                blocked[u] = st
            elif st in (404, 410):
                dead[u] = st
            else:
                unknown[u] = st
        else:
            unknown[u] = st
        done += 1
        if done % 50 == 0:
            print(f"  probed {done}/{len(remote_urls)}")

print(f"\nremote ALIVE (2xx/3xx): {len(alive)}")
print(f"remote BLOCKED (401/403/429, may still show in browser): {len(blocked)}")
print(f"remote DEAD (404/410): {len(dead)}")
print(f"remote UNKNOWN/ERR: {len(unknown)}")

# save details
out = {
    "local_missing_files": sorted(local_missing_files),
    "remote_alive": sorted(alive.keys()),
    "remote_blocked": {k: v for k, v in sorted(blocked.items())},
    "remote_dead": {k: v for k, v in sorted(dead.items())},
    "remote_unknown": {k: v for k, v in sorted(unknown.items())},
}
with open("image_scan_report.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("\nwrote image_scan_report.json")
