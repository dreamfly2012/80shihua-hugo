#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给缺少 description/summary 的文章自动补一个纯文本摘要到 front matter。

为什么做这件事：
Hugo 的 .Summary 在文章没有 summary/description 前置字段时，会【渲染整篇正文】
来截取摘要。本站点 859 篇文章里只有 2 篇带 description、0 篇带 summary，导致
构建时 .Summary 被反复渲染正文（post-card 4000+ 次、seo/rss 也都吃），是构建
性能的最大开销来源。补上 summary 后，.Summary 直接取前置字段，省掉整篇正文渲染。

用法：
    python tools/add_summary.py            # 实际写入
    python tools/add_summary.py --dry-run  # 只统计会改多少，不写文件

幂等：已存在 description 或 summary 的文件会被跳过。
支持 TOML(+++) 与 YAML(---) 两种 front matter。
"""
import os
import re
import glob
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")


def toml_str(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return '"' + s.strip() + '"'


def yaml_str(s: str) -> str:
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    s = s.strip()
    if any(ch in s for ch in ':"#'):
        s = s.replace('"', '\\"')
        return '"' + s + '"'
    return s


def extract_plain(body: str, n: int = 100) -> str:
    """从正文抽取前 n 个可见字符的纯文本摘要（兼容 WordPress 残留 HTML/短代码）。"""
    body = re.sub(r"{{.*?}}", " ", body, flags=re.S)        # Hugo 短代码
    body = re.sub(r"{%.*?%}", " ", body, flags=re.S)        # 另一种短代码
    body = re.sub(r"<[^>]+>", " ", body)                   # HTML 标签
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body)      # 图片
    body = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", body)       # 链接
    body = re.sub(r"[#>*_`~=|]", " ", body)               # Markdown 语法
    body = re.sub(r"\s+", " ", body).strip()
    if not body:
        return ""
    if len(body) > n:
        body = body[:n].rstrip(" ，。、,.;；:：!！?？") + "…"
    return body


def process(path: str, dry_run: bool) -> bool:
    with open(path, encoding="utf-8") as f:
        text = f.read()

    if text.startswith("+++"):
        delim = "+++"
        pat = re.compile(r"(\+\+\+\n)(.*?)(\n\+\+\+\n|\n\+\+\+\s*$)", re.S)
    elif text.startswith("---"):
        delim = "---"
        pat = re.compile(r"(---\n)(.*?)(\n---\n|\n---\s*$)", re.S)
    else:
        return False

    m = pat.search(text)
    if not m:
        return False

    fm = m.group(2)
    if re.search(r"(?m)^\s*(description|summary)\s*[:=]", fm):
        return False  # 已有，跳过

    body = text[m.end():]
    summ = extract_plain(body)
    if not summ:
        return False

    newline = ("summary = %s\n" % toml_str(summ)) if delim == "+++" \
        else ("summary: %s\n" % yaml_str(summ))

    if dry_run:
        return True

    new_fm = m.group(1) + fm + "\n" + newline + m.group(3)
    new_text = text[:m.start()] + new_fm + text[m.end():]
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写入")
    args = ap.parse_args()

    count = 0
    skipped = 0
    for path in glob.glob(os.path.join(CONTENT, "**", "*.md"), recursive=True):
        try:
            if process(path, args.dry_run):
                count += 1
            else:
                skipped += 1
        except Exception as e:  # noqa
            print(f"ERR {path}: {e}")

    mode = "（DRY-RUN，未写入）" if args.dry_run else ""
    print(f"将/已修改 {count} 个文件，跳过 {skipped} 个 {mode}")


if __name__ == "__main__":
    main()
