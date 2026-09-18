# Semi-VIX 代码审查与改善计划

审查日期：2026-09-17 至 2026-09-18<br>
仓库：[Dexterhhhh/semi-vix-platform](https://github.com/Dexterhhhh/semi-vix-platform)<br>
审查基准：[4010d346743e5a2bd75fd3c21ea581f8a7bd09a9](https://github.com/Dexterhhhh/semi-vix-platform/tree/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9)，提交时间 2026-09-10，README 版本 v0.2。

本次包含计算引擎、行情适配与采集、历史回填、数据库与生命周期、任务调度、认证、前端看板和部署构建。本文是审查结果与实施计划，未修改业务代码，也未向 GitHub 提交变更。

## 1. 审查结论

项目已有可以继续迭代的基础：行情接口与计算引擎分层、计算任务独立运行、自定义指数配置有版本、认证有 MFA、凭据使用加密保存、数据库有迁移。单期限方差主公式、非均匀行权价间距、组合方差 `wᵀΣw` 的基本结构正确，不需要整体推倒重写。

但目前还不能把看板中的“严格 SVIX 30D”当作已经验证的、口径稳定的行业波动率基准。最优先的问题是：

1. **30 日期限插值公式有确定错误，现有测试也固定了错误期望。**
2. **严格计算的期权选择不完整，零买价、缺失 K0 配对等异常仍能生成结果。**
3. **输入来源与计算方式没有可靠隔离，旧数据可被改标为新来源，历史收盘价代理可进入严格路径。**
4. **收益序列没有按交易日对齐，也没有显式复权，相关性可能严重失真。**
5. **自定义指数、行情适配、历史降采样和任务恢复存在实际功能缺陷。**

建议顺序是：先保证“算得对、输入可信”，再保证“历史可追溯、运行稳定”，最后增强看板分析能力和视觉体验。

### 优先级定义

| 级别 | 本文含义 |
| --- | --- |
| P0 | 正式发布可信指数前的阻断项：可直接改变指数数值或将不合格输入呈现为合格结果；不是安全漏洞评级 |
| P1 | 高优先级：影响数据正确性、主要功能、历史完整性或持续运行 |
| P2 | 常规改善：交互、测试工程、可维护性及运行保障 |
| P3 | 增强项：在正确性得到保证后推进 |

## 2. 实际验证结果与边界

| 验证 | 结果 |
| --- | --- |
| 后端 `python -m pytest -q`，在 `backend` 目录执行 | **48 passed，1 failed**；Python 3.12.14，按仓库 `requirements-dev.txt` 安装依赖 |
| 失败用例 | `tests/data/test_adapters.py::test_alpaca_adapter_marks_indicative_quotes_as_delayed`；固定的 `NVDA260821...` 合约在审查日已经过期，被基于真实当前时间的筛选移除，随后 `[0]` 抛出 `IndexError` |
| 前端 `npm test` | **1 个测试通过**；当前测试主要是类型样例的数值断言 |
| 前端 `npm run build` | TypeScript 与 Vite 构建通过；JS 约 1,349.74 kB，gzip 445.63 kB，存在大包警告 |
| 前端冻结安装 | `pnpm install --frozen-lockfile` 下载并安装依赖后，因 `ERR_PNPM_IGNORED_BUILDS: esbuild@0.25.12` 退出 1；后续测试和构建独立执行成功 |
| 前端验证环境 | Node v26.5.0、pnpm 11.19.0；Docker 使用 Node 22，尚需在生产构建环境复验 |
| 独立复现 | 已运行期限插值、零买价污染、K0 缺腿、收益错位、零方差历史、自定义标的干扰、无关到期日失败、负方差回退、来源改标、代理数据严格计算、降采样覆盖、错误清理、任务分发失败等用例 |
| 前端逻辑复现 | 执行实际组件逻辑并模拟依赖，确认图表跨质量断点连线、设置连续修改覆盖；输入丢焦为代码层判断，未做真实浏览器交互复验 |

未连接真实 IBKR、Futu 或 Alpaca 账户，未验证行情订阅权限、真实期权覆盖率和生产数据误差分布；未启动完整 Docker/PostgreSQL/Redis 集成环境。下文将“已复现的代码问题”和“需要真实数据验证的方法选择”区分处理。不能把单元测试通过解释成线上行情或金融模型已经验证。

## 3. 计算正确性：先修这几项

### 01｜P0：30 日插值必须基于累计方差

**证据：** [interpolation.py:36–37](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/interpolation.py#L36) 直接对两个期限的年化方差加权；[对应测试:26–33](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/tests/svix/test_variance_and_interpolation.py#L26) 将 `0.10` 作为期望值。

设近、远到期时间为 `T1、T2`，目标为 `T*=30/365`，单期限结果为年化方差 `v1、v2`：

```text
a = (T2 - T*) / (T2 - T1)
v30 = [a × T1 × v1 + (1-a) × T2 × v2] / T*
指数点数 = 100 × sqrt(v30)
```

这是对累计方差 `T×v` 插值，再转换回年化方差。[Cboe VIX 方法公式](https://cdn.cboe.com/resources/vix/VIX_Methodology.pdf)

**复现：** 20 日方差 0.04、40 日方差 0.16，当前得到 `v30=0.10`、31.6228 点；正确值为 `0.12`、34.6410 点，相差约 3.02 点，当前低估约 8.71%。这只是构造例，不代表整个历史序列的固定误差比例。

**改善：** 修改公式和错误测试；为新方法建立版本，评估能够重算的历史区间，保留旧版记录，不能直接把新旧结果拼接成同一条无说明曲线。

**验收：** 独立手算样例、平坦与陡峭期限结构、恰好 30 日、目标边界、分钟级剩余期限均通过；期望值不得通过调用被测实现生成。

### 02｜P0：补全严格期权选择规则，停止静默修复异常报价

**证据：** [forward.py:14–24](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/forward.py#L14) 只检查中间价是否为正；[option_filter.py:31–54](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/option_filter.py#L31) 未实现零报价尾部截断；[variance.py:38–43](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/variance.py#L38) 先筛掉不成对的行权价，再选择 K0。

**已复现：**

- 有效 90/100/110 行权价链后追加 120/130/140 三个 `bid=0、ask=10` 的 Call，严格波动率从 **35.0929** 升至 **58.4559**，质量指标不变。
- `F=106`、挂牌行权价 90/100/105/110，105 只有 Put，代码改用 100 作为 K0 并成功计算，且未标记回退。

**改善：** 保留原始 bid/ask，分别向两翼扫描并执行连续零报价截断；先确定真正 K0，再校验其 Call/Put；严格模式缺腿或没有合法 K0 时返回明确失败。两翼有效性和尾部覆盖要有检查。相关选择规则可对照 [Cboe 波动率指数数学方法](https://cdn.cboe.com/resources/indices/Cboe_Volatility_Index_Mathematics_Methodology.pdf)。

另有 [Alpaca adapter:21–26](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/data/providers/alpaca/adapter.py#L21) 将 `bid>ask` 直接交换。这虽然不改变中间价，却抹掉了报价异常证据，绕过模型的价差检查。应保留原值并拒绝或降级该条数据，不应把交换后的数值当正常报价。

**验收：** 覆盖孤立零价、连续零价、截断后重新出现正价、K0 单腿、只有单侧 OTM、交叉报价、重复合约及异常价差；每条排除记录有原因。

### 03｜P0：严格模式、来源与历史代理数据必须在输入层隔离

**证据：** [alpaca_history.py:187–204](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/alpaca_history.py#L187) 把历史成交收盘价同时写入 bid/ask；[svix_calculator.py:110–114](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/svix_calculator.py#L110) 在 `strict=True` 时仅关闭近似计算开关，并未筛掉这些代理输入。原始快照没有 `feed` 或 `price_type` 字段，结果来源取自计算时的当前配置。

**实测：** 在内存数据库写入完整的历史收盘价代理链，全部 `delayed=True`，执行 `strict=True` 得到 `estimated=False`。不改输入，只将当前配置 `indicative` 改成 `opra`，结果来源从 `alpaca:indicative` 变成 `alpaca:opra`，指数仍为 28.0425609、质量仍为 0.5525。

这比“Indicative 也标严格”更严重：README 已说明严格算法并不等于官方 OPRA 行情，但当前存储结构还无法保证结果记录的来源是真实输入来源。Alpaca 官方也明确区分 Indicative 衍生报价和 OPRA BBO。[Alpaca 数据源说明](https://docs.alpaca.markets/us/docs/historical-option-data)

**改善：**

- 快照落库时固化 `provider、feed、price_type、market_timestamp、received_at、batch_id`；`price_type` 至少区分 BBO、indicative quote、trade close proxy。
- 实时报价、日线代理、未知来源使用独立的数据选择规则；正式结果不能消费日线代理或未知来源。
- 将 `estimated` 拆为计算方法、行情等级、成分完整度等独立字段；来源由实际输入推导，不从当前设置补写。
- 存量无法恢复来源的记录标为 legacy/unknown，不能推断成 OPRA。

**验收：** 切换当前 provider/feed 后，旧记录的来源不变；历史代理不能生成正式 BBO 结果；混合来源必须显式拒绝或按有版本的降级规则处理。

### 04｜P1：相关性先对齐交易日，再算收益；引入复权价格

**证据：** [svix_calculator.py:76–91](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/svix_calculator.py#L76) 将各标的日价格转为无日期列表；[correlation.py:23–39](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/correlation.py#L23) 只按相同尾部长度对齐。

**复现：** 同一条 270 日价格路径复制为 A/B，B 仅缺倒数第 10 日，当前相关系数约 **0.04573**；先按共同日期对齐价格再计算同区间收益，相关系数是 **1.0**。

此外，[alpaca_history.py:101](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/alpaca_history.py#L101) 未指定 `adjustment`，官方默认 `raw`，拆股可能被计为巨额负收益。[Alpaca 股票历史 bars 参数](https://docs.alpaca.markets/us/reference/stockbars)

**改善：** 建立带 session_date 的日价格/收益表；只使用计算时已经可得的数据。用复权价格计算收益，保留未复权现价供当日期权行权价与远期估计使用。缺日后不能把不同时间跨度的收益当同一天收益；明确停牌、补齐和样本不足政策。

`correlation.py:35–37` 将 `NaN` 改为 0；两只标的全零收益已复现得到单位相关矩阵，这会凭空产生分散化效果。应拒绝零方差历史，记录不可用原因。若采用收缩估计，应作为明确模型规则，不应静默填零。

**验收：** 错位、缺日、停牌、10 拆 1、跨源切换、零收益序列均有用例；任何相关窗口中的收益必须具有一致起止交易日。

### 05｜P1：自定义指数要真正独立，并打通标的采集能力

**证据一：** [svix_calculator.py:62–63](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/svix_calculator.py#L62) 将自定义标的并入总输入；[engine.py:63–80](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/engine.py#L63) 对所有输入计算波动率，但权重和相关矩阵仅包含默认标的。加入有效 TSM 数据后，标准 SVIX 抛出资产集合不一致异常。

**证据二：** 三个 provider adapter 的 `get_stock_quote/get_option_chain` 均调用 [universe.py:8–16](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/data/universe.py#L8)；该函数仅允许默认六个代码。因此页面允许新增 TSM 等自定义标的，但自动采集会被拒绝。历史回填绕过这一校验，反而可能在回填后触发上述标准指数错误。

**改善：** 标准引擎入口严格限定默认成分，自定义引擎按自己的版本配置选择数据；将代码格式验证和“属于默认指数”判断分离；新增标的前查询数据源合约能力，而不是静态放行任意代码。

**验收：** 创建含 TSM 的自定义指数后可以采集、回填和计算；无论 TSM 成功或失败，标准指数在相同默认输入下输出完全不变。

### 06｜P1：近似回退必须保留数学含义，坏期限不能拖垮好期限

**证据：** [variance.py:47–54](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/variance.py#L47) 遇到负方差且存在 fallback spot 时，直接丢弃远期修正项；[interpolation.py:30–34](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/interpolation.py#L30) 的最近期限回退没有距离上限。

**复现：** 仅有 K=80/90/100 的 Put，bid=0.09、ask=0.11，spot=200，原公式约为负 12.1574，代码改成正方差 0.0092395，输出 9.6122 点。这是换了计算含义，不是修好了输入。

另在 [engine.py:33–35](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/engine.py#L33)，严格路径先计算所有期限，任一期限出错就中止。有效 20/40 日链加入一个无关的 300 日单边 Call，整个资产计算失败，已复现。

**改善：** 无效方差返回具体失败原因；另设有名称、有适用边界的代理估计方法。记录目标期限与实际期限，限制回退距离。按已公布规则筛选候选期限，记录每个期限的成功/失败，再判断是否存在有效包围区间。行业期权的期限带应单独规定，不能机械照搬 SPX 的全部合约规则。

**验收：** 负方差不能靠删除公式项变为合格结果；1 日或 180 日单一期限不得被直接当成 30 日值；无关坏期限不影响合法近远期结果。

## 4. 行情、历史与运行可靠性

### 07｜P1：修复 IBKR 采集路径，并支持历史收益预热

**证据：** [IBKR client:27–45、98–117](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/data/providers/ibkr/client.py#L27) 用 `asyncio.to_thread` 调同步 SDK；无指定 expiry 时仅取 `min(chain.expirations)`。采集器未主动请求包围 30 日的两个期限。

**影响与复现：** 正常实时采集只得到最近期限，无法满足严格 30 日插值。当前 Python 3.12 环境中，在线程执行实际 SDK 的 `ib_insync.util.getLoop()` 得到 `RuntimeError: There is no current event loop in thread 'asyncio_0'`；这是运行边界问题，尚未做真实网关连接验证。

此外，[tasks.py:125–137](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/scheduler/tasks.py#L125) 只有 Alpaca 历史回填，新 IBKR/Futu 实例若无已有历史，无法满足 253 个价格点的要求，只能长期等采集积累。

**改善：** 使用 SDK 一致的事件循环/专用线程，不能假设任意线程池线程都有循环；为各 provider 实现统一的候选期限选择和历史日价格预热接口。行情权限、可用期限、历史覆盖率都应在连接测试中分别报告。

**验收：** 真实 IBKR/Futu 环境完成从空数据库到首个合格结果的联调；近远期限完整，断连恢复、超时和配额均可观察。

### 08｜P1：使用一致的估值快照和合约时间，不要用“当天最新”拼链

**证据：** [svix_calculator.py:65–74、110](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/svix_calculator.py#L65) 为每份合约分别取当日最后一条，再以所有合约最大时间作为估值时间；没有最大年龄或跨合约时间差限制。IBKR/Futu adapter 直接用抓取时刻作为报价时刻，到期日期按 UTC 零点处理。Alpaca 到期被硬编码为 21:00 UTC。

**影响：** 早盘未更新的 Put 与午后 Call 可以组成“最新”期权链；夏令时、提前收盘及各类合约约定没有进入到期时间；日线 close 所属的 bar 时间也不等于 close 已可用的时间。这些都会影响期限、远期或相关性，且当前无法审计。

**改善：** 给每轮采集分配 batch_id，区分市场时间、接收时间、估值时间和交易日；使用 as-of 查询及报价年龄/批内时间差门槛。报价新鲜度阈值按实时、延迟和日终产品分别制定。根据具体合约的最后交易/结算约定及交易日历确定到期时间，不能统一替换成 UTC 午夜或固定 21 点。

**验收：** 夏令时切换、提前收盘、过期合约、旧 Put/新 Call、延迟报价和日线 bar 可用时点用例均有明确结果；失败不能通过伪造当前 timestamp 隐藏。

### 09｜P1：采样上限应服从期限与两翼覆盖，不能只截取前 120 份合约

**证据：** [market_collector.py:90–99](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/market_collector.py#L90) 使用 `contracts[:120]`；Alpaca 优先靠近现价的合约，Futu 返回顺序没有对应完整性保证；历史回填 [alpaca_history.py:143–146](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/alpaca_history.py#L143) 每个期限只取靠近月度参考价的 40 个行权价。

**影响：** 可能缺少另一到期日、K0 配对或尾部积分。VIX 式计算对整条有效 OTM 价格带敏感，接近 ATM 的固定数量不能自动代表足够覆盖。历史月度参考价使用整月价格，也让月初合约选择依赖月内后续信息，不适合直接拿来做严格的当时可得回测。

**改善：** 先分期限，再围绕 K0 保证两翼和配对，按过滤规则确定边界；存行权价覆盖范围、排除数量、截断原因及尾部敏感性。历史合约选择使用估值当时已知价格。性能方面优先批量接口与行情缓存，并记录任务耗时和请求预算。

IBKR 每份期权默认等待 3 秒，仅 120 份就约 6 分钟/标的；当前串行结构下不能把 30 秒设置解释为实际每 30 秒完成一轮采集。

**验收：** 合约输入乱序不改变选择结果；正常两期限和两翼都有覆盖；将可用行权价带扩大后量化指数变化，达到预先定义的收敛标准。

### 10｜P1：日降采样必须可重入，清理必须按实际计算依赖执行

**证据：** [data_lifecycle.py:37–69](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/data_lifecycle.py#L37) 直接用本批旧明细覆盖已有日汇总；[120–133 行](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/data_lifecycle.py#L120) 只要标准 SVIX 某日有结果，就可清理该日所有 provider 的期权快照。

**复现：** 首次两点 15:00=10、18:00=30 汇总为 O10/H30/L10/C30/count2；随后补一条 17:00=20 再维护，变成 O20/H20/L20/C20/count1。另验证 ALPACA 当日有结果时，同日尚未计算的 FUTU 输入也会被删。

历史 API 会优先选严格明细，而日汇总用最后一条记录决定 close/estimated，两套选点策略不一致；明细清理前后，同日展示结果可能变化。

**改善：** 只聚合已结束的完整交易日；定义迟到数据、重算与日汇总合并语义，保留首末时间和去重计数依据，禁止用部分新增数据覆盖完整汇总。标准、自定义、历史 API 应共享选点政策。清理按 batch/provider/feed/index/version 的依赖完成状态决定，并与运行中任务互斥；关键计算输入压缩归档后再清理在线表。

**验收：** 重复维护、分批维护、迟到数据、历史重算均不丢原 OHLC；维护前后 API 结果一致；一个指数成功不能清掉其他指数仍需的输入。

### 11｜P1：持久化完整计算依据，版本化指数定义和历史重算

**证据：** [SVIXResult](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/models.py#L80) 包含 weights/correlation，但 [svix_repository.py:17–34](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/svix_repository.py#L17) 不保存；[SVIXHistory](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/database/models.py#L120) 仅以 timestamp 唯一，无法并存不同来源、方法版本的同一时点结果。

**改善：** 增加不可变 calculation_run，至少保留：方法版本、指数配置版本、代码提交、输入批次/哈希、实际权重、缺失成分、覆盖率、相关矩阵及资产顺序、收益窗口、利率、每资产两期限、F/K0、有效行权价和回退原因。结果唯一键纳入指数版本、方法版本和数据系列身份。

默认成分中 SKHY 的可用性应由实际券商的标的、期权链和历史长度验证；不能假定一个展示代码在三个源都代表相同可交易合约。现有三个 adapter 固定按美股/USD 处理，多市场扩展还需要币种、交易时区和合约映射。

**验收：** 给定一个历史点，能重建输入并复算；新版本与旧版本可并排比较，默认查询明确选择哪版；原始输入已清理且无法恢复时，明确标注不可复算。

### 12｜P1：采集、分发和执行需要可恢复的任务状态机

**证据：** [market_collector.py:90–101](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/services/market_collector.py#L90) 中所有期权报价失败时，仍将标的计为成功；已实测得到 `symbols_succeeded=1、symbols_failed=0、option_quotes_saved=0`。[tasks.py:89–99](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/scheduler/tasks.py#L89) 又将该轮标为 COMPLETED。

[jobs_routes.py:55–70](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/api/jobs_routes.py#L55) 在 broker 分发失败后留下 PENDING，但没有重新分发入口或扫描任务；用户再次提交相同任务又被 409 拒绝，已复现。

**改善：** 分开记录采集成功、有效链就绪、计算成功；明确 PARTIAL/NO_VALID_DATA/DISPATCH_FAILED 等状态。使用数据库 outbox 或可恢复的投递记录，提供幂等重试、取消和超时恢复。任务绑定提交时的 provider/feed/指数版本，避免执行中设置变化影响任务身份。

[tasks.py:76–86](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/scheduler/tasks.py#L76) 的先查后插不能构成并发互斥。应采用数据库原子锁或带续租的锁，并为计算结果和快照去重。Redis 数据目录目前未挂持久卷，容器重建后的队列恢复应依赖数据库重投递机制。

**验收：** 两个 worker 同时触发只形成一个有效批次；全报价失败不显示成功；Redis 暂停后恢复可重投；任务中途重启不会永久卡住或重复覆盖历史。

## 5. 明确指数的经济含义

以下属于模型治理与产品定义，不应全部归为代码 bug。

### 13｜P1：区分行业期权指标与混合相关性组合指标

当前实现可概括为：各标的期权推导波动率 → 历史 60/120/252 日相关矩阵 → 组合方差。`wᵀΣw` 本身正确，但历史相关性并非期权隐含相关性，因此整个组合结果是一个**模型估计指标**，不能仅凭各资产用了期权价格，就称其为组合层面完全可复制的纯期权隐含 VIX。

建议保留两个清晰系列：

| 系列 | 经济含义 | 需要披露 |
| --- | --- | --- |
| SOXX 30D 期权波动率 | 基于 SOXX 自身期权条带的行业代理 | 流动性、期权类型、利率、报价质量及方法差异 |
| Semi-VIX Composite | 期权波动率与历史相关性结合的半导体组合估计 | 组合权重、历史窗口、缺失政策、相关性假设和版本 |

不建议未经实证就重调 50/30/20 权重。先明确它代表投资组合配置、行业分组覆盖还是压力监测，再根据样本外表现决定。

需要补齐四项方法规则：

- **缺失成分：** 当前 [engine.py:72–77](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/svix/engine.py#L72) 全局重新归一化。缺 SKHY 时实测 SOXX 变成 58.8235%、Memory 变成 17.6471%、AI 变成 23.5294%，且仍可 `estimated=False`。选择固定完整组合、板块内重配或全局重配，并显示实际权重；降质量分不能代替政策披露。
- **利率：** `constants.py:8` 默认 0，服务没有注入期限利率。建立按估值日和到期日取值的曲线接口，保存连续复利口径与来源，不能拿今天利率重算过去。
- **美式期权：** 股票/ETF 期权的提前行权和分红影响需要单独研究。直接套用平价与指数期权公式应披露近似，并检查除息、深度实值和异常借券情形；先评估实际偏差，再决定过滤或模型调整。[OIC 股票与指数期权差异](https://prd-web.optionseducation.org/advancedconcepts/equity-vs-index-options)、[OIC 平价与利率分红说明](https://prd-web.optionseducation.org/advancedconcepts/put-call-parity)
- **SOXX 重叠持仓：** `weighting.py:19–43` 的去重只有传入成分暴露才生效，主计算服务没有提供该输入。保留 ETF 加个股倾斜是一种有效的组合定义；若要穿透去重，则需有时点版本的 ETF 持仓和明确目标敞口。减掉再归一化是配置策略，不是相关性公式自动要求的步骤。

**验收：** 发布方法说明与变更政策，明确年化单位、30 自然日目标、相关性估计、缺失及再平衡规则。做按时间推进的样本外评估，对比后续 30 自然日区间的已实现方差，统一年化和收益口径；期权风险溢价意味着不能要求隐含与未来已实现波动完全相等。

## 6. 看板与交互改善

### 14｜P1：先让用户看到“这个数值是否仍然可信”

**证据：** [Dashboard.tsx:30–36、52](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/frontend/src/pages/Dashboard.tsx#L30) 主查询没有定时刷新，卡片只传数值；[IntradayDashboard.tsx:31、42](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/frontend/src/pages/IntradayDashboard.tsx#L31) 的 LIVE 取决于交易窗口，而非选中日期或最新成功结果。

**改善：** 每个核心指标附近展示估值时间、美东交易日、来源、计算方法、实际覆盖率、数据年龄和失败原因。只有正在查看当前交易日、任务正常且结果足够新时才显示 LIVE；其余区分历史、延迟、过期、数据不足和计算失败。质量分目前是启发式乘数，应称“数据质量评分”，不能解释成统计置信度。

**验收：** 开市期间暂停采集、只返回 Indicative、查看过去交易日、最近任务失败时，卡片和图表都有正确状态；旧值保留但明确标注其时间。

### 15｜P2：修复图表跨质量断点连线和时间展示

**证据：** [VolatilityChart.tsx:32–49](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/frontend/src/components/VolatilityChart.tsx#L32) 先 filter，再分别 map 严格与近似序列。严格→近似→严格的三点输入会把两个严格点直接连线；`connectNulls:false` 没有作用，因为序列里没有 null。已运行组件代码确认。自定义图也未区分 estimated。

**改善：** 用完整时间轴的 null 占位或连续分段，显式标出来源、方法和版本切换；不跨缺失区间平滑连接。日终数据使用 session_date，而不是把 UTC 午夜的虚构 timestamp 当真实收盘时间。周频应取每周最后有效交易日，当前 [svix.py:91–92](https://github.com/Dexterhhhh/semi-vix-platform/blob/4010d346743e5a2bd75fd3c21ea581f8a7bd09a9/backend/app/api/svix.py#L91) 只取周五，会漏掉周五休市的一周。

**验收：** 混合质量、缺日、单点、周五假期、跨时区浏览及自定义版本切换均正确；提示框注明年化波动率点数和计算身份。

### 16｜P2：修复设置覆盖、输入丢焦和错误反馈

| 问题 | 证据与触发 | 改善及验收 |
| --- | --- | --- |
| 连续保存覆盖旧设置 | `frontend/src/pages/Settings.tsx:43、58、60、96、102–105` 基于旧 query 数据提交完整 PUT；已复现将 15min/300sec 连续改为 5min/60sec，发出的两次请求是 `{5,300}` 和 `{15,60}` | 用本地草稿统一保存，或 PATCH 配合版本冲突检测；延迟和乱序返回下不丢修改，失败必须反馈 |
| 自定义代码输入丢焦 | `CustomIndexEditor.tsx:40` 的行 key 包含正在编辑的 symbol，每输入字符都会替换行身份 | 使用稳定 rowId；连续输入 TSM、插入/删除成分时保持焦点和值 |
| 错误被解释为无数据 | `Dashboard.tsx:75` 将所有 current 错误显示为暂无历史；`History.tsx:11` 将日期错误/重复任务也归因于 Worker/Redis | 按 401/404/409/422/503 区分，展示后端 detail 和相应操作 |
| MFA setup 网络失败后进入错误流程 | `Login.tsx:6–8` 提前保存 temporaryToken，初始化失败后可能把 setup token 送到 verify 接口 | 使用显式登录状态机，支持 setup 重试和返回；网络失败后可正常恢复 |
| 设置项与引擎不一致 | `manual_component_weights` 可被后端保存，但引擎始终读取常量；selected_symbols 也没有指数可计算性校验 | 实现有版本的配置生效，或移除未实现接口；保存时预告哪些指标将无法计算 |

## 7. 工程、认证与验证体系

### 17｜P1/P2：让安装、测试与健康状态反映实际可用性

**构建可重复性：** `frontend/pnpm-workspace.yaml:2` 的 esbuild 配置仍是占位字符串；`Dockerfile:6–7` 使用 `npm install`，没有使用仓库实际存在的 `pnpm-lock.yaml`。统一包管理器及版本，冻结安装；Python 不只锁顶层包，也应锁传递依赖。干净环境安装必须退出 0。

**测试：** 修复过期的固定日期 fixture，通过注入时钟测试当前日和历史日；把本次错误复现加入回归。仓库没有发现 `.github/workflows`，建议 CI 至少运行数学基准、后端测试、前端组件测试、类型检查、冻结安装与构建，以及 PostgreSQL 迁移/持久化集成测试。当前 SQLite 单测不能覆盖生产并发锁和迁移行为。

**健康状态：** `api/health.py` 固定返回 ok；`settings_routes.py:113–121` 的 engine Ready/worker Idle 并未探测 worker。保留轻量 liveness，新增受控 readiness 和任务心跳，分别报告数据库、broker、worker、beat、行情最近成功时间及最近合格指数时间。

**性能：** 当前历史查询及维护有多处 `.all()`，日内每次计算还重复扫描 400 天股票快照。建立独立日价格表、每日缓存相关矩阵、数据库端按时点取快照、分批归档；先测量查询计划和 p95 耗时再优化。前端采用 ECharts 按需导入和路由拆包属于 P3，不应早于公式与数据修复。

**验收：** 同一提交可复现依赖和产物；数据库迁移可从上版升级；worker 停止时不会继续显示系统可用；真实采集频率与处理耗时可观察。

### 18｜P1/P2：补齐 MFA 恢复和实际限流

**证据：** `config.py:23` 声明 `rate_limit_per_minute`，但认证路由和 Nginx 没有实际使用；`auth/routes.py:73` 生成并加密恢复代码，却没有返回给用户，也没有恢复验证接口。README 要求保存恢复代码，与实际功能不一致。

**改善：** 对密码和 MFA 验证实现可跨 worker 的限速、失败计数和渐进退避；TOTP 验证记录已消费时间步，临时挑战成功后失效。恢复码在设置成功时仅展示一次，保存不可逆校验值，使用后原子作废，并提供轮换。补充前端恢复入口和流程测试。

默认本机绑定、HTTPS 场景 secure cookie、凭据加密等设计可以保留。单容器部署对 NAS 使用有合理性，不必为了架构形式立刻拆成多个服务；应先验证备份恢复、队列重建和健康告警。

**验收：** 超额尝试被限制；重复消费同一恢复码失败；丢失认证器时可按文档恢复；备份与密钥恢复演练能恢复已有加密配置。

## 8. 建议实施顺序与交付物

| 阶段 | 工作范围 | 交付物 | 进入下一阶段的条件 |
| --- | --- | --- | --- |
| A：修正计算与输入准入 | 01–04、06；先建立失败复现，再修公式、过滤、来源和收益对齐 | 独立数学基准、数据质量拒绝原因、方法 vNext 草案 | 所有 P0 复现关闭；代理/未知来源不能进入正式结果 |
| B：打通真实行情与指数隔离 | 05、07–09；解决自定义 universe、期限采集、历史预热、事件循环、时间与采样 | 至少一个正式数据源的端到端联调记录；其他源标明完成状态 | 从空库产生可审计结果；真实合约覆盖和新鲜度满足门槛 |
| C：历史与运行可靠性 | 10–12、17 的后端部分 | 版本化结果库、归档与重算流程、任务恢复、迁移及故障演练 | 重算/清理不改坏已发布历史；宕机和队列故障能恢复 |
| D：看板可信展示与交互 | 14–16、18 | 来源/时效/覆盖展示，图表断点，设置和认证回归测试 | 用户能明确区分正式、指示、代理、缺失和过期数据 |
| E：模型校准与分析增强 | 13、性能优化、相关性情景和风险贡献 | 方法文档、样本外报告、版本差异报告 | 有明确适用范围和误差证据，再决定是否扩展标的与刷新频率 |

阶段 A 开始前应保存现有数据库备份和代码基准。公式、相关性、权重政策或输入身份变化均需要新方法版本；先并行计算比较，再选择展示版本。历史原始数据若已按 3 天策略清理且没有归档，不承诺可以无损修正全部过去结果。

### 必须补入的验收用例

- [ ] 20D/40D 累计方差例得到 0.12，且有另一份独立基准验证。
- [ ] 零价两翼截断、K0 缺腿、交叉报价、极宽价差和旧报价被正确处理。
- [ ] 切换 Indicative/OPRA 不改旧来源；close proxy 不能通过正式准入。
- [ ] 同一价格路径缺一日不产生虚假低相关；拆股不制造虚假收益；常量序列被拒绝。
- [ ] 新增 TSM 自定义指数不影响默认 SVIX，并能实际采集。
- [ ] 有效近远期限不受无关坏期限影响；负方差和过远期限有明确失败状态。
- [ ] 夏令时、提前收盘、交易日缺失、周五假期、日线可用时点正确。
- [ ] 重复维护/迟到数据/重算保持正确 OHLC；跨 provider 和自定义指数输入不被误删。
- [ ] broker 分发失败、worker 重启、并发采集、全报价失败均能恢复并正确显示。
- [ ] 图表质量断点、历史日期 LIVE、设置连续修改、输入焦点、认证恢复有组件或端到端测试。
- [ ] 干净安装、完整构建、数据库升级和备份恢复演练通过。

## 9. 后续有价值的分析功能

在上述基础问题解决后，再增加：SOXX 与混合 Semi-VIX 的并列比较、各资产实际权重与方差贡献、期限结构、按来源分组的质量趋势、隐含与后续已实现方差比较、相关性升高的压力情景。

已有 `portfolio.py` 的 `w_i(Σw)_i` 是方差贡献，其总和等于组合方差，这是正确的。如果展示波动率点数贡献，应除以组合波动率并转换为百分数单位；贡献占比则除以组合方差，不能直接把现有字段当波动率点数。

优先做到：每一个看板点都能回答“来自哪些行情、使用哪个方法和组合、为何可信、能否复算”。再增加更多曲线和更高刷新频率，才有稳定的基础。
