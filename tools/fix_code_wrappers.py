#!/usr/bin/env python3
"""
Strip redundant WordPress-migration `<code class="language-X">...</code>` wrappers
that sit INSIDE fenced code blocks, and hoist the language onto the fence info
string so syntax highlighting still works.

Before:
    ```
    <code class="language-php"><?php
    echo 1;</code>
    ```
After:
    ```php
    <?php
    echo 1;
    ```

Usage:
    python fix_code_wrappers.py            # dry-run (report only)
    python fix_code_wrappers.py --apply    # write files
"""
import os
import sys
import glob
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, "content", "posts")

import re

CODE_OPEN = re.compile(r"<code(?:\s+[^>]*)?>", re.I)
CODE_CLOSE = re.compile(r"</code\s*>", re.I)
LANG_RE = re.compile(r'<code\s+class="language-([^"]+)"', re.I)

# Chroma (Hugo) lexer aliases for languages used in this blog
LANG_MAP = {
    "js": "javascript",
    "golang": "go",
    "mysql": "sql",
    "c#": "csharp",
    "c++": "cpp",
    "shell": "bash",
    "sh": "bash",
}


def clean_body(body, lang):
    """Remove code tags from a fenced block body; return (new_body, new_lang)."""
    if "<code" not in body and "</code>" not in body:
        return body, lang
    m = LANG_RE.search(body)
    if m and not lang:
        raw = m.group(1).strip().lower()
        lang = LANG_MAP.get(raw, raw)
    new = CODE_OPEN.sub("", body)
    new = CODE_CLOSE.sub("", new)
    new = new.strip("\n")
    return new, lang


def process_file(path, apply=False):
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    lines = txt.split("\n")
    out = []
    cur = None          # lines inside the current fence
    cur_lang = ""
    fence_prefix = ""
    changes = 0
    for ln in lines:
        stripped = ln.lstrip()
        if stripped.startswith("```"):
            if cur is None:
                fence_prefix = ln[: len(ln) - len(stripped)]
                cur = []
                cur_lang = stripped[3:].strip()
            else:
                body = "\n".join(cur)
                new_body, new_lang = clean_body(body, cur_lang)
                if new_body != body or new_lang != cur_lang:
                    changes += 1
                out.append(fence_prefix + "```" + new_lang)
                if new_body:
                    out.extend(new_body.split("\n"))
                out.append(fence_prefix + "```")
                cur = None
                cur_lang = ""
        else:
            if cur is not None:
                cur.append(ln)
            else:
                out.append(ln)
    if cur is not None:  # unclosed fence -> flush with cleanup, flag it
        body = "\n".join(cur)
        new_body, new_lang = clean_body(body, cur_lang)
        if new_body != body:
            changes += 1
        out.append(fence_prefix + "```" + new_lang)
        if new_body:
            out.extend(new_body.split("\n"))
        out.append(fence_prefix + "```")

    new_txt = "\n".join(out)
    if changes and apply:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_txt)
    return changes, new_txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.md")))
    total_files = 0
    total_blocks = 0
    samples = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        if "<code" not in txt:
            continue
        changes, new_txt = process_file(path, apply=args.apply)
        if changes:
            total_files += 1
            total_blocks += changes
            if len(samples) < 2:
                samples.append((os.path.basename(path), new_txt))
    print(f"{'[APPLIED]' if args.apply else '[DRY-RUN]'} files changed: {total_files}, "
          f"code blocks fixed: {total_blocks}")
    for name, txt in samples:
        print(f"\n===== sample after: {name} =====")
        print(txt[:900])


if __name__ == "__main__":
    main()
