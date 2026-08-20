#!/usr/bin/env bash
# ============================================================
# courseManage 部署环境一键生成脚本（Linux / macOS / NAS）
#
# 作用：
#   1. 自动探测 GHCR 镜像归属（IMAGE_OWNER）—— fork 本仓库后无需手改
#   2. 自动生成强随机的 POSTGRES_PASSWORD / SECRET_KEY / MCP_AUTH_TOKEN
#   3. 由 .env.example 生成 .env
#
# 用法：
#   bash scripts/setup-env.sh                    # 自动探测归属
#   bash scripts/setup-env.sh --owner myname     # 手动指定 GHCR 归属
#   bash scripts/setup-env.sh --force            # 覆盖已存在的 .env
# ============================================================
set -euo pipefail

OWNER=""
FORCE=0
ENV_FILE=".env"
EXAMPLE_FILE=".env.example"

usage() {
    cat <<'USAGE'
用法：bash scripts/setup-env.sh [选项]

  --owner <名字>   指定 GHCR 镜像归属（默认从 git 远端自动探测）
  --output <路径>  输出文件，默认 .env
  --force          覆盖已存在的输出文件
  -h, --help       显示本帮助

生成的 .env 会自动填好 IMAGE_OWNER，并随机生成
POSTGRES_PASSWORD / SECRET_KEY / MCP_AUTH_TOKEN。
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --owner)
            [ $# -ge 2 ] || { echo "✗ --owner 缺少参数值" >&2; exit 2; }
            OWNER="$2"; shift 2 ;;
        --output)
            [ $# -ge 2 ] || { echo "✗ --output 缺少参数值" >&2; exit 2; }
            ENV_FILE="$2"; shift 2 ;;
        --force) FORCE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "✗ 未知参数：$1（用 --help 查看用法）" >&2; exit 2 ;;
    esac
done

# 切换到仓库根目录（脚本可能从任意位置调用）
cd "$(dirname "$0")/.."

if [ ! -f "${EXAMPLE_FILE}" ]; then
    echo "✗ 找不到 ${EXAMPLE_FILE}，请确认脚本位于仓库的 scripts/ 目录下" >&2
    exit 1
fi

if [ -e "${ENV_FILE}" ] && [ "${FORCE}" -ne 1 ]; then
    echo "✗ ${ENV_FILE} 已存在。如需重新生成请加 --force（会覆盖，请先备份！）" >&2
    exit 1
fi

# ---------- 1. 探测 IMAGE_OWNER ----------
detect_owner() {
    local url
    url="$(git config --get remote.origin.url 2>/dev/null || true)"
    [ -n "${url}" ] || return 0
    # 同时支持 https://github.com/OWNER/repo(.git) 与 git@github.com:OWNER/repo(.git)
    printf '%s' "${url}" \
        | sed -E 's#^[A-Za-z0-9._-]+@[^:]+:#https://placeholder/#' \
        | sed -E 's#^[A-Za-z][A-Za-z0-9+.-]*://[^/]+/##' \
        | cut -d'/' -f1
}

if [ -z "${OWNER}" ]; then
    OWNER="$(detect_owner)"
fi

if [ -z "${OWNER}" ]; then
    echo "✗ 无法从 git 远端探测归属。" >&2
    echo "  若只下载了部署文件而没有克隆仓库，请手动指定：" >&2
    echo "  bash scripts/setup-env.sh --owner <你的GitHub用户名>" >&2
    exit 1
fi

# OCI 仓库名必须全小写
OWNER="$(printf '%s' "${OWNER}" | tr '[:upper:]' '[:lower:]')"

# ---------- 2. 生成随机密钥 ----------
# 注意：刻意不用 `tr < /dev/urandom | head -c N`。head 提前关闭管道会让 tr 收到
# SIGPIPE，在 `set -o pipefail` 下整条管道返回 141，进而被 set -e 判定为失败而中断。
# 这里改成每次读固定长度再过滤，读取端总会读完，不会产生 SIGPIPE。

rand_hex() {
    local bytes="$1"
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex "${bytes}"
        return 0
    fi
    # 退回 /dev/urandom + od（busybox 也自带 od），输出恰好 bytes*2 个 hex 字符
    dd if=/dev/urandom bs=1 count="${bytes}" 2>/dev/null | od -An -tx1 | LC_ALL=C tr -d ' \n'
    printf '\n'
}

rand_alnum() {
    local want="$1" out="" chunk=""
    while [ "${#out}" -lt "${want}" ]; do
        chunk="$(dd if=/dev/urandom bs=256 count=1 2>/dev/null | LC_ALL=C tr -dc 'A-Za-z0-9' || true)"
        out="${out}${chunk}"
    done
    printf '%s' "${out:0:want}"
}

DB_PASSWORD="$(rand_alnum 28)"
SECRET_KEY="$(rand_hex 32)"
MCP_TOKEN="$(rand_hex 24)"

for pair in "DB_PASSWORD:${DB_PASSWORD}" "SECRET_KEY:${SECRET_KEY}" "MCP_TOKEN:${MCP_TOKEN}"; do
    if [ -z "${pair#*:}" ]; then
        echo "✗ 随机密钥生成失败（${pair%%:*}）。请确认系统提供 /dev/urandom 或 openssl。" >&2
        exit 1
    fi
done

# ---------- 3. 生成 .env ----------
# 用 awk 逐行替换：sed 的分隔符容易和随机串里的字符冲突
awk -v owner="${OWNER}" \
    -v dbpw="${DB_PASSWORD}" \
    -v secret="${SECRET_KEY}" \
    -v mcptoken="${MCP_TOKEN}" '
    /^IMAGE_OWNER=/       { print "IMAGE_OWNER=" owner;       next }
    /^POSTGRES_PASSWORD=/ { print "POSTGRES_PASSWORD=" dbpw;  next }
    /^SECRET_KEY=/        { print "SECRET_KEY=" secret;       next }
    /^MCP_AUTH_TOKEN=/    { print "MCP_AUTH_TOKEN=" mcptoken; next }
    { print }
' "${EXAMPLE_FILE}" > "${ENV_FILE}"

chmod 600 "${ENV_FILE}" 2>/dev/null || true

cat <<EOF

✓ 已生成 ${ENV_FILE}

  IMAGE_OWNER        = ${OWNER}
  镜像地址           = ghcr.io/${OWNER}/coursemanage-{backend,frontend,mcp}
  POSTGRES_PASSWORD  = （已随机生成 28 位字母数字）
  SECRET_KEY         = （已随机生成 32 字节 hex）
  MCP_AUTH_TOKEN     = （已随机生成 24 字节 hex）

还需要你确认的项：
  1. ALLOWED_ORIGINS  —— 有域名或固定 IP 时改成实际访问地址
  2. FRONTEND_PORT / BACKEND_PORT —— 端口被占用时修改
  3. MCP_API_USERNAME / MCP_API_PASSWORD —— 启用 MCP 时改成专用系统账号

下一步：
  docker compose -f docker-compose.deploy.yml up -d                 # 主服务
  docker compose -f docker-compose.deploy.yml --profile mcp up -d   # 额外启用 MCP

⚠️  ${ENV_FILE} 含明文密钥，请勿提交到版本库（.gitignore 已忽略）。
EOF
