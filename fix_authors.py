#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把所有文章 / 独立页面的作者统一为 dreamfly（站点单一作者）。
只修改 front matter 的 authors 字段，正文与图片 URL 原样保留。
依赖：仅 Python 标准库
"""
import os
import re
import glob

ROOT = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(ROOT, "content", "posts")
CONTENT = os.path.join(ROOT, "content")


def set_authors(text):
    if not text.startswith("+++"):
        return text, False
    end = text.find("\n+++", 3)
    if end == -1:
        return text, False
    fm = text[3:end]
    body = text[end + 4:]
    lines = fm.split("\n")
    out = []
    replaced = False
    for ln in lines:
        if re.match(r"^\s*authors\s*=", ln):
            out.append('authors = ["dreamfly"]')
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append('authors = ["dreamfly"]')
    return "+++" + "\n".join(out) + "\n+++" + body, True


def main():
    targets = glob.glob(os.path.join(POSTS, "*.md"))
    targets += [f for f in glob.glob(os.path.join(CONTENT, "*.md"))]
    count = 0
    for fp in targets:
        with open(fp, encoding="utf-8") as f:
            t = f.read()
        nt, changed = set_authors(t)
        if changed:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(nt)
            count += 1
    print(f"已统一作者为 dreamfly：{count} 个文件")


if __name__ == "__main__":
    main()
