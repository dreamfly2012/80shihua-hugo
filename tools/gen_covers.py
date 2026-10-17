#!/usr/bin/env python3
"""
Batch cover generator for 80shihua-hugo.
For every post that has no body image and no `cover` front-matter, generate a
unique, on-topic cover image via the (free) Agnes image API, convert it to WebP,
save to static/uploads/covers/<slug>.webp, and inject
`cover = "/uploads/covers/<slug>.webp"` into the TOML front matter.

Resumable / idempotent: posts already having a cover (front matter or file) are
skipped; legacy .png covers are migrated to .webp automatically.

Usage:
  python gen_covers.py              # process all image-less posts
  python gen_covers.py --limit 5    # only the first 5 (test)
"""
import os
import re
import sys
import json
import time
import ssl
import hashlib
import tomllib
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, "content", "posts")
COVERS_DIR = os.path.join(ROOT, "static", "uploads", "covers")
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "covers_log.txt")
os.makedirs(COVERS_DIR, exist_ok=True)

# per-shard log when sharding to avoid concurrent-append corruption
import sys as _sys
_SHARD = 0
for _i, _a in enumerate(_sys.argv[1:]):
    if _a == "--shard":
        _SHARD = int(_sys.argv[1:][_i + 1])
    elif _a.startswith("--shard="):
        _SHARD = int(_a.split("=")[1])
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"covers_log{('_'+str(_SHARD)) if _SHARD else ''}.txt")

API_KEY = os.environ.get("AGNES_API_KEY", "")
BASE_URL = os.environ.get("AGNES_API_BASE", "https://api.agnes-ai.cn/v1")
MODEL = "agnes-image-2.5-flash"
SIZE = "1K"
RATIO = "16:9"
SLEEP = 3.1  # 1K free tier = 20 RPM -> 3s floor
WEBP_QUALITY = 82

# ---- category / tag -> visual subject (English prompts work best) ----
THEME = {
    "php": "modern PHP web development, clean code and a sleek dashboard UI",
    "javascript": "modern JavaScript web development with dynamic UI components",
    "js": "modern JavaScript web development with dynamic UI components",
    "css": "modern CSS web design with stylish layout and typography",
    "html": "clean modern HTML web page structure and markup",
    "jquery": "interactive web frontend with smooth UI animations",
    "thinkphp": "PHP framework web application architecture",
    "dedecms": "content management system website admin interface",
    "ecshop": "e-commerce online shop storefront interface",
    "seo": "search engine optimization with analytics and rising traffic graphs",
    "python": "Python programming with data flows and scripting",
    "golang": "Go programming language and concurrent systems",
    "go": "Go programming language and concurrent systems",
    "c_cplus": "C and C++ low-level systems programming",
    "algorithm2": "algorithms and data structures visualization",
    "linux": "Linux command line and a server terminal",
    "server": "server infrastructure and cloud hosting",
    "mysql": "MySQL database with organized data tables",
    "redis": "Redis in-memory cache and a key-value store",
    "os_system": "operating system and computer internals",
    "version": "version control and collaborative software development",
    "vim": "a code editor and terminal productivity",
    "editor": "a modern code editor interface",
    "software": "a software application and digital tools",
    "app": "a mobile app and application design",
    "apache": "web server and hosting infrastructure",
    "nginx": "web server and reverse proxy infrastructure",
    "ubuntu": "Linux desktop and open source environment",
    "git": "version control and code collaboration",
    "cache": "high speed caching and memory architecture",
    "json": "structured data and API interchange",
    "vscode": "a modern code editor workspace",
    "sublime": "a minimal code editor environment",
    "dropbox": "cloud storage and file sync",
    "bug": "debugging and software problem solving",
    "time": "time, clocks and productivity",
    "个人博客": "a personal blog and a cozy lifestyle journal",
    "essay": "a personal essay and reflective quiet writing",
    "beautiful_sentence": "elegant typography and a poetic mood",
    "short_meangful_story": "a short meaningful story illustration",
    "novel": "a literary novel and an atmospheric narrative scene",
    "menghuiguli": "a dreamy literary illustration",
    "reprint": "an editorial magazine article illustration",
    "micro_reasoning": "abstract logical reasoning and connected ideas",
    "uncategorized": "an abstract modern gradient artwork",
}
DEFAULT_THEME = "an abstract modern gradient artwork"

PALETTES = [
    "deep indigo and vivid cyan",
    "violet and warm amber",
    "teal and rose pink",
    "royal blue and emerald green",
    "magenta and slate gray",
    "orange and ocean blue",
    "crimson and gold",
    "forest green and sky blue",
]
COMPS = [
    "floating geometric polygons",
    "flowing data streams and glowing particles",
    "soft gradient mesh waves",
    "layered paper-cut shapes",
    "minimal glowing line art",
    "an abstract wireframe grid",
]


def build_prompt(slug, cats, tags):
    keys = (cats or []) + (tags or [])
    theme = DEFAULT_THEME
    for k in keys:
        if k in THEME:
            theme = THEME[k]
            break
    h = int(hashlib.md5(slug.encode()).hexdigest(), 16)
    palette = PALETTES[h % len(PALETTES)]
    comp = COMPS[(h >> 4) % len(COMPS)]
    return (
        f"Minimalist editorial magazine illustration of {theme}. "
        f"{comp}, {palette} gradient, clean modern flat style, soft lighting, "
        f"subtle depth, no text, no letters, no words, no watermark, no signature."
    )


def api_generate(prompt):
    url = BASE_URL.rstrip("/") + "/images/generations"
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "size": SIZE,
        "extra_body": {"ratio": RATIO, "response_format": "url"},
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return resp["data"][0]["url"]


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        content = r.read()
    with open(path, "wb") as f:
        f.write(content)


def to_webp(png_path, webp_path):
    from PIL import Image
    with Image.open(png_path) as im:
        im.convert("RGB").save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
    os.remove(png_path)


def parse_post(path):
    txt = open(path, encoding="utf-8").read()
    m = re.match(r"^\+\+\+\s*\n(.*?)\n\+\+\+\s*\n", txt, re.S)
    if not m:
        return None, None, None
    return tomllib.loads(m.group(1)), m.group(1), txt[m.end():]


def has_image(body):
    return bool(re.search(r"<img", body, re.I)) or bool(
        re.search(r"!\[[^\]]*\]\([^)]+\)", body)
    )


FM_RE = re.compile(r"^\+\+\+\s*\n(.*?)\n\+\+\+\s*\n", re.S)
ANY_COVER_RE = re.compile(r'(?m)^cover\s*=\s*"[^\n]*"\n?')
OUR_COVER_RE = re.compile(r'(?m)^cover\s*=\s*"/uploads/covers/[^\n]*\n?')


def set_cover_line(path, cover_path):
    """Insert/replace `cover = "..."` INSIDE the TOML front matter, and strip
    any stray cover lines that earlier versions wrongly left in the body."""
    txt = open(path, encoding="utf-8").read()
    m = FM_RE.match(txt)
    if not m:
        return False
    fm_text = m.group(1)
    rest = txt[m.end():]
    # never clobber a user-set cover pointing outside our covers dir
    if re.search(r'(?m)^cover\s*=\s*"', fm_text) and not OUR_COVER_RE.search(fm_text):
        return False
    cover_line = f'cover = "{cover_path}"'
    fm_clean = ANY_COVER_RE.sub("", fm_text)  # avoid duplicates
    rest = OUR_COVER_RE.sub("", rest)         # clean legacy body strays
    open(path, "w", encoding="utf-8").write(
        "+++\n" + fm_clean + "\n" + cover_line + "\n+++\n" + rest
    )
    return True


def fm_cover(path):
    fm, _, _ = parse_post(path)
    if fm is None:
        return None
    return fm.get("cover")


def process(f):
    """Returns one of: 'skip', 'migrated', 'generated', 'failed'."""
    slug = os.path.splitext(os.path.basename(f))[0]
    webp = os.path.join(COVERS_DIR, slug + ".webp")
    legacy_png = os.path.join(COVERS_DIR, slug + ".png")
    fm, _, body = parse_post(f)
    if fm is None:
        return "skip"

    # 1) legacy png -> migrate to webp + fix fm
    if os.path.exists(legacy_png) and not os.path.exists(webp):
        to_webp(legacy_png, webp)
        set_cover_line(f, f"/uploads/covers/{slug}.webp")
        return "migrated"

    # 2) already done?
    if os.path.exists(webp):
        if fm_cover(f) != f"/uploads/covers/{slug}.webp":
            set_cover_line(f, f"/uploads/covers/{slug}.webp")
        return "skip"

    # 3) has body image or any cover -> not our target
    if "cover" in fm or has_image(body):
        return "skip"

    # 4) generate
    cats = fm.get("categories") or []
    tags = fm.get("tags") or []
    prompt = build_prompt(slug, cats, tags)
    tmp_png = os.path.join(COVERS_DIR, slug + ".png")
    for attempt in range(3):
        try:
            img_url = api_generate(prompt)
            download(img_url, tmp_png)
            to_webp(tmp_png, webp)
            set_cover_line(f, f"/uploads/covers/{slug}.webp")
            return "generated"
        except Exception as e:
            print(f"  retry {attempt+1} for {slug}: {e}", flush=True)
            time.sleep(5)
    if os.path.exists(tmp_png):
        os.remove(tmp_png)
    return "failed"


def main():
    if not API_KEY:
        print("ERROR: AGNES_API_KEY not set")
        sys.exit(1)
    limit = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--limit":
            limit = int(args[i + 1])
        elif a.startswith("--limit="):
            limit = int(a.split("=")[1])

    import glob
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.md")))
    # sharding: only handle files where index % shards == shard
    shards = 1
    shard = 0
    for i, a in enumerate(args):
        if a == "--shards":
            shards = int(args[i + 1])
        elif a.startswith("--shards="):
            shards = int(a.split("=")[1])
        if a == "--shard":
            shard = int(args[i + 1])
        elif a.startswith("--shard="):
            shard = int(a.split("=")[1])
    if shards > 1:
        files = [f for idx, f in enumerate(files) if idx % shards == shard]
        print(f"[shard {shard}/{shards}] handling {len(files)} files", flush=True)
    log = open(LOG_PATH, "a", encoding="utf-8")
    counts = {"generated": 0, "migrated": 0, "skipped": 0, "failed": 0}
    started = time.time()
    for i, f in enumerate(files):
        if limit is not None and counts["generated"] >= limit:
            break
        slug = os.path.splitext(os.path.basename(f))[0]
        try:
            r = process(f)
        except Exception as e:
            r = "failed"
            print(f"ERROR {slug}: {e}", flush=True)
        counts[r] = counts.get(r, 0) + 1
        if r == "failed":
            log.write(f"FAILED {slug}\n")
            log.flush()
        if (i + 1) % 25 == 0:
            el = time.time() - started
            line = (f"[{i+1}/{len(files)}] gen={counts['generated']} "
                    f"skip={counts['skipped']} fail={counts['failed']} "
                    f"({el:.0f}s, ~{(len(files)-i-1)*max(el/(i+1),1):.0f}s left)")
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()
        if r == "generated":
            time.sleep(SLEEP)
    summary = f"DONE {counts} in {time.time()-started:.0f}s"
    print(summary, flush=True)
    log.write(summary + "\n")
    log.close()


if __name__ == "__main__":
    main()
