# CI/CD 与镜像发布说明

本项目使用两条 GitHub Actions 流水线：

| 工作流 | 文件 | 触发 | 职责 |
| --- | --- | --- | --- |
| CI | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | PR / push main | 语法、依赖、前端构建、MCP 单测、Compose 与工作流校验 |
| Build & Push | [`.github/workflows/docker-build.yml`](../.github/workflows/docker-build.yml) | push main / `v*` tag / 手动 | 构建并发布 GHCR 镜像、漏洞扫描、Release、Gitee 同步 |
| Repo Setup | [`.github/workflows/repo-setup.yml`](../.github/workflows/repo-setup.yml) | 手动 | 配置分支保护 |

---

## 1. 会产出哪些镜像

| 组件 | 镜像 | 架构 |
| --- | --- | --- |
| 后端 | `ghcr.io/<owner>/coursemanage-backend` | `linux/amd64`, `linux/arm64` |
| 前端 | `ghcr.io/<owner>/coursemanage-frontend` | `linux/amd64`, `linux/arm64` |
| MCP | `ghcr.io/<owner>/coursemanage-mcp` | `linux/amd64`, `linux/arm64` |

`<owner>` 是仓库所属 GitHub 用户名/组织名的**小写形式**（流水线会自动转换，
因为 OCI 仓库名不允许大写）。

标签规则：

| 触发 | 产生的标签 |
| --- | --- |
| push `main` | `main`、`sha-<短SHA>`、`latest` |
| tag `v1.4.2` | `1.4.2`、`1.4`、`1`、`sha-<短SHA>` |
| PR | 不推送，只验证能否构建成功 |

---

## 2. 流水线做了哪些优化

### 2.1 组件矩阵 + 增量构建

三个镜像由 `prepare` 阶段生成的 JSON 矩阵驱动，不再复制粘贴三份 job。
并且按目录变更决定要重建哪些组件：

- 只改了 `frontend/**` → 只重建前端
- 只改了 `mcp-server/**` → 只重建 MCP
- 改了 `docker-build.yml` / `docker-compose*` / 打 tag / 手动触发 → 全量重建

对于只改前端的提交，节省约 2/3 的构建时间。

### 2.2 原生 Runner 多架构构建（而非 QEMU）

`amd64` 跑在 `ubuntu-latest`，`arm64` 跑在 `ubuntu-24.04-arm` 原生 ARM Runner。
后端 Dockerfile 里有 Cython 编译，QEMU 模拟下极慢，改成原生 Runner 后
arm64 构建时间从"十几分钟甚至超时"降到与 amd64 相当。

流程是 Docker 官方推荐的 **按 digest 推送 + manifest 合并**：

```
build (amd64) ─┐
               ├─► merge: docker buildx imagetools create -t <tags> <digests>
build (arm64) ─┘
```

这样两个架构不会互相覆盖 `latest` 标签。

> ARM Runner 对公开仓库免费。若你的仓库是私有仓库且套餐不支持，
> 在仓库 **Settings → Variables** 里加一个 `BUILD_ARM64=false` 即可只构建 amd64；
> 手动触发时也可以取消勾选 `build_arm64`。

### 2.3 缓存隔离

每个「组件 × 架构」使用独立的 GitHub Actions 缓存 scope
（`cache-to: type=gha,scope=backend-arm64`），避免不同镜像互相污染缓存。
配合新增的 `.dockerignore`（后端排除 `logs/`、`backups/`、`uploads/`；
前端排除 `node_modules/`、`dist/`），构建上下文显著变小，层缓存命中率更高。

### 2.4 安全与可追溯

- **Trivy** 扫描合并后的镜像，`CRITICAL`/`HIGH` 结果以 SARIF 上传到
  仓库的 Code scanning 页面（`ignore-unfixed`，避免上游未修复漏洞刷屏）。
- **SBOM**（CycloneDX）作为构建产物保留 30 天。
- **构建产物证明**：`actions/attest-build-provenance` 为镜像 digest 生成
  可验证的 provenance 并推送到 registry，可用
  `gh attestation verify oci://ghcr.io/<owner>/coursemanage-backend:latest -R <owner>/courseManage` 校验。
- Trivy 与 CodeQL Action 均**锁定版本**，不再使用 `@master`。

### 2.5 其它改动

- `concurrency`：PR 的重复推送自动取消旧运行，节省额度。
- PR 只构建不推送，可提前发现 Dockerfile 问题。
- 打 `v*` tag 时自动创建 GitHub Release，并附带
  `docker-compose.deploy.yml` 与 `.env.example`，客户可直接从 Release 下载。
- Gitee 同步改为原生 `git push --mirror` 逻辑，去掉第三方 Action 依赖；
  未配置 `GITEE_*` Secret 时自动跳过而不是失败。
- `docs/**`、`*.md` 变更不再触发镜像构建。

---

## 3. 首次启用需要做的事

### 3.1 允许 Actions 写包

仓库 **Settings → Actions → General → Workflow permissions**
选择 *Read and write permissions*（`GITHUB_TOKEN` 需要 `packages: write`）。

### 3.2 首次推送后把包设为公开（可选）

GHCR 新建的包默认私有。若希望客户无需登录即可拉取：
**个人头像 → Packages → coursemanage-backend → Package settings → Change visibility → Public**
（三个包各做一次）。

私有包则需要客户先登录：

```bash
echo <你的PAT> | docker login ghcr.io -u <用户名> --password-stdin
```

### 3.3 可选 Secret / Variable

| 名称 | 类型 | 说明 |
| --- | --- | --- |
| `GITEE_USERNAME` | Secret | Gitee 用户名，缺失则跳过同步 |
| `GITEE_TOKEN` | Secret | Gitee 私人令牌 |
| `GITEE_REPO` | Variable | Gitee 仓库名，默认与 GitHub 同名 |
| `BUILD_ARM64` | Variable | 设为 `false` 时不构建 arm64 |

---

## 4. 手动触发

**Actions → Build and Push Docker Images → Run workflow**，可选：

- `components`：`all` / `backend` / `frontend` / `mcp`（可逗号分隔）
- `push_images`：取消勾选则只验证构建、不推送
- `build_arm64`：是否构建 arm64

---

## 5. fork 之后要改什么

镜像会推到**你自己的**命名空间——流水线用 `github.repository_owner` 自动取当前
仓库归属并转成小写，所以 fork 后 **不需要改任何 workflow 文件**，推一次 main
就会得到 `ghcr.io/<你的用户名>/coursemanage-*`。

唯一需要对齐的是部署时的 `.env`。有三种方式，任选其一：

### 方式 A：一键脚本（推荐，clone 了仓库时）

```bash
bash scripts/setup-env.sh          # Linux / macOS / NAS
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-env.ps1   # Windows
```

脚本会：

1. 从 `git remote get-url origin` 自动探测归属并转小写，写入 `IMAGE_OWNER`
2. 随机生成 `POSTGRES_PASSWORD`（28 位字母数字）、`SECRET_KEY`（32 字节 hex）、
   `MCP_AUTH_TOKEN`（24 字节 hex）
3. 由 `.env.example` 生成 `.env`（已存在时不会覆盖，除非加 `--force` / `-Force`）

没有 clone 仓库时可手动指定：`bash scripts/setup-env.sh --owner 你的用户名`。

### 方式 B：从 Release 下载（客户最省事）

打 tag 后，`release` job 会在**上传前**把 `.env.example` 里的 `IMAGE_OWNER`
改写成当前仓库归属：

```bash
sed -i "s|^IMAGE_OWNER=.*|IMAGE_OWNER=${OWNER}|" .env.example
```

也就是说，**任何人 fork 后自己发一个 tag，他 Release 里的 `.env.example`
就已经指向他自己的 GHCR**，客户下载后只需再改 `POSTGRES_PASSWORD` 与
`SECRET_KEY` 两项即可，不用理解镜像归属这件事。

### 方式 C：手动改一行

```bash
IMAGE_OWNER=你的github用户名小写
```

`docker-compose.deploy.yml` 里镜像地址已参数化为
`${IMAGE_REGISTRY:-ghcr.io}/${IMAGE_OWNER:-daiyu116}/coursemanage-xxx:${IMAGE_TAG:-latest}`，
不改文件、只改 `.env` 即可切换镜像来源与版本。

> 每次 `merge` job 的运行摘要里都会直接打印
> `请在 .env 中设置 IMAGE_OWNER=<owner>`，以及各架构镜像的压缩体积，
> 不用去猜。

---

## 6. 镜像体积

`merge` job 会在运行摘要里报告每个架构的**压缩后下载体积**（各层 size 之和），
方便持续跟踪。当前的取舍：

| 组件 | 基础镜像 | 说明 |
| --- | --- | --- |
| frontend | `nginx:1.27-alpine` | 本来就是 Alpine；构建阶段用 `node:18-alpine` |
| mcp | `python:3.12-alpine` | 依赖只有 pydantic-core / rpds-py 两个二进制扩展，均提供 musllinux wheel |
| backend | `python:3.11-slim-bookworm` | **刻意不用 Alpine**，原因见下 |

### 为什么 backend 不换 Alpine

- `psycopg2-binary` 官方只发布 glibc(manylinux) wheel，musl 上必须源码编译
- `pandas` / `numpy` 在 **musl + aarch64** 组合下 wheel 覆盖不完整
- 一旦退化成源码编译，arm64 构建会从几分钟涨到几十分钟，且容易在 Runner 上 OOM
- musl 的 malloc 在这类数值计算负载下性能也弱于 glibc

换 Alpine 省下的基础层（约 70MB）远小于它带来的构建风险，因此 backend 改为：

- `--no-install-recommends`（原先缺失，apt 会顺带装一堆推荐包）
- 只保留 `fonts-wqy-microhei` 一套中文字体，去掉 `fonts-wqy-zenhei`
  （`routers/schedules.py` 的字体候选列表以 microhei 优先，导出 PDF 不受影响）
- 清掉站点包里的 `tests/` 与 `__pycache__`（pandas / numpy 的测试套件就有数十 MB）
- 基础镜像钉到 `slim-bookworm`，避免 Debian 大版本漂移

如果后续确实要试 Alpine，建议先单独跑一次
`workflow_dispatch → components=backend, build_arm64=true`
验证 arm64 能在超时前完成，再决定是否合并。

---

## 7. 发布一个版本

```bash
git tag v1.4.2
git push origin v1.4.2
```

流水线会：构建三个镜像的多架构 manifest → 打 `1.4.2` / `1.4` / `1` 标签 →
扫描 → 生成 provenance → 创建 GitHub Release。
