# courseManage MCP 服务器

把 [courseManage](../README.md) 教育培训机构管理平台的能力，通过
[Model Context Protocol](https://modelcontextprotocol.io) 暴露给
**AstrBot**、Claude Desktop、Cherry Studio、Dify、Cline 等任意 MCP 客户端。

接好之后，你可以直接在 QQ / 微信 / Telegram 群里问机器人：

> 「今天有几节课？」
> 「查一下张三的剩余课时」
> 「王老师明天上午的课改到下午 3 点，原因是临时开会」

---

## 特性

| 能力 | 说明 |
| --- | --- |
| 双传输 | `stdio`（本地进程）/ `http` Streamable HTTP（远程，推荐）/ `sse`（兼容旧客户端） |
| 只读开关 | `COURSEMANAGE_MCP_READONLY=true` 时**根本不注册**写操作工具，从协议层面阻断误操作 |
| 通知隔离 | 默认强制把 `send_notification` 降级为 `false`，避免机器人误发企业微信群通知 |
| 客户端鉴权 | `COURSEMANAGE_MCP_AUTH_TOKEN` 提供 Bearer / `X-Api-Key` 共享密钥校验 |
| 上下文友好 | 后端返回的臃肿 JSON 会被投影成精简结构，并按 `MCP_MAX_ITEMS` 截断 |
| 自动续期 | JWT 过期时自动重新登录并重放请求 |
| 中文错误 | 403 会明确提示「需要在系统授权管理中激活对应高级功能」 |

## 快速开始

### 方式一：Docker（推荐）

```bash
# 在 courseManage 部署目录下
docker compose -f docker-compose.deploy.yml --profile mcp up -d
docker compose -f docker-compose.deploy.yml logs -f mcp
```

需要先在 `.env` 中设置 `MCP_API_USERNAME` / `MCP_API_PASSWORD` / `MCP_AUTH_TOKEN`。

### 方式二：本地 Python

```bash
cd mcp-server
pip install -e .

export COURSEMANAGE_API_BASE=http://127.0.0.1:35000
export COURSEMANAGE_USERNAME=admin
export COURSEMANAGE_PASSWORD=Admin.123

coursemanage-mcp --list-tools          # 先看看有哪些工具
coursemanage-mcp                       # stdio 模式
coursemanage-mcp --transport http      # HTTP 模式，监听 0.0.0.0:8765/mcp
```

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `COURSEMANAGE_API_BASE` | `http://backend:8000` | 后端地址，必须带 `http(s)://` |
| `COURSEMANAGE_USERNAME` | — | 系统账号（与 `TOKEN` 二选一） |
| `COURSEMANAGE_PASSWORD` | — | 系统密码 |
| `COURSEMANAGE_TOKEN` | — | 已有 JWT，设置后不再自动登录 |
| `COURSEMANAGE_TIMEOUT` | `30` | 单次请求超时（秒） |
| `COURSEMANAGE_VERIFY_SSL` | `true` | HTTPS 证书校验 |
| `COURSEMANAGE_MCP_TRANSPORT` | `stdio` | `stdio` / `http` / `sse` |
| `COURSEMANAGE_MCP_HOST` | `0.0.0.0` | HTTP 监听地址 |
| `COURSEMANAGE_MCP_PORT` | `8765` | HTTP 监听端口 |
| `COURSEMANAGE_MCP_PATH` | `/mcp` | Streamable HTTP 端点路径 |
| `COURSEMANAGE_MCP_STATELESS` | `true` | 无状态 HTTP，重启后客户端不需要重建会话 |
| `COURSEMANAGE_MCP_AUTH_TOKEN` | — | 客户端共享密钥，留空则不校验 |
| `COURSEMANAGE_MCP_READONLY` | `false` | 只读模式 |
| `COURSEMANAGE_MCP_ALLOW_NOTIFICATIONS` | `false` | 允许触发企业微信/邮件通知 |
| `COURSEMANAGE_MCP_MAX_ITEMS` | `50` | 列表返回上限 |
| `COURSEMANAGE_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` |

## 工具一览

**查询类（只读模式下依然可用）**

`get_system_status` `get_site_info` `list_courses` `list_teachers` `list_classes`
`list_students` `get_student` `list_rooms` `list_schedules` `get_schedules_by_day`
`get_schedule` `list_schedule_conflicts` `get_absent_students` `list_leaves`
`list_holidays` `get_dashboard_kpi` `get_teacher_workload` `get_room_utilization`
`get_incomplete_schedules` `list_student_fees` `get_fee_alerts` `list_grades`
`get_student_grade_trend` `get_student_evaluation_profile` `parse_smart_command`

**写入类（`READONLY=false` 才注册）**

`create_schedule` `complete_schedule` `postpone_schedule` `cancel_schedule`
`update_attendance` `create_leave` `create_student` `create_course` `run_smart_command`

**通知类（额外需要 `ALLOW_NOTIFICATIONS=true`）**

`notify_schedule`

> 费用、成绩、评价、运营大屏、智能指令相关工具依赖 courseManage 的**高级授权**，
> 未激活时后端返回 403，工具会返回明确的中文提示。

**资源**：`coursemanage://today-schedules`、`coursemanage://site-info`
**提示词**：`daily_briefing`（每日课务简报）、`conflict_review`（排课冲突排查）

## 客户端接入

完整的 AstrBot / Claude Desktop / Cherry Studio / Dify 配置示例见
[`docs/MCP.md`](../docs/MCP.md)，示例 JSON 见 [`examples/`](./examples)。

## 开发

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

## 许可证

AGPL-3.0-only，与主项目一致。
