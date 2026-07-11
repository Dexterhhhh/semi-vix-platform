# Semi-VIX Platform — Phase 1

Semi-VIX 是一个计划自托管部署的半导体波动率分析平台。本阶段只交付生产基础：FastAPI、PostgreSQL、单管理员认证、TOTP MFA、JWT 会话和配置体系。不含行情接入、SVIX 计算、交易能力或前端仪表盘。

## 本阶段内容

- PostgreSQL/Alembic 初始迁移：`admin_account`、`admin_security`、`system_settings`、`sessions`
- 只允许一位管理员的数据库约束与 Docker 启动初始化
- Argon2id 密码哈希、AES-256-GCM 加密的 TOTP 秘钥和恢复代码
- 登录、MFA 设置、MFA 验证、JWT 访问令牌及 HttpOnly 刷新 Cookie
- CORS 配置、限流预留配置与健康检查 `GET /health`

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

对于 Docker 内服务，使用 `host.docker.internal` 访问宿主机上的 TWS/IB Gateway 或 Futu OpenD。IBKR 必须启用 API、只读模式和美股期权行情权限；Futu OpenD 必须启用美股报价权限。Futu 部署额外执行 `pip install -r requirements-futu.txt`，以避免在未使用 Futu 时下载其大型可选依赖。通过 `POST /api/provider/configure` 保存的可选 API 凭据会以 AES-256-GCM 加密写入数据库，响应从不返回明文。`GET /api/provider/status` 会报告当前提供商与连通性。

行情采集服务位于 `backend/app/services/market_collector.py`，会统一保存 SOXX、MU、SKHY、NVDA、AMD、AVGO 的现货与期权快照。调度器仅保留占位接口，Celery 将在后续阶段接入。

## 后续 Phase 2

React 界面、Redis/Celery 实际调度、SVIX 计算、历史可视化仍未实现。IBKR/Futu 的只读行情架构、加密配置与快照存储已在 Phase 2 实现。
