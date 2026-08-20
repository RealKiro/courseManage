# ============================================================
# courseManage 部署环境一键生成脚本（Windows PowerShell）
#
# 作用：
#   1. 自动探测 GHCR 镜像归属（IMAGE_OWNER）—— fork 本仓库后无需手改
#   2. 自动生成强随机的 POSTGRES_PASSWORD / SECRET_KEY / MCP_AUTH_TOKEN
#   3. 由 .env.example 生成 .env
#
# 用法（Windows PowerShell 5.1 与 PowerShell 7 均可）：
#   powershell -ExecutionPolicy Bypass -File scripts\setup-env.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup-env.ps1 -Owner myname
#   powershell -ExecutionPolicy Bypass -File scripts\setup-env.ps1 -Force
# ============================================================
[CmdletBinding()]
param(
    [string]$Owner = '',
    [switch]$Force,
    [string]$Output = '.env'
)

$ErrorActionPreference = 'Stop'

# 切换到仓库根目录（脚本可能从任意位置调用）
Set-Location (Join-Path $PSScriptRoot '..')
$RepoRoot = (Get-Location).Path

$ExampleFile = '.env.example'
if (-not (Test-Path -LiteralPath $ExampleFile)) {
    throw "找不到 $ExampleFile，请在仓库根目录运行本脚本"
}

# 相对路径按仓库根目录解析，绝对路径原样使用
if ([System.IO.Path]::IsPathRooted($Output)) {
    $OutputPath = $Output
} else {
    $OutputPath = Join-Path $RepoRoot $Output
}

if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
    throw "$Output 已存在。如需重新生成请加 -Force（会覆盖，请先备份！）"
}

# ---------- 1. 探测 IMAGE_OWNER ----------
if (-not $Owner) {
    $url = $null
    if (Get-Command git -ErrorAction SilentlyContinue) {
        try {
            $url = (& git config --get remote.origin.url 2>$null | Select-Object -First 1)
        } catch {
            $url = $null
        }
    }
    if ($url) {
        # 支持 https://github.com/OWNER/repo(.git) 与 git@github.com:OWNER/repo(.git)
        if ($url -match '[:/]([^/:]+)/([^/]+?)(\.git)?/?$') {
            $Owner = $Matches[1]
        }
    }
}
if (-not $Owner) {
    throw '无法从 git 远端探测归属，请用 -Owner <你的GitHub用户名> 指定'
}

# OCI 仓库名必须全小写
$Owner = $Owner.ToLowerInvariant()

# ---------- 2. 生成随机密钥 ----------
# 用 RandomNumberGenerator::Create()：.NET Framework 4.x（PS 5.1）与 .NET Core 都支持，
# 不能用 ::Fill()，那是 .NET Core 3.0+ 才有的静态方法。
function New-SecureBytes([int]$Count) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $buffer = New-Object 'byte[]' $Count
        $rng.GetBytes($buffer)
        return $buffer
    } finally {
        if ($rng -is [System.IDisposable]) { $rng.Dispose() }
    }
}

function New-RandomHex([int]$ByteCount) {
    $bytes = New-SecureBytes $ByteCount
    return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}

function New-RandomAlnum([int]$Length) {
    # 数据库密码只用字母数字，避免 @ : / 等字符破坏 DATABASE_URL
    $chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    # 取 4 倍随机字节并做拒绝采样，避免取模引入偏差
    $out = New-Object System.Text.StringBuilder
    while ($out.Length -lt $Length) {
        foreach ($b in (New-SecureBytes ($Length * 4))) {
            if ($out.Length -ge $Length) { break }
            if ($b -lt 248) { [void]$out.Append($chars[$b % $chars.Length]) }
        }
    }
    return $out.ToString()
}

$DbPassword = New-RandomAlnum 28
$SecretKey  = New-RandomHex 32
$McpToken   = New-RandomHex 24

# ---------- 3. 生成 .env ----------
# 刻意不用 switch：switch 里的 break 在 foreach 中的行为容易踩坑，改用 if/elseif
$result = New-Object System.Collections.Generic.List[string]
foreach ($line in (Get-Content -LiteralPath $ExampleFile -Encoding UTF8)) {
    if ($line -match '^IMAGE_OWNER=') {
        $result.Add("IMAGE_OWNER=$Owner")
    } elseif ($line -match '^POSTGRES_PASSWORD=') {
        $result.Add("POSTGRES_PASSWORD=$DbPassword")
    } elseif ($line -match '^SECRET_KEY=') {
        $result.Add("SECRET_KEY=$SecretKey")
    } elseif ($line -match '^MCP_AUTH_TOKEN=') {
        $result.Add("MCP_AUTH_TOKEN=$McpToken")
    } else {
        $result.Add($line)
    }
}

# 写 UTF-8 无 BOM：带 BOM 会让 docker compose 把第一个变量名读错
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($OutputPath, $result, $utf8NoBom)

Write-Host ""
Write-Host "已生成 $Output" -ForegroundColor Green
Write-Host ""
Write-Host "  IMAGE_OWNER        = $Owner"
Write-Host "  镜像地址           = ghcr.io/$Owner/coursemanage-{backend,frontend,mcp}"
Write-Host "  POSTGRES_PASSWORD  = （已随机生成 28 位）"
Write-Host "  SECRET_KEY         = （已随机生成 32 字节 hex）"
Write-Host "  MCP_AUTH_TOKEN     = （已随机生成 24 字节 hex）"
Write-Host ""
Write-Host "还需要你确认的项：" -ForegroundColor Yellow
Write-Host "  1. ALLOWED_ORIGINS  —— 有域名或固定 IP 时改成实际访问地址"
Write-Host "  2. FRONTEND_PORT / BACKEND_PORT —— 端口被占用时修改"
Write-Host "  3. MCP_API_USERNAME / MCP_API_PASSWORD —— 启用 MCP 时改成专用系统账号"
Write-Host ""
Write-Host "下一步："
Write-Host "  docker compose -f docker-compose.deploy.yml up -d"
Write-Host "  docker compose -f docker-compose.deploy.yml --profile mcp up -d"
Write-Host ""
Write-Host "注意：$Output 含明文密钥，请勿提交到版本库（.gitignore 已忽略）。" -ForegroundColor Red
