# -*- coding: utf-8 -*-
"""
WP 迁移内容清理：把文章里的 WP 编辑器 HTML 转成纯 Markdown。
- <pre class="brush:xxx"> ... </pre>  ->  ```xxx 围栏代码块（解码 HTML 实体、&nbsp; 还原为空格）
- <p>/<div>/<h1-6>/<ul>/<ol>/<blockquote>/<table>/<strong>/<em>/<a>/<code>/<img>/<br>/<hr> 等转 Markdown
- style/script/svg 内容丢弃；iframe/embed 保留原样；span/font/wbr 等只解包
用法: python clean_wp_html.py [--dry]
"""
import re, os, sys, html as htmllib
from html.parser import HTMLParser

DRY = '--dry' in sys.argv

DROP_CONTENT = {'style', 'script', 'svg', 'object', 'button', 'select', 'form'}
BLOCK_TAGS = {'p', 'div', 'section', 'article', 'figure', 'figcaption', 'center',
              'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'blockquote',
              'table', 'hr', 'li', 'dl', 'dt', 'dd'}

def fence_for(code: str) -> str:
    return '````' if '```' in code else '```'

def convert_pre(m: str) -> str:
    """把一个 <pre ...>...</pre> 转成围栏代码块"""
    attrs = m.group(1)
    body = m.group(2)
    lang = ''
    mm = re.search(r'brush:\s*(\w+)', attrs) or \
         re.search(r'(?:language|lang)-(\w+)', attrs) or \
         re.search(r'class="[^"]*\b(js|javascript|python|php|css|html|bash|shell|java|c|cpp|go|sql|json|xml|yaml)\b[^"]*"', attrs, re.I)
    if mm:
        lang = mm.group(1).lower()
        lang = {'js': 'javascript', 'shell': 'bash', 'html': 'html'}.get(lang, lang)
    code = htmllib.unescape(body)
    code = code.replace('\xa0', ' ')
    code = '\n'.join(line.rstrip() for line in code.split('\n'))
    # WP 存储常把每个换行翻倍（行间多出空行）。空白行占比高时判定为伪影，直接去掉空行；
    # 否则视为正常代码，仅把 3+ 连续空行压成 1 个空行。
    lines = [l for l in code.split('\n')]
    nonblank = sum(1 for l in lines if l.strip())
    blank = len(lines) - nonblank
    if nonblank and blank / max(nonblank, 1) > 0.15:
        code = '\n'.join(l for l in lines if l.strip())
    else:
        code = re.sub(r'\n{3,}', '\n\n', code)
    code = code.strip('\n')
    f = fence_for(code)
    return f"{f}{lang}\n{code}\n{f}"

PRE_RE = re.compile(r'<pre\b([^>]*)>(.*?)</pre>', re.S | re.I)
KEEP_RAW_RE = re.compile(r'(<iframe\b.*?</iframe>|<embed\b[^>]*/?>)', re.S | re.I)

class MDConverter(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []            # 已完成的块（每块为字符串，内部可含换行）
        self.buf = []            # 当前内联缓冲
        self.list_stack = []     # ['ul'|'ol', ...]
        self.ol_counters = []
        self.quote_depth = 0
        self.skip_depth = 0
        self.head_prefix = ''    # '### ' 等
        self.li_prefix = ''      # '- ' / '1. '（含缩进）
        # 表格状态
        self.in_table = 0
        self.rows = []
        self.row = None
        self.cell = None
        self.holders = None  # 占位内容列表，由 clean_body 注入

    # ---------- helpers ----------
    def emit_text(self, s: str):
        if self.skip_depth:
            return
        if self.in_table and self.cell is not None:
            self.cell.append(s)
        else:
            self.buf.append(s)

    def flush(self):
        text = ''.join(self.buf).strip()
        self.buf = []
        saved_head = self.head_prefix
        saved_li = self.li_prefix
        self.head_prefix = ''
        self.li_prefix = ''
        if not text:
            return
        # 关键：先把占位符展开成真实内容（可能是多行代码块），
        # 再对每一行统一加前缀（引用块 > 、列表项 - ）。否则多行代码块只有首行拿到前缀。
        if self.holders:
            text = re.sub(r'\x00H(\d+)\x00', lambda m: self.holders[int(m.group(1))], text)
        quote_prefix = '> ' * self.quote_depth if self.quote_depth else ''
        out_lines = []
        for i, l in enumerate(text.split('\n')):
            if quote_prefix:
                l = quote_prefix + l
            if i == 0:
                if saved_head:
                    l = saved_head + l
                if saved_li:
                    l = saved_li + l
            out_lines.append(l)
        self.out.append('\n'.join(out_lines))

    def block_boundary(self):
        self.flush()
        if self.out and self.out[-1] != '':
            self.out.append('')

    # ---------- parser events ----------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in DROP_CONTENT:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == 'table':
            self.flush()
            self.in_table += 1
            self.rows = []
            return
        if self.in_table:
            if tag == 'tr':
                self.row = []
            elif tag in ('td', 'th'):
                self.cell = []
            return
        ad = dict(attrs)
        if tag == 'br':
            self.emit_text('\n')
        elif tag == 'hr':
            self.block_boundary(); self.out.append('---'); self.out.append('')
        elif tag == 'img':
            src = ad.get('src', ''); alt = ad.get('alt', '')
            if src:
                self.emit_text(f'![{alt}]({src})')
        elif tag == 'a':
            self.emit_text('[')
            self.a_stack = getattr(self, 'a_stack', [])
            self.a_stack.append(ad.get('href', ''))
        elif tag in ('strong', 'b'):
            self.emit_text('**')
        elif tag in ('em', 'i', 'var'):
            self.emit_text('*')
        elif tag == 'code':
            self.emit_text('`')
        elif tag in BLOCK_TAGS:
            self.flush()
            if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                self.head_prefix = '#' * int(tag[1]) + ' '
            elif tag in ('ul', 'ol'):
                self.list_stack.append(tag)
                self.ol_counters.append(0)
            elif tag == 'li':
                if not self.list_stack:
                    self.list_stack = ['ul']; self.ol_counters = [0]
                kind = self.list_stack[-1]
                ind = '  ' * (len(self.list_stack) - 1)
                if kind == 'ol':
                    self.ol_counters[-1] += 1
                    self.li_prefix = f'{ind}{self.ol_counters[-1]}. '
                else:
                    self.li_prefix = f'{ind}- '
            elif tag == 'blockquote':
                self.block_boundary()
                self.quote_depth += 1
        # span / font / center / section / wbr / figure 等：解包，不处理

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP_CONTENT:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == 'table':
            self.flush()
            self.in_table = max(0, self.in_table - 1)
            self.emit_table()
            return
        if self.in_table:
            if tag in ('td', 'th'):
                if self.cell is not None and self.row is not None:
                    self.row.append(''.join(self.cell).strip().replace('\n', ' '))
                self.cell = None
            elif tag == 'tr':
                if self.row is not None:
                    self.rows.append(self.row)
                self.row = None
            return
        if tag == 'a':
            self.a_stack = getattr(self, 'a_stack', [''])
            href = self.a_stack.pop() if self.a_stack else ''
            self.emit_text(f']({href})' if href else ']')
        elif tag in ('strong', 'b'):
            self.emit_text('**')
        elif tag in ('em', 'i', 'var'):
            self.emit_text('*')
        elif tag == 'code':
            self.emit_text('`')
        elif tag in BLOCK_TAGS:
            if tag in ('ul', 'ol'):
                self.flush()
                if self.list_stack: self.list_stack.pop()
                if self.ol_counters: self.ol_counters.pop()
            elif tag == 'li':
                self.flush()
            elif tag == 'blockquote':
                self.flush()
                self.quote_depth = max(0, self.quote_depth - 1)
            else:
                self.block_boundary()

    def emit_table(self):
        if not self.rows:
            return
        ncol = max(len(r) for r in self.rows)
        for r in self.rows:
            r += [''] * (ncol - len(r))
        head, *body = self.rows
        lines = ['| ' + ' | '.join(head) + ' |',
                 '| ' + ' | '.join(['---'] * ncol) + ' |']
        for r in body:
            lines.append('| ' + ' | '.join(c.replace('|', '\\|') for c in r) + ' |')
        self.out.append('\n'.join(lines))
        self.out.append('')

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.emit_text(data)

    def handle_entityref(self, name):
        self.emit_text(htmllib.unescape(f'&{name};'))

    def handle_charref(self, name):
        self.emit_text(htmllib.unescape(f'&#{name};'))

    def result(self) -> str:
        self.flush()
        text = '\n'.join(self.out)
        text = re.sub(r'\n{3,}', '\n\n', text).strip('\n')
        return text

# 已存在的围栏代码块（含 <?php、< 比较符等），先整块抽出保护，避免被 HTML 解析器二次破坏
FENCE_RE = re.compile(r'```(?:[^\n]*\n)?([\s\S]*?)```', re.S)

def clean_body(body: str) -> str:
    # 0. 先抽出已有围栏代码块，原样保护（保证脚本可重复运行 / 幂等）
    holders = []

    def stash(s: str) -> str:
        holders.append(s)
        return f'\x00H{len(holders)-1}\x00'

    body = FENCE_RE.sub(lambda m: stash(m.group(0)), body)
    # 1. 摘出 pre / iframe / embed
    body = PRE_RE.sub(lambda m: stash(convert_pre(m)), body)
    body = KEEP_RAW_RE.sub(lambda m: stash(m.group(1)), body)

    # 2. 解析其余 HTML（holders 注入解析器，flush 时展开占位符并逐行加前缀）
    p = MDConverter()
    p.holders = holders
    p.feed(body)
    p.close()
    text = p.result()

    # 3. 兜底：放回仍残留的占位内容（如表格单元格内的占位）
    text = re.sub(r'\x00H(\d+)\x00', lambda m: holders[int(m.group(1))], text)
    # 清理残留空占位（如未闭合标签导致的丢失）
    text = re.sub(r'\x00H\d+\x00', '', text)
    # 4. 转义代码块「之外」的危险原始标签（<script>/<style>/<iframe>/<?php 等）。
    #    这些来自 WP 用 <blockquote> 包裹、且源码已 HTML 转义的代码示例；
    #    若不转义，Goldmark 会当成真实标签执行/破坏 minify。代码块内部已由 Goldmark 自行转义，跳过。
    text = escape_danger_outside_fences(text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip('\n') + '\n'
    return text


# 需要被转义为纯文本展示（而非执行）的危险标签 / 指令
_DANGER = re.compile(r'</?(?:script|style|iframe|object|embed|frame|frameset|link|meta)\b|<\?php|<\?=|<\?|<!\[CDATA')

def escape_danger_outside_fences(text: str) -> str:
    parts = re.split(r'(```)', text)
    out = []
    in_fence = False
    for part in parts:
        if part == '```':
            in_fence = not in_fence
            out.append(part)
            continue
        if in_fence:
            out.append(part)
        else:
            out.append(_DANGER.sub(lambda m: m.group(0).replace('<', '&lt;'), part))
    return ''.join(out)


SPLIT_RE = re.compile(r'^\+\+\+\s*$(.*?)^\+\+\+\s*$', re.S | re.M)

def process_file(path: str) -> bool:
    raw = open(path, encoding='utf-8').read()
    m = SPLIT_RE.match(raw)
    if not m:
        body = raw
        fm = ''
    else:
        fm = raw[:m.end()]
        body = raw[m.end():]
    if '<' not in body:
        return False
    new = fm + '\n' + clean_body(body)
    if not DRY:
        open(path, 'w', encoding='utf-8', newline='\n').write(new)
    return True

def main():
    changed = 0
    targets = []
    root = 'content'
    for dirpath, dirs, files in os.walk(root):
        for f in files:
            if f.endswith('.md'):
                targets.append(os.path.join(dirpath, f))
    for path in targets:
        if process_file(path):
            changed += 1
    print(f'processed {changed}/{len(targets)} files' + (' (dry run)' if DRY else ''))

if __name__ == '__main__':
    main()
