# Semi-VIX Platform

当前发布版本：**v0.2**

Semi-VIX 是一个私有、自托管的半导体波动率分析平台。系统通过只读行情接口采集期权数据，计算 SVIX、Core、Memory 和 AI Semiconductor Volatility，并提供历史图表、后台计算任务、数据保留策略和系统状态面板。

支持的行情来源：

- Interactive Brokers TWS / IB Gateway
- Futu OpenD
- Alpaca Market Data（免费 Indicative 测试源 / 付费 OPRA 正式源）

平台不包含下单、撤单、持仓或资金操作，不能用于交易。

## 系统要求

- Ubuntu 22.04 或 24.04（推荐）
- 2 核 CPU、4 GB 内存、20 GB 可用磁盘起步
- 可以访问 Docker Hub、PyPI 和 npm 镜像
- 已运行并正确授权的 IBKR TWS / IB Gateway 或 Futu OpenD
- 对应的美股及期权行情权限

## Ubuntu 新手一键安装（推荐）

将项目下载到 Ubuntu 22.04 或 24.04 服务器后，进入项目目录，只需执行：

```sh
sudo bash install-ubuntu.sh
```

脚本会交互式询问：

- 管理员用户名
- 管理员密码（二次确认，不回显）
- 面板端口（留空则自动选择未占用的高位端口）

然后自动完成：Docker 安装、安全密钥生成、`.env` 创建、镜像构建、数据库初始化、服务启动和健康检查。安装成功后会显示 SSH 隧道命令和面板地址。

发布到自己的 GitHub 仓库后，可使用一条命令下载并安装（请替换仓库地址）：

```sh
git clone https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git semi-vix-platform && cd semi-vix-platform && sudo bash install-ubuntu.sh
```

> 当仓库为私有状态时，服务器必须事先配置该仓库的 GitHub SSH 读取权限。

## 手动安装

仅在需要自定义 Docker 安装方式或手工管理 `.env` 时使用以下步骤。

### 1. 在 Ubuntu 安装 Docker

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

### 2. 下载项目

```sh
sudo apt update
sudo apt install -y git openssl
git clone https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git semi-vix-platform
cd semi-vix-platform
cp .env.example .env
```

### 3. 配置密钥和管理员

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
SVIX_ADMIN_USERNAME=设置你自己的管理员用户名
SVIX_ADMIN_PASSWORD=设置一个高强度且唯一的密码
POSTGRES_PASSWORD=设置另一个随机数据库密码
```

同步修改 `DATABASE_URL` 中的 PostgreSQL 密码，使其与 `POSTGRES_PASSWORD` 一致：

```dotenv
DATABASE_URL=postgresql+psycopg://svix:你的数据库密码@postgres:5432/svix
```

`.env` 包含所有真实密钥，已被 Git 忽略。不要上传、复制到工单或发送给其他人。

### 4. 设置面板访问端口

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

### 5. 选择行情提供商

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

### Alpaca

首次登录后进入“设置与系统状态”，选择 `Alpaca Market Data`，填写 Alpaca API Key 和 API Secret，再选择数据源：

- `Indicative（免费）`：提供 bid/ask，但它们是 Alpaca 由 OPRA 数据派生并修改后的指示性报价，不是官方 OPRA BBO。历史数据使用期权日线收盘成交价代理当日 BBO；面板运行后采集的新快照只有在双边报价、Call/Put 配对和 30 日期限插值均完整时才生成“严格计算值”。
- `OPRA（付费正式）`：适用于正式 SVIX 计算，需要 Alpaca 有效的 OPRA 市场数据订阅。

平台只访问 `data.alpaca.markets` 的只读行情端点，不使用下单、账户或持仓接口。

### 6. 启动平台

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
5. 首次验证后，浏览器会通过 HttpOnly Refresh Cookie 静默续期；默认 7 天内无需重复输入密码和动态验证码。主动退出、Cookie 被清除或会话过期后需要重新完整登录。

会话时长由 `.env` 中的 `REFRESH_EXPIRE_DAYS` 控制，默认值为 `7`。使用本机 HTTP 或 SSH 隧道访问时设置 `COOKIE_SECURE=false`；部署 HTTPS 后必须改为 `COOKIE_SECURE=true` 并重建服务。

系统只支持一个管理员，不提供注册、多用户或角色管理。

## 9. 使用面板

### Dashboard

查看当前 SVIX、Core、Memory、AI 指标及历史曲线。没有足够期权链或历史收益数据时，系统不会生成虚假的零值。

### 单日仪表盘

单日仪表盘只展示通过完整行情校验的严格计算点，并每 30 秒自动检查新结果。曲线按美东时间沿当日时间轴逐点生长，可切换 SVIX、Core Semi、Memory 和 AI Semi，也可选择此前仍保留详细数据的交易日。

行情采集使用 NYSE 交易日历，自动处理周末、美国交易所假期、提前收盘以及夏令时。后台只在正常交易时段至正常收盘后 30 分钟之间运行；收盘后的延长窗口用于补全延迟数据。Celery 每10秒检查一次是否到期，实际采集间隔读取设置页面的“日内独立计算频率”，可选30秒、60秒、2分钟、5分钟或15分钟，修改后无需重启容器。免费 Alpaca 源最低限制为30秒，以避免超过接口调用限制或造成任务重叠。

### 历史计算

选择起止日期和频率后创建后台任务。计算通过 Redis/Celery 异步执行，可在页面查看进度和结果。

使用 Alpaca 免费延迟日线时，平台会自动启用历史近似模式：优先执行标准 30 日 VIX 插值；当免费数据缺少完整 Call/Put 配对或无法包围 30 日期限时，使用标的收盘价估算远期，并选取最接近 30 日的有效到期日。此类结果会降低质量分并标记为“近似”，任务完成信息会分别显示正式、近似和跳过的日期数量。该模式适合观察历史趋势，不等同于 OPRA 实时报价计算结果。

Dashboard 使用同色系区分计算方法：浅色虚线表示历史近似值，实线表示面板采集后通过完整校验的严格计算值。`Indicative` 的严格值表示计算过程未使用历史回退，不代表报价已经升级为 OPRA 官方 BBO；切换到付费 `OPRA` 后，来源字段会相应记录为 `alpaca:opra`。

### 数据提供商

在设置页选择 Alpaca、IBKR 或 Futu，填写对应凭据或连接参数，然后保存并测试连接。平台同时只启用一个行情来源。

### 独立自定义指数

在“设置与系统状态”中可以创建一个独立自定义指数，填写指数名称、1～20个美股或ETF期权标的及基础权重；权重合计必须为100%。可选择两种缺失策略：

- 严格：任一标的缺少有效期权链或历史收益数据时不生成结果
- 容错：可用标的达到至少50%基础权重时，将剩余权重重新归一化后计算

启用后，系统会把自定义成分自动加入行情采集和历史回填范围，并在主仪表盘与单日仪表盘显示独立结果。修改名称、成分、权重或缺失策略会创建新版本；不同版本的历史结果不会混合。自定义指数同样遵循详细结果保留与每日降采样策略。

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
