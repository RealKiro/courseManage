# MCP 服务器接入指南

> 让 AstrBot 等第三方框架直接「操作」courseManage

courseManage 内置了一个 **MCP（Model Context Protocol）服务器**，把排课、
学员、导师、课费、成绩、统计等能力封装成标准工具。任何支持 MCP 的框架
（AstrBot、Claude Desktop、Cherry Studio、Dify、Cline、Continue…）接上之后，
大模型就能自主调用这些工具，用自然语言完成日常课务。

- 镜像：`ghcr.io/<你的用户名小写>/coursemanage-mcp:latest`（`linux/amd64` + `linux/arm64`）
- 源码：[`mcp-server/`](../mcp-server)
- 工具与环境变量清单：[`mcp-server/README.md`](../mcp-server/README.md)

---

## 目录

1. [架构与端口](#1-架构与端口)
2. [第一步：启动 MCP 服务器](#2-第一步启动-mcp-服务器)
3. [第二步：验证端点可用](#3-第二步验证端点可用)
4. [第三步：接入 AstrBot](#4-第三步接入-astrbot)
5. [接入其它框架](#5-接入其它框架)
6. [安全建议（必读）](#6-安全建议必读)
7. [能做什么：对话示例](#7-能做什么对话示例)
8. [常见问题排查](#8-常见问题排查)

---

## 1. 架构与端口

```
┌──────────────┐   MCP over Streamable HTTP    ┌────────────────────┐
│   AstrBot    │ ────────────────────────────► │ coursemanage-mcp   │
│ (QQ/微信/TG) │   Authorization: Bearer ***    │   :8765/mcp        │
└──────────────┘                                └─────────┬──────────┘
                                                          │ REST + JWT
                                                          ▼
                                       ┌────────────────────────────┐
                                       │ coursemanage-backend :8000 │
                                       └─────────────┬──────────────┘
                                                     ▼
                                              PostgreSQL
```

| 组件 | 容器名 | 默认端口 | 说明 |
| --- | --- | --- | --- |
| 前端 | `coursemanage-frontend` | `18080` | Web 界面 |
| 后端 | `coursemanage-backend` | `35000`（仅本机） | REST API |
| MCP | `coursemanage-mcp` | `8765`（默认仅本机） | MCP 端点 `/mcp` |

MCP 容器通过 Docker 网络别名 `backend:8000` 直连后端，**不经过宿主机端口**，
所以后端保持只监听 `127.0.0.1` 也没问题。

---

## 2. 第一步：启动 MCP 服务器

MCP 是**可选组件**，用 Compose profile 控制，不启用时完全不影响现有部署。

### 2.1 修改 `.env`

```bash
# ---- MCP 调用后端使用的系统账号 ----
# 建议在「系统管理 → 用户管理」新建一个专用账号，按最小权限授予角色
MCP_API_USERNAME=mcp-bot
MCP_API_PASSWORD=换成你设置的强密码

# ---- 客户端访问令牌（★强烈建议设置）----
# 生成：openssl rand -hex 24
# Windows PowerShell：-join ((48..57)+(97..102) | Get-Random -Count 48 | % {[char]$_})
MCP_AUTH_TOKEN=1f3c8a90b2e74d56af01c8d3e5b7920a4c6d8e1f

# ---- 监听地址 ----
# AstrBot 在同一台机器的另一个容器里 → 改成 0.0.0.0
# AstrBot 在别的机器上           → 改成 0.0.0.0，并只在内网开放该端口
MCP_BIND_HOST=0.0.0.0
MCP_PORT=8765

# ---- 首次接入建议先开只读，确认稳定后再放开写操作 ----
MCP_READONLY=true
MCP_ALLOW_NOTIFICATIONS=false
```

### 2.2 启动

```bash
# 生产部署（拉取预构建镜像）
docker compose -f docker-compose.deploy.yml --profile mcp up -d

# 本地构建部署
docker compose --profile mcp up -d --build
```

### 2.3 看日志确认

```bash
docker compose -f docker-compose.deploy.yml logs -f mcp
```

正常输出类似：

```
courseManage MCP 1.0.0 启动：api_base=http://backend:8000 transport=http 模式=只读 认证=账号 mcp-bot 客户端鉴权=已启用 max_items=50
MCP 端点：http://0.0.0.0:8765/mcp（健康检查 /healthz）
```

> 关闭 MCP：`docker compose -f docker-compose.deploy.yml --profile mcp down`
> （不带 `--profile mcp` 的 `down` 不会动 MCP 容器）

---

## 3. 第二步：验证端点可用

```bash
# 健康检查（不需要令牌）
curl http://127.0.0.1:8765/healthz
# {"status":"ok","version":"1.0.0"}

# 列出工具（标准 MCP JSON-RPC 调用）
curl -sS http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

也可以直接进容器自检（不连网络、只看工具是否注册齐全）：

```bash
docker exec coursemanage-mcp python -m coursemanage_mcp --list-tools
```

---

## 4. 第三步：接入 AstrBot

AstrBot 的 MCP 配置入口：**WebUI → 工具 / MCP → 添加 MCP 服务器**
（不同版本菜单名略有差异，也可能在「配置 → 服务提供商 → MCP」下）。

### 4.1 远程接入（推荐）

在「添加 MCP 服务器」里粘贴：

```json
{
  "mcpServers": {
    "coursemanage": {
      "transport": "streamable_http",
      "url": "http://192.168.1.100:8765/mcp",
      "headers": {
        "Authorization": "Bearer 1f3c8a90b2e74d56af01c8d3e5b7920a4c6d8e1f"
      },
      "timeout": 30
    }
  }
}
```

要点：

- `192.168.1.100` 换成运行 courseManage 的机器 IP。
  - AstrBot 与 courseManage 在**同一个 Docker 网络**时，可直接写 `http://coursemanage-mcp:8765/mcp`。
  - AstrBot 在同机但**不同 Docker 网络**时，Linux 用 `http://172.17.0.1:8765/mcp`，
    Windows / macOS 用 `http://host.docker.internal:8765/mcp`。
- `Authorization` 的值必须与 `.env` 中的 `MCP_AUTH_TOKEN` 完全一致。
- 部分 AstrBot 版本的键名为 `type` 而非 `transport`，若保存后连不上，
  把 `"transport"` 改成 `"type"` 再试；仅支持 SSE 的旧版本请把
  `.env` 里 `MCP_TRANSPORT` 改为 `sse`，URL 改为 `http://IP:8765/sse`。

配置文件也可参考 [`mcp-server/examples/astrbot-streamable-http.json`](../mcp-server/examples/astrbot-streamable-http.json)。

### 4.2 本地 stdio 接入

若 AstrBot 与 MCP 装在同一环境，可让 AstrBot 直接拉起子进程，见
[`mcp-server/examples/astrbot-stdio.json`](../mcp-server/examples/astrbot-stdio.json)。

### 4.3 启用工具

1. 保存后在 MCP 列表里点「启用 / 刷新」，应能看到 20+ 个工具。
2. 到「服务提供商」确认所用大模型**支持 Function Calling**
   （DeepSeek-V3 / Qwen-Max / GPT-4o / GLM-4 等均支持）。
3. 在人格 / 系统提示里加一句引导，效果会明显更好：

```
你是课程管理助手，可以调用 coursemanage 工具查询与操作培训机构的排课、
学员、导师、课费数据。规则：
1. 需要 ID 的操作，先用 list_* 工具按名称查到 ID，不要凭空猜测 ID。
2. 涉及新建、修改、取消、延期等写操作，必须先向用户复述完整信息并得到确认。
3. 工具返回什么就说什么，不要编造数据。
4. 回答尽量用简洁的中文列表。
```

---

## 5. 接入其它框架

### Claude Desktop / Cline / Continue（stdio）

见 [`mcp-server/examples/claude-desktop.json`](../mcp-server/examples/claude-desktop.json)。
Claude Desktop 只支持 stdio，接远程端点需用 `npx -y mcp-remote <url> --header ...` 桥接。

### Cherry Studio / ChatWise / Dify（HTTP）

这类客户端直接支持 Streamable HTTP，填两项即可：

- URL：`http://<IP>:8765/mcp`
- Header：`Authorization: Bearer <MCP_AUTH_TOKEN>`

### 自己写客户端

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main() -> None:
    headers = {"Authorization": "Bearer <MCP_AUTH_TOKEN>"}
    async with streamablehttp_client("http://127.0.0.1:8765/mcp", headers=headers) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            print([t.name for t in (await session.list_tools()).tools])
            print(await session.call_tool("get_schedules_by_day", {"day": "today"}))

asyncio.run(main())
```

---

## 6. 安全建议（必读）

MCP 服务器持有一个 courseManage 系统账号，等于把系统操作能力交给了大模型，
请务必按下面几点收敛权限：

1. **单独建账号**：不要用 `admin`。在「用户管理」新建 `mcp-bot`，
   只授予业务需要的角色（例如只做查询就给「系统审计员」）。
2. **必开访问令牌**：`MCP_AUTH_TOKEN` 留空时任何人访问 `8765` 端口都能操作数据。
3. **先只读跑一段时间**：`MCP_READONLY=true`，写工具在协议层就不存在，
   模型不可能"手滑"删课。确认稳定后再放开。
4. **通知默认关闭**：`MCP_ALLOW_NOTIFICATIONS=false` 时，即使模型传了
   `send_notification=true` 也会被强制降级为 `false`，不会误发企业微信群消息。
5. **不要暴露到公网**：如必须远程访问，请走内网穿透 + HTTPS 反向代理，
   并在代理层再加一层鉴权与 IP 白名单。
6. **注意提示注入**：群成员的消息会进入模型上下文，可能诱导模型调用写工具。
   开放写权限时，请在系统提示中要求"写操作必须二次确认"，并只在可信群启用。

### Nginx 反向代理示例（加 HTTPS）

```nginx
location /mcp {
    proxy_pass         http://127.0.0.1:8765/mcp;
    proxy_http_version 1.1;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    # Streamable HTTP 可能使用 SSE 流，必须关闭缓冲
    proxy_buffering    off;
    proxy_read_timeout 600s;
    chunked_transfer_encoding on;
}
```

---

## 7. 能做什么：对话示例

| 你说 | 机器人调用的工具 |
| --- | --- |
| 今天有几节课？都是谁上的？ | `get_schedules_by_day(day="today")` |
| 明天上午王老师的课在哪个教室？ | `list_teachers(search="王")` → `get_schedules_by_day(day="tomorrow", teacher_id=…)` |
| 三年级A班这周的课表 | `list_classes(search="三年级A")` → `list_schedules(...)` |
| 张三还剩多少课时？ | `list_students(search="张三")` → `list_student_fees(student_id=…)` |
| 有哪些排课冲突？ | `list_schedule_conflicts()` |
| 最近 30 天导师工作量排行 | `get_teacher_workload(days=30)` |
| 哪些学员该催费了？ | `get_fee_alerts()` |
| 张三的数学成绩趋势 | `get_student_grade_trend(student_id=…)` |
| 把 128 号课延到下周三 19:00，原因是导师出差 | `postpone_schedule(...)`（需关闭只读） |
| 帮我登记李老师 3 月 5 日请假 | `list_teachers` → `create_leave(...)`（需关闭只读） |
| 给三年级A班周三 19 点排一节数学课 | `parse_smart_command` → 确认 → `run_smart_command` |

还可以直接用内置提示词：`daily_briefing`（每日课务简报）、
`conflict_review`（排课冲突排查）。

---

## 8. 常见问题排查

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| MCP 容器反复重启，日志 `配置错误：必须提供 COURSEMANAGE_TOKEN，或同时提供…` | `.env` 里 `MCP_API_USERNAME/PASSWORD` 为空 | 填好账号密码后 `docker compose --profile mcp up -d` |
| 日志 `认证失败…账号或密码错误` | 账号密码不对，或该账号被禁用 | 用同一账号登录 Web 端验证 |
| 日志 `无法连接后端 http://backend:8000` | MCP 容器不在 courseManage 网络里 | 用同一份 compose 启动；自建容器需 `--network coursemanage_default` |
| AstrBot 显示连接失败 / 401 | `Authorization` 与 `MCP_AUTH_TOKEN` 不一致 | 两边核对，注意 `Bearer ` 后有一个空格 |
| AstrBot 连不上但 curl 正常 | `MCP_BIND_HOST` 还是 `127.0.0.1` | 改成 `0.0.0.0` 后重启 mcp 容器 |
| AstrBot 版本较老，只认 SSE | 客户端不支持 Streamable HTTP | `MCP_TRANSPORT=sse`，URL 用 `/sse` |
| 工具列表里看不到写操作工具 | 处于只读模式 | `MCP_READONLY=false` 后重启 |
| 调用费用/成绩/统计工具报 403 | 所用系统账号角色权限不足（本仓库已移除授权门禁，见 docs/PREMIUM.md） | 给 `MCP_API_USERNAME` 账号授予对应角色 |
| 模型答非所问、不调工具 | 模型不支持 Function Calling | 换 DeepSeek-V3 / Qwen-Max / GPT-4o 等 |
| 返回内容被截断，提示"结果已截断" | 超过 `MCP_MAX_ITEMS` | 让模型加筛选条件，或调大 `MCP_MAX_ITEMS` |
| 群里问一句要等很久 | 后端统计类接口本身较慢 | 调大 `COURSEMANAGE_TIMEOUT`，或避免频繁查大屏 KPI |

排查第一步永远是让机器人调用 **`get_system_status`**：它会一次性返回后端连通性、
当前登录身份和已激活的高级功能。
