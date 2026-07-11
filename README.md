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

## 后续 Phase 2

React 前端、Redis/Celery、IBKR/Futu 只读行情接入、期权快照、SVIX 计算与历史可视化仍未实现。
