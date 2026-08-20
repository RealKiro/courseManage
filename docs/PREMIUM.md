# 高级功能：本分支已放开门禁

上游 courseManage 把 9 项功能列为「高级授权」，需要用 RSA 签名的 License Key
激活才能使用。**本仓库是 AGPL-3.0 下的自用分支，已完整移除这套门禁**：
所有功能开箱可用，无需激活、无需机器码、无需联网校验。

本文说明：改了什么、为什么这样改、如何还原。

---

## 1. 现在的状态

9 项原「高级功能」全部可用：

| 功能标识 | 名称 | 相关 API |
| --- | --- | --- |
| `grade_trend` | 学员成绩管理 | `/api/grades` |
| `fee_management` | 费用管理 | `/api/fees` |
| `smart_scheduling` | 智能算法排课 | `/api/schedules/auto-schedule` |
| `wechat_notify` | 微信通知管理 | `/api/wechat` |
| `smart_command` | 智能指令管理 | `/api/smart-command` |
| `dashboard_view` | 运营大屏 | `/api/statistics/*` |
| `database_management` | 数据库管理 | `/api/database` |
| `student_evaluation` | 学员评价管理 | `/api/evaluations` |
| `floating_sphere` | 全站快捷按钮 | 仅前端 |

界面上「系统管理 → 系统授权管理」页面仍然存在，会显示为已激活状态，
但激活/申请/停用等按钮已无实际作用。

---

## 2. 具体改了哪些地方

### 删除

| 文件 | 原内容 |
| --- | --- |
| `backend/utils/license.py` | RSA-PSS 验签、机器码生成、供应商心跳、供应商配置发现（discovery） |

### 改为占位实现

**`backend/routers/license.py`** —— 从 887 行缩减为约 200 行的占位模块：

- `_check_premium_feature(feature_name, db)` **恒返回 `True`**
- 保留只读接口 `/license/status`、`/features`、`/check/{name}`、`/machine-code`，
  让前端「系统授权管理」页面仍能正常渲染
- **删除全部向供应商回传数据的接口实现**：`/apply`、`/feedback`、
  `/notify-supplier-view`、`/request-replace`、`/preview-addon`
  改为空实现，不再发送任何信息（原先会把机构名称、联系人、电话、邮箱、
  机器码推送到上游的企业微信 webhook）

> **为什么保留这个文件而不是一并删掉？**
> `_check_premium_feature` 被 **11 个模块**引用（fees / grades / evaluations /
> database / wechat / settings / schedules / smart_command / smart_command_examples /
> remainder ×2）。保留这一个恒真函数即可一次性放开所有调用点，
> 无需改动那 11 个文件——改动面最小，回归风险最低。

**`backend/main.py`**：

- 移除 `premium_feature_guard` HTTP 中间件（原先对 9 类路径前缀逐一鉴权，
  未授权返回 403）
- 移除启动时的 `verify_compiled_modules()` 完整性校验
- 移除 `from routers.license import _check_premium_feature`
  与 `from utils.license import FEATURE_NAMES`
- `PREMIUM_PATH_MAP` 常量保留，仅作为「哪些接口原属高级功能」的文档，无运行时作用

**`frontend/src/utils/license.js`**：

- `licenseState` 初始即为 `activated: true` + 9 项功能全 `true`
- `hasFeature()` 恒返回 `true`
- `loadLicenseStatus()` 仍拉取 `/license/status` 以同步机构/联系人信息，
  但不再让后端返回值影响 `activated` 与 `features`

> 这里必须同时改两处：模板里十余处用的是 `hasFeature()`，
> 而 `router/index.js` 的路由守卫（第 186–192 行）是**直接读**
> `licenseState.activated` 与 `licenseState.features[...]`。
> 只改 `hasFeature()` 的话，导航到费用管理/成绩管理等页面仍会被拦回首页。

**`backend/setup_cython.py`** 与 **`backend/Dockerfile`**：
从 `CRITICAL_MODULES` 中移除两个 license 模块（不再需要源码保护），
其余模块（optimizer、smart_command、wechat_notifier、remainder）保持编译。

### 保留

- `models.py` 中的 `license_key` / `premium_features` / `deactivated_licenses`
  等字段，以及 `migrate_add_license.py`
  —— 纯数据库结构，删掉反而可能影响已有部署，留着无害且不再被读写

---

## 3. 顺带解决的两个上游隐患

### 3.1 机器码丢失导致授权失效（已不存在）

上游的机器码取自 `${BACKUP_DIR}/.machine_id`（即数据卷 `backup_data` 内的
`/app/backups/.machine_id`）。执行 `docker compose down -v` 删卷后机器码会变化，
`_check_premium_feature()` 验证失败时还会**主动清空数据库里的 `license_key`**：

```python
_append_deactivated(settings, settings.license_key)
settings.license_key = None
settings.premium_features = "{}"
db.commit()
```

门禁移除后这条链路整体消失，删卷不再影响功能可用性
（当然，删卷仍然会删掉数据库数据，该注意的还是要注意）。

### 3.2 每小时一次的 5 秒阻塞（已消除）

`heartbeat_check()` 会向 `https://courseManage-licence.service.local/api/v1/hb`
发 POST，超时 5 秒，结果缓存 1 小时。这个 `.local` 域名在正常环境里无法解析，
所以每小时的第一个高级功能请求都要**先卡最多 5 秒**才 fail-open 放行。
同理 `_fetch_discovery()` 每 24 小时会请求一次
`courseManage-discovery.example.com`（`example.com` 是保留域名，永远不解析）。

移除后这两处网络等待都不再发生。

---

## 4. 如何还原门禁

改动集中在 4 个文件，还原方式：

```bash
# 找到移除门禁的那次提交
git log --oneline -- backend/routers/license.py

# 从上游或该提交之前恢复
git checkout <commit>^ -- backend/utils/license.py \
                          backend/routers/license.py \
                          backend/main.py \
                          backend/setup_cython.py \
                          frontend/src/utils/license.js
```

如果是想换成**自己签发**的授权体系（而不是完全放开），做法是：

1. 生成 RSA 密钥对，私钥自己保管
2. 恢复 `utils/license.py`，把 `LICENSE_PUBLIC_KEY_PEM` 换成你的公钥
3. 把 `_SUpLIER_DISCOVERY` / `_SUpLIER_COMM_DEFAULT` / `_SUpLIER_HB_DEFAULT`
   指向你自己的服务，或直接让 `get_supplier_hb()` 返回空字符串跳过心跳
4. 按 `verify_license()` 期望的结构自建签发脚本：
   payload 用 `json.dumps(payload, sort_keys=True, ensure_ascii=False)` 序列化，
   以 PSS(MGF1-SHA256, salt=MAX_LENGTH) + SHA256 签名，
   最后 `base64.urlsafe_b64encode(json.dumps({"payload":…,"signature":…}))`

注意 `backend/Dockerfile` 会把 `CRITICAL_MODULES` 里的模块 Cython 编译成 `.so`
**并删除 `.py` 源码**，所以任何改动都必须在构建前落到源码里。

---

## 5. 许可证提醒

本项目为 **AGPL-3.0-only**。AGPL §2 允许你为自用目的修改并运行修改后的版本，
移除功能门禁属于该范围内。需要注意的是 **AGPL §13**：
如果你让第三方通过网络与本系统交互，就必须向这些使用者提供对应的完整源码。
本仓库是公开的 fork，这一点自然满足；如果你后续转为私有部署并对外提供服务，
请自行确认合规。

若你与上游作者另有商业协议，请以协议约定为准。
