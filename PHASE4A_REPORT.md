# MarginGuard Phase 4A：ABS 数据处理与计算模块

完成日期：2026-10-28（Australia/Sydney）。项目目录：`outputs/MarginGuard`。

## 1. 交付结论

已在现有项目中完成独立 ABS 数据层。优先批次 MHSI、Business Indicators，以及独立第二批 Business Counts 均已生成可供后续 Flask 读取的数据文件。全部 **109 项测试通过：原有 61 项 + 新增 ABS 48 项，失败 0、跳过 0**。

没有修改现有四个网页、`app.py`、预测/库存/财务/情景核心算法，也没有改写 M5 原始数据、历史处理结果或预测结果。本阶段没有增加网页或 API 路由，没有公开部署。下一步须经确认后进入 Phase 4B。

## 2. 新增文件

| 文件 | 用途 |
|---|---|
| `abs_data.py` | 官方 Excel 读取、元数据识别、统计口径与日期校验、跨表重复引用合并 |
| `abs_indicators.py` | 环比/同比、金额单位转换、官方库存销售比率读取与核对 |
| `abs_counts.py` | 企业数量、进入退出、两类企业存续 cohort 的独立解析与核对 |
| `scripts/prepare_abs.py` | 可重复的 market / counts / all 批次构建命令 |
| `requirements-abs.txt` | 独立列出 Pandas 2.2.3、openpyxl 3.1.5，并引用现有 Flask 依赖 |
| `tests/test_abs_data.py` | 21 项读取、来源、实际产物及隔离测试 |
| `tests/test_abs_indicators.py` | 14 项计算、空值、单位、比率及统计口径测试 |
| `tests/test_abs_counts.py` | 13 项企业数量与存续数据测试 |
| `data/abs/sources.json` | 17 个本地官方工作簿的路径、来源、日期、许可和 SHA-256 |
| `data/abs/market_data.json.gz` | 1,497 条时间序列及来源、数值、计算结果，1,557,978 字节 |
| `data/abs/market_catalog.json` | 不含逐期数值数组的序列目录，1,025,427 字节 |
| `data/abs/market_quality.json` | 缺失、重复引用、负值及比率核对统计 |
| `data/abs/business_counts.json` | 独立企业数量和存续结果，5,543 字节 |
| `data/abs/build_all.json` | 本次构建的输出大小及校验和 |
| `PHASE4A_REPORT.md` | 本报告 |

同时更新 README 的安装、重建、数据结构和解释说明。原有 `requirements.txt` 与启动脚本保持不变。原始 ABS Excel 仍在 `research/datasets/`，没有重复下载或复制进部署目录。

## 3. 使用的官方文件及统计范围

| 数据集 | 表格 | 本次处理范围 | 发布日期 |
|---|---|---|---|
| MHSI | Table 1 | 全国家庭消费及消费汇总 | 2026-09-29 |
| MHSI | Table 2 | 全国家庭消费类别 | 2026-09-29 |
| MHSI | Table 3–10 | NSW、VIC、QLD、SA、WA、TAS、NT、ACT | 2026-09-29 |
| MHSI | Table 19 | Experimental Retail Turnover，独立实验性指标 | 2026-09-29 |
| Business Indicators | Table 3 | Inventories，21 条序列 | 2026-08-31 |
| Business Indicators | Table 6 | Sales，45 条序列 | 2026-08-31 |
| Business Indicators | Table 15 | Business Gross Operating Profits，48 条序列 | 2026-08-31 |
| Business Indicators | Table 17 | Wages，54 条序列 | 2026-08-31 |
| Business Indicators | Table 23 | 官方 Inventory-to-Sales Ratio，6 条序列 | 2026-08-31 |
| Business Counts | Data Cube 1，Table 1 | Retail trade 四个财年的企业数、进入、退出 | 2026-08-18 |
| Business Counts | Data Cube 1，Table 2–3 | Retail trade 两个固定 cohort 的存续情况 | 2026-08-18 |

数据来源为已下载并验证的 ABS 官方工作簿，下载日期均为 **2026-10-27**。本次可用性截止日为 **2026-10-28**；MHSI 截至 **2026-08**，Business Indicators 截至 **2026-Q2**，Counts 截至 **2026-06-30**。没有添加这些快照之外的记录，也没有使用尚未发布的数据。

官方发布页及版权说明：

- [MHSI August 2026](https://www.abs.gov.au/statistics/economy/finance/monthly-household-spending-indicator/aug-2026)
- [Business Indicators June 2026](https://www.abs.gov.au/statistics/economy/business-indicators/business-indicators-australia/jun-2026)
- [Counts July 2022–June 2026](https://www.abs.gov.au/statistics/economy/business-indicators/counts-australian-businesses-including-entries-and-exits/jul2022-jun2026)
- [ABS copyright、许可排除与署名条件](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer)

每个具体 XLSX 的官方下载 URL、文件哈希及许可链接保存在 `sources.json`。ABS 材料一般采用 CC BY 4.0，受其列明的排除条款约束。后续网页应保留 Australian Bureau of Statistics 署名、来源、许可链接，并明确哪些数值由本项目计算，不暗示官方认可。

## 4. 成功处理的数据量

| 范围 | 唯一序列数 | 逐期数值位置数（含空值） | 空值数 | 日期覆盖 |
|---|---:|---:|---:|---|
| MHSI | 1,323 | 224,910 | 22,293 | 2012-07 至 2026-08，每条 170 个月份位置 |
| Business Indicators | 174 | 20,317 | 616 | 最早 1984-Q2，最晚 2026-Q2；每条以官方声明的起止期为准 |
| 合计 | **1,497** | **245,227** | **22,909** | 月度与季度分开 |

16 个时间序列工作簿共有 1,506 个序列列引用。MHSI Table 1 与 Table 2 有 9 个相同官方 Series ID；只有在元数据、日期和数值完全一致时才合并为同一条序列，保留两个来源引用，绝不重复相加。

1,497 条序列中，**735 条为金额水平序列**，已计算增长率；**756 条为 ABS 已发布百分比序列**，按原值保留；**6 条为官方库存销售比率**，不再进行增长率转换。序列唯一键由 `dataset_id + series_id` 组成，避免不同来源的标识碰撞。

Counts 不混入上述月度/季度计数：Table 1 有 **4 条财年记录（2022-23 至 2025-26）**；Table 2–3 有 **2 个固定 cohort、7 个存续观测**。其官方工作表没有 Series ID，输出明确为 null，不伪造官方编号。Counts 本次仅提取零售业，未扩展至所有行业。

## 5. 读取、数据结构与计算规则

### Excel 读取和校验

从 Data1 识别 `Unit`、`Series Type`、`Data Type`、`Frequency`、`Collection Month`、`Series Start`、`Series End`、`No. Obs`、`Series ID` 等标签，并结合描述解析指标、类别、地区和价格口径。按每条序列自己的声明区间截取，防止把其他列更早的历史范围误认为本序列的缺失历史。

日期序列必须严格有序、唯一且逐月或逐季连续。真实缺失观测保留日期，数值为 null；日期缺口、重复日期、未知文本、非有限数值、不匹配的单位或口径会明确报错。源文件必须匹配 SHA-256；发布日期、下载日期及参考期必须满足可用性截止规则。

统一结构保留 `dataset_id`、`series_id`、`table_ids`、`source_ids`、`frequency`、`adjustment`、`price_basis`、`unit`、`currency`、`classification`、`domain`、`experimental` 和逐期 `periods/values/status`。来源放在顶层 `sources` 字典，通过 `source_ids` 关联；这样不必在每个观测重复整段来源文本。

### 增长率与金额单位

`增长率（%） = (本期值 / 对比期值 − 1) × 100`。

- 月度：上月环比、上年同月同比，分别滞后 1、12 个月。
- 季度：上季环比、上年同季同比，分别滞后 1、4 个季度；不年化，也不称为月度增长。
- 当前值或基期缺失，或基期 ≤ 0 时，增长率返回 null。当前值为 0、基期为正时，增长率为 −100%。负利润观测保留；基期为负时不输出容易误读的常规增长率。
- ABS 官方百分比与依据公布金额重算的百分比分开保存。后者保存至小数点后 6 位；这不是新增统计精度，也不是百分点变化。
- 金额保持 `AUD million`。`convert_value` 支持 AUD、AUD million、AUD billion 间的显式量级换算，不进行汇率、通胀、季节调整或频率转换。百分比、比率、企业数不能互相转换。

### 官方库存销售比率

直接保留 Table 23 官方比率，同时用相同发布批次、行业、地区、Original、Current Prices、`TOTAL (SCP_SCOPE)` 的 Table 3 库存和 Table 6 销售额作核对。库存是季末存量，销售是季度流量；不能混入 CORP 范围或季调值。

官方比率公布至两位小数，核对允许 0.005 加极小浮点容差。6 个行业共 **742 个可比季度观测全部一致**；零售业其中 **110 个季度一致**。读取结果仍以官方 Table 23 为准，不用重算值替代。该指标不是库存覆盖天数，也不是基于 COGS 的周转率。

### 企业数量和存续

Table 1 核对 `期初 + 进入 − 退出 = 期末`，并核对净变化及官方四舍五入后的百分比。Table 2–3 分别以原有企业 cohort 和新增企业 cohort 的固定起始数量为分母计算存续率；不能把它们连接成单一年度存续序列。

Counts 单位是企业数，不能解释为门店数。进入包含企业出生及其他进入，退出也不能直接称为破产。

## 6. 从本次文件读取的示例结果

金额以下均为 **AUD million**，仅为核对示例，不是商品级 USD 情景结果。

| 官方 Series ID / 范围 | 指标及口径 | 最新参考期 | 原始发布值 |
|---|---|---|---:|
| A130200584T | 全国家庭消费，Seasonally Adjusted | 2026-08 | 82,340.5 |
| A130200588A | 上述口径官方同比（%） | 2026-08 | 6.8 |
| A130276228K | Table 19 总零售营业额，Seasonally Adjusted，Experimental | 2026-08 | 40,037.6 |
| A3531380T | 零售业库存，Original | 2026-Q2 | 47,803 |
| A3531378F | 零售业销售额，Original | 2026-Q2 | 147,756 |
| A3531381V | 零售业 Business Gross Operating Profits，Original | 2026-Q2 | 7,686 |
| A3531379J | 零售业工资，Original | 2026-Q2 | 15,249 |
| A3531382W | 零售业官方库存销售比率，Original，无量纲 | 2026-Q2 | 0.32 |

由公布的季调家庭消费金额重算，2026-08 环比为 **0.030249%**、同比 **6.840529%**；官方同比为 6.8%。这是公布数值精度不同导致的展示差异，不能把重算数值标成 ABS 官方精确增长率。

2025-26 财年零售企业期末数量 **156,143**，进入 **24,568**、退出 **24,443**，净增 **125**。June 2022 原有企业 cohort 到 June 2026 存续 **88,856 / 157,321**，官方存续率 **56.5%**；2022-23 新增企业 cohort 到 June 2026 存续 **10,979 / 23,766**，官方存续率 **46.2%**。

## 7. 数据质量与限制

1. **22,909 个源表空值按 null 保存。** 其中有趋势估计暂停及增长率起始期等情况，不一概解释成销量或业务为零。例如零售库存 Trend 序列在 2020-Q1 至 2022-Q3 有 11 个空值。前端应显示缺失和断线，不自动插值。
2. 金额水平序列有 **33 个负值**，出现在利润等可为负的指标中，已保留。若把官方百分比的负增长也计入，总负值位置为 29,783；这些不自动构成数据错误。
3. 所选表格是 **Current Prices**；没有加入 Chain Volume Measures。解析器会拒绝意外出现的其他价格口径，后续需要单独扩展与测试，不能把名义金额称为实际增长。
4. **Original / Seasonally Adjusted / Trend 分开保存**，没有自行做季节调整。MHSI 消费类别使用 COICOP；消费总项保留为 spending aggregate；Table 19 保留为 ANZSIC retail groups；Business Indicators 与 Counts 使用 ANZSIC。
5. Table 19 为 Experimental；未与旧 Retail Trade 拼接。Household Spending 与 Business Sales 的统计对象不同，不直接相加。
6. Business Gross Operating Profits 为行业经营统计，不是本项目商品的 Revenue−COGS 毛利润；也不据此推断某个 Walmart 商品盈利。
7. 当前输出是固定发布批次的快照，后续 ABS 修订需人工审核新来源、校验和与口径。`--as-of` 仅验证可用性，不能还原更早发布批次；本次未开发自动更新。
8. 源文件存在本机研究目录。项目单独迁移后仍能读取轻量 JSON，但重新生成 Excel 处理结果需要保留这些已验证工作簿及目录结构。

## 8. 自动化测试与保留验证

实际运行环境：Python 3.9.6、Flask 3.1.2、Pandas 2.2.3、openpyxl 3.1.5。

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```

结果：**Ran 109 tests — OK**。新增测试覆盖 Excel 字段、Series ID、日期连续性、重复引用、月度/季度增长、零/负基期、单位换算、空值、官方比率、统计范围、不同来源隔离、Original 与季调区分、Experimental 标记、来源/发布日期、未来不可用数据拒绝、真实 XLSX 解析与交付数据一致性。原有 Phase 1–3 的 61 项测试全部保留并通过，包括真实 M5 数据和 Flask 接口回归。

完整日志：项目外 `research/datasets/phase4a_tests.log`。原始文件保护清单及结果位于同目录的 `phase4a_before.json`、`phase4a_preservation.json`。对本阶段开始前的 49 个文件进行 SHA-256 比较，确认 48 个完全不变，只有文档 README 发生已说明的修改；四个核心算法、应用/页面、旧测试和 M5 文件保持不变。17 个 ABS 输入工作簿及全部生成产物的校验和也已核对通过。

本阶段没有重做浏览器交互测试；已有 Flask 回归测试通过，网站文件未改。Phase 4B 新页面仍需单独执行浏览器验证。

## 9. 运行方式及后续 API 建议

```sh
.venv/bin/python -m pip install -r requirements-abs.txt
.venv/bin/python scripts/prepare_abs.py --dataset all --research-dir ../../research/datasets --as-of 2026-10-28 --overwrite
```

也可以先使用 `--dataset market`，再单独运行 `--dataset counts`。默认禁止覆盖已有输出；明确 `--overwrite` 只覆盖选择批次的 ABS 生成文件，不修改 Excel 或 M5。完整说明见 README。

Phase 4B 可考虑以下只读 API，**本阶段尚未实现**：

| 建议 API | 用途与校验 |
|---|---|
| `GET /api/market/catalog` | 返回可选数据集、指标、地区、频率、调整方式、单位与日期范围 |
| `GET /api/market/series?dataset_id=...&series_id=...` | 返回选定序列、已有 Python 增长率、空值状态、来源；拒绝未知 ID，限制一次请求序列数 |
| `GET /api/market/business-counts` | 独立返回财年企业数量与两组存续情况，避免混入月度图表 |
| `GET /api/market/sources` | 来源、发布日期、参考期、许可及方法说明 |

后端可在启动时读取并缓存轻量文件，API 仅过滤已计算结果。JavaScript 负责交互和呈现，不重算核心指标。默认显示时需在同一视图明确指标、频率、口径、单位和参考期；缺失显示为 unavailable，Experimental 需可见标识。ABS 金额使用 AUD，现有 Walmart 情景继续使用 USD。

Phase 4A 已完成，等待用户确认 Phase 4B 后再开展网页开发。
