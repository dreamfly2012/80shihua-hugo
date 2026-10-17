# preview-post.ps1 —— 供 find-post.ps1 的 fzf 预览调用
# 用法: powershell -NoProfile -ExecutionPolicy Bypass -File preview-post.ps1 <postsDir> <filename>
# 以纯 UTF-8 字节写 stdout，避免 Windows 控制台编码乱码。

[CmdletBinding()]
param(
    [string]$PostsDir,
    [string]$FileName
)

$ErrorActionPreference = 'Stop'

if (-not $PostsDir -or -not $FileName) {
    exit 0
}

$path = Join-Path $PostsDir $FileName
if (-not (Test-Path -LiteralPath $path)) {
    exit 0
}

# 读文件（UTF-8）
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)

# 直接以 UTF-8 字节写 stdout，绕开控制台编码
$utf8 = New-Object System.Text.UTF8Encoding($false)
$stdout = [System.Console]::OpenStandardOutput()
$writer = New-Object System.IO.StreamWriter($stdout, $utf8)
$writer.Write($content)
$writer.Flush()
$stdout.Flush()

