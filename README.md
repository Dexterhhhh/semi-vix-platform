# Semi-VIX Platform — Phase 2

Semi-VIX 是一个计划自托管部署的半导体波动率分析平台。本阶段交付 FastAPI、PostgreSQL、单管理员认证、TOTP MFA、JWT 会话，以及独立的只读行情数据层。不含 SVIX 计算、交易能力或完整前端仪表盘。

## 本阶段内容

- PostgreSQL/Alembic 初始迁移：`admin_account`、`admin_security`、`system_settings`、`sessions`
- 只允许一位管理员的数据库约束与 Docker 启动初始化
- Argon2id 密码哈希、AES-256-GCM 加密的 TOTP 秘钥和恢复代码
- 登录、MFA 设置、MFA 验证、JWT 访问令牌及 HttpOnly 刷新 Cookie
- CORS 配置、限流预留配置与健康检查 `GET /health`
- IBKR TWS/IB Gateway 与 Futu OpenD 的统一只读行情接口
- SOXX、MU、SKHY、NVDA、AMD、AVGO 的现货、期权合约和期权报价标准化快照
- AES-256-GCM 加密的提供商凭据、受 MFA 会话保护的提供商配置 API 与配置审计事件

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

后端监听 `http://localhost:8000`，健康检查地址为 `http://localhost:8000/health`。

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

对于 Docker 内服务，使用 `host.docker.internal` 访问宿主机上的 TWS/IB Gateway 或 Futu OpenD。Compose 默认只公开平台后端的 `8000` 端口，不公开券商网关端口；不要将 TWS、IB Gateway 或 OpenD 暴露到互联网。

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

React 界面、Redis/Celery 实际调度、SVIX 计算、历史可视化仍未实现。IBKR/Futu 的只读行情架构、加密配置与快照存储已在 Phase 2 实现。
