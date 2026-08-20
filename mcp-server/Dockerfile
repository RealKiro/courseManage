# ============================================================
# courseManage MCP 服务器镜像（Alpine，最终镜像约 60-70MB）
#
# 为什么 MCP 可以用 Alpine 而 backend 不行：
#   本服务的依赖（mcp / httpx / uvicorn / pydantic）只有 pydantic-core 与
#   rpds-py 两个二进制扩展，二者都提供 musllinux wheel，纯 Rust 静态链接；
#   backend 依赖的 psycopg2-binary / pandas / numpy 在 musl 上缺少可靠 wheel，
#   改 Alpine 会退化成源码编译（arm64 尤其致命），因此 backend 保持 slim。
#
# builder 阶段仍装 build-base：万一某个依赖临时缺 musl wheel 也能就地编译，
# 编译产物同 libc，拷到运行阶段可直接使用，而工具链不进入最终镜像。
# ============================================================
FROM python:3.12-alpine AS builder

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apk add --no-cache build-base libffi-dev

COPY requirements.txt ./
RUN pip install --prefix=/install -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" \
        -r requirements.txt \
    # 依赖自带的测试/文档/类型桩对运行毫无用处，直接清掉
    && find /install -type d -name "__pycache__" -prune -exec rm -rf {} + \
    && find /install -type d -name "tests" -prune -exec rm -rf {} + \
    && find /install -name "*.pyi" -delete

# ------------------------------------------------------------
FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

# 只留下 Asia/Shanghai 一个时区文件，装完 tzdata 立刻卸载，省约 3MB
RUN apk add --no-cache tzdata \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apk del tzdata

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ ./src/
COPY pyproject.toml README.md ./

# 非 root 运行（Alpine 用 busybox adduser，没有 useradd）
RUN adduser -D -u 10001 mcp \
    && chown -R mcp:mcp /app
USER mcp

# 默认以 Streamable HTTP 方式对外提供服务，方便 AstrBot 等远程接入
ENV COURSEMANAGE_MCP_TRANSPORT=http \
    COURSEMANAGE_MCP_HOST=0.0.0.0 \
    COURSEMANAGE_MCP_PORT=8765 \
    COURSEMANAGE_MCP_PATH=/mcp \
    COURSEMANAGE_API_BASE=http://backend:8000

EXPOSE 8765

# /healthz 由 GatewayMiddleware 提供，不需要访问令牌
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null "http://127.0.0.1:${COURSEMANAGE_MCP_PORT}/healthz" || exit 1

ENTRYPOINT ["python", "-m", "coursemanage_mcp"]
