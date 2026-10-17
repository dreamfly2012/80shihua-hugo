#!/usr/bin/env bash
# find-post.sh —— 在 content/posts 下交互式查找文章（标题 / ID / 正文 都能搜）
#
# 用法：
#   ./find-post.sh            交互式查找，选中后打印完整路径（默认）
#   ./find-post.sh -o         选中后直接用 $EDITOR（或 code）打开
#
# 说明：文章文件名是 WP 数字 ID，光看文件名搜不到。本脚本把
#       "文件名<TAB>标题<TAB>正文片段" 拼成一行交给 fzf：
#         - 显示列：文件名 + 标题（--with-nth=1,2）
#         - 匹配列：文件名 + 标题 + 正文（--nth=1,2,3），所以正文里的词也能命中
#       右侧 --preview 实时预览选中文章的真实文件。
#       标题解析兼容 TOML(title = "x") 与 YAML(title: 'x') 两种 front matter；
#       正文自动跳过 +++/--- 包裹的 front matter，并压成单行、截到前 4000 字符。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POSTS="$ROOT/content/posts"

OPEN=0
for arg in "$@"; do
  case "$arg" in
    -o|--open) OPEN=1 ;;
  esac
done

# 单次 awk 扫描全部文章（shell 通配符展开，路径为正斜杠），输出 "文件名<TAB>标题<TAB>正文片段"
list_posts() {
  awk -v MAX=4000 -- "$POSTS"/*.md '
    function basename(p){ sub(/.*[\/\\]/, "", p); return p }
    function flush(){
      if (seen) printf "%s\t%s\t%s\n", basename(fn), (t=="" ? "（无标题）" : t), substr(b, 1, MAX)
      t=""; b=""; started=0; fm=0; seen=0
    }
    FNR==1 { if (seen) flush(); fn=FILENAME; seen=1 }
    /^(\+\+\+|---)$/ { if (!started){ started=1; next } else { fm=1; next } }
    fm==1 { gsub(/\t/, " "); b = b $0 " " }
    /^[[:space:]]*title[[:space:]]*[:=]/ && t=="" {
      line=$0
      sub(/^[[:space:]]*title[[:space:]]*[:=][[:space:]]*/, "", line)
      sub(/^["\047]/, "", line)
      sub(/["\047]?[,]?$/, "", line)
      t=line
    }
    END { if (seen) flush() }
  '
}

choice="$(list_posts | fzf \
  --delimiter='\t' \
  --nth=1,2,3 \
  --with-nth=1,2 \
  --prompt='找文章(标题/ID/正文)> ' \
  --preview="bat --color=always --style=plain \"$POSTS/{1}\" 2>/dev/null || cat \"$POSTS/{1}\"" \
  --preview-window='right:60%:wrap')" || true

[ -z "$choice" ] && exit 0

name="$(printf '%s' "$choice" | cut -f1)"
path="$POSTS/$name"

if [ "$OPEN" -eq 1 ]; then
  if [ -n "${EDITOR:-}" ]; then
    "$EDITOR" "$path"
  elif command -v code >/dev/null 2>&1; then
    code "$path"
  else
    echo "$path"
  fi
else
  echo "$path"
fi
