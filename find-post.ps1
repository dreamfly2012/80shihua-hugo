# find-post.ps1 —— 在 content/posts 下交互式查找文章（标题 / ID / 正文 都能搜）
#
# 用法（在 PowerShell 中）：
#   .\find-post.ps1               交互式查找，选中后打印完整路径
#   .\find-post.ps1 -Open         选中后用 $env:EDITOR 或 code 打开
#   .\find-post.ps1 -BuildList    仅输出 "文件名<TAB>标题<TAB>正文片段" 列表（不进 fzf），用于核查
#
# 说明：文章文件名是 WP 数字 ID，光看文件名搜不到。本脚本把
#       "文件名<TAB>标题<TAB>正文片段" 拼成一行交给 fzf：
#         - 显示列：文件名 + 标题（--with-nth=1,2）
#         - 匹配列：文件名 + 标题 + 正文（--nth=1,2,3），所以正文里的词也能命中
#       右侧预览实时显示选中文章的真实内容（强制 UTF-8，避免 Windows 控制台乱码）。
#       标题解析兼容 TOML(title = "x") 与 YAML(title: 'x') 两种 front matter。

[CmdletBinding()]
param(
    [switch]$Open,
    [switch]$BuildList
)

$ErrorActionPreference = 'Stop'

# 仓库根目录 = 脚本所在目录（不依赖当前工作目录）
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$postsDir = Join-Path (Join-Path $repoRoot 'content') 'posts'

if (-not (Test-Path $postsDir)) {
    Write-Error "找不到文章目录: $postsDir"
    exit 1
}

# 提取 front matter 标题（兼容 TOML title = "x" 与 YAML title: 'x'）
function Get-Title {
    param([string]$Text)
    if ($Text -match '(?m)^\s*title\s*[:=]\s*(.*)$') {
        $t = $Matches[1] -replace '^["'']' -replace '["'']?[,]?$'
        return $t.Trim()
    }
    return '（无标题）'
}

# 提取正文：去掉 +++ / --- 包裹的 front matter，压成单行，截前 4000 字
function Get-Body {
    param([string]$Text)
    $body = $null
    if ($Text -match '(?s)(\+\+\+|---)\r?\n.*?\r?\n(\+\+\+|---)\r?\n(.*)$') {
        $body = $Matches[3]
    } else {
        $body = $Text
    }
    $body = $body -replace "`r?`n", ' '
    $body = $body -replace "`t", ' '
    if ($body.Length -gt 4000) { $body = $body.Substring(0, 4000) }
    return $body
}

# 构建列表
$lines = [System.Collections.Generic.List[string]]::new()
foreach ($file in Get-ChildItem -Path $postsDir -Filter *.md -File) {
    $text  = Get-Content -LiteralPath $file.FullName -Encoding UTF8 -Raw
    $name  = $file.Name
    $title = Get-Title $text
    $body  = Get-Body $text
    $lines.Add("$name`t$title`t$body")
}

if ($BuildList) {
    $lines | ForEach-Object { $_ }
    exit 0
}

if (-not (Get-Command fzf -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 fzf，请先安装：scoop install fzf"
    exit 1
}

# 写入临时文件（UTF-8 无 BOM），再喂给 fzf，避开 PowerShell 管道编码的坑
$tmp = [System.IO.Path]::GetTempFileName()
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($tmp, $lines, $utf8NoBom)

# 让 PowerShell 以 UTF-8 与 fzf 通信
$OutputEncoding = [System.Text.Encoding]::UTF8

# 预览命令：调用独立的 preview-post.ps1（避免内联 [System.Text...] 触发 PowerShell
# 对传统命令行解析的回退，从而把 --preview 参数按空格拆碎丢给 fzf 报 unknown option）。
$previewScript = Join-Path $repoRoot 'preview-post.ps1'
$preview = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$previewScript`" `"$postsDir`" {1}"

try {
    # 用数组传参，避免 --preview=xxx 拼接带来的解析问题
    $fzfArgs = @(
        '--delimiter', "`t",
        '--nth', '1,2,3',
        '--with-nth', '1,2',
        '--prompt', 'find-post > ',
        '--preview', $preview,
        '--preview-window', 'right:60%:wrap'
    )
    $choice = Get-Content -LiteralPath $tmp -Encoding UTF8 | fzf @fzfArgs
} finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}

if (-not $choice) { exit 0 }

$selectedName = ($choice -split "`t")[0]
$selectedPath = Join-Path $postsDir $selectedName

if ($Open) {
    if ($env:EDITOR) {
        & $env:EDITOR $selectedPath
    } elseif (Get-Command code -ErrorAction SilentlyContinue) {
        code $selectedPath
    } else {
        Write-Output $selectedPath
    }
} else {
    Write-Output $selectedPath
}



