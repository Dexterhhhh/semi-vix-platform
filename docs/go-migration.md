# Go 迁移

生产镜像中的所有 `/api/` 请求由 Go 处理。Go 调度器调用 Go 服务，不再调用 Python 任务。

| 模块 | 生产实现 |
| --- | --- |
| API、登录、JWT、TOTP、刷新会话、管理员初始化 | Go |
| Alpaca 实时报价、期权链、历史下载、归一化与入库 | Go |
| SVIX 方差、30 日插值、相关性、组合、日内观测与缓存 | Go |
| 独立自定义指数计算、配置版本、名称验证与查询 | Go |
| 交易日历、定时采集、历史任务、任务恢复 | Go |
| 数据聚合、降采样、过期数据清理 | PostgreSQL SQL；Go 管理策略、锁和运行状态 |
| IBKR／Futu 行情连接与采集 | Python SDK 桥接，仅监听容器内回环地址 |
| PostgreSQL 模式升级 | Go 执行内嵌 SQL，沿用原 Alembic 修订编号 |

保留原 Python API 与数学实现供参考和回归测试；生产入口为 `app.bridge:app`，不注册这些接口。Alpaca 生产路径完全由 Go 执行。完整版的 `requirements-runtime.txt` 是 SDK 桥接依赖，`requirements.txt`／`requirements-dev.txt` 用于原实现的回归测试。

完整版镜像及源码发行包共用 `docker/sdk-files.txt`，只收录 SDK 桥接实际需要的模块。旧 Python API、Alpaca 客户端、计算与调度实现不进入生产镜像。Go 与 Python 之间已移除数学计算的过渡接口；SDK 采集使用 Go 选定的标的列表，避免两边重复读取配置和组合。

## 升级兼容

继续使用原 PostgreSQL 16 数据卷、表结构、管理员密码哈希、AES-256-GCM 密文和 TOTP 配置。已有账户不会被环境变量覆盖，现有 JWT 与刷新 Cookie 格式保持兼容。升级前按 README 备份数据库。

Go 工作任务使用 PostgreSQL advisory lock，历史任务通过原子更新领取；持锁的执行者退出后，下次调度会恢复遗留的 RUNNING 任务。SQL 降采样与删除在同一事务中执行，避免重复计数；原始期权只有存在归档水位和对应计算记录时才清理。

NYSE 日历嵌入 2020～2040 年交易时段，来源为项目原 `pandas-market-calendars 5.4.0` 的 NYSE 日历。它覆盖节假日、夏令时和半日交易，临时休市公告需要更新日历后重新构建；超出支持年份时停止采集并报告日历不可用。

## 验证

```sh
go test ./...
bash scripts/test-go-integration.sh
```

集成脚本自动创建并删除专用 PostgreSQL 容器，不挂载项目数据卷。测试覆盖标准与自定义计算参考值、相关性无前视、重复报价、同日缓存、严格值优先、版本保存、加密凭据、SQL 归档保护和任务恢复。数学参考值允许误差 `1e-8`。真实行情订阅权限和供应商连接需在使用自己的凭据后验证。

NAS 可继续使用现有 Docker Compose 和本地构建镜像导入方式；本次没有修改数据库主版本或默认面板端口。

两套源码发行包及通用编译方式见 [源码版本说明](source-editions.md)。Alpaca 专用版不含 Python；两个版本均使用 Go 进程管理器，不依赖 Supervisor。
