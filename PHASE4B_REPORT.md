# MarginGuard Phase 4B：Australian Retail Market Insights

完成日期：2026-10-28（Australia/Sydney）

## 1. 交付结果

已在现有 `outputs/MarginGuard` 项目完成 **Australian Retail Market Insights**，导航新增 **Market Insights**。本地地址为 **http://127.0.0.1:5050/market**，Flask 已成功重启并运行。

页面包含七个主要功能区，使用 Phase 4A 已处理的 ABS 轻量数据。全部 **133 项自动化测试通过**，其中原有 109 项全部保留，新增 24 项网页/API 测试；无失败、无跳过。另已执行实际浏览器筛选、图表、错误恢复及原有四页回归检查。

本阶段未公开部署，未接入其他商品数据源，也未修改 M5 原始数据、Phase 4A 数据文件或原有预测、库存、财务、情景计算算法。

## 2. 新增和修改的文件

| 文件 | 状态 | 职责 |
|---|---|---|
| `market_service.py` | 新增 | 固定快照读取与缓存所用服务；序列筛选、比较排序、季度差值及规则化 Business Insights |
| `market_api.py` | 新增 | 六个只读 Flask API、严格参数验证、首次加载锁及错误响应 |
| `templates/market.html` | 新增 | 英文市场分析页面，七个功能区及统计说明 |
| `static/js/market.js` | 新增 | 筛选、请求、结果显示、分区重试、本地 SVG 图表 |
| `static/css/market.css` | 新增 | Market 专属顶部导航、卡片、图表和响应式样式 |
| `tests/test_market_web.py` | 新增 | 24 项网页和 API 集成测试 |
| `PHASE4B_REPORT.md` | 新增 | 本中文交付报告 |
| `app.py` | 修改 | 注册市场 Blueprint，增加 `/market` 页面路由 |
| `templates/base.html` | 修改 | 增加 Market Insights 导航；为 Market 加载独立资源与 ABS 来源说明 |
| `README.md` | 修改 | 新页面打开方式、API、缓存及运行说明 |

原有四个页面的内容模板、`static/js/main.js`、`static/css/style.css`、启动脚本及依赖文件保持不变。共检查阶段开始前的 **64 个文件**，其中 **61 个哈希完全相同**，其余仅为表中列出的 3 个既有文件，没有缺失文件。

验收记录在项目外 `research/datasets/`：`phase4b_before.json`、`phase4b_preservation.json`、`phase4b_baseline_tests.log`、`phase4b_tests.log`、`phase4b_browser_validation.json`。截图和临时响应式验收 HTML 位于 `phase4b_browser_checks/`，不属于部署所需文件。临时 QA 服务器已经停止，主网站继续在 5050 端口运行。

## 3. 页面功能与统计口径

| 功能区 | 已实现功能 | 数据和解释边界 |
|---|---|---|
| Market Overview | 家庭消费、实验性零售营业额、零售库存、库存销售比率四项 KPI；每项显示参考期、单位、调整口径、来源及发布日期 | 月度和季度各自标记，不包装成同一期快照 |
| Consumer Spending Trends | Table 1 趋势、月环比、年同比、Goods/Services 比较；170 个月范围、5 个消费总项和 Original/SA/Trend 切换 | Household Spending 不等于 Business Sales；缺失折线断开 |
| Industry Performance | Table 2 的 9 个 COICOP 类别比较；Table 19 的 6 个细分零售行业比较及总行业趋势；月份、焦点类别/行业、环比/同比、口径筛选 | 两种分类分卡展示；Table 19 始终标记 Experimental，总行业不与细分行业一起排名 |
| State Comparison | NSW/VIC/QLD/SA/WA/TAS/NT/ACT 同比增长比较与 Python 排序；月份、类别、口径和焦点州筛选；焦点州同比历史 | 采用百分比增长排序，不将消费金额规模解释为增长表现 |
| Retail Financial Performance | 同季度销售、季末库存、经营利润、工资四项快照；季度/指标/Original/SA 切换，默认展示截至所选季度的最近 20 季趋势 | AUD million、Current Prices、ANZSIC Retail trade；Business Gross Operating Profits 不是商品毛利润 |
| Inventory-to-Sales Ratio | 官方最新比率、上一季度差值、完整 110 季历史和定义 | 季末库存存量除以当季销售流量；不是周转天数、缺货概率或企业风险评分；没有人为风险阈值 |
| Business Dynamics | 四个财年的企业数、进入、退出、净变化；两组固定 cohort 存续图和对照表 | 企业不等于门店，退出不等于破产；财年筛选不会改变 cohort 的固定分母 |

界面为英文，沿用深蓝、浅灰和白色卡片。Market 页面使用深蓝顶部导航；原有页面的桌面布局保持原有方式。图表全部采用本地 SVG，无 CDN、React 或 Node.js 运行依赖。每个区块独立显示加载状态和清晰错误；筛选开始后隐藏旧结果，并取消该区块的旧请求，避免较慢响应覆盖新选择。

## 4. 后端与 API

仅读取固定目录下的 `data/abs/market_data.json.gz` 和 `business_counts.json`。第一次市场请求在锁保护下加载，之后在同一 Flask 应用实例内复用快照。网页访问不解析 Excel；Flask 运行不需要 Pandas/openpyxl。更换处理文件后重启服务器即可载入新快照。

| 只读 API | 输入与输出 |
|---|---|
| `/api/market/catalog` | 无参数；返回序列元数据、日期范围、单位、口径和财年列表 |
| `/api/market/overview` | 无参数；返回四项 KPI 及每项来源、参考期、口径 |
| `/api/market/series` | 必填 `dataset_id`、`series_id`；可选 `start`、`end`；返回观察值、已有 Python 增长率、所选末期值、来源和解释 |
| `/api/market/compare` | 必填数据集、表格、指标、调整口径、月份、增长方式及分组；按类别或州比较并由 Python 排序 |
| `/api/market/business-counts` | 可选 `financial_year`；返回所选财年流量与独立固定 cohort |
| `/api/market/sources` | 无参数；官方 URL、参考期、发布/下载日期、许可及方法说明 |

接口拒绝未知、重复、空白、过长参数及错误的数据集/Series ID、分类组合、日期格式或范围。未发布到当前快照中的未来月份不接受。参数无法指定任意文件路径；不提供写入接口。无效请求返回 JSON 400，固定处理文件缺失或损坏返回清晰 JSON 503，不向用户暴露本地路径或异常堆栈。

月度 `start/end` 格式为 YYYY-MM，季度格式为 YYYY-Qn。单一日期窗口只改变展示范围；同比仍取 Phase 4A 完整历史计算结果，不会因屏幕只显示一个月份而丢失同比基期。

示例：

```text
/api/market/series?dataset_id=abs_mhsi&series_id=A130200584T&start=2025-01&end=2026-08
```

## 5. Business Insights 如何生成

增长率沿用 Phase 4A Python 结果；后端根据数值符号描述上升、下降或不变，根据可用增长率计算显示范围内的最高值，并说明缺失比较项被排除。官方比率的季度差值在 Python 计算。企业动态说明读取企业净变化和两组官方存续率。

例如本次快照显示：

- 2026-08 季调家庭消费环比 **0.03%**、同比 **6.84%**，明确为从公布水平值计算的名义变化。
- 2026-08 季调 COICOP 比较中，Transport 同比 **10.36%**，为当前显示的 9 类中最高。
- 2026-Q2 零售官方库存销售比率 **0.32**，较上一季度减少 **0.02 个比率单位**，不解释为百分比下降或风险等级。
- 2025-26 财年零售企业净增加 **125** 家；企业存续另保留两组固定 cohort。

没有调用大语言模型 API，没有从历史变化推断原因、商品级风险或未来表现。当前值缺失、增长基期不足或没有可比较数据时，明确显示无法判断，不补零、不自动退回较早月份冒充最新值。

## 6. 自动化测试

开发前运行原有 **109 项：全部通过**。功能完成后运行：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```

结果：**Ran 133 tests in 2.979s — OK**，原有 109 项 + 新增 24 项，跳过 0。环境仍为 Python 3.9.6、Flask 3.1.2；完整离线 ABS 测试继续使用已安装的 Phase 4A 依赖。

新增测试覆盖：

- 五个页面、Market 静态资源及专属导航/来源展示。
- KPI、序列与 Phase 4A 保存数值精确一致。
- 月份、州、行业筛选；环比/同比及 Original/Seasonally Adjusted 隔离。
- 所选末期为空时保持 null，官方比率说明和 Experimental 标记。
- 企业财年流量与固定 cohort；发布日期、参考期、许可和来源。
- 非法、重复、未知、未来日期、路径形参数和只读 HTTP 方法。
- 数据缺失/损坏的 503；重复请求不重新读取文件；网页运行不依赖 Excel/Pandas。

另以 12 个 worker 执行了 36 个混合月份请求，快照仅加载一次，各月份结果独立且正确。JavaScript 已使用已有工具运行语法检查，未安装 Node.js 或添加其为项目依赖。

## 7. 实际浏览器验收

验收使用 Codex 内置浏览器访问真实运行的 Flask 服务，实际选择控件、点击计算并检查 DOM、SVG 和 Console；不只是检查 HTTP 200。

| 操作 | 观察结果 |
|---|---|
| 打开 Market Insights | 四项 KPI 分别为 82,340.5、40,037.6、47,803、0.32；参考期与口径正确；12 个核心 SVG 图表加载完成 |
| 消费结束月份改为 2025-08 | 季调家庭消费变为 77,068.6；环比 0.20%、同比 4.67% |
| 同月份切换 Original | 数值变为 77,355.8；环比 0.61%、同比 3.35%；口径标签同步变化 |
| Trend，2019-01 至 2023-01 | SVG 保留 30 个 null，形成 2 段折线；2023-01 同比显示 Unavailable |
| 食品消费焦点州 VIC → NSW | 2026-08 季调同比从 5.11% 变为 5.67%，图标题同步变化 |
| 零售焦点改为 Household goods retailing，并切换环比 | 行业趋势更新，Experimental 标签保留；排名说明改为 month-on-month |
| 财务 Original → Seasonally Adjusted | 2026-Q2 销售变为 150,785，库存 49,033，经营利润 8,106，工资 15,541（AUD million） |
| 季度改为 2025-Q2、选择经营利润 | 同季度四项值和经营利润历史同步更新；季调经营利润为 8,071 |
| 企业财年改为 2024-25，选择 entrants cohort | 企业数 156,018、进入 24,192、退出 24,809、净变化 −617；cohort 分母保持 23,766 |
| 日期起点晚于终点 | 显示明确日期错误和 Retry，旧结果隐藏；修正后恢复正常 |
| 消费类别月份改为 2012-07 | 9 类同比不可用，显示无法排名，没有虚构最高类别 |
| Overview 切换真实 M5 商品 | FOODS_3_252 → HOUSEHOLD_1_535 后，14 天预测从 525.5 变为 114 |
| Sales Forecasting | 三张图加载；历史回测为 2016-04-11 至 2016-04-24，未来预测为 2016-04-25 至 2016-05-08，区间分开 |
| Inventory Risk 修改库存并计算 | HOUSEHOLD_1_535 库存 0 时 Stockout Risk，改为 200 后 Sufficient Inventory |
| Scenario Lab 运行默认模拟 | Wait/Reorder/Discount 正常比较并推荐 Wait，预算、采购现金及毛利字段保留原有逻辑 |

浏览器 Console 未发现 error/warn，本次主 Flask 日志中未发现 4xx/5xx 响应；非法 API 的预期 400/503 已由 test client 验证。

响应式验证包括实际 **1280px 桌面**和 **588px 窄屏**：页面宽度均等于视口，无整页横向溢出。另以真实浏览器内 **390px iframe 视口**查看手机宽度下的导航、标题和 KPI 排列，未见这些区域重叠。这是浏览器布局检查，不等同于在真实 iPhone/Android 设备上完成全部触摸测试。表格允许自身横向滚动。

截图：`research/datasets/phase4b_browser_checks/desktop.png`、`phone.png`，以及 `phase4b_market_preview.png`。

## 8. 在 Mac 上打开

在现有项目目录运行：

```sh
./start.command
```

或使用已激活的虚拟环境运行 `python app.py`。访问 **http://127.0.0.1:5050/market**，也可从任一原有页面点击 **Market Insights**。本次服务器已在运行，不必同时再启动一个占用同端口的进程。

之后独立启动不需要 Codex 保持运行。终端窗口需保持打开，Ctrl+C 可停止服务；系统重启后需重新启动。若仍看到旧版页面，先确认原终端运行的是本项目，再停止旧进程并启动新版。

## 9. 限制和后续事项

- 当前为 Phase 4A 固定发布快照：MHSI 截至 2026-08，Business Indicators 截至 2026-Q2，Counts 截至 June 2026；没有自动获取未来发布数据。更换快照后需要重启服务。
- 当前使用名义现价指标，没有新增 Chain Volume Measures；不与旧 Retail Trade 拼接。
- 首次初始化需要市场与企业数量两个已处理数据文件；任一缺失时给出恢复提示，不伪造示例结果。
- 已完成本机浏览器交互和宽度检查，尚未在独立 Safari/Chrome 版本矩阵或真实移动设备上完成全面兼容性验收。
- 公开部署、生产服务器配置、域名、HTTPS、监控和部署打包均未开展，本阶段没有发布网站。
- 当前未发现阻塞本阶段功能的已知问题。用户 CSV 上传、自动数据更新和其他高级分析不属于本次交付。

Phase 4B 已完成，暂停等待用户确认下一阶段。
