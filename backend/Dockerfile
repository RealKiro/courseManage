# ============================================================
# 阶段1：构建 — Cython 编译关键模块
# ============================================================
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} --trusted-host ${PIP_TRUSTED_HOST} -r requirements.txt
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} --trusted-host ${PIP_TRUSTED_HOST} cython

COPY . .

RUN python setup_cython.py build_ext --inplace

RUN CRITICAL_MODULES="utils/license.py routers/license.py optimizer.py utils/smart_command.py utils/wechat_notifier.py utils/remainder.py" && \
    for f in $CRITICAL_MODULES; do \
        rm -f "$f" && rm -f "${f%.py}.c"; \
    done

RUN find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
RUN find . -type f -name "*.pyc" -delete 2>/dev/null || true
RUN rm -rf build/ setup_cython.py

# ============================================================
# 阶段2：运行 — 仅复制编译产物，不含源码和编译工具链
#
# 关于 Alpine：backend 刻意保留 slim(glibc)。psycopg2-binary 官方明确只发
# glibc 轮子，pandas / numpy 在 musl-aarch64 上轮子覆盖也不完整，换成
# Alpine 会退化为源码编译 —— arm64 构建时间与内存都不可接受。
# 体积优化改为：--no-install-recommends + 只保留一套中文字体。
# ============================================================
FROM python:3.11-slim-bookworm

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# fonts-wqy-microhei 供 reportlab 导出中文 PDF；postgresql-client 供数据库备份/恢复。
# schedules.py 的字体候选列表以 microhei 优先，因此不再安装体积相近的 zenhei。
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    fonts-wqy-microhei \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} --trusted-host ${PIP_TRUSTED_HOST} -r requirements.txt && \
    SP=/usr/local/lib/python3.11/site-packages && \
    # 站点包里的测试套件与字节码缓存对运行毫无用处（pandas/numpy 的 tests 就有数十 MB）
    find "$SP" -type d -name "tests" -prune -exec rm -rf {} + 2>/dev/null || true && \
    find "$SP" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true

COPY --from=builder /app/ .

RUN mkdir -p logs

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]