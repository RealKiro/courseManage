# 高级功能（授权）说明

courseManage 的功能分两类：**默认授权**即开即用，**高级授权**需要激活。
本文说明高级功能的鉴权机制、如何开启，以及运维上最容易踩的坑。

---

## 1. 有哪些高级功能

后端 `backend/utils/license.py` 的 `PREMIUM_FEATURES` 定义了 9 项：

| 功能标识 | 名称 | 受影响的 API 前缀 |
| --- | --- | --- |
| `grade_trend` | 学员成绩管理 | `/api/grades` |
| `fee_management` | 费用管理 | `/api/fees` |
| `smart_scheduling` | 智能算法排课 | `/api/schedules/optimize` |
| `wechat_notify` | 微信通知管理 | `/api/wechat` |
| `smart_command` | 智能指令管理 | `/api/smart-command`、`/api/smart-command-examples` |
| `dashboard_view` | 运营大屏 | `/api/statistics/dashboard` |
| `database_management` | 数据库管理 | `/api/database` |
| `student_evaluation` | 学员评价管理 | `/api/evaluations` |
| `floating_sphere` | 全站快捷按钮 | 仅前端 |

拦截点是 `backend/main.py` 的 `premium_feature_guard` 中间件（`PREMIUM_PATH_MAP`），
未授权时返回 **HTTP 403** 与「功能 'xxx' 需要授权，请在系统授权管理中激活」。

> MCP 服务器会把这个 403 翻译成明确的中文提示，所以机器人调用
> `get_fee_alerts` 之类的工具报「需要在系统授权管理中激活」是**预期行为**，不是故障。

授权类型（`LICENSE_TYPES`）：`trialA`(3天)、`trialB`(7天)、`monthly`(30天)、
`quarterly`(90天)、`semiannual`(180天)、`annual`(365天)、`perpetual`(永久)。

---

## 2. 鉴权链是怎么走的

`backend/routers/license.py` 的 `_check_premium_feature()` 依次校验 5 层，
任何一层不过就返回 `False`：

```
1. 数据库 settings.license_key 存在
        ↓
2. LicenseService.verify_license(key, machine_code)
     · base64 解码 → { payload, signature }
     · RSA-PSS-SHA256 用【硬编码公钥】验签
     · payload.machine_code 必须 == 本机机器码
     · payload.expiry_date 必须未过期
        ↓
3. heartbeat_check() 向供应商心跳地址上报
     · 网络失败时【放行】（fail-open），结果缓存 1 小时
     · 所以内网 / 断网部署不受影响
        ↓
4. 请求的功能名必须在 payload.features 列表里
        ↓
5. settings.premium_features 的 HMAC 签名校验
     · HMAC 密钥由 SECRET_KEY + 内置盐 + 公钥前 64 字节派生
```

第 5 步有个重要副作用：**`SECRET_KEY` 一旦更换，
`premium_features` 的 HMAC 签名就会失效**，需要重新激活。

---

## 3. 正常开启流程（作为客户）

1. 用系统管理员账号登录 → **系统管理 → 系统授权管理**
2. 页面会显示**机器码**（也可调 `GET /api/license/machine-code`）
3. 填写机构名称、联系人、联系方式，点「申请授权」
   （`POST /api/license/apply`，会把信息推送到供应商的企业微信 webhook 与邮箱）
4. 供应商用**私钥**签发 License Key 并回传
5. 把 License Key 粘贴回该页面激活（`POST /api/license/activate`，需系统管理员权限）
6. 激活成功后 `GET /api/license/features` 会列出已启用的功能，前端菜单随之解锁

激活失败时接口会同时回显「服务器机器码」和「License 中机器码」，便于比对。

---

## 4. ⚠️ fork 自建镜像的人请注意

仓库里只有 `LICENSE_PUBLIC_KEY_PEM`（**公钥**），**没有私钥**。
这意味着：**你自己构建的镜像无法自行签发能通过验证的 License Key。**

三条可行路径：

| 方案 | 做法 | 注意 |
| --- | --- | --- |
| A. 向上游取得授权 | 走上面第 3 步流程 | License 绑定机器码；心跳与申请通知都发往上游供应商 |
| B. 换成自己的密钥对 | 生成 RSA 密钥对 → 把自己的公钥写入 `backend/utils/license.py` 的 `LICENSE_PUBLIC_KEY_PEM` → 自建签发脚本（按 §2 的 payload 结构用 PSS-SHA256 签名）→ 同时把 `_SUpLIER_*` 常量指向自己的服务 | 本项目为 AGPL-3.0，允许修改；若对外分发，需按 AGPL 提供完整源码 |
| C. 自用直接放开 | 让 `_check_premium_feature()` 直接返回 `True`，或清空 `main.py` 的 `PREMIUM_PATH_MAP` | 同样受 AGPL 约束；若你与上游存在商业协议，请先确认不违约 |

选 B 时别忘了 `backend/Dockerfile` 会把 `utils/license.py`、`routers/license.py`
等模块 Cython 编译成 `.so` 并**删除源码**，所以改动必须在构建前落到源码里。

---

## 5. ⚠️ 最容易踩的运维坑：机器码会丢

机器码的生成方式（`LicenseService.get_machine_code`）：

```python
machine_id_file = os.path.join(os.environ.get('BACKUP_DIR', '/app/backups'), '.machine_id')
# 文件存在 → sha256(内容)[:16]
# 文件不存在 → 新建 uuid4 写入，再取哈希
```

即机器码持久化在 **`/app/backups/.machine_id`**，位于 `backup_data` 数据卷里。
容器重建、镜像升级都不影响它，**但是**：

> **`docker compose down -v` 会删除数据卷 → `.machine_id` 丢失 → 机器码变化
> → License 立即失效，必须重新签发。**

README 的「清理」小节里就有 `down -v` 这条命令，请务必看清警告再执行。

更要命的是失效不只是「暂时不可用」——`_check_premium_feature()` 在验证失败时会
**主动把 `settings.license_key` 置空并写库**，同时把这个 key 记入「已停用」列表：

```python
_append_deactivated(settings, settings.license_key)
settings.license_key = None
settings.premium_features = "{}"
db.commit()
```

### 建议：先备份机器码文件

```bash
# 备份（建议连同数据库备份一起做）
docker cp coursemanage-backend:/app/backups/.machine_id ./machine_id.bak

# 万一卷被删，恢复顺序：先起容器，再塞回文件，然后重启后端
docker cp ./machine_id.bak coursemanage-backend:/app/backups/.machine_id
docker compose -f docker-compose.deploy.yml restart backend
```

查看当前机器码：

```bash
docker exec coursemanage-backend cat /app/backups/.machine_id     # 原始 UUID
# 或用接口拿哈希后的 16 位机器码（需登录 Token）
curl -H "Authorization: Bearer <token>" http://127.0.0.1:35000/api/license/machine-code
```

---

## 6. 排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 激活报「License 中机器码」与「服务器机器码」不一致 | 换机、卷被删、或 License 是给别的部署签发的 | 用当前机器码重新签发；或恢复 `.machine_id` |
| 原本能用，某天全部高级功能变 403 | 多为 `.machine_id` 丢失或 License 过期 | 看后端日志中 `[License]` 开头的行，会打印具体原因 |
| 改了 `SECRET_KEY` 后高级功能失效 | 第 5 层 HMAC 签名依赖 `SECRET_KEY` | 重新激活一次 License |
| 启动日志有 `Module is not compiled` 警告 | 非 Docker 方式跑源码，关键模块是 `.py` 而非 `.so` | 开发环境正常现象，只是告警不影响功能 |
| 断网后高级功能是否失效 | 心跳 fail-open 且缓存 1 小时 | 不失效，可离线运行 |

日志过滤：

```bash
docker compose -f docker-compose.deploy.yml logs backend | grep '\[License\]'
```
