# 公开合成经营演示：最小增量方案（已获批准）

检查日期：2026-10-28。**用户已明确批准本方案，固定样本适配现已实现。** 下文保留批准前的技术评估；实际接口采用 `/api/demo/*`，以独立 `ENABLE_SYNTHETIC_DEMO` 开关和已启用来源选择默认入口，不另外引入 `DEFAULT_DEMO_SOURCE`。测试及部署现状以 `PUBLIC_DEPLOYMENT_REPORT.md` 为准。预测/库存/财务公式、M5与ABS数据未改。

## 1. 当前是否可以直接部署完整合成流程

**现有代码不能在关闭M5与匿名上传的同时，直接提供完整合成经营演示。需要一个小型数据适配增量。**

已存在的基础可全部复用：

- `examples/business_csv/synthetic_84_days.csv`：明确人工构造的84天样本，2024-01-01至2024-03-24，单商品、单门店；不是Walmart或企业实际记录。
- `business_csv.load_business_csv` 与 `business_forecast.analyse_business_series`：已经可以解析这个文件，并调用原 `forecast.py` 生成14天回测、两方法MAE及独立未来预测。
- `inventory.inventory_risk`、`scenario.compare_strategies`及其财务函数：已经支持已有全部规则，币种支持AUD/USD且不换汇。
- 四个My Business页面、SVG图表、财务表和决策摘要、参数草稿：已经具备所需交互主体。

当前阻碍是入口与来源绑定，而不是算法：

1. `/api/catalog`、`/api/analysis`、`/api/inventory`、`/api/scenarios` 都通过 `app.py` 的M5加载器读取 `data/processed_sales.csv`，受 `ENABLE_M5_DEMO` 控制。
2. 企业路径需要匿名session、上传、确认及私有SQLite；关闭 `ENABLE_BUSINESS_UPLOAD` 后不能调用它来预置合成数据。
3. `main.js` 当前只有M5/企业两分支，非企业请求明确发送USD，来源标签默认Walmart。
4. `business_context.js` 当前仅允许 `m5_demo` 与 `user_csv`；不能将合成数据套在这两个名称下。
5. M5 `data_loader.load_series` 要求M5结构且至少120天，合成文件只有84天。不能重命名、伪造M5字段或降低该校验来绕过。

因此只把CSV加入服务器、切换环境变量、偷偷在启动时创建一个上传会话，均不是合格的公开合成方案。

## 2. 推荐的最小范围

在现有 **Explore Demo** 内增加一种明确的演示来源，公开环境默认使用 **Synthetic Business Demo**；保留现有四条业务页面路由及独立 `/market`。它是可信固定输入的交互式演示：访问者可以修改假设并计算，但不能上传文件、修改服务器数据或创建真实采购订单。

最小首版只使用现有单商品/单门店84天文件，币种固定为明确声明的 **AUD**，所有输入和结果为同一币种。本地M5继续USD，企业CSV原有AUD/USD能力保留但公开入口关闭。无需新增多商品批量分析、价格弹性、账户、存储服务或新的页面。

合成文件本身不编码币种；服务端适配应明确赋予这个演示的AUD上下文，并把所有财务假设作为AUD输入交给已有财务接口。不是仅替换网页USD字样。后续若确需演示币种选择，可增加独立AUD/USD声明上下文，但这不是本次最小版本的必要内容，不执行换汇。

## 3. 后端适配

建议新增一个小模块 `synthetic_demo.py`，封装Flask Blueprint与固定样本读取适配；不复制已有预测和财务函数。

| 接口 | 作用 |
|---|---|
| GET `/api/synthetic/catalog` | 返回固定样本商品/门店目录及明确合成来源 |
| GET `/api/synthetic/analysis` | 服务器读取样本并调用已有适配/预测引擎，返回四页使用的统一数据结构 |
| POST `/api/synthetic/inventory` | 严格读取库存假设，需求来自服务器固定样本预测，调用原库存函数 |
| POST `/api/synthetic/scenarios` | 严格读取成本、数量、预算等假设，调用原策略/财务函数 |

这些POST仅进行无持久化的计算，不写数据、订单、数据库或用户结果；“只读演示”并不意味着为了HTTP动词而把金额放到GET URL中。金额仍在JSON body，不记录到访问日志。

加载规则：

- 文件路径由源码中的固定相对常量确定，基于 `Path(__file__).resolve().parent`，不接受用户路径、URL或文件名。
- 首次访问/每worker首次初始化时，复用CSV校验和预测适配；只缓存可信样本历史及预测。请求不重解析Excel或读取M5。
- 构造独立context：`source_kind=synthetic_demo`、固定 `dataset_id`、样本内容与适配schema生成的 `revision`、固定系列ID、真实预测原点 `2024-03-24`、`currency=AUD`。
- 返回结构复用现有 `history / analysis / defaults / inventory / overview / price_reference / cost_reference` 等前端契约；明确 `is_synthetic=true`。不把适配层内部原有 `user_csv` 来源字段原样当公开来源标签使用。
- 缓存视为不可变；每次构造独立响应或安全复制。用户A修改的假设绝不能修改共享默认对象，影响用户B。
- 库存与财务计算使用服务器缓存的未来14日需求；拒绝客户端传入 `daily_demand`、任意预测结果、任意日期或数据源路径。
- 精确校验允许字段、重复字段/JSON键、数值类型与范围、币种、商品/门店及版本。M5/私有数据ID不能被用于合成接口。
- JSON body保持小限额；只接受同源JSON计算请求，拒绝异常Origin/跨站请求。无需调用私有上传session或创建SQLite，但仍需要生产进程和入口资源保护。

默认假设可以从已经公开说明的合成演示案例挑选一套，单独作为演示配置并明确披露。例如现有示例README列出的库存30、lead3、安全10、在途0、售价14.50、旧成本8.20、新成本7.50、数量60、运费12、其他0、MOQ20、预算500、折扣10%、假设增量20%。这些是固定输入假设，**收入、毛利润、建议、MAE等输出必须由Python实时计算**，不能预写进前端。

## 4. 开关与最小前端变化

增加 `ENABLE_SYNTHETIC_DEMO`，与 `ENABLE_M5_DEMO`、`ENABLE_BUSINESS_UPLOAD` 三者独立。公开候选配置为：

```text
ENABLE_SYNTHETIC_DEMO=true
DEFAULT_DEMO_SOURCE=synthetic
ENABLE_M5_DEMO=false
ENABLE_BUSINESS_UPLOAD=false
M5_PUBLIC_LICENSE_CONFIRMED=false
```

`DEFAULT_DEMO_SOURCE` 必须只接受预定义值，且所选来源必须启用；非法或不可用配置不能悄悄退回未获准数据源。本地默认继续M5以保留现有行为和回归。

`/api/features` 增加合成能力及默认演示来源。前端在得到明确能力状态后选择固定来源，不能把“没有M5数据”当作自动合成替换。业务URL可使用 `?mode=synthetic&item_id=...&store_id=...`；导航继续携带相同上下文。

具体修改：

| 文件 | 最小修改 |
|---|---|
| 新 `synthetic_demo.py` | 固定样本适配、独立API和输入边界 |
| `app.py` | 注册Blueprint、扩展features、给模板传演示来源配置 |
| `runtime_config.py`、`render.yaml` | 新来源开关和公开默认值；不打开上传/M5 |
| `static/js/main.js` | 将二分支选择收敛为明确来源选择；请求路由、币种、上下文、来源文字与演示默认值 |
| `static/js/business_context.js` | 允许 `synthetic_demo`；沿用完整键，不与M5/上传混用 |
| `templates/base.html`、`dashboard.html` | 合成来源、默认入口及历史图表标注，避免初始闪现Walmart标签 |
| 必要时 `forecasting.html` | “Actual/Observed”增加合成历史限定，保留回测和未来分区 |
| 新 `tests/test_synthetic_demo.py`；现有JS测试增补 | API、引擎一致性、开关、隔离、来源与输入验证 |
| README、部署报告及白名单 | 加入新模块/测试，记录能力和限制 |

不修改 `forecast.py`、`inventory.py`、`finance.py`、`scenario.py` 的公式；不改原CSV内容或ABS模块。已有库存/财务HTML通常只需来源文字或契约适配，不另建界面。

## 5. 页面必须始终说明

- `Synthetic Business Demo · Illustrative data, not real business transactions`。
- 合成历史2024-01-01至03-24；模拟预测03-25至04-07，不是今日或真实2026年经营预测。
- 默认库存、价格、成本、交货时间、预算和促销增量都是可修改的演示假设。
- 样本有人工固定周模式，0 MAE不代表现实准确性或高置信度。
- 未连接企业账户，不生成采购订单；上传暂时关闭并说明待安全验收。
- ABS仍单独标官方来源、参考期和AUD，不参与修改合成或M5需求。

## 6. 确认后必须完成的验收

1. 原278项Python测试及12项JS测试保留，运行完整回归。
2. 固定CSV解析、日期、42天门槛与原forecast输出精确一致；两MAE与未来区间分开，不预写结果。
3. 关闭M5/上传时合成四页及所有合成API可用；原M5/上传接口仍拒绝，ABS继续正常。
4. 修改库存、采购量、预算和折扣后结果由原Python函数变化；检验FIFO、延迟到货、MOQ、现金/COGS规则未改变。
5. `source_kind`、revision、currency草稿隔离；两浏览器/请求的默认参数互不污染，不能替换固定需求。
6. 拒绝非法币种、字段、大小、非有限数、未知series、路径/URL与跨站请求，返回不包含本地路径/秘密。
7. 首屏、图表、审计表、推荐摘要和手机布局清楚标注Synthetic，不出现Walmart误标签或虚构真实企业KPI。
8. Git只提交审计白名单；确认服务器不含M5、上传库、密钥或研究原文件。
9. Render部署后用真实HTTPS独立浏览器重复四页流程及ABS、禁用功能检查。不能以本地测试代替。

## 7. 工作量与批准边界

这是一个小型适配功能，预计一个开发批次加一个回归/浏览器验收批次；不需要React、数据库迁移、网站重设计或新的托管付费服务。工时取决于现有前端来源分支调整与部署构建结果，不承诺未经执行的完成时间。

当前可继续做GitHub/Render授权核对、文件审计和不改变业务功能的部署准备。**合成公开入口的代码修改、开关启用及以此为默认的公开发布，须先获得用户对本方案的确认。** 若用户不批准增量，现有安全配置只能公开ABS及My Business不可用提示，不能声称已满足完整经营决策演示目标。
