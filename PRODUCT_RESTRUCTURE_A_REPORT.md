# MarginGuard 产品结构方案 A 实施报告

日期：2026-10-28（Australia/Sydney）  
状态：**方案 A 完成；方案 B 尚未开始。仅本机运行，未公开部署。**

## 1. 实施结果与范围

产品定位为 **MarginGuard — Retail Risk & Financial Decision Intelligence**，面向中小型零售企业、品牌经营者、采购经理与运营分析人员。

本次在既有 `outputs/MarginGuard` 项目中调整了定位、导航、页面名称和业务步骤引导。My Business 成为默认核心工作空间；Market Intelligence 提供独立的 ABS 市场背景。仍然只有原来的五条 Flask 页面路由，没有创建新项目或新的市场子页面。

四个业务页面均明确显示 **Business data: Walmart M5 Demo**，并说明历史销量来自 M5，库存、采购成本与交货期为用户假设，没有连接真实企业账户，预测日期是历史数据集的模拟预测区间。首页仍展示所选商品—门店的既有指标，不增加企业总收入、利润或其他虚构 KPI。

## 2. 导航结构

| 工作空间 | 显示名称 | 路由或页内位置 |
|---|---|---|
| My Business（默认） | Business Overview | `/` |
| My Business | Demand Forecasting | `/forecasting` |
| My Business | Inventory & Risk | `/inventory` |
| My Business | Financial Decision Lab | `/scenarios` |
| Market Intelligence（辅助） | Australian Retail Market Overview | `/market#market-overview`，包含 `#consumer` |
| Market Intelligence | Industry Performance | `/market#industry` |
| Market Intelligence | State Comparison | `/market#states` |
| Market Intelligence | Retail Financial Indicators | `/market#financial`，包含 `#ratio` |
| Market Intelligence | Business Dynamics | `/market#dynamics` |

两种工作空间共用深蓝导航、浅灰内容背景和白色卡片。桌面端使用侧栏；窄屏改为顶部换行布局。当前工作空间、当前业务页面与业务步骤都有高亮及 `aria-current` 标记。市场页根据点击的栏目或 URL 锚点高亮导航，兼容原有 `#consumer` 和 `#ratio` 深链接。

市场页原来重复的七项横向导航已移除，七个实际分析区块全部保留。家庭消费趋势归入市场总览，官方库存销售比率归入财务指标；没有删掉图表、筛选器、来源或定义。ABS 的参考期、Original / Seasonally Adjusted、Experimental、AUD 单位和许可说明均保留，ABS 指标不进入 My Business KPI。

## 3. 业务流程与参数边界

四个 My Business 页面统一显示：

**Overview → Forecast → Inventory → Decision Lab**

| 当前页面 | 下一步按钮 | 行为 |
|---|---|---|
| Business Overview | View demand forecast | 进入所选商品的预测分析 |
| Demand Forecasting | Assess inventory risk | 进入同一商品的库存分析 |
| Inventory & Risk | Compare financial strategies | 进入同一商品的财务决策页，提示审核假设 |
| Financial Decision Lab | Review business overview | 回到同一商品总览，形成审核循环 |

导航、步骤链接、下一步按钮及首页的决策页入口通过 URL 继续传递 `item_id` 与 `store_id`。没有修改预测内容或在 JavaScript 中新增业务计算。用户仍可自由进入任意步骤，无强制锁定的向导。

**本阶段仅保留商品和门店，不贯通库存、成本、交货期等输入。** 换页时表单仍恢复原有默认假设，页面已明确提示这一行为。首页库存 KPI 仍标注默认假设；不会假装沿用之前输入的库存。

Market Intelligence 不接收 M5 商品参数。通过它的 My Business 入口返回 `/` 时，加载默认商品；本阶段没有增加跨工作空间选择记忆。现有带商品和门店参数的业务深链接仍可使用。

## 4. 文件清单

| 文件 | 变更 |
|---|---|
| `app.py` | 仅更新五个页面的显示标题，保留路由、内部页面标识与 API |
| `templates/base.html` | 共享工作空间导航、产品定位、M5 身份说明、四步流程、下一步按钮及页脚 |
| `templates/dashboard.html` | 首页业务导语、演示商品表说明和 Financial Decision Lab 入口 |
| `templates/market.html` | 市场背景定位、五组栏目对应的区块说明，移除重复导航 |
| `static/css/style.css` | 共享导航、工作空间切换、流程卡片和响应式样式 |
| `static/css/market.css` | 移除与共享导航冲突的市场专属页面外壳样式，保留分析内容样式 |
| `static/js/main.js` | 将商品参数传递限定到 `data-business-link`；更新一处库存页显示名称 |
| `static/js/market.js` | 五组锚点导航、高亮、旧锚点归组及异步加载后的定位 |
| `tests/test_market_web.py` | 更新两处旧页面名称断言，保留原有 24 项测试 |
| `tests/test_product_navigation.py`（新增） | 8 项导航、路由、流程、数据说明和工作空间隔离测试 |
| `README.md` | 更新产品定位、页面入口、导航结构与方案 A 的参数边界 |
| `PRODUCT_RESTRUCTURE_A_REPORT.md`（新增） | 本中文交付报告 |

未引入新依赖、框架、账户系统、前端存储或数据库。`templates/forecasting.html`、`templates/inventory.html`、`templates/scenarios.html` 无需修改，由共享模板获得新导航与业务流程。

## 5. 自动化测试与完整性核对

实施前运行 **133 项既有测试，全部通过**。完成后运行同一套测试及新增的 8 项导航测试：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```

最终结果：**141 项通过，0 失败，0 错误，0 跳过；耗时 3.190 秒。** Phase 1、Phase 2、原网页、ABS 数据及市场 API 测试均保留。既有测试仅两处显示名称断言随新产品名称更新，没有删除测试或放宽数值校验。

实施前后使用 SHA-256 核对 72 个基线文件：62 个未改，10 个为本报告列出的预期修改，0 个缺失。以下 11 个模块与全部 20 个 `data/` 基线文件完全一致：

`forecast.py`、`inventory.py`、`finance.py`、`scenario.py`、`data_loader.py`、`phase2_inputs.py`、`abs_data.py`、`abs_indicators.py`、`abs_counts.py`、`market_service.py`、`market_api.py`。

因此 M5 原始数据、处理后销量、预测 JSON、ABS 轻量文件和核心计算均未更改。其他未列为修改的原有脚本与历史报告也保持原状。

## 6. 实际浏览器验收

使用本机运行的 Flask 和内置浏览器检查，不仅验证 HTTP 200。

| 检查 | 实际结果 |
|---|---|
| 五个页面 | 全部正常加载；标题、当前空间和当前业务步骤正确 |
| 商品切换 | `HOUSEHOLD_1_535 / CA_1` 显示历史销量 2,523、14 天预测 114、选定方法 MAE 2.82；与默认 FOODS 商品结果不同 |
| 完整业务流程 | 从 Overview 依次点击下一步到 Forecast、Inventory、Decision Lab，再返回 Overview，商品和门店保持一致 |
| 预测页 | Moving Average MAE 3.52、Same-Weekday Average MAE 2.82；历史回测与未来预测仍分开 |
| 库存计算 | 将选定商品当前库存改为 0 后重新计算，显示 Stockout Risk |
| 财务决策页 | 页面按原行为恢复默认库存 200；Run Simulation 正常展示三策略及推荐 Wait，未继承上一页的 0 库存假设 |
| 工作空间切换 | 业务页切换至 `/market` 不携带商品参数；从市场返回业务首页加载默认商品 |
| 市场导航 | State Comparison 点击后定位 `#states` 并高亮；直接访问 `#ratio` 定位比率区块并高亮 Retail Financial Indicators |
| ABS 图表与结构 | 七个区块、12 个 SVG 图表正常加载，筛选交互仍可用 |
| 消费日期筛选 | 结束月份选 2025-08，消费金额更新为 77,068.6 AUD million，环比 0.20%、同比 4.67% |
| 类别与行业筛选 | 切换环比后显示 Transport 增长 2.29%；选择 Household goods 后对应零售趋势更新，Experimental 标签保留 |
| 州/类别筛选 | Victoria + Food 在 2026-08 的同比显示 5.11% |
| 财务口径筛选 | 切换 Seasonally Adjusted，2026-Q2 的销售、库存、经营利润、工资分别显示 150,785 / 49,033 / 8,106 / 15,541 AUD million |
| 官方库存销售比率 | 最新 0.32，较前季差值 -0.02；没有转换为天数或添加风险阈值 |
| 企业动态筛选 | 2024-25 显示企业 156,018、进入 24,192、退出 24,809、净变化 -617；切换 entrants cohort，显示对应固定 cohort 基数 23,766 |
| 浏览器与服务日志 | 检查期间未发现浏览器 warning/error；本次 Flask 日志未发现 Traceback 或 HTTP 500 |

布局检查覆盖 1280px 桌面视口、588px 窄视口，以及 390px iframe 内的手机宽度渲染。工作空间切换、长市场栏目名称、业务步骤和标题未见重叠或遮挡；桌面及 588px 主文档未出现横向溢出。390px 检查是窄宽度视觉检查，**没有冒充真实手机、触屏或 Safari 的专项兼容性测试**。

当前演示只有 CA_1 一个门店。因此验证的是该真实门店 ID 在链接和请求中正确保留，不能声称已完成多个实际门店之间的浏览器切换验证。

测试日志、哈希审计和截图保存在项目旁的 `../../research/datasets/`：

- `restructure_a_before.json`：修改前哈希基线。
- `restructure_a_baseline_tests.log`：133 项基线测试。
- `restructure_a_tests.log`：141 项最终测试。
- `restructure_a_preservation.json`：文件完整性核对。
- `restructure_a_browser_validation.json`：浏览器验收记录。
- `restructure_a_browser_checks/`：桌面/390px 截图和本地响应式检查页，不属于网站功能。

## 7. 打开与继续开发

默认业务入口：**http://127.0.0.1:5050/**  
市场工作空间：**http://127.0.0.1:5050/market**

独立启动方法不变：在现有 MarginGuard 文件夹的终端运行 `./start.command`，保留终端窗口；按 Ctrl+C 停止。不需要 Codex 一直运行。当前本机 5050 服务器已启动，布局检查使用的临时 5052 服务已关闭，没有公开部署。

## 8. 尚未实现的功能

- 方案 B：sessionStorage 假设草稿、库存参数带入决策页、建议采购量带入及对应审核流程。
- 返回 Overview 时根据其他页面编辑过的假设重新计算风险。
- 跨工作空间保存当前商品选择或市场筛选状态。
- 真实企业账户、用户 CSV 上传、多商品组合分析、企业与 ABS 的可比性分析、业务报告导出。
- 实际采购、供应商联络、付款或公开生产部署。

这些功能未加入本次交付。**方案 A 完成后暂停，等待用户确认方案 B。**
