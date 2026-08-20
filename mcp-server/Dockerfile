# ============================================================
# courseManage MCP 服务器镜像
# 多阶段构建：wheel 在 builder 里装好，运行镜像只带站点包 + 源码
# ============================================================
FROM python:3.12-slim AS builder

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org

WORKDIR /build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN pip install --prefix=/install -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" \
        -r requirements.txt

# ------------------------------------------------------------
FROM python:3.12-slim

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ ./src/
COPY pyproject.toml README.md ./

# 非 root 运行
RUN useradd --create-home --shell /usr/sbin/nologin mcp \
    && chown -R mcp:mcp /app
USER mcp

# 默认以 Streamable HTTP 方式对外提供服务，方便 AstrBot 等远程接入
ENV COURSEMANAGE_MCP_TRANSPORT=http \
    COURSEMANAGE_MCP_HOST=0.0.0.0 \
    COURSEMANAGE_MCP_PORT=8765 \
    COURSEMANAGE_MCP_PATH=/mcp \
    COURSEMANAGE_API_BASE=http://backend:8000

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os,sys; \
port=os.getenv('COURSEMANAGE_MCP_PORT','8765'); \
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=4).status==200 else 1)"

ENTRYPOINT ["python", "-m", "coursemanage_mcp"]
