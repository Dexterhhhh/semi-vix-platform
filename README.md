# Semi-VIX Platform — Phase 4

Semi-VIX 是一个计划自托管部署的半导体波动率分析平台。当前交付 FastAPI、PostgreSQL、单管理员认证、TOTP MFA、JWT 会话、独立的只读行情数据层，以及 VIX 风格 SVIX 计算引擎。不含交易能力或完整前端仪表盘。

## 本阶段内容

- PostgreSQL/Alembic 初始迁移：`admin_account`、`admin_security`、`system_settings`、`sessions`
- 只允许一位管理员的数据库约束与 Docker 启动初始化
- Argon2id 密码哈希、AES-256-GCM 加密的 TOTP 秘钥和恢复代码
- 登录、MFA 设置、MFA 验证、JWT 访问令牌及 HttpOnly 刷新 Cookie
- CORS 配置、限流预留配置与健康检查 `GET /health`
- IBKR TWS/IB Gateway 与 Futu OpenD 的统一只读行情接口
- SOXX、MU、SKHY、NVDA、AMD、AVGO 的现货、期权合约和期权报价标准化快照
- AES-256-GCM 加密的提供商凭据、受 MFA 会话保护的提供商配置 API 与配置审计事件

## Ubuntu 服务器一键安装 Docker（新手）

适用于全新的 Ubuntu 22.04 / 24.04 服务器。先通过 SSH 登录服务器，然后执行 Docker 官方便捷安装脚本：

```sh
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh && sudo sh /tmp/get-docker.sh && sudo usermod -aG docker "$USER"
```

> Docker 官方将 `get.docker.com` 便捷脚本定位为开发、测试或快速初始化用途。正式生产服务器若有严格的版本锁定与升级要求，应改用 [Docker 官方 Ubuntu APT 仓库安装步骤](https://docs.docker.com/engine/install/ubuntu/)。不要在来源不可信的服务器上直接执行网络脚本；可先运行 `sudo sh /tmp/get-docker.sh --dry-run` 查看将要执行的操作。

安装后退出 SSH 并重新登录，让 Docker 用户组权限生效，然后验证：

```sh
docker --version
docker compose version
docker run --rm hello-world
```

如果出现 `permission denied`，说明当前 SSH 会话尚未取得新的用户组权限，请重新登录服务器，或暂时在 Docker 命令前加 `sudo`。

### 在 Ubuntu 上部署 Semi-VIX

安装 Git、克隆本项目并创建本地环境文件：

```sh
sudo apt update && sudo apt install -y git
git clone https://github.com/YOUR_GITHUB_USERNAME/semi-vix-platform.git
cd semi-vix-platform
cp .env.example .env
nano .env
```

必须修改 `.env` 中的管理员密码、PostgreSQL 密码以及所有 `SECRET_*`、`CREDENTIAL_MASTER_KEY` 示例值。`.env` 包含敏感信息，绝不能提交到 GitHub。

安装时可以在 `.env` 中自定义面板端口：

```dotenv
SVIX_BIND_ADDRESS=127.0.0.1
SVIX_HTTP_PORT=18443
```

- `SVIX_HTTP_PORT` 填写 `1`～`65535` 的可用端口即可自定义。
- `SVIX_HTTP_PORT` 留空时，Docker 会自动分配随机可用端口，这是默认行为。
- `SVIX_BIND_ADDRESS=127.0.0.1` 仅允许服务器本机和 SSH 隧道访问，安全性更高。
- 只有已配置云防火墙和 HTTPS 反向代理时，才应考虑设置为 `0.0.0.0`。

保存配置后，一条命令构建并启动全部服务：

```sh
docker compose up -d --build
```

检查运行状态和健康接口：

```sh
docker compose ps
docker compose port nginx 80
```

`docker compose port nginx 80` 会显示实际地址，例如 `127.0.0.1:32768`。使用显示的端口检查健康状态：

```sh
curl -fsS http://127.0.0.1:32768/health
```

不建议把未配置 HTTPS 的面板端口直接暴露到公网。最简单的安全访问方式是在自己的电脑建立 SSH 隧道；把示例中的 `32768` 替换成服务器实际显示的随机或自定义端口：

```sh
ssh -L 8080:localhost:32768 SERVER_USER@SERVER_IP
```

保持 SSH 会话开启，然后在本机浏览器访问 `http://localhost:8080`。正式公网部署应在云防火墙中限制来源，并在平台前配置 HTTPS 反向代理。

常用维护命令：

```sh
docker compose logs -f
docker compose restart
docker compose down          # 停止服务，保留 PostgreSQL 数据卷
docker compose down -v       # 同时删除数据卷；会永久删除数据库，请谨慎使用
```

## 本地安装

需要 Python 3.12 和 PostgreSQL。复制环境配置并填入真实随机值：

```sh
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

## Docker 启动

```sh
cp .env.example .env
# 修改 .env 中全部示例密码与密钥
docker compose up -d --build
```

Docker 环境不会向宿主机公开 backend 的 `8000` 端口；健康检查统一通过 Nginx 的随机或自定义面板端口访问。仅在上面的非 Docker 本地开发模式中，FastAPI 才直接监听 `http://localhost:8000`。

## 环境变量

| 变量 | 用途 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL SQLAlchemy 连接串 |
| `SECRET_KEY` | JWT 签名密钥 |
| `SECRET_ENCRYPTION_KEY` | URL-safe Base64 编码的 32 字节 AES-256-GCM 密钥 |
| `SVIX_ADMIN_USERNAME` / `SVIX_ADMIN_PASSWORD` | 首次启动时创建的唯一管理员 |
| `JWT_EXPIRE_MINUTES` | 访问令牌有效期，默认 15 分钟 |
| `REFRESH_EXPIRE_DAYS` | 刷新 Cookie 有效期，默认 7 天 |
| `CORS_ORIGINS` | 逗号分隔的允许来源 |
| `SVIX_BIND_ADDRESS` | 面板绑定地址，默认 `127.0.0.1`；不建议无保护地使用 `0.0.0.0` |
| `SVIX_HTTP_PORT` | 面板宿主机端口；留空时由 Docker 随机分配 |
| `DATA_PROVIDER` | `IBKR` 或 `FUTU`；启动时严格校验 |
| `IBKR_HOST` / `IBKR_PORT` / `IBKR_CLIENT_ID` | TWS 或 IB Gateway API socket 地址、端口和客户端 ID |
| `FUTU_HOST` / `FUTU_PORT` | Futu OpenD 报价服务地址和端口 |
| `CREDENTIAL_MASTER_KEY` | 独立的 URL-safe Base64 32 字节 AES-256-GCM 密钥，用于提供商凭据 |

## 首次登录与 MFA

1. 调用 `POST /api/auth/login`，传入管理员用户名和密码，得到临时 MFA 设置令牌。
2. 调用 `POST /api/auth/setup-mfa`，仅传临时令牌，得到 `provisioning_uri`；用认证器扫描或导入该 URI。
3. 再次调用 `/api/auth/setup-mfa`，带临时令牌及认证器生成的六位代码，完成启用并取得 JWT。
4. 之后登录会返回 MFA 验证临时令牌；调用 `POST /api/auth/verify-mfa` 取得 JWT 和刷新 Cookie。

## 测试

```sh
PYTHONPATH=backend pytest backend/tests -q
```

## 行情数据配置（Phase 2）

Phase 2 新增了独立于券商的只读行情层，支持 `IBKR` 与 `FUTU`。绝不包含下单、交易或账户资金 API。

在 `.env` 中选择默认来源并配置网关地址：

```dotenv
DATA_PROVIDER=IBKR
IBKR_HOST=host.docker.internal
IBKR_PORT=7497
IBKR_CLIENT_ID=19
FUTU_HOST=host.docker.internal
FUTU_PORT=11111
CREDENTIAL_MASTER_KEY=<独立的 32 字节 Base64 AES-256-GCM 密钥>
```

对于 Docker 内服务，使用 `host.docker.internal` 访问宿主机上的 TWS/IB Gateway 或 Futu OpenD。Compose 不公开 FastAPI backend、PostgreSQL、Redis 或券商网关端口；只由 Nginx 提供一个随机或自定义的面板端口。不要将 TWS、IB Gateway 或 OpenD 暴露到互联网。

IBKR 使用 [`ib_insync`](https://ib-insync.readthedocs.io/) 连接 TWS/IB Gateway API socket。需要在网关启用 API 访问、配置相应主机/端口/客户端 ID，并具备美股及期权行情权限。请求仅进行合约发现和行情订阅，快照完成后会取消订阅；不调用任何订单、持仓或资金接口。

Futu 使用 `OpenQuoteContext`，不创建交易上下文。部署选择 `FUTU` 时设定 `INSTALL_FUTU=true` 并重新构建后端镜像（本地 Python 部署则执行 `pip install -r requirements-futu.txt`），并确保 OpenD 已运行且具有美股报价权限。期权动态报价会按需订阅并在读取后释放，仍受 OpenD 的订阅配额限制。

通过 `POST /api/provider/configure` 保存的可选 API 凭据会以 AES-256-GCM 加密写入数据库；每次加密都使用新的随机 nonce，响应和审计事件均不包含明文。`CREDENTIAL_MASTER_KEY` 必须独立生成，不能复用 JWT 密钥，`.env` 绝不可提交。前端只与本后端通信，绝不会得到解密后的凭据。

受已完成 MFA 验证的 JWT 保护的接口：

- `GET /api/provider/status`：返回非敏感配置与连通状态。
- `POST /api/provider/configure`：保存加密凭据并记录无敏感字段的审计事件。
- `POST /api/provider/test-connection`：在有界超时内测试连接并返回净化后的错误。
- `GET /api/provider/configuration`：仅返回 host、port、client ID 与是否存在凭据等掩码元数据。

行情采集服务位于 `backend/app/services/market_collector.py`，会统一保存 SOXX、MU、SKHY、NVDA、AMD、AVGO 的现货与期权快照。每个标的使用独立数据库 savepoint；如 SKHY 没有可用期权链，不会伪造零值，也不会回滚其他标的已采集的数据。调度器仅保留占位接口，Celery 将在后续阶段接入。

实时 IBKR/Futu 连通性和行情权限未在仓库测试中验证；它们需要上述外部网关及有效的市场数据权限。

## 测试

当前可通过的本地测试命令：

```sh
PYTHONPATH=backend pytest backend/tests -q
docker compose exec -T backend pytest -q
```

## 后续阶段

React 界面、Redis/Celery 实际调度和历史可视化仍未实现。SVIX 数学引擎与历史结果存储已在 Phase 3 实现；异步历史任务调度将在后续阶段接入。

## SVIX Methodology（Phase 3）

Phase 3 新增完全独立于 IBKR/Futu 的计算引擎。它只接收 Phase 2 已标准化的期权快照，不会导入券商 SDK，也不具备任何交易能力。

- 每个到期日根据有效 bid/ask 中间价计算 put-call parity forward：`F = K + exp(RT) × (C - P)`；缺失中间价默认不会使用 last price 或虚构零值。
- 选择不高于 forward 的最大 `K0`；若不存在会记录最近行权价回退。K0 必须同时具备有效 call 与 put，采用两者中间价平均值。
- K0 以下使用 puts、K0 以上使用 calls；通过 `ΔK` 与 VIX 式方差复制公式计算单到期日的年化隐含方差。
- 使用包围 30 个日历日的两个到期日对**方差**插值，而不是线性插值波动率。
- Core 为 SOXX；Memory 为 MU/SKHY（各 50%）；AI 为 NVDA/AMD/AVGO（50%/25%/25%）；总 SVIX 权重为 50%/30%/20%。
- 相关性以 60、120、252 日历史对数收益率矩阵按 50%/30%/20% 加权，组合方差为 `wᵀΣw`。
- 可选的 SOXX 成分权重输入会减少与直接股票仓位重复的暴露，并重新归一化。

计算结果写入 `svix_history`。受 MFA 会话保护的接口：

- `GET /api/svix/current`
- `GET /api/svix/history?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- `POST /api/svix/calculate`，请求体包含 `start_date`、`end_date` 与 `frequency`（`daily` 或 `weekly`）。

历史计算要求每个标的已有足够的期权快照，并至少有 252 个对齐历史收益率；数据不足时会跳过该日期，不会写入零值。

## Dashboard 与后台任务（Phase 4）

Phase 4 将平台扩展为持续运行的自托管分析应用。启动完整栈：

```sh
docker compose up -d --build
```

服务包括：Nginx 网关、React Dashboard、FastAPI 后端、Celery Worker、Celery Beat、PostgreSQL 和 Redis。FastAPI backend 不再映射固定宿主机端口；使用 `docker compose port nginx 80` 查询面板入口，并通过该入口的 `/health` 执行健康检查。

仪表盘使用现有用户名、密码和 TOTP MFA 登录，不保存券商凭据或解密后的密钥。登录后可查看 SVIX、Core/Memory/AI 组件、历史曲线、历史计算作业、数据提供商状态与系统状态。

- `POST /api/jobs/create` 创建历史 SVIX 计算任务；Worker 会持续写入作业进度与结果摘要。
- `GET /api/jobs` 和 `GET /api/jobs/{id}` 查询任务状态。
- `GET` / `PUT /api/settings` 管理刷新间隔、标的选择与预留手动权重设置；所有设置接口均需要现有 MFA JWT。
- Celery Beat 默认每 15 分钟安排行情刷新和最新 SVIX 计算；可通过 `MARKET_REFRESH_MINUTES`、`SVIX_CALCULATION_MINUTES` 与 `REDIS_URL` 配置。

Worker 日志采用结构化 JSON 事件，不记录令牌、凭据或券商原始响应。Broker 网关端口不会由 Compose 暴露；浏览器仅经 Nginx 与后端 API 通信。
