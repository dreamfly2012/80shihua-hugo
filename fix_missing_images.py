#!/usr/bin/env python3
"""Replace broken image references with content-derived placeholder figures.

Broken = source-deleted local files + dead external links (confirmed via scan).
Placeholder shows the image description (alt text, else humanized filename),
so layout does not collapse and readers get context (the user's "根据内容补全").
"""
import os, re, html

ROOT = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(ROOT, "content", "posts")

# Curated broken set (verified: source-deleted / 404, 0 false positives)
BROKEN = [
    # --- 2181.md macOS VMware 教程（源站已删，19 张）---
    "/uploads/wp-content/uploads/2019/09/macos-8g内存.png",
    "/uploads/wp-content/uploads/2019/09/macos-修改vmx.png",
    "/uploads/wp-content/uploads/2019/09/macos-光盘.png",
    "/uploads/wp-content/uploads/2019/09/macos-创建账号.jpg",
    "/uploads/wp-content/uploads/2019/09/macos-安装VMwaretools.jpg",
    "/uploads/wp-content/uploads/2019/09/macos-安装完成.png",
    "/uploads/wp-content/uploads/2019/09/macos-自定义.png",
    "/uploads/wp-content/uploads/2019/09/macos-选择光盘.png",
    "/uploads/wp-content/uploads/2019/09/macos-错误.png",
    "/uploads/wp-content/uploads/2019/09/安全与隐私-macos.jpg",
    "/uploads/wp-content/uploads/2019/09/安装VMwaretools-mac重启.jpg",
    "/uploads/wp-content/uploads/2019/09/安装开始.png",
    "/uploads/wp-content/uploads/2019/09/手动指定虚拟机分辨率.png",
    "/uploads/wp-content/uploads/2019/09/抹掉.png",
    "/uploads/wp-content/uploads/2019/09/磁盘工具.png",
    "/uploads/wp-content/uploads/2019/09/等待几分钟.png",
    "/uploads/wp-content/uploads/2019/09/管理员cmd运行win-install.png",
    "/uploads/wp-content/uploads/2019/09/虚拟机保存位置.png",
    "/uploads/wp-content/uploads/2019/09/选择macos10.13虚拟机.png",
    "/uploads/wp-content/uploads/2019/09/选择语言.png",
    # --- 3324 / 3331 / 3333 / 824 ---
    "/uploads/wp-content/uploads/2024/03/image-1024x650.png",
    "/uploads/wp-content/uploads/2024/07/4e351c8c29dece80f67df5f544c27a12-2-1024x583.png",
    "/uploads/wp-content/uploads/2024/08/9c25-kphwumr1486662.jpg",
    "/images/header.jpeg",
    # --- 128.md 网易缓存图（404，10 张）---
    "http://img1.cache.netease.com/catchpic/0/06/0639477AD2E8981D1428459200533758.jpg",
    "http://img1.cache.netease.com/catchpic/3/34/34463AA2CFB8553BA9AD1119C070ADEB.jpg",
    "http://img1.cache.netease.com/catchpic/3/35/35A3DE85617A1A1D53DAF7389AD8663B.jpg",
    "http://img1.cache.netease.com/catchpic/4/40/403ABB0338527519EBC712B4D2325F3D.jpg",
    "http://img1.cache.netease.com/catchpic/7/7F/7FB238565FE4D8C3FC6D59F6CD8940D0.jpg",
    "http://img1.cache.netease.com/catchpic/8/83/83492D13A8CC07E8DD7CBAFFABD4ED52.jpg",
    "http://img1.cache.netease.com/catchpic/A/AC/AC9B780669C8962E4C1F79FA47713C33.jpg",
    "http://img1.cache.netease.com/catchpic/B/B4/B4D2324A5BF0B73BEC5DD1B4F6F4FAFB.jpg",
    "http://img1.cache.netease.com/catchpic/C/C3/C3C5C39BD0281E14515F1CF98359992C.jpg",
    "http://img1.cache.netease.com/catchpic/F/F9/F9B1FFF1A29AA51D57A27355E29052C3.jpg",
]
BROKEN_SET = set(BROKEN)

def norm_url(u):
    u = u.strip()
    # strip surrounding smart/straight quotes that sometimes wrap refs
    u = u.strip('"\u201c\u201d\u2018\u2019')
    if u.startswith("//"):
        u = "https:" + u
    return u

def humanize(url):
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    name = re.sub(r"\.\w+$", "", name)
    name = name.replace("_", " ").replace("-", " ")
    return name.strip() or url

MD_RE = re.compile(r"(!\[)([^\]]*?)(\]\()([^)\s]+)(\))")
IMG_RE = re.compile(r"(<img\b[^>]*?\bsrc=[\"'])([^\"']+)([\"'][^>]*?>)")

def figure_for(alt, url):
    desc = (alt or "").strip()
    if not desc:
        desc = humanize(url)
    desc = html.escape(desc, quote=True)
    return ('<figure class="img-missing">'
            '<span class="im-label">图片缺失</span>'
            f'<span class="im-desc">{desc}</span></figure>')

def replace_in_text(txt):
    changes = 0
    def md_sub(m):
        nonlocal changes
        url = norm_url(m.group(4))
        if url in BROKEN_SET:
            changes += 1
            return figure_for(m.group(2), url)
        return m.group(0)
    txt = MD_RE.sub(md_sub, txt)

    def img_sub(m):
        nonlocal changes
        url = norm_url(m.group(2))
        if url in BROKEN_SET:
            changes += 1
            tag = m.group(0)
            am = re.search(r"alt=[\"']([^\"']*)[\"']", tag)
            alt = am.group(1) if am else ""
            return figure_for(alt, url)
        return m.group(0)
    txt = IMG_RE.sub(img_sub, txt)
    return txt, changes

total = 0
touched = []
for fn in sorted(os.listdir(POSTS)):
    if not fn.endswith(".md"):
        continue
    p = os.path.join(POSTS, fn)
    txt = open(p, encoding="utf-8").read()
    new, c = replace_in_text(txt)
    if c:
        open(p, "w", encoding="utf-8").write(new)
        total += c
        touched.append((fn, c))

print(f"Replaced {total} broken image refs across {len(touched)} posts:")
for fn, c in touched:
    print(f"  {fn}: {c}")
