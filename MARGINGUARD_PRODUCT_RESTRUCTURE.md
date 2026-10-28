# MarginGuard 产品结构优化方案

日期：2026-10-28（Australia/Sydney）  
状态：**设计提案，待用户确认后实施。本轮仅新增本文档。**

## 1. 产品定位与本次建议

**MarginGuard — Retail Risk & Financial Decision Intelligence**

面向中小型零售企业、品牌经营者、采购经理和运营分析人员，帮助用户把商品需求预测转化为库存风险判断，再通过财务情景比较支持采购与经营决策。

核心流程保持为：

**Demand Forecasting → Inventory Risk → Financial Scenario Simulation → Purchasing Decision**

建议采用 **两个工作空间、五条既有页面路由** 的最小改动方案：My Business 为默认入口和核心工作空间；Market Intelligence 提供独立的外部市场背景。通过导航分区、业务步骤引导和可审核的假设传递突出主流程，复用全部现有 Python 算法与图表。

这里的 Purchasing Decision 是 Financial Decision Lab 内的建议摘要，不新增采购系统、不提交真实订单。Market Intelligence 的五个栏目是现有 `/market` 页内导航，不新增五个市场页面。

## 2. 当前产品结构的问题

以下判断来自现有代码及 Phase 3、Phase 4B 报告，而非假设网站已具备尚未实现的能力。

| 当前情况 | 对产品定位的影响 | 最小改进 |
|---|---|---|
| 四个业务页面与 Market Insights 在同一级导航中并列 | 用户难以辨认哪个是主要工作流程、哪个是辅助分析 | 顶层分为 My Business / Market Intelligence，默认打开 My Business |
| 市场页包含七个丰富区块，视觉内容明显多于业务页 | ABS 容易被理解为产品中心 | 市场指标留在独立空间；业务首页不插入 ABS KPI、榜单或市场新闻 |
| Overview、Scenario Lab 等名称偏功能展示 | 没有突出中小零售企业的采购决策目标 | 使用 Business Overview、Financial Decision Lab 等业务名称 |
| Overview 已有销量、预测、MAE 和默认库存风险，但缺少完整下一步提示 | 用户能看指标，却不清楚如何推进到采购判断 | 加入四步流程提示及明确的下一步按钮 |
| `main.js` 已用 URL 传递商品和门店，但每次加载表单都重置为默认假设 | 在库存页修改参数后进入情景页，实际假设并未贯通 | 小范围增加同一浏览器标签页的假设草稿；不建设数据库 |
| Overview 风险来自默认假设，不随库存页编辑更新 | 用户可能把旧的默认风险误认为当前分析结果 | 标明默认/会话假设；已有草稿时重新调用库存 API，再更新风险 |
| 当前仅有五个 M5 商品、一个 CA_1 门店，无企业档案或账户体系 | “My Business”可能让用户误以为已连接自己的企业 | 固定显示 M5 demo 身份，真实企业连接留待未来 |
| Market 专属顶部导航与业务页桌面侧栏不同 | 两个空间有可能显得像两个不同产品 | 复用共享导航骨架，以工作空间区分内容，不另造一套应用 |

因此，仅改名称或增加 Next 按钮可以改善阅读顺序，但不能声称已经完成参数贯通。方案将这两项工作分别估算、分别验收。

## 3. 推荐导航与页面映射

### 3.1 顶层结构

```text
MarginGuard
Retail Risk & Financial Decision Intelligence

My Business                         ← 默认核心工作空间
  Business Overview
  Demand Forecasting
  Inventory & Risk
  Financial Decision Lab

Market Intelligence                 ← 独立的辅助工作空间
  Australian Retail Market Overview
  Industry Performance
  State Comparison
  Retail Financial Indicators
  Business Dynamics
```

桌面端优先复用原有业务侧栏：顶部显示工作空间切换，下面显示当前空间的导航；手机端沿用紧凑顶部导航和换行布局。Market 页只调整与共享导航冲突的少量 CSS，不重画现有分析卡片。品牌链接始终返回 `/`，无指定深链接时默认进入 My Business。

完整定位语用于首页、README 和项目介绍；导航品牌仍显示短名称 MarginGuard，避免长标题占满导航。进入 Market Intelligence 后，清楚显示当前空间，并提供返回 My Business 的入口。

### 3.2 既有路由全部保留

| 工作空间 | 推荐显示名称 | 现有位置 | 改动范围 |
|---|---|---|---|
| My Business | Business Overview | `/` | 改标题、增加主流程引导与清晰的数据身份 |
| My Business | Demand Forecasting | `/forecasting` | 改标题、增加到库存评估的下一步 |
| My Business | Inventory & Risk | `/inventory` | 改标题、增加审核补货候选的入口 |
| My Business | Financial Decision Lab | `/scenarios` | 改标题、突出建议摘要及采购权衡 |
| Market Intelligence | Australian Retail Market Overview | `/market#market-overview` | 作为市场主页；保留 `#consumer` 家庭消费趋势为其下属内容 |
| Market Intelligence | Industry Performance | `/market#industry` | 保留 COICOP 与实验性零售行业分开的比较 |
| Market Intelligence | State Comparison | `/market#states` | 保留州/领地增长比较 |
| Market Intelligence | Retail Financial Indicators | `/market#financial` | 包含经营指标，以及 `#ratio` 官方库存销售比率 |
| Market Intelligence | Business Dynamics | `/market#dynamics` | 保留企业进入、退出、净变化及两组 cohort |

`/market` 本身继续可用。原来的七个区块及其锚点全部保留，只把局部导航归为五组；不删除 Consumer Spending 或 Inventory-to-Sales Ratio。市场页直接打开带锚点 URL 时，应在异步内容加载完成后定位对应区块。

后端 endpoint 名称与前端内部 page key 可继续保留 `dashboard`、`forecasting`、`inventory`、`scenarios`、`market`。改动显示文案即可，不为改名重命名模块、文件和计算接口。

## 4. 两个工作空间的职责

| 维度 | My Business | Market Intelligence |
|---|---|---|
| 核心问题 | 这个商品未来需要多少库存？不同经营策略如何影响毛利和现金？ | 澳洲消费、行业经营及企业动态如何变化？ |
| 数据层级 | 选定商品—门店的每日记录和 14 天情景 | 国家、州/领地、行业的月度、季度或财年统计 |
| 当前数据 | Walmart M5 历史样本；库存、成本、交货时间等为假设 | Phase 4A 的 ABS 已发布快照 |
| 当前金额 | USD | AUD，明确 million/billion |
| 输出 | 预测、MAE、库存风险、三策略比较、条件化建议 | 官方指标、增长比较、描述性 Business Insights |
| 与另一空间的关系 | 可以主动打开市场空间了解背景 | 不自动调整 M5 预测、库存规则或经营策略评分 |

两个空间可以共享视觉、导航、帮助与来源说明，但不共享混杂的 KPI 或计算输入。切换空间不应把 M5 的 `item_id/store_id` 附加到 ABS 筛选请求，也不应将 ABS 的州、行业和月份注入商品情景。

### 当前企业身份如何显示

推荐固定展示：**Business data: Walmart M5 demo**，旁边保留 **Store: CA_1** 和实际商品选择。

可以将这一展示行称为 Business context，但本次不创建虚构企业列表、不开发注册登录、多租户、企业数据连接。需要选择器外观时，仅保留一个明确的演示选项；不要显示不可用的虚构客户、门店或“已连接企业”。

首页说明可写为：

> Decision support for small retailers. This demo uses historical Walmart M5 sales; inventory and cost inputs are assumptions.

这一区分说明产品面向 SME，但现有案例并不是某家 SME 的真实经营数据。Overview 的指标仍应标明“所选商品—门店”，不能把五个样本商品称为企业完整经营总览。

## 5. 从 Business Overview 到采购建议的交互流程

### 5.1 六步业务体验

| 步骤 | 用户行为与界面 | 复用能力与下一步 |
|---|---|---|
| 1. 确认业务范围 | 查看 M5 demo 身份，选择真实门店/商品，确认历史日期、预测日期、币种 | 使用 `/api/catalog` 和 `/api/analysis`；CA_1 是目前唯一门店，不虚构第二家 |
| 2. 查看需求 | 首页保留历史销量、14 天预测、MAE、风险状态；进入 Demand Forecasting 查看两方法和回测 | 按钮 `Assess inventory risk`，继续携带同一商品和门店 |
| 3. 评估库存 | 输入库存、交货期、安全库存、在途数量；查看缺货/过剩规则和建议额外补货量 | 继续调用 `/api/inventory`；结果旁显示本次假设与是否外推超过 14 天 |
| 4. 建立财务情景 | 从库存页进入 Financial Decision Lab，审核带入的库存、交货期和补货候选；补全价格、旧库存成本、新采购成本、MOQ、运费和预算 | 按钮 `Compare strategies`；调用现有 `/api/scenarios`，不在 JavaScript 计算财务指标 |
| 5. 比较策略 | 在相同 14 天需求下比较 Wait、Reorder、Discount；展示毛利、收入、未满足需求、期末库存、采购现金、可行性 | 保留现有表格、利润图、预算/MOQ 检查和每日审计 |
| 6. 审核决策 | 在同一页顶部查看 `Purchasing decision summary`：推荐动作、已测试采购量、现金、到货时间、未满足需求、原因和权衡 | 可以修改参数再比较；不增加真实下单、供应商发送或付款按钮 |

主流程提示可在四个业务页面显示：`Overview → Forecast → Inventory → Decision Lab`，突出当前步骤，但允许用户直接进入任一页面，不强制向导锁定。

Business Overview 保持现有四项有依据的 KPI。没有运行情景前，不新增固定利润、采购金额或“预计节省”数字；显示 `Run a financial scenario` 引导即可。ABS KPI 不进入这个首页。

### 5.2 最小的参数贯通设计

建议使用 **sessionStorage 中的假设草稿**，限定当前浏览器标签页。它是交互状态，不是企业账本或多用户库存数据库。

- 草稿按数据源标识、商品、门店、历史截止/预测区间隔离。商品切换不沿用其他商品的库存和成本；未来更换数据集或预测区间时旧结果失效。
- 继续用 URL 保存可公开的商品和门店选择。库存、成本、预算等不放入 URL，避免作为链接参数外传。
- 只保存输入与必要的版本标识。跨页显示计算结果时调用现有 Python API 重算，不将旧浏览器结果当作新的权威结果。
- 页面标明 `Assumption draft · this tab`。保存失败或浏览器禁用存储时，继续支持手工分析，并明确提示本次输入不会跨页保留。
- 修改参数后隐藏旧推荐，显示待重算；重置清除当前商品对应草稿并恢复明示的默认假设。
- 返回 Overview 时，有库存草稿则用同一组参数重新调用库存 API；没有草稿时继续显示 `Default assumptions`，不能把默认值描述为实际库存。
- 不自动覆盖用户已编辑的 Decision Lab 草稿。使用显式 `Use inventory assumptions` / `Use suggested quantity` 操作，显示将带入的字段及其来源；用户可保留或修改。

此处可以增加少量前端状态管理函数，不需要 React、数据库、新业务对象体系或新的预测服务。所有输入仍须经过已有 Python 校验。

### 5.3 必须保留的模型边界

**库存建议量不是最优采购量。** 现有建议量是交货期需求加安全库存、减当前及在途数量后的正差，并向上取整。它未考虑成本、MOQ、预算，也没有遍历所有采购数量。因此带入 Decision Lab 时标记为 `Proposed order quantity`，仍需审核并通过现有可行性比较。

| 输入或情形 | 最小方案的处理规则 |
|---|---|
| 当前库存、供应商交货期 | 可显式带入同一商品的财务情景；不改变实际算法的“交货期 7 天＝第 8 天开始可售”规则 |
| 安全库存、过剩阈值 | 保存在库存分析草稿中；不能宣称已成为情景期末库存的硬约束 |
| `max_unmet_units` | 继续作为用户独立设定的服务约束，不能由安全库存数值自动替代 |
| 已有 `on_order_units > 0` | 禁止一键复用该库存建议进入完整情景；说明当前情景引擎不支持既有在途订单的收货与成本层。不能忽略在途量，也不能把它加到当前库存 |
| 在途订单场景仍需探索 | 可独立打开 Decision Lab，手工建立清楚标注“不含既有在途订单”的假设；不得声称是在评估原完整库存情境。完整支持另列后续算法需求 |
| 建议额外采购量为 0 | 显示无需按该库存规则额外补货；若用户采用零采购情景，费用须符合现有零数量校验，不静默覆盖已填运费或其他费用 |
| 最后观察到的售价 | 可作为未来售价默认参考，仍标记为假设，保留其历史日期 |
| 旧库存单位成本与新采购单位成本 | 保留两个独立输入，不合并为一个 Purchase Cost；采购现金与已售商品 COGS 继续区分 |
| 折扣与销量提升 | 沿用用户假设，不描述为 M5 已验证价格弹性 |

建议摘要应准确表述：**在当前测试的 Wait、指定采购方案 Reorder 和 Discount 中，选择满足预算、MOQ 及已设服务约束的预计毛利润最高方案。** 它不是所有采购量中的全局最优解，也不是实际净利润保证。未设置服务约束时，缺货本身不会自动使策略不可行。

推荐 Wait 时表示不新增采购；推荐 Discount 时是促销方案；推荐 Reorder 时展示实际被比较的采购量及现金，而不是另算“最优数量”。全部不可行时保留 `No feasible strategy`，不强行推荐。

## 6. 未来扩展：只规划，暂不开发

| 功能 | 未来用途 | 开发前需要明确的条件 |
|---|---|---|
| Upload Your Own Sales Data | 将 M5 demo 替换或切换为用户自己的业务数据 | 上传模板、日期/商品/门店键、销量与退货定义、币种、缺失日期语义、重复检测、历史长度；库存成本独立说明；文件大小/格式限制、存储和删除规则 |
| Business vs Market Comparison | 帮助用户将可比的企业趋势置于行业背景中 | 先通过下述可比性检查；不通过时不给“跑赢市场”等结论 |
| Multi-product Inventory Analysis | 多商品库存风险排序、采购现金与服务约束统筹 | 逐商品库存与成本、统一周期、单位、供应约束及共享预算；不能简单相加单品独立建议后声称组合最优 |
| Business Performance Report | 输出可复现的企业决策摘要与情景报告 | 来源、数据截止日、参数版本、计算结果和限制；实际业绩与预测情景分开，不能把预计毛利称为已实现业绩 |

第一版不在导航里增加四个无法使用的功能入口。未来路线放在项目文档中；上线展示如需介绍，明确标记 Planned，不伪造已完成功能。

### Business vs Market Comparison：必须先判断可比性

未来宜由 Python 返回 `Comparable`、`Context only` 或 `Not comparable`，附具体原因；不设置未经依据的综合可比性分数。

| 检查项 | 最低要求 |
|---|---|
| 地区 | 确认企业销售发生地及覆盖范围；单店、跨州、电商订单的地区分配规则必须明确 |
| 行业/类别 | 区分企业的 ANZSIC 行业与商品/消费的 COICOP 分类；不假定二者一一对应，也不把单 SKU 自动等同于整行业 |
| 日期与频率 | 使用共同已观察区间、完整月份或季度；每日企业数据先按明确规则汇总，不能将 14 天未来预测与当月实际统计直接相减 |
| 指标定义 | 销量、含税收入、净销售、家庭消费、企业销售额分别匹配；明确退货、取消订单和 GST 等定义，不混用金额与件数 |
| 调整和价格口径 | Original、Seasonally Adjusted、Trend 及 Current Prices/CVM 分开；没有合适季调方法时，不把企业原始月环比直接解释为相对市场季调表现 |
| 币种与规模 | 比较金额时保证币种与量级一致；增长率或基期指数可辅助观察，但不能消除地区、定义和样本覆盖差异 |
| 库存与利润 | 商品毛利润不是 ABS Business Gross Operating Profits；库存假设不是观察值，Days of Cover 不是行业库存销售比率 |
| 质量与版本 | 足够的连续历史、清楚的缺失/零值规则、同比基期、来源发布日期、修订版本及覆盖范围 |

**现有 M5 demo 与 2026 年 ABS 不应生成企业相对市场绩效结论。** 当前商品样本来自美国 CA_1、使用 USD、历史在 2015–2016 年；ABS 为澳大利亚统计，最新参考期在 2026 年。ABS 虽有更早历史可选，但选取重叠年份也不能消除国家、业务范围和指标定义差异。当前只能独立展示背景，不输出“本企业跑赢澳洲市场 X%”或用 ABS 调整 M5 预测。

## 7. 预计需要修改的文件与开发工作量

### 7.1 后续实施文件清单

| 文件 | 计划改动 |
|---|---|
| `templates/base.html` | 两工作空间切换、当前空间导航、产品定位文案、业务/市场身份与币种提示 |
| `app.py` | 页面显示标题及必要的工作空间模板上下文；五条路由和计算 API 保留 |
| `templates/dashboard.html` | Business Overview 标题、业务步骤、所选商品范围、下一步入口 |
| `templates/forecasting.html` | Demand Forecasting 标题、库存评估下一步及范围摘要 |
| `templates/inventory.html` | Inventory & Risk 标题、假设来源、补货候选审核及不兼容在途情况提示 |
| `templates/scenarios.html` | Financial Decision Lab 标题、可审核预填区、建议摘要与模型边界 |
| `templates/market.html` | 归并为五组局部导航，七个现有分析区块保留 |
| `static/js/main.js` | 只给 My Business 链接传商品参数；会话草稿隔离、显式预填、旧结果失效及调用已有 API |
| `static/js/market.js` | 仅在需要时补充异步加载后的锚点定位，不改变统计/筛选逻辑 |
| `static/css/style.css`、`static/css/market.css` | 共享工作空间导航、步骤条和简洁提示；消除重复导航覆盖规则，不重做图表 |
| `tests/test_web.py`、`tests/test_market_web.py`，必要时新增 `tests/test_product_flow.py` | 保留数值和安全断言；同步预期显示名称，增加导航和流程验收 |
| `README.md`，后续实施报告 | 新定位、演示身份、操作路径、草稿规则及验证结果 |

`forecast.py`、`inventory.py`、`finance.py`、`scenario.py`、`data_loader.py`、`phase2_inputs.py` 无需改动；M5/ABS 文件、ABS 计算模块及市场 API 无需改动。sessionStorage 的行为须用实际浏览器验证，不能仅用 Flask HTTP 200 代替。

### 7.2 建议分两小步实施

| 小步 | 内容 | 估计投入 |
|---|---|---:|
| A：定位与导航 | 两工作空间、四页显示名、市场五组导航、demo 身份、流程步骤和下一步按钮 | 3–5 小时 |
| B：可审核的会话衔接 | 商品隔离的草稿、显式预填、Overview 风险重算、在途与旧结果边界、建议摘要 | 4–7 小时 |
| 联合验收和文档 | 原有 133 项回归、必要新增测试、浏览器连贯流程、宽度检查、README/报告 | 3–5 小时 |
| 预留修复 | 导航样式、异步状态和边界处理 | 2–3 小时 |
| 推荐最小完整版本 | A + B + 验收，不含任何未来扩展或公开部署 | **约 12–20 小时，通常 2–3 个工作日** |

以上为设计估算，不是已完成工时或交付保证。A 可以单独交付以先恢复产品重心；若只完成 A，必须继续说明表单假设未贯通，不将其宣传为完整业务闭环。推荐确认后按 A → B 顺序推进，每步可回归验证，不一次重构整个站点。

### 7.3 验收标准

- `/` 默认为 My Business；五个原有页面和旧 URL 继续可访问。
- 导航清晰区分两空间；市场七个区块仍可使用，所有原统计口径和来源标识保留。
- 从选择商品到查看采购建议使用同一商品、门店和预测区间；不得跨商品污染草稿。
- 库存修改后返回首页，风险明确来自相同假设的 Python 重算；未计算时无虚假财务 KPI。
- 带入采购量可审核，已有在途、零采购费用、预算/MOQ和全部不可行情况有明确处理。
- 刷新、返回、换商品、重置、存储不可用及 API 失败时不显示过期推荐。
- 所有计算继续调用原算法；原 133 项测试的业务断言保留并通过，代码/数据校验确认核心文件未变。

## 8. 对 COMP9001 提交与公开部署的影响

### COMP9001

这次调整使演示更容易围绕一个业务问题展开：解释销量预测，说明库存规则，然后比较毛利、采购现金和服务水平。这样能够更清楚地展示现有 Python 的模块化、输入校验、控制流程、文件读取、测试和解释性；ABS 保留为辅助扩展，不抢占核心讲解时间。

建议课堂演示以 My Business 为主，先完整展示一个商品的决策流程，再简要介绍 Market Intelligence 的独立来源与口径。继续保留 CLI 和算法说明，能够离开界面解释核心逻辑。

此前计划目标是 **2026-11-01** 提交，具体截止时间和正式评分要求仍以课程通知为准。本方案没有核实新的 rubric、依赖限制或 AI 使用政策，因此不能据此保证已满足全部课程要求。

建议确认后优先完成 A；若时间允许且边界测试通过，再纳入 B。10 月 31 日保留为版本冻结、回归、干净环境演练与备份时间；11 月 1 日不临时加入 CSV 上传、企业比较、多商品优化或公开部署。若 B 来不及稳定，提交诚实标注状态的 A 版本比带有隐性假设错配的版本更可靠。

### 公开部署

结构优化能明确“商品决策 demo”与“官方市场数据”的边界，但它本身不完成部署准备，也不改变数据使用权限。

- M5 历史/子集通过网页和 API 公开展示的许可范围，依据既有研究记录仍需确认；仅排除原始 CSV 并不等于已经确认展示权限。本文不作新的许可结论。
- ABS 的来源、发布日期、Experimental、CC BY 4.0 与排除条件说明继续保留，不暗示 ABS 背书。
- 默认仍是演示数据与假设输入，不宣称已接入真实客户或提供多租户服务。当前会话草稿不是安全的企业数据托管方案。
- 后续部署须单独确认生产运行方式、HTTPS、错误与日志边界、资源限制、静态路径范围、恢复方式及公开数据范围。
- 新增导航不应把 `research/`、原始数据或本地路径暴露为下载入口。未来上传真实企业数据时，再单独设计隐私、访问控制和删除规则。

**本次建议的确认范围为 A 和 B 的产品结构与流程设计；未来扩展和公开部署均不包含在内。当前网站、算法和数据保持原样，等待用户确认后再实施。**
