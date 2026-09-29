# Semi-VIX 改善计划实施记录与后续路线

> 本文是对《semivix改善计划.md》的实施补充，记录已经执行的代码、发布和 NAS 部署步骤，并保留当前未闭环的问题，方便在新窗口继续调查。它不是对原审查结论的替代，也不把“镜像已启动”视为“服务已验收”。

## 1. 用户约束与实施原则

- 数据源：只能使用 Alpaca 免费数据。当前免费路径是 Alpaca Indicative；历史数据使用 trade-close proxy，必须标记为估算，不能冒充 OPRA BBO。
- 部署：实际部署只能是一个 Docker Compose `app` 容器。容器内部由 Supervisor 管理 PostgreSQL、Go 引擎、Go 调度器、Python API 和 Nginx；升级时不能使用 `docker compose down -v`。
- 性能：高频数值计算、相关性、组合方差和调度优先迁移到 Go；Python 暂时保留 API、认证、迁移和 Alpaca 兼容层。Java 暂不引入，以免增加运行时和镜像复杂度。
- NAS 交付：当前已经可以通过本地电脑将便携发布包上传到 DSM。后续默认不再让 NAS 通过 shell 从 GitHub 拉取源码，也不在 NAS 上完成依赖下载和应用编译；GitHub Release 仅保留为备用来源。
- 数据安全：任何升级先备份数据库和旧部署文件，再加载/切换新镜像；制品校验、镜像加载或配置预检失败时，旧容器和数据卷必须保持不变。

## 2. 已完成的代码与发布工作

### 2.1 v0.3 代码迭代

- 发布仓库：https://github.com/Dexterhhhh/semi-vix-platform
- 发布版本：`v0.3`
- 发布提交：`b5eddf1`
- 已加入 Go 数值引擎和 Go 调度器，减少 Python 高频计算和任务扫描开销。
- 已改为单容器 Docker 架构：不再依赖 Redis、Celery Worker 或 Celery Beat。
- 保留 Alpaca 免费 Indicative 兼容路径，并在结果中区分来源/估算性质。
- Docker 镜像包含前端静态文件、Nginx、FastAPI、Go 二进制和内置 PostgreSQL。

### 2.2 v0.3 原始发布前验证（历史）

- Python 测试、Go 测试和前端构建在发布前通过；发布前的测试结果以当时工作区记录为准。
- 原始发布时本地 Docker daemon 不可用，因此当时的最终镜像构建在 NAS 完成；后续已由第 2.3 节的本地 amd64 离线镜像取代该构建路径。
- 发布前工作区保持干净。

### 2.3 已完成的 NAS amd64 离线镜像

- 构建来源提交：`b5eddf1`。
- 目标平台：`linux/amd64`；镜像内运行验证为 `x86_64`。
- 精确标签：`semi-vix-platform:0.3.0-b5eddf1-amd64`。
- 兼容当前 Compose 的标签：`semi-vix-platform:latest`。
- 本地压缩包：`releases/nas-amd64-v0.3.0-b5eddf1/semi-vix-image-v0.3.0-b5eddf1-linux-amd64.tar.gz`。
- 压缩包 SHA-256：`993cbbaff95b9c6772245d0770923fc4afa15885001cd5f11470cbc45ba461f3`。
- 本地未压缩包：`releases/nas-amd64-v0.3.0-b5eddf1/semi-vix-image-v0.3.0-b5eddf1-linux-amd64.tar`，供只接受普通 Docker archive 的 DSM 导入界面使用。
- 镜像 ID：`sha256:b86880f7e9d219a1d7c3cd4962964442dd5e172d8ae3fd6722cb2d3cddeb3811`。
- 已验证：Go 测试/编译、前端生产构建、Python 主要依赖导入、PostgreSQL 16.15、Nginx、Supervisor 和 amd64 运行环境。

## 3. NAS 实际实施步骤

### 3.1 发现旧部署并准备新版本（历史做法）

旧项目目录：

    /volume1/homes/dexterma/docker/semi-vix-platform

当时使用 GitHub Release 下载：

    curl -fL -o ../semi-vix-v0.3.tar.gz github.com/Dexterhhhh/semi-vix-platform/archive/refs/tags/v0.3.tar.gz
    mkdir ../semi-vix-platform-v0.3
    tar -xzf ../semi-vix-v0.3.tar.gz -C ../semi-vix-platform-v0.3 --strip-components=1
    cp .env ../semi-vix-platform-v0.3/.env

旧源码没有删除，而是移动为：

    /volume1/homes/dexterma/docker/semi-vix-platform-v0.2-backup

随后将 v0.3 目录切换为正式目录名，保证 Compose 项目名和既有数据卷继续匹配。

这段是 v0.3 的历史实施记录，不再是后续推荐方式。现在本地电脑可以经 DSM File Station 或局域网文件共享上传发布物，应优先在本地准备并校验发布包，再上传到 NAS。这样可以绕开 NAS 到 GitHub、PyPI、npm、Debian 镜像站的不稳定外网链路。

### 3.2 数据库备份

- 旧容器内的 `pg_dump` 不在默认 PATH，通过 PostgreSQL 16 的绝对路径完成备份。
- 备份文件约 31 MB，确认存在于 PostgreSQL 持久化数据目录：

      /var/lib/postgresql/data/semi-vix-before-v0.3.backup

- 备份是在旧容器停止前完成的；没有删除 PostgreSQL volume。
- 本次备份仍位于容器数据卷内部。下一轮应复制到宿主机 `backups/`，并执行 `pg_restore -l` 与 SHA-256 校验。

### 3.3 停止旧容器并构建 v0.3

执行了不带 `-v` 的停止：

    sudo docker compose down
    sudo docker compose up -d --build

构建耗时较长的原因是 NAS 首次拉取并解压多个基础镜像层（Go、Node、Python、PostgreSQL），同时执行 apt、pip、npm 和前端 Vite 构建。构建过程约经历 38 个 BuildKit 步骤，最慢的是 `golang:1.23-bookworm` 的大层下载；这属于首次缓存成本，不是 Go 编译本身异常。

构建结果：

- `semi-vix-platform:latest` 镜像成功生成。
- `semi-vix-platform-app-1` 容器成功创建并启动。
- 单容器目标已实现，宿主机映射仍为 `18443 -> 80`。

### 3.4 运行期排查与配置修正

初次健康检查返回 Nginx 502，日志显示：

    connect() failed (111: Connection refused) while connecting to upstream
    upstream: http://127.0.0.1:8000/health

Supervisor 状态为：

    backend    FATAL
    go-engine  RUNNING
    nginx      RUNNING
    postgres   RUNNING
    scheduler  RUNNING

确认 Go 引擎健康接口已返回 `HTTP/1.1 200 OK`，因此当前阻塞点是 Python backend 启动，不是 Go 引擎或 PostgreSQL 进程未启动。

NAS 上曾将 `.env` 中的数据库主机从旧多容器服务名 `postgres` 改为 `127.0.0.1`，并执行：

    sudo docker compose up -d --force-recreate app

注意：`docker compose restart` 不会重新读取容器环境变量；修改 `.env` 后必须 `--force-recreate` 或重新 `up`。不过当前镜像的 `docker/entrypoint.sh` 本身会根据 `POSTGRES_*` 重建 `DATABASE_URL` 为 `127.0.0.1`，因此真正尚未闭环的问题仍是 backend 的迁移阶段。

## 4. 当前部署状态（新窗口调查起点）

> 本节记录上一次 NAS 现场状态。下一窗口执行实际版本升级时，以第 11 节的“新窗口 NAS 升级交接单”为最高优先级；不得因排查或重建而替换 `.env`、改变 Compose 项目名或创建新的数据库卷。

### 已确认

- v0.3 镜像构建成功。
- 单容器已启动，PostgreSQL、Go engine、scheduler、Nginx 均能由 Supervisor 拉起。
- Go engine `127.0.0.1:8090/health` 返回 200。
- 数据卷未用 `-v` 删除，旧源码备份仍保留。
- backend 启动脚本追踪到以下位置后退出：

      python /opt/svix/ensure_database.py
      cd /opt/svix/backend
      alembic upgrade head

### 尚未确认/必须优先调查

1. `alembic upgrade head` 是失败、等待数据库锁，还是连接认证/连接池超时。
2. PostgreSQL 旧数据卷中的 `svix` 角色密码是否与当前 `.env` 的 `POSTGRES_PASSWORD` 一致。
3. 旧数据库是否已存在 Alembic 版本，是否需要从当前版本升级到 `0014_market_data_identity`。
4. backend 失败时的 stderr 是否被 Supervisor 丢到 `/dev/fd/2`，导致 `docker compose logs` 只看到 Nginx 502。
5. 健康检查需同时满足 Nginx `/health`、Go `/health` 和 backend `127.0.0.1:8000/health`；目前只能确认 Go 端点。

### 建议的新窗口第一组命令

在 NAS 项目目录执行，先完成一次 `sudo -v` 认证，然后尽量连续执行：

    cd /volume1/homes/dexterma/docker/semi-vix-platform
    sudo docker compose exec -T app supervisorctl status
    sudo docker compose exec -T app sh -lc 'command -v pg_isready; command -v psql; command -v alembic'
    sudo docker compose exec -T app sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d postgres -c "select 1"'
    sudo docker compose exec -T app sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version_num from alembic_version"'
    sudo docker compose exec -T app sh -lc 'cd /opt/svix/backend && alembic upgrade head'
    sudo docker compose logs --tail=200 app
    sudo docker compose ps

若迁移等待不返回，不要反复重启或删除 volume；先检查 PostgreSQL 活动会话和锁：

    sudo docker compose exec -T app sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select pid, state, wait_event_type, wait_event, query from pg_stat_activity"'

## 5. 部署时间很长的原因分析

部署耗时必须拆成“制品获取、镜像准备、停机切换、启动验收”四段。当前流程把这四段都放在 NAS 上连续执行，只要其中一段没有进度提示，操作者看到的就是一次长时间、不可预测的部署。

### 5.1 主要原因与影响排序

| 优先级 | 原因 | 当前证据/机制 | 实际影响 |
| --- | --- | --- | --- |
| P0 | NAS 首次或缓存失效时下载并解压多个基础镜像 | Dockerfile 同时使用 Node、Go、Python、PostgreSQL 四个基础镜像；其中 Go/Bookworm 层较大 | 本次构建的最大耗时，受 NAS 外网、CPU、机械盘/存储池写入和 Docker layer 解压共同影响 |
| P0 | NAS 构建期间还需访问 apt、pip、npm | 最终镜像安装 Nginx/Supervisor/curl，Python 安装 requirements，前端执行 npm install | 任一镜像站慢、DNS/TLS 重试或跨境路由抖动都会造成长时间停顿；缓存失效后会重复发生 |
| P0 | backend 在 Alembic 迁移阶段退出或等待 | Supervisor 显示 backend FATAL，8000 端口未监听，Nginx 持续 502 | 镜像其实已经构建完成，但服务迟迟不能通过健康检查；容易被误判为“还在部署”并触发无效重建 |
| P1 | NAS 直接从 GitHub 拉取/下载 | 仓库本身较小，但 NAS 到 GitHub 的 DNS、TLS、路由、限速和重试不可控 | 不一定是本次最大字节量，却是高波动步骤；失败后往往整段重新执行 |
| P1 | 生产部署现场执行测试和编译 | Dockerfile 的 Go 阶段同时执行 `go test` 和两次 `go build`，前端执行 TypeScript 与 Vite 构建 | 占用 NAS CPU、内存和磁盘；构建失败会延长维护窗口；这些工作更适合在本地或 CI 完成 |
| P1 | 缓存只依赖 NAS 本地 BuildKit | 换机、清理 Docker、基础镜像更新或依赖清单变化都会使层缓存失效 | “第二次快”不能当作稳定部署能力，冷构建仍然很慢 |
| P2 | 前端依赖没有锁文件 | 当前仓库没有 `frontend/package-lock.json`，Dockerfile 使用 `npm install` | 每次可能重新解析不同依赖版本，降低可复现性，也使安装时间和缓存结果不稳定 |
| P2 | 若直接打包本地工作目录，会携带无用文件 | 本地项目约 145 MB，`frontend` 约 143 MB；`.dockerignore` 虽排除了 `node_modules`，但普通 tar/DSM 上传不会自动遵循 `.dockerignore` | 压缩、上传、NAS 解压以及升级脚本的 `chown -R` 都会变慢；本机 `node_modules` 也不能作为 NAS 运行依赖 |
| P2 | 升级脚本缺少分阶段计时和明确超时 | 只有最后健康检查轮询，没有记录下载、解压、build、migration、startup 各段耗时 | 无法快速判断是在网络、编译、数据库迁移还是健康检查处等待 |

### 5.2 本次耗时的准确结论

1. 源码体积很小，因此“GitHub 拉源码”是高波动因素，但不是最大的数据量；最大冷启动成本是四套基础镜像及 apt/pip/npm 依赖的下载和 layer 解压。
2. Go 编译本身不是主要瓶颈，但不应放在生产 NAS 的部署窗口内。生产机应消费已通过测试的不可变镜像，而不是临场完成测试、解析依赖和编译。
3. 镜像构建结束不等于部署结束。本次 backend 卡在数据库迁移阶段，使 Nginx 返回 502，是独立于构建速度的第二个 P0 问题。
4. 仅把源码改成本地上传，可以消除 GitHub 拉取波动，但 NAS 仍需下载基础镜像和依赖并完成编译，无法根治长耗时。要真正缩短部署，必须优先上传“已构建镜像包”。

### 5.3 目标部署路径

推荐把流程拆成离线准备和 NAS 切换两部分：

    本地/CI：测试 -> 构建目标架构镜像 -> 导出并压缩 -> 生成 SHA-256
                                      |
                                      v
    本地到 DSM：上传镜像包 + 部署包 + SHA256SUMS（局域网/便携介质）
                                      |
                                      v
    NAS 在线服务仍运行：校验 -> 解压/加载镜像 -> 配置预检 -> 数据库备份
                                      |
                                      v
    短暂停机窗口：停止旧容器 -> 启动新镜像 -> 迁移 -> ready 验收 -> 成功或回滚

这样 NAS 在停机前不访问 GitHub、apt、pip 或 npm，也不进行应用编译。维护窗口只包含备份确认、容器切换、迁移和验收。

## 6. 部署改善计划

### 6.1 P0：立即改为“本地制品上传，NAS 只加载和启动”

每个版本应形成三个发布物：

- `semi-vix-image-<version>-linux-<arch>.tar.gz`：已经构建完成的 Docker 镜像。
- `semi-vix-deploy-<version>.tar.gz`：只含 `docker-compose.yml`、部署/回滚脚本、`.env.example` 和版本清单；不得包含 `.env`、`.git`、`node_modules`、`dist`、`.venv`、日志或备份。
- `SHA256SUMS`：上述文件的 SHA-256，NAS 加载前必须校验。

目标架构必须与 NAS 一致。先在 NAS 执行 `uname -m` 或 `docker info --format '{{.Architecture}}'` 确认；Intel/AMD NAS 通常使用 `linux/amd64`，ARM NAS 使用 `linux/arm64`。Apple Silicon 本地构建 Intel NAS 镜像时必须显式指定 `--platform linux/amd64`，不能直接导出本机默认的 arm64 镜像。

NAS 侧的新流程应是：

1. 通过 DSM File Station、SMB 或便携介质上传三个发布物到独立的 `incoming/<version>/` 目录。
2. 执行 `sha256sum -c SHA256SUMS`，校验失败立即停止，不覆盖当前项目。
3. 解压部署包到新的 release 目录，不直接覆盖正在使用的源码目录。
4. 在旧服务仍运行时执行 `docker load`，并核对镜像的版本标签、架构和 digest。
5. 执行 `docker compose config --quiet` 和环境变量预检。
6. 完成宿主机数据库备份与 `pg_restore -l` 校验后，才进入短暂停机切换。
7. 使用精确版本标签启动，例如 `semi-vix-platform:0.4.0-<commit>`；生产 Compose 不使用 `latest`，也不包含 `build:`。

源码上传仍可作为备用方案，但只能上传干净源码包。可用 `git archive` 或显式排除规则生成，禁止将整个开发目录直接打包。源码路径仍需 NAS 编译，只解决 GitHub 拉取慢的问题，优先级低于镜像包路径。

### 6.2 P0：把构建与测试移出 NAS

- 本地或 CI 先运行 Python、Go 和前端测试，测试通过后再构建生产镜像。
- 镜像构建失败不触碰 NAS；NAS 仅接收已通过测试的镜像。
- Dockerfile 中的 `go test` 应移到独立验证任务；生产镜像构建只编译二进制。若出于保险保留，也只在本地/CI 执行，不再消耗 NAS 维护窗口。
- 增加并提交前端锁文件，改用 `npm ci`，确保依赖版本和安装过程可复现。
- 镜像用版本号和提交 SHA 双重标识，并记录构建平台；部署后记录实际 image digest。
- 本地机器不适合跨架构构建时，可由 CI 生成 `linux/amd64`/`linux/arm64` 镜像包，再由本地浏览器下载后上传 DSM。NAS 本身仍不访问 GitHub。

### 6.3 P0：将数据库迁移从“无提示等待”改成有界步骤

- `start-backend.sh` 对 `ensure_database.py`、`alembic upgrade head`、Uvicorn 启动分别打印开始时间、结束时间、退出码和耗时。
- 数据库连接、锁等待和迁移分别设置明确超时；超时后输出 `pg_stat_activity`/锁诊断提示并退出，不能无限等待。
- 部署前记录当前 `alembic_version` 和镜像目标版本，检查升级路径。
- `/health` 只用于进程存活；新增 `/ready`，至少检查迁移完成、数据库可读写、Go engine 可用、关键 Supervisor 进程运行。
- 健康验收失败时，不要再次执行 build。应保存容器日志和 Supervisor 状态，依据失败阶段回滚应用；只有 schema 确实发生不可逆变化时才考虑恢复数据库备份。

### 6.4 P1：保留源码构建时的加速措施

若临时无法分发镜像、必须在 NAS 构建，则至少执行以下优化：

- 在服务仍运行时先上传干净源码并执行 build，构建成功后再停旧容器；禁止先停服务再下载或编译。
- 固定基础镜像版本/digest，并建立受控更新节奏，避免部署当天意外拉取新层。
- 为 apt、pip、npm 和 Go 使用 BuildKit cache mount 或 NAS 上的受控缓存；缓存只用于加速，不能替代锁文件和版本固定。
- Python 优先在构建端生成 wheel，前端使用锁文件与 `npm ci`，避免每次重新解析依赖。
- 将不常变化的系统依赖做成稳定基础镜像；业务代码层变化时不重复安装 Nginx、Supervisor、Python 依赖。
- 不在升级脚本中对包含依赖缓存的大目录执行递归 `chown`；只处理本次 release 目录和确需改属主的文件。

### 6.5 P1：增加部署计时、状态与失败归因

升级脚本至少记录以下结构化阶段：

| 阶段 | 计时起止 | 成功标准 | 失败后动作 |
| --- | --- | --- | --- |
| artifact_verify | 上传完成后 | 所有 SHA-256 通过 | 删除/隔离损坏制品，旧服务不动 |
| image_load | 旧服务运行中 | 镜像存在、架构和标签正确 | 旧服务不动，重新准备制品 |
| config_preflight | 旧服务运行中 | Compose 与必需变量通过 | 旧服务不动，修正配置 |
| backup | 旧服务运行中 | 宿主机备份非空、`pg_restore -l` 通过 | 不进入切换 |
| switch | 停机窗口 | 新容器创建 | 失败立即收集日志并回滚容器 |
| migrate | 停机窗口 | Alembic 到目标 head | 超时/失败停止验收，按兼容性决定应用回滚或数据库恢复 |
| ready | 停机窗口 | `/ready`、Supervisor、端口、核心查询全部通过 | 保留现场并回滚 |

日志必须带版本、提交 SHA、镜像 digest、阶段名和秒数。构建日志与部署日志分开，避免把镜像准备时间算成业务停机时间。

### 6.6 分阶段落地与验收目标

| 阶段 | 交付内容 | 验收目标 |
| --- | --- | --- |
| 第 1 阶段 | 干净源码包、SHA-256、DSM 上传说明、分段计时 | NAS 不再通过 shell 从 GitHub 拉源码；能准确指出慢在哪一段 |
| 第 2 阶段 | 目标架构镜像包、无 `build:` 的生产 Compose、版本标签 | NAS 部署时不访问 GitHub/apt/pip/npm，不执行 npm/Go/Python 构建 |
| 第 3 阶段 | 迁移超时与日志、`/ready`、自动验收和应用回滚 | 迁移失败可定位，健康检查不再只表现为 Nginx 502 |
| 第 4 阶段 | 可选 CI 多架构构建、缓存治理、定期恢复演练 | 每个版本可重复部署，冷缓存也不扩大 NAS 维护窗口 |

在取得 3 次真实部署数据前不承诺绝对分钟数。首要服务级目标是：制品上传和镜像加载都在旧服务运行期间完成；正式停机窗口不包含外网下载和应用编译；部署失败时能在一个明确超时周期内进入回滚，而不是无限等待。

## 7. 短期修复计划（先恢复可用）

### S0：完成迁移故障定位

- 用 `psql` 验证数据库密码和目标库连接。
- 读取 `alembic_version`，确认当前迁移版本。
- 对 `alembic upgrade head` 增加明确的超时、日志和错误输出；不要让 Supervisor 只显示 `Exited too quickly`。
- 若是锁，定位持锁会话后先判断是否为残留迁移进程，再安全处理；禁止直接删除 PostgreSQL 数据目录。
- 若是密码不一致，先做一次已校验的数据库备份，再通过 `ensure_database.py` 或受控 SQL 同步角色密码。

### S1：修复健康检查和启动可观测性

- backend 启动脚本将数据库初始化、迁移和 uvicorn 分阶段打印耗时。
- Supervisor 为 backend、Go engine、scheduler 分别保留可读 stderr 日志。
- `/health` 只表示 HTTP 存活；新增 `/ready`，明确报告 PostgreSQL、迁移完成标记、Go engine 和最近一次合格计算。
- 迁移失败时容器状态必须明确为 `migration_failed`，而不是只显示 Nginx 502。

### S2：完善 NAS 升级脚本

将 `deploy/nas-upgrade.sh` 作为唯一推荐入口：

1. 从 DSM 上传目录读取本地准备好的版本化镜像包和部署包，并验证 SHA-256。
2. 备份数据库到宿主机 `backups/`，校验可恢复性；备份旧部署文件和 `.env`。
3. 在旧容器运行期间加载新镜像、检查架构/digest，并执行 Compose 配置预检。
4. 停止旧容器但不删除数据卷；禁止使用 `down -v`。
5. 用精确版本镜像执行 `up -d --no-build --remove-orphans`。
6. 等待 `/ready`，同时检查 Supervisor、迁移版本、端口和核心查询。
7. 失败时保留现场和日志，按镜像标签恢复旧应用；不得通过重新 build 掩盖迁移或配置错误。

## 8. 中长期实施路线

### 阶段 A：计算正确性与免费数据边界

- 修复累计方差 30D 插值、零报价尾部截断、K0 配对、交叉报价和异常价差处理。
- 将 Alpaca Indicative 与 trade-close proxy 固化为输入级元数据；严格模式不得消费 proxy。
- 结果记录方法版本、数据源、feed、price_type、batch_id、估值时间和报价新鲜度。
- 免费源能力不足时，明确输出“估算/不可用”，不通过静默回退制造正式指数。

### 阶段 B：历史、时间和自定义指数

- 按交易日对齐股票收益，使用复权价格，拒绝零方差和样本不足窗口。
- 期限采集按近远期限和两翼覆盖选择，不再固定截断前 120 个合约。
- 自定义指数拥有独立 universe、权重和数据能力检查，不能污染标准 SVIX。
- 将历史日价格和相关矩阵做成可重用表/缓存，减少每轮重复扫描数百天明细。

### 阶段 C：运行可靠性与可恢复性

- 任务使用可见的 retry/backoff、heartbeat、幂等键和失败原因。
- 日降采样、清理和迟到数据维护必须可重入，按实际计算依赖而非“某个 provider 有结果”删除数据。
- 备份恢复、迁移升级、容器重启和单容器队列恢复形成定期演练。
- 继续保持单 Docker；只有在真实负载证明需要独立扩容时，才评估拆分服务。

### 阶段 D：看板、认证和性能

- 看板明确区分正式、Indicative、trade-close proxy、过期、缺失和失败数据。
- 修复图表质量断点、设置连续编辑、MFA 恢复码、真实限流和错误分类。
- Go 继续承接高频数值与调度；Python 保留边界清晰的 API/迁移职责。
- 用 p95/p99 查询和采集耗时决定是否进一步将 Alpaca HTTP 采集迁入 Go，而不是仅凭语言偏好重写。

## 9. 版本与回滚策略

- 公式、相关性、权重、数据准入或来源语义变化必须提升方法版本；不能把新旧结果无说明拼接。
- 升级前至少保留：旧源码目录、`.env` 安全副本、数据库逻辑备份、当前镜像标签和 `docker compose ps` 输出。
- 回滚顺序：停止新容器 → 恢复旧源码/镜像 → 启动旧容器 → 只有在迁移已改变 schema 且不可逆时才按备份恢复数据库；禁止未经确认执行 `down -v`。
- 每次上线记录提交 SHA、Release、镜像 digest、数据库迁移版本、数据源配置和健康检查结果。

## 10. 新窗口交接结论

本次长耗时由两部分组成：NAS 冷构建的外网下载、依赖安装和 layer 解压成本，以及 backend 在数据库迁移阶段未成功进入 8000 端口。Go 编译本身不是主因，GitHub 拉源码是应消除的高波动步骤，但只改为上传源码仍不能消除 NAS 编译成本。

后续默认方案应是：本地或 CI 完成测试与目标架构镜像构建，本地将校验过的镜像包和部署包上传 DSM，NAS 在旧服务运行时完成校验和 `docker load`，最后只用短窗口完成备份、容器切换、迁移和 `/ready` 验收。当前功能上仍须先完成 Alembic/数据库锁与密码诊断；在 backend 健康、Nginx `/health` 返回 200、Supervisor 全部关键进程 RUNNING、备份可恢复之前，不应把 NAS 部署标记为 v0.3 验收完成。

## 11. 新窗口 NAS 升级交接单（保留历史数据与配置）

### 11.1 本次部署目标与不可违反的约束

本次操作是原部署的**版本升级**，不是全新安装。升级完成后必须同时保留：

- PostgreSQL 中全部历史行情、SVIX 历史、自定义指数、任务记录、管理员、安全设置、系统设置和 provider 凭据。
- 原 `.env` 中全部配置及密钥，特别是 `POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`SECRET_KEY`、`SECRET_ENCRYPTION_KEY`、`CREDENTIAL_MASTER_KEY`、端口和数据源设置。
- 原 DSM 反向代理、端口映射、持久化卷和 Compose 项目标识。

以下操作禁止执行：

- 禁止 `docker compose down -v`、`docker volume rm`、`docker system prune --volumes`，以及任何删除 PostgreSQL 数据目录/卷的操作。
- 禁止用 `.env.example` 覆盖现有 `.env`，禁止重新生成加密密钥或数据库密码。更换加密密钥会导致已保存的 provider 凭据无法解密。
- 禁止因新版本目录名不同而直接使用新的 Compose 项目名；这会创建新的 `postgres_data` 卷并表现为“历史数据消失”。
- 禁止在未完成宿主机逻辑备份、配置备份、旧镜像标签保留和恢复性校验前停止/替换旧容器。
- 禁止在迁移或启动失败后反复 build、初始化数据库或删除卷。先保留日志并判断是迁移、密码、锁还是项目名/卷挂载错误。

### 11.2 上传到 NAS 的文件

优先上传以下三个文件到 NAS 的独立目录，例如：

    /volume1/homes/dexterma/docker/incoming/v0.3.0-b5eddf1/

文件为：

    semi-vix-image-v0.3.0-b5eddf1-linux-amd64.tar.gz
    SHA256SUMS
    README-NAS.txt

若 DSM 图形界面只接受未压缩 Docker archive，则上传 `.tar` 文件代替 `.tar.gz`。不要上传本机整个开发目录或 `frontend/node_modules`。

### 11.3 第一步：只读识别当前部署，确认数据卷身份

在任何变更前执行并保存输出。第 11.3 至 11.8 节的命令应在同一个 SSH shell 中连续执行，以保留 `project_name`、`postgres_volume`、`stamp`、`backup_dir` 等变量；若 SSH 断开，先重新执行本节和第 11.4 节中的变量定义，确认输出与原记录一致后再继续：

    cd /volume1/homes/dexterma/docker/semi-vix-platform
    sudo -v
    sudo docker compose ps
    current_container="$(sudo docker compose ps --all -q app)"
    test -n "${current_container}"
    project_name="$(sudo docker inspect "${current_container}" --format '{{ index .Config.Labels "com.docker.compose.project" }}')"
    current_image_id="$(sudo docker inspect "${current_container}" --format '{{.Image}}')"
    postgres_volume="$(sudo docker inspect "${current_container}" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}')"
    printf 'project=%s\ncontainer=%s\nimage=%s\npostgres_volume=%s\n' \
      "${project_name}" "${current_container}" "${current_image_id}" "${postgres_volume}"
    test -n "${project_name}"
    test -n "${postgres_volume}"
    sudo docker volume inspect "${postgres_volume}"

预期 Compose 项目名通常为 `semi-vix-platform`，卷名通常为 `semi-vix-platform_postgres_data`，但必须以实际输出为准。若无法取得当前容器、项目名或 `/var/lib/postgresql/data` 挂载卷，立即停止，不得继续升级。

### 11.4 第二步：在旧服务仍运行时完成三类备份

先创建仅当前用户可访问的宿主机备份目录：

    stamp="$(date +%Y%m%d-%H%M%S)"
    backup_dir="/volume1/homes/dexterma/docker/semi-vix-platform/backups/${stamp}"
    install -d -m 0700 "${backup_dir}"

备份原配置和 Compose 文件，不修改原文件：

    cp -p .env "${backup_dir}/.env.before-upgrade"
    cp -p docker-compose.yml "${backup_dir}/docker-compose.before-upgrade.yml"
    chmod 0600 "${backup_dir}/.env.before-upgrade"
    sha256sum .env docker-compose.yml > "${backup_dir}/config.sha256"

为当前运行镜像增加可回滚标签，避免加载新的 `latest` 后失去旧镜像引用：

    sudo docker image tag "${current_image_id}" "semi-vix-platform:pre-upgrade-${stamp}"
    sudo docker image inspect "semi-vix-platform:pre-upgrade-${stamp}"

从当前单容器内导出 PostgreSQL 逻辑备份到宿主机：

    db_backup="${backup_dir}/semi-vix-before-${stamp}.backup"
    sudo docker compose -p "${project_name}" exec -T app bash -lc \
      'PGPASSWORD="$POSTGRES_PASSWORD" /usr/lib/postgresql/16/bin/pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
      > "${db_backup}"
    test -s "${db_backup}"
    sudo docker compose -p "${project_name}" exec -T app \
      /usr/lib/postgresql/16/bin/pg_restore -l < "${db_backup}" > /dev/null
    sha256sum "${db_backup}" | tee "${db_backup}.sha256"

备份必须位于 NAS 宿主机，而不能只放在 PostgreSQL 数据卷内部。上述任一步失败都不得进入容器切换。

### 11.5 第三步：记录升级前数据基线

至少记录迁移版本、数据库大小和关键表行数；只记录数量，不输出凭据内容：

    baseline_file="${backup_dir}/database-baseline-before.txt"
    sudo docker compose -p "${project_name}" exec -T app bash -lc \
      'PGPASSWORD="$POSTGRES_PASSWORD" /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' \
      <<'SQL' | tee "${baseline_file}"
    select 'alembic_version=' || coalesce((select version_num from alembic_version limit 1), 'missing');
    select 'database_size=' || pg_database_size(current_database());
    select 'svix_history=' || count(*) from svix_history;
    select 'svix_daily=' || count(*) from svix_daily;
    select 'option_snapshot=' || count(*) from option_snapshot;
    select 'stock_snapshot=' || count(*) from stock_snapshot;
    select 'system_settings=' || count(*) from system_settings;
    select 'provider_credentials=' || count(*) from provider_credentials;
    select 'custom_indices=' || count(*) from custom_indices;
    select 'custom_index_history=' || count(*) from custom_index_history;
    SQL

如果旧 schema 尚无其中某张表，应单独记录该事实，不要为了让基线命令通过而执行迁移或修改数据库。

### 11.6 第四步：校验并加载离线镜像，不停止旧服务

在上传目录执行：

    cd /volume1/homes/dexterma/docker/incoming/v0.3.0-b5eddf1
    sha256sum -c SHA256SUMS
    sudo docker load -i semi-vix-image-v0.3.0-b5eddf1-linux-amd64.tar.gz
    sudo docker image inspect semi-vix-platform:0.3.0-b5eddf1-amd64 \
      --format 'os={{.Os}} arch={{.Architecture}} id={{.Id}} tags={{json .RepoTags}}'

必须确认输出包含 `os=linux arch=amd64`。本机构建环境记录的镜像 ID 为：

    sha256:b86880f7e9d219a1d7c3cd4962964442dd5e172d8ae3fd6722cb2d3cddeb3811

较旧 DSM/Docker 在导入多平台格式归档后，`docker image inspect` 显示的本地 ID 可能是配置 digest，而不是上述 manifest-list ID，因此不得仅因 ID 显示不同判定制品损坏；制品真实性以 `SHA256SUMS` 校验通过、标签正确和 `os=linux arch=amd64` 为准。镜像归档同时提供 `semi-vix-platform:latest`，因此兼容当前 `docker-compose.yml`。完成镜像加载前旧容器应持续运行。

### 11.7 第五步：使用相同 Compose 项目和原 `.env` 执行升级

返回原项目目录；不要在 `incoming/` 或带版本号的新目录直接启动 Compose：

    cd /volume1/homes/dexterma/docker/semi-vix-platform
    test -s .env
    sudo docker compose -p "${project_name}" config --quiet
    sudo docker compose -p "${project_name}" up -d --no-build --force-recreate app

这里不需要先执行 `down`。Compose 应替换应用容器并把**同一个** `${postgres_volume}` 重新挂载到 `/var/lib/postgresql/data`。启动后立即复核：

    new_container="$(sudo docker compose -p "${project_name}" ps -q app)"
    new_postgres_volume="$(sudo docker inspect "${new_container}" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}')"
    printf 'old_volume=%s\nnew_volume=%s\n' "${postgres_volume}" "${new_postgres_volume}"
    test "${new_postgres_volume}" = "${postgres_volume}"

若卷名不一致，立即停止新容器并进入回滚；不要在新空卷中继续初始化或写入业务数据。原卷此时仍然存在，历史数据没有被删除。

### 11.8 第六步：迁移、健康与数据保留验收

先观察启动与迁移，不要因 502 直接重建镜像：

    sudo docker compose -p "${project_name}" logs --tail=300 app
    sudo docker compose -p "${project_name}" exec -T app supervisorctl status
    sudo docker compose -p "${project_name}" exec -T app bash -lc \
      'PGPASSWORD="$POSTGRES_PASSWORD" /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version_num from alembic_version"'
    sudo docker compose -p "${project_name}" exec -T app curl --fail --silent http://127.0.0.1/health
    sudo docker compose -p "${project_name}" exec -T app curl --fail --silent http://127.0.0.1:8090/health

最终验收必须全部满足：

1. 新容器挂载卷名与升级前 `${postgres_volume}` 完全一致。
2. 在原项目目录执行 `sha256sum -c "${backup_dir}/config.sha256"` 成功；`.env` 没有用示例文件覆盖，也没有更换三个密钥或数据库密码。
3. PostgreSQL 可连接，Alembic 已到镜像目标 head，迁移日志无失败或无限等待。
4. Supervisor 中 `postgres`、`backend`、`go-engine`、`scheduler`、`nginx` 全部为 `RUNNING`。
5. Nginx `/health` 与 Go `/health` 返回成功，不再持续出现 backend 8000 端口拒绝连接。
6. 再次查询第 11.5 节的关键表；历史表行数不得无故减少，`system_settings`、`provider_credentials`、自定义指数和管理员登录仍可用。
7. DSM 入口、端口、HTTPS/反向代理、登录、历史图表和数据源配置完成实际页面验证。

只有以上项目全部通过，才可把版本升级标记为成功。旧镜像回滚标签、数据库备份、`.env` 备份和旧部署文件至少保留到完成一次稳定运行与恢复验证之后。

### 11.9 失败回滚原则

- 迁移尚未改变 schema 时：使用 `semi-vix-platform:pre-upgrade-${stamp}` 恢复旧镜像标签，并用相同 `${project_name}`、原 `.env` 和原 `${postgres_volume}` 重建旧容器。
- 迁移已改变 schema 但应用启动失败时：先保留新容器日志和当前数据库现场，再判断迁移是否向后兼容。不能仅切回旧应用后继续写入不兼容 schema。
- 只有确认需要数据库恢复时，才从 `${db_backup}` 恢复；恢复前还要再保存失败现场的数据库副本。不得用删除 volume 的方式“恢复”。
- 若只是新容器误挂新空卷：停止新容器，使用正确的原 Compose 项目名重新挂载 `${postgres_volume}`；不要把空卷内容覆盖到原卷。
