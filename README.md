# Semi-VIX Platform

Semi-VIX 是一个私有、自托管的半导体波动率分析平台。系统通过只读行情接口采集期权数据，计算 SVIX、Core、Memory 和 AI Semiconductor Volatility，并提供历史图表、后台计算任务、数据保留策略和系统状态面板。

支持的行情来源：

- Interactive Brokers TWS / IB Gateway
- Futu OpenD

平台不包含下单、撤单、持仓或资金操作，不能用于交易。

## 系统要求

- Ubuntu 22.04 或 24.04（推荐）
- 2 核 CPU、4 GB 内存、20 GB 可用磁盘起步
- 可以访问 Docker Hub、PyPI 和 npm 镜像
- 已运行并正确授权的 IBKR TWS / IB Gateway 或 Futu OpenD
- 对应的美股及期权行情权限

## 1. 在 Ubuntu 安装 Docker

通过 SSH 登录服务器，执行 Docker 官方便捷安装脚本：

```sh
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
sudo sh /tmp/get-docker.sh
sudo usermod -aG docker "$USER"
```

退出 SSH 并重新登录，让 Docker 用户组权限生效，然后验证：

```sh
docker --version
docker compose version
docker run --rm hello-world
```

Docker 官方将便捷脚本定位为快速初始化方式。需要锁定 Docker 版本或制定升级策略的生产服务器，请使用 [Docker 官方 Ubuntu APT 安装说明](https://docs.docker.com/engine/install/ubuntu/)。可以先执行 `sudo sh /tmp/get-docker.sh --dry-run` 检查脚本将进行的操作。

## 2. 下载项目

```sh
sudo apt update
sudo apt install -y git openssl
git clone https://github.com/YOUR_GITHUB_USERNAME/semi-vix-platform.git
cd semi-vix-platform
cp .env.example .env
```

## 3. 配置密钥和管理员

生成 JWT 密钥：

```sh
openssl rand -hex 32
```

分别执行两次以下命令，生成两个不同的 AES-256-GCM 密钥：

```sh
python3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

编辑配置：

```sh
nano .env
```

至少修改以下字段：

```dotenv
SECRET_KEY=填入随机JWT密钥
SECRET_ENCRYPTION_KEY=填入第一个AES密钥
CREDENTIAL_MASTER_KEY=填入第二个AES密钥
SVIX_ADMIN_USERNAME=admin
SVIX_ADMIN_PASSWORD=设置一个高强度密码
POSTGRES_PASSWORD=设置另一个高强度密码
```

同步修改 `DATABASE_URL` 中的 PostgreSQL 密码，使其与 `POSTGRES_PASSWORD` 一致：

```dotenv
DATABASE_URL=postgresql+psycopg://svix:你的数据库密码@postgres:5432/svix
```

`.env` 包含所有真实密钥，已被 Git 忽略。不要上传、复制到工单或发送给其他人。

## 4. 设置面板访问端口

默认配置只绑定服务器本机，并由 Docker 随机选择可用端口：

```dotenv
SVIX_BIND_ADDRESS=127.0.0.1
SVIX_HTTP_PORT=
```

如需固定端口，可填写任意未占用的 `1`～`65535` 端口：

```dotenv
SVIX_BIND_ADDRESS=127.0.0.1
SVIX_HTTP_PORT=18443
```

除非已经配置云防火墙和 HTTPS 反向代理，否则不要将 `SVIX_BIND_ADDRESS` 改为 `0.0.0.0`。FastAPI、PostgreSQL、Redis 和券商网关端口均不会映射到宿主机。

## 5. 选择行情提供商

### IBKR

确保 TWS 或 IB Gateway 已启用 API、设置为只读模式，并配置：

```dotenv
DATA_PROVIDER=IBKR
IBKR_HOST=host.docker.internal
IBKR_PORT=7497
IBKR_CLIENT_ID=19
INSTALL_FUTU=false
```

常见 IBKR 端口：TWS 模拟账户 `7497`，TWS 实盘账户 `7496`，IB Gateway 模拟账户 `4002`，IB Gateway 实盘账户 `4001`。请以自己的网关设置为准。

### Futu

确保 OpenD 已启动并已登录，然后配置：

```dotenv
DATA_PROVIDER=FUTU
FUTU_HOST=host.docker.internal
FUTU_PORT=11111
INSTALL_FUTU=true
```

修改 `INSTALL_FUTU` 后必须重新构建镜像。平台只创建 `OpenQuoteContext`，不会创建交易上下文。

连接参数也可以在首次登录后的“设置与系统状态”页面修改。可选凭据会使用独立的 AES-256-GCM 密钥加密保存，页面不会回显明文。

## 6. 启动平台

```sh
docker compose up -d --build
```

检查服务状态：

```sh
docker compose ps
```

查询面板实际端口：

```sh
docker compose port nginx 80
```

随机端口示例输出：

```text
127.0.0.1:32768
```

使用实际端口检查健康状态：

```sh
curl -fsS http://127.0.0.1:32768/health
```

成功时返回：

```json
{"status":"ok"}
```

## 7. 安全访问面板

推荐通过 SSH 隧道访问。把 `32768` 替换成服务器实际端口：

```sh
ssh -L 8080:localhost:32768 SERVER_USER@SERVER_IP
```

保持 SSH 会话开启，在本机浏览器访问：

```text
http://localhost:8080
```

如果需要公网访问，应在平台前配置 HTTPS 反向代理，并通过云防火墙限制来源地址。不要直接公开随机或固定的 HTTP 面板端口。

## 8. 首次登录和 MFA

1. 使用 `.env` 中的 `SVIX_ADMIN_USERNAME` 和 `SVIX_ADMIN_PASSWORD` 登录。
2. 将页面提供的 TOTP 信息导入 Google Authenticator、Microsoft Authenticator 或 Authy。
3. 输入认证器当前显示的 6 位验证码完成绑定。
4. 保存页面提供的恢复代码，并放在离线安全位置。
5. 后续登录必须同时提供密码和动态验证码。

系统只支持一个管理员，不提供注册、多用户或角色管理。

## 9. 使用面板

### Dashboard

查看当前 SVIX、Core、Memory、AI 指标及历史曲线。没有足够期权链或历史收益数据时，系统不会生成虚假的零值。

### 历史计算

选择起止日期和频率后创建后台任务。计算通过 Redis/Celery 异步执行，可在页面查看进度和结果。

### 数据提供商

在设置页选择 IBKR 或 Futu，填写 Host、端口及 IBKR Client ID，然后保存并测试连接。平台同时只启用一个行情来源。

### 数据生命周期

默认策略：

- 原始期权快照保留 3 天
- 只清理已有成功计算结果覆盖的日期
- 详细 SVIX 结果保留 7 天
- 更早结果聚合为每日 OHLC 后长期保存
- 每批最多删除 10,000 行，避免长事务

可以在设置页修改保留天数、每日维护时间，或手动触发维护任务。

## 10. 常用维护命令

查看状态：

```sh
docker compose ps
```

查看日志：

```sh
docker compose logs -f
docker compose logs --tail=200 backend worker beat nginx
```

重启服务：

```sh
docker compose restart
```

停止服务并保留数据：

```sh
docker compose down
```

重新启动：

```sh
docker compose up -d
```

## 11. 升级

升级前先备份数据库，然后执行：

```sh
git pull --ff-only
docker compose up -d --build
docker compose ps
```

后端启动时会自动运行数据库迁移。不要同时运行多个升级命令。

## 12. 数据库备份与恢复

创建备份：

```sh
docker compose exec -T postgres pg_dump -U svix -d svix -Fc > semi-vix.backup
```

备份文件包含平台设置、加密凭据和历史结果，应按敏感数据保护。

恢复前先停止会写数据库的服务：

```sh
docker compose stop backend worker beat
docker compose exec -T postgres pg_restore -U svix -d svix --clean --if-exists < semi-vix.backup
docker compose start backend worker beat
```

建议先在独立测试服务器验证恢复流程。

## 13. 故障排查

### `permission denied` 访问 Docker

退出 SSH 并重新登录，确认当前用户已加入 `docker` 组：

```sh
groups
```

### 页面无法打开

```sh
docker compose ps
docker compose port nginx 80
docker compose logs --tail=100 nginx frontend backend
```

确认 SSH 隧道使用的是服务器当前实际端口。

### 数据提供商连接失败

- 确认 TWS、IB Gateway 或 OpenD 正在运行。
- 确认 API/行情权限已启用。
- 检查 Host、端口和 IBKR Client ID。
- 检查网关是否限制受信任 IP。
- Futu 部署确认 `.env` 中 `INSTALL_FUTU=true`，并重新执行 `docker compose up -d --build`。

### 查看健康状态

```sh
PORT=$(docker compose port nginx 80 | sed 's/.*://')
curl -fsS "http://127.0.0.1:${PORT}/health"
```

## 14. 安全须知

- 不要提交 `.env`、数据库备份、证书私钥或恢复代码。
- 不要复用 JWT、TOTP、凭据加密和数据库密码。
- 不要公开 TWS、IB Gateway、Futu OpenD、PostgreSQL 或 Redis 端口。
- 默认使用 `127.0.0.1` 和 SSH 隧道访问。
- 公网部署必须启用 HTTPS、防火墙和定期备份。
- 定期检查 `docker compose logs`、磁盘空间和最近数据维护状态。

## 15. 卸载

停止并删除容器，保留数据库卷：

```sh
docker compose down
```

永久删除容器和数据库卷：

```sh
docker compose down -v
```

`docker compose down -v` 会永久删除管理员、设置、加密凭据和全部历史数据，无法撤销。
