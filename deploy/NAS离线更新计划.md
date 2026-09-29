# NAS 离线更新计划（x86_64 / amd64）

状态：已在本机独立 Docker 项目验证，**尚未上传或部署到 NAS**。本机是 arm64，NAS 是 amd64。当前改动相对于 NAS 旧镜像 `b5eddf1` 涉及 Python、Alembic 迁移、React 前端及入口脚本；Go、Python 依赖、前端依赖和 Docker 基础运行层未变。

## 选择路线

| 路线 | NAS 工作 | 传输量 | 适用条件 |
| --- | --- | --- | --- |
| A：本地构建完整 amd64 镜像 | `docker load`、重建容器 | 旧版镜像包约 300 MB；新版以实际构建为准 | 最稳妥、正式长期部署，或 Go/依赖/Dockerfile 改变时 |
| B：代码挂载更新 | 解压约数 MB 的 Python/前端/入口脚本包、重建容器 | 约数 MB；以实际包为准 | **仅这次**基于 `b5eddf1` 旧镜像且 Go/依赖未变的更新 |

推荐这次先在备份副本验证 B，再按需要选择 A 上正式 NAS。B 无需在 NAS 或本地编译 amd64；本地只运行 `npm run build`，Python 源码和迁移直接上传。两条路线都复用现有 `.env` 和 `postgres_data` 卷。

## 部署前共同检查

1. 确认 NAS 项目目录（下文以 `/path/to/semi-vix-platform` 表示）当前确实运行 `b5eddf1` 构建的 `semi-vix-platform:latest`，CPU 架构为 `amd64`。若来源不同，不使用 B。
2. 在 NAS 当前项目目录备份数据库：

   ```sh
   cd /path/to/semi-vix-platform
   mkdir -p backups
   docker compose exec -T app bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/before-v1.0.backup
   test -s backups/before-v1.0.backup
   docker compose exec -T app pg_restore -l < backups/before-v1.0.backup > /dev/null
   docker image inspect semi-vix-platform:latest --format 'os={{.Os}} arch={{.Architecture}} id={{.Id}}'
   docker compose ps
   ```

3. 保留 `.env` 原件和旧镜像；不要运行 `docker compose down -v`。选择美股交易时段之外切换。备份含加密凭据，限制文件权限并另存一份到安全位置。

## B：小文件代码挂载（本次可用）

在**本地项目根目录**制作包：

```sh
bash deploy/prepare-code-overlay.sh v1.0
```

脚本检查运行层/依赖未变，构建前端，并输出 `releases/nas-code-v1.0/semi-vix-code-v1.0.tar.gz` 及 `SHA256SUMS`。包中包含修复首次建库问题的入口脚本。上传这两个文件，以及 `deploy/compose-code-overlay.yml` 到 NAS 的项目目录。NAS 端保留 `docker-compose.yml`、`.env` 原件。上传后：

```sh
cd /path/to/semi-vix-platform
cd releases/nas-code-v1.0
sha256sum -c SHA256SUMS
cd ../..
mkdir -p deploy/code-releases/v1.0
tar -xzf releases/nas-code-v1.0/semi-vix-code-v1.0.tar.gz -C deploy/code-releases/v1.0
test -f deploy/code-releases/v1.0/backend/alembic/versions/0015_free_observation.py
test -f deploy/code-releases/v1.0/frontend/dist/index.html
test -f deploy/code-releases/v1.0/docker/entrypoint.sh
if [ -e deploy/code-current ]; then
  mv deploy/code-current "deploy/code-releases/previous-$(date +%Y%m%d-%H%M%S)"
fi
mv deploy/code-releases/v1.0 deploy/code-current
docker compose -f docker-compose.yml -f deploy/compose-code-overlay.yml config --quiet
docker compose -f docker-compose.yml -f deploy/compose-code-overlay.yml up -d --no-build --pull never --force-recreate app
```

`deploy/compose-code-overlay.yml` 把新 Python 代码、前端静态文件和入口脚本以只读方式挂进旧镜像，PostgreSQL/Go/Nginx 等运行层保持旧镜像。后端启动时会运行新迁移。脚本会将已有的 `deploy/code-current` 移到带日期的备份目录；不要直接覆盖正在运行的文件。

验证：

```sh
docker compose -f docker-compose.yml -f deploy/compose-code-overlay.yml ps
docker compose -f docker-compose.yml -f deploy/compose-code-overlay.yml exec -T app supervisorctl status
docker compose -f docker-compose.yml -f deploy/compose-code-overlay.yml exec -T app curl -fsS http://127.0.0.1/health
docker compose -f docker-compose.yml -f deploy/compose-code-overlay.yml exec -T app bash -lc 'cd /opt/svix/backend && alembic current'
```

`alembic current` 应为 `0015_free_observation`。随后在页面检查设置、日内仪表盘以及首轮采集的批次/失败原因。综合值仍取决于免费报价质量和 253 个对齐的股票日线价格点。

**回滚边界：**旧镜像缺少 `0015_free_observation` 迁移文件，升级后的数据库不能简单地移除挂载并启动旧镜像。若本次刚切换就要回滚，先停止写入并从 `before-v1.0.backup` 恢复数据库到迁移前状态，然后去掉 Compose 覆盖文件重建旧容器。这样会丢失备份之后的新数据。请先在数据库备份副本演练；若需要无数据损失回滚，应另行准备携带 `0015` 迁移文件的旧代码兼容镜像并验证。

## A：本地完整镜像，NAS 只加载（长期推荐）

在本地启动 Docker Desktop 后，从项目根目录运行：

```sh
docker buildx build --platform linux/amd64 --load \
  -t semi-vix-platform:v1.0-amd64 .
docker image inspect semi-vix-platform:v1.0-amd64 \
  --format 'os={{.Os}} arch={{.Architecture}} id={{.Id}}'
docker save semi-vix-platform:v1.0-amd64 | gzip > semi-vix-v1.0-amd64.tar.gz
shasum -a 256 semi-vix-v1.0-amd64.tar.gz > semi-vix-v1.0-amd64.tar.gz.sha256
```

本地 arm64 到 amd64 的 `RUN` 步骤可能走仿真，首次构建仍可能慢；后续利用本地缓存。上传镜像包与校验文件到 NAS。先做上述数据库备份，再执行：

```sh
cd /path/to/semi-vix-platform
sha256sum -c semi-vix-v1.0-amd64.tar.gz.sha256
docker tag semi-vix-platform:latest semi-vix-platform:before-v1.0
docker load -i semi-vix-v1.0-amd64.tar.gz
docker image inspect semi-vix-platform:v1.0-amd64 --format 'os={{.Os}} arch={{.Architecture}}'
docker tag semi-vix-platform:v1.0-amd64 semi-vix-platform:latest
docker compose up -d --no-build --pull never --force-recreate app
docker compose ps
docker compose exec -T app supervisorctl status
docker compose exec -T app bash -lc 'cd /opt/svix/backend && alembic current'
```

若已经采用 B 的代码挂载，切换 A 前必须明确去掉 `-f deploy/compose-code-overlay.yml`，并确认容器没有旧挂载。A 的旧镜像回滚同样受 Alembic 版本限制：仅 retag 旧镜像不足以回滚迁移后的数据库。

## 尚未完成的验收

- 本机已用旧 amd64 运行镜像和代码挂载启动独立 Docker 项目，并在 PostgreSQL 16 上运行迁移；修复后的入口脚本还通过了全新数据库卷的初始化测试。尚未构建新的完整 amd64 镜像，也尚未在 NAS 数据副本上演练。
- 后端测试、Go 联调和前端构建已通过，但仍需在数据库备份副本演练 `0015` 迁移及首轮真实 Alpaca 采集。
- 上线后观察至少三个完整交易日，记录每轮报价年龄、分项/综合可计算率、API 与图表一致性。
