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

镜像会推到**你自己的**命名空间，所以部署时要改 `.env`：

```bash
IMAGE_OWNER=你的github用户名小写
IMAGE_TAG=latest
```

`docker-compose.deploy.yml` 已改为
`${IMAGE_REGISTRY:-ghcr.io}/${IMAGE_OWNER:-daiyu116}/coursemanage-xxx:${IMAGE_TAG:-latest}`，
不改文件、只改 `.env` 即可切换镜像来源与版本。

---

## 6. 发布一个版本

```bash
git tag v1.4.2
git push origin v1.4.2
```

流水线会：构建三个镜像的多架构 manifest → 打 `1.4.2` / `1.4` / `1` 标签 →
扫描 → 生成 provenance → 创建 GitHub Release。
