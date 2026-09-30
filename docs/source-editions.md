# 两套通用源码发行包

| 版本 | 数据源 | 生产运行时 |
| --- | --- | --- |
| Alpaca | Alpaca Market Data | Go、Nginx、PostgreSQL 16；没有 Python 或 Supervisor |
| Full | Alpaca、IBKR、Futu | 同上，加 Python 的 IBKR／Futu SDK 桥接 |

源码和 Dockerfile 不固定 CPU 架构。默认在当前平台编译；`build.sh --platform linux/amd64` 或 `build.sh --platform linux/arm64` 可选择目标平台。SDK 版的可用平台还取决于上游 Python 依赖。TWS／IB Gateway、Futu OpenD 均在外部运行。

## 生成发行包

```sh
go run ./go/cmd/svix-package
```

默认输出到忽略目录 `releases/source-editions/`，包含两份源码压缩包和 `SHA256SUMS`。不生成或上传 Docker 镜像，不创建 GitHub Tag／Release。文件名不预设下一次发布版本号。

每份包包含自己的 Dockerfile、Compose 配置、编译脚本、配置生成脚本和说明。Alpaca 包不包含 Python 源码或后端目录；完整版只带 SDK 桥接所需的 Python 模块，不包含旧的 Python API、计算、调度及 Alembic 迁移代码。两版均内嵌 Go 管理的 SQL 数据库迁移。

生成器只收录明确允许的源码目录及文件类型，拒绝符号链接；不收录 `.env`、数据卷、数据库、备份、日志、证书、私钥、Git 历史、个人说明文档、依赖目录或本机构建产物。还会检查源码是否包含本地配置敏感值、个人目录、邮箱或私钥。压缩包中的所有者和时间戳已归一化。合成测试值和公开项目模块标识保留。

## 编译与安装

解压所需版本，进入解压目录：

```sh
./init-env.sh
./build.sh
docker compose up -d --no-build
docker compose port app 80
```

配置生成脚本需要 OpenSSL；产生的 `.env` 只保存在本机，权限为 600。它拒绝覆盖原配置。管理员初始密码在本地 `.env` 中；首次登录绑定 TOTP。NAS 可在性能较好的机器用目标平台参数构建镜像，再 `docker save`／`docker load` 导入，但私有运行配置与数据库不得加入公开发行包。

## 现有数据卷升级

保留原 `.env`、Compose 项目名称和 PostgreSQL 16 卷。数据库迁移沿用 `alembic_version` 的原修订编号，Go 执行未应用的 SQL；升级在事务和数据库锁内进行。未知修订编号会拒绝升级，避免误修改较新的数据库。已有管理员、MFA 和凭据不会被配置模板覆盖。

完整版切换到 Alpaca 版后，如原启用 IBKR／Futu，需要在面板中配置并启用 Alpaca。原提供商凭据保留，但 Alpaca 版不会调用 SDK；接口拒绝配置不支持的提供商，设置页面只显示本版支持的数据源。

## 验证范围

Go 单元测试、数据库集成测试覆盖空库及全部 15 个历史修订的升级、表结构与 Alembic 的一致性、升级幂等性、账户保留和版本边界。发行包应解压后独立构建，再用合成账户和独立测试数据库检查启动、登录、MFA、任务调度和重启。真实行情权限需要用户自行配置后验证。
