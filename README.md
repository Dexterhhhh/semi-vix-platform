# Semi-VIX

Semi-VIX 是自托管的半导体波动率观察平台。它通过只读行情接口计算 Semi-VIX、Core、Memory、AI 分项和自定义指数，提供日内趋势、历史图表与数据状态。当前版本为 **v1.0**。

支持 Alpaca Market Data、Interactive Brokers TWS / Gateway 和 Futu OpenD。平台没有下单、持仓或资金操作。Alpaca 免费 Indicative 报价生成的是**估算观察值**，不等同于 OPRA 实时行情或官方 VIX。

## 主要功能

- 日内折线图与 5、15、30 分钟蜡烛图，可切换观察分项。
- 免费行情观察模式显示报价时效、成分覆盖率与缺失原因，不用旧报价伪造新数据点。
- 自定义指数支持 1～20 个标的、权重和缺失策略；输入代码后显示标的名称并在保存时校验。
- 浅色/深色界面、历史计算、数据库备份和数据保留设置。

## 运行环境

建议使用 Linux 或 NAS 上的 Docker Compose，至少 2 核 CPU、4 GB 内存。一个 `app` 容器运行 Nginx、Go 服务和 PostgreSQL 16，数据库保存在 `postgres_data` 卷中。Alpaca 版不含 Python；完整版增加 IBKR／Futu SDK 桥接。两版均由 Go 管理数据库升级和进程，构建时自动适配目标 CPU 架构。详见 [版本与编译说明](docs/source-editions.md)。

### Ubuntu 22.04 / 24.04

在完整项目目录中运行交互式安装脚本：

```sh
sudo bash install-ubuntu.sh
```

脚本会安装 Docker、生成密钥、设置管理员、构建镜像并检查服务。首次登录需要绑定 TOTP 验证器。

### 手动使用 Docker Compose

```sh
./scripts/init-env.sh
docker compose up -d --build
docker compose ps
docker compose port app 80
```

初始化脚本在本机生成随机密钥和密码，管理员登录信息保存在 `.env`。首次登录需绑定 TOTP。本机 HTTP 或 SSH 隧道访问时设置 `COOKIE_SECURE=false`，HTTPS 反向代理下设置为 `true`。数据库连接地址由运行器自动生成，行情采集频率在设置页面调整。

默认只在 `127.0.0.1` 监听面板端口。通过 SSH 隧道或 HTTPS 反向代理访问，不要直接公开 HTTP 面板。登录后在“设置与系统”中配置并测试行情提供商；默认 Dockerfile 构建完整版，已包含 IBKR／Futu SDK；仅需 Alpaca 时设置 `SVIX_DOCKERFILE=Dockerfile.alpaca`。两者均不固定 CPU 架构。

## 更新与备份

更新前先备份数据库，并把备份保存到安全位置：

```sh
docker compose exec -T app bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > semi-vix.backup
test -s semi-vix.backup
git pull --ff-only
docker compose up -d --build
docker compose ps
```

启动时会自动运行数据库迁移。`docker compose down` 会保留数据卷；**`docker compose down -v` 会删除数据库和全部历史数据**。不要把 `.env`、数据库备份、恢复代码或私钥提交到公开仓库。

## 开发检查

```sh
# 后端：先在虚拟环境安装 requirements-dev.txt
(cd backend && python -m pytest -q)
# 前端
(cd frontend && npm test && npm run build)
# Go
go test ./...
# Go 与 PostgreSQL 的隔离集成测试，需要 Docker
bash scripts/test-go-integration.sh
```

Go 迁移范围与兼容性说明见 [迁移说明](docs/go-migration.md)。
