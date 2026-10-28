# MarginGuard — Retail Risk & Financial Decision Intelligence

MarginGuard 面向中小型零售企业、品牌经营者、采购经理和运营分析人员，提供需求预测、库存风险与财务情景决策支持。Python 完成预测和统计计算；Flask 提供页面与 API；HTML、CSS、Vanilla JavaScript 和本地 SVG 负责交互与展示。生产运行不需要 Node.js、外部图表 CDN 或大语言模型 API。

当前提供两个工作空间：

- **My Business**：本地 `Explore Demo` 保留 Walmart M5；公开网站使用独立的 **Synthetic Business Demo**。本地 `Analyse My Business` 通过临时匿名会话分析用户 CSV，公开上传保持关闭。流程为 **Upload → Validate → Select Product & Store → Forecast → Inventory → Financial Scenario → Decision Summary**。
- **Market Intelligence**：独立展示 ABS 官方行业统计，不用于修改商品预测或财务参数。

企业上传、AUD/USD 财务上下文和 Restructure B 跨页面输入草稿均已实现。没有连接企业账户，也不执行实际采购下单。网站已部署到 [MarginGuard Online](https://marginguard-lkno.onrender.com)，无需安装 Python，也不依赖 Mac 或 Codex 开机。版本、功能开关及真实公网验收见 [PUBLIC_DEPLOYMENT_REPORT.md](PUBLIC_DEPLOYMENT_REPORT.md)。此前本地验收见 [FINAL_QA_REPORT.md](FINAL_QA_REPORT.md)；旧阶段报告是当时的历史记录。 本轮上线后体验优化和上传开放评估见 [POST_DEPLOYMENT_UAT_REPORT.md](POST_DEPLOYMENT_UAT_REPORT.md)，公开 CSV 在生产安全验收通过前保持关闭。

## 1. 在 Mac 上独立启动

在 VS Code 打开当前 `MarginGuard` 文件夹，或用 macOS Terminal 进入该目录：

```sh
./start.command
```

启动器切换到自己的目录，必要时创建 `.venv`，在 Flask 不可用时安装 `requirements.txt`，然后监听 **http://127.0.0.1:5050**。如果解压工具没有保留执行权限，使用 `sh start.command`。运行不依赖 Codex；保留启动服务器的终端窗口，按 Ctrl+C 停止服务。退出 Codex 不会停止由独立终端启动的服务，注销或重启 Mac 后需重新启动。

也可手动执行：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

已有本地环境支持 Python 3.9+；新环境建议使用项目固定的 **Python 3.12.14**，生产依赖与版本见第 9 节。启动前可以运行 `python3 --version` 检查实际解释器。不要把其他电脑的 `.venv` 复制过来，也不要直接通过 `file://` 打开 HTML 模板。

若出现连接错误，检查终端是否显示 `Running on http://127.0.0.1:5050`，重新启动后点击 **Retry connection** 或刷新。浏览器可能保留旧页面，而 Python 服务已经停止。端口冲突可用 `lsof -nP -iTCP:5050 -sTCP:LISTEN` 检查；先确认进程身份，再决定是否停止。更新代码或 ABS 快照后，应在原终端停止旧服务并重新启动。

## 2. 解压最终交付包后先体验完整流程

最终包 `MarginGuard_COMP9001_Final.zip` 包含源码、测试、文档、配置、ABS 轻量快照和明确标注的合成 CSV。它**不包含 M5 原始记录、处理后销量、回测实际值、预测 JSON 或旧 M5 数值报告**，也不是企业上传数据的备份。本地原项目中的 M5 文件仍保留。

无需先恢复 M5，即可体验完整业务流程：

1. 启动网站，打开 **http://127.0.0.1:5050/?mode=business**。
2. 选择 `examples/business_csv/synthetic_84_days.csv`，明确选择 AUD 或 USD、经营时区及统一税额口径，并确认有权分析该数据、销量是与退货分开的销售数量。
3. 点击 **Validate CSV**，查看记录预览、缺失情况和连续区间；确认所选 84 天历史。
4. 切换商品/门店，查看 Overview 和 Forecast。此时库存显示 **Not assessed**，上传模式不套用 M5 库存、成本或预算默认值。
5. 在 Inventory & Risk 输入假设，并确认库存日期与预测原点一致，或明确选择在该原点使用假设库存。
6. 在 Financial Decision Lab 填写财务假设，比较 Wait、Reorder、Discount；查看可行性、推荐理由与 Purchasing Decision Summary。

合成样本是接口与教学演示数据，不是 Walmart、ABS 或真实企业记录，其预测效果不能作为真实预测准确率证据。还可上传 `synthetic_multi_series.csv` 验证多商品、多门店切换和草稿隔离；其数值同样全部合成。完整字段规则与可复现的假设案例见 [examples/business_csv/README.md](examples/business_csv/README.md)。

## 3. 页面、数据来源与输入草稿

| 路由 | 页面 | 用途 |
|---|---|---|
| `/` | Business Overview | 已观察销量、14 天需求、回测 MAE、已评估或未评估的库存状态 |
| `/forecasting` | Demand Forecasting | 历史趋势、两方法 MAE、独立的历史回测与未来预测 |
| `/inventory` | Inventory & Risk | 库存覆盖、交货期需求、库存位置、建议额外采购量及规则说明 |
| `/scenarios` | Financial Decision Lab | 三策略财务结果、预算/MOQ/服务约束、采购决策摘要 |
| `/market` | Market Intelligence | 同页内五组导航与七个 ABS 分析区块 |

业务页面之间传递所选上下文。Demo URL 使用商品/门店 ID；上传 URL 仅携带模式与不透明的数据集/序列标识，不含私有商品名称、金额或认证令牌。ABS 页面保持独立，不将 ABS 指标混入 My Business 的 KPI。

输入草稿使用当前标签页的 `sessionStorage`，按 **数据来源、数据集、版本、商品—门店序列、预测原点、币种** 隔离。库存与财务输入分别保存；CSV 明细、认证令牌、计算结果不写入 Web Storage。恢复完整输入后，重新请求 Python 计算；切换商品或数据源不会沿用另一个上下文的输入。浏览器禁用存储时仍可手动计算，但不承诺换页保留。

Inventory → Decision Lab 提供 **Use inventory assumptions** 和 **Use suggested quantity**，均先展示需要替换的字段并等待用户确认。建议量称为 **Proposed Order Quantity**，只是库存规则的结果，不是全局最优采购量。已有在途库存大于零时禁止自动转移；若要手动模拟，必须确认这是排除既有在途数量及成本的独立情景。

**Reset current assumptions** 清除当前上下文的库存与财务草稿；Demo 恢复已披露的演示假设，上传模式恢复空白。删除或过期会使服务器数据失效并清理相关上传草稿。输入变化时旧结果会隐藏，旧请求不能覆盖新上下文。草稿只是操作便利，不是认证，也不等于长期保存；同一浏览器的标签页可能共享服务器会话 cookie，不应视为独立用户账户。

## 4. 企业 CSV 与临时数据保护

必需列：`Date,Product,Store,Units Sold`；可选列：`Unit Price,Unit Cost`。使用 UTF-8 或 UTF-8 BOM，日期严格为 `YYYY-MM-DD`，每个商品—门店—日只能一行。

- 负销量、非整数销量、重复键、非法日期、非法金额或标识会拒绝；重复行不会自动相加。
- 显式 `0` 是零销量；缺失日期与空白销量是未知，不能自动补零。
- 当前只支持 gross sold units，退货需要分开处理。声明不会证明正数从未被扣除退货，用户必须确认数据含义。
- 每次预测必须选择至少 **42 个连续有效日**，推荐 **84 天或以上**。可明确选择完整子区间，不能跨越未知日；预测日期紧接所选历史，不会自动变成今天。
- 价格、成本空白保持未知；历史参考价只在用户明确选择后用于假设。现有库存成本与新采购成本分别填写，不自动同时套用一个历史成本。
- 同一数据集只使用 **AUD 或 USD**。所有金额输入须使用同一币种与税额口径；没有汇率换算或税务计算。ABS 指标仍为 AUD，不能与 USD 商品金额直接混算。

默认保护边界：

| 项目 | 默认限制 |
|---|---|
| CSV | 5 MiB、50,000 行、100 个商品—门店组合；每组历史跨度最多 1,096 天 |
| 待确认数据 | 15 分钟后过期 |
| 匿名会话 | 空闲 30 分钟或创建后 2 小时失效，以先到者为准 |
| 计算 | 单任务 5 秒超时；共享并发上限 2；另有进程资源限制 |
| 请求频率 | 每会话 10 分钟最多 3 次上传；每分钟最多 30 次计算类请求 |
| 私有存储 | 仓库外 SQLite；单数据集默认 20 MiB，总容量默认 500 MiB |

上传在服务器端按会话校验所有权；POST/DELETE 校验 CSRF 与来源。用户文件不作为代码执行，不接受本地文件路径输入，不提供原文件下载。私有响应使用 `no-store`；不将企业数据写入 GitHub、静态目录或最终 ZIP。权限和限额不等于经过独立生产安全审计。

过期在请求时即检查，后台周期清理处理过期存储；物理删除不承诺发生在到期的同一秒。重启、部署或临时磁盘丢失可能使数据提前不可用。删除数据、确认替换数据集或会话过期后不能恢复；不要把此系统用作唯一备份。不要上传客户、支付或其他个人信息。

主要后端入口包括 `GET /api/business/session`、`POST /api/business/uploads`、确认接口、私有 catalog/analysis/inventory/scenarios 接口及 DELETE 接口。API 合约、安全测试和限制见 [PHASE5B_REPORT.md](PHASE5B_REPORT.md)；页面与参数保留见 [PHASE5C_REPORT.md](PHASE5C_REPORT.md) 和 [RESTRUCTURE_B_REPORT.md](RESTRUCTURE_B_REPORT.md)。

## 5. 预测、库存与财务规则

`forecast.py` 的原公式保持不变。最后 14 个观察日用于时间顺序回测；7-day Moving Average 使用训练尾部 7 日均值，Same-Weekday Average 使用训练尾部 28 日中的四个同星期日均值。两方法使用相同 holdout 比较 MAE，完全相同时优先 moving average。选定方法使用全部确认历史重新拟合，生成独立的未来 14 个日历日预测，回测实际值不进入对应训练窗口。

`business_csv.py` 负责校验，`business_forecast.py` 适配现有预测接口。后者的 `financial_analysis_available=False` 仅说明该**预测适配结果本身**不包含财务分析；完整网页通过独立的 `finance.py` / `scenario.py` 计算财务结果，不能据此理解为当前网站不支持财务分析。

| 模块 | 主要规则 |
|---|---|
| `inventory.inventory_risk` | 平均需求；覆盖天数=库存/平均需求；库存位置=库存+在途；目标=交货期需求+安全库存；建议额外量=max(0, ceil(目标−库存位置)) |
| `finance.procurement` | 新采购现金=单位采购成本×采购量+运费+其他费用；单位到手成本=该金额/采购量 |
| `finance.gross_profit` | 收入=售价×销量；分别计算现有与新增商品 COGS；毛利=收入−COGS；毛利率=毛利/收入×100 |
| `finance.lost_sales` | 潜在流失收入=未满足数量×售价；潜在流失毛利=未满足数量×单位贡献 |
| `scenario.simulate` | 按日扣减库存，现有库存先售出；仅到货后的新库存可销售 |
| `scenario.compare_strategies` | 在 MOQ、预算和可选缺货上限约束下，选择三种被测试策略中未舍入毛利润最高者 |

零需求的覆盖天数为 `None`；超过 14 天的交货期以 14 天平均需求外推，并明确标识。库存状态按缺货、补货关注、过剩关注、充足的优先级判断；过剩阈值由用户指定，默认演示值为 30 天。在途数量可以减少补货缺口，但没有到货日期时不假定它能满足近期销售。

交货期 7 天表示第 8 天开始到货；0 表示第 1 天；≥14 天表示预测期内未到货。未满足需求视为流失，不形成积压订单。新采购现金支出不会立即全部计入当期 COGS，新运费不改变旧库存成本。零采购时非零运费/其他费用无效；零收入的毛利率为 `None`。销量预测保持小数期望值。

Discount 售价=售价×(1−折扣/100)，需求=预测×(1+假设增长/100)。销量增长只是用户假设，不是已验证的价格弹性。推荐完全相同时按 Wait → Reorder → Discount；没有可行策略则不推荐。预算仅约束新增采购现金；未设置服务约束时，缺货会披露但不自动使策略不可行。没有税务、持有成本、经营费用或需求不确定区间，因此不保证实际利润或全局最优结果。

AUD/USD 通过统一货币上下文传入财务函数与 API 返回，前端按币种显示；数值公式与舍入规则保持一致，未把 USD 标签直接替换成 AUD 来伪装换汇。设计背景见 [AUD_USD_CURRENCY_DESIGN.md](AUD_USD_CURRENCY_DESIGN.md)。

## 6. 本地恢复 Walmart M5 Demo

原开发目录已保留本地 M5，不必重复下载或重建。以下步骤用于**解压交付包后尚无 M5 生成文件的目录**；已有结果时先核对和备份，不要直接覆盖。合法取得三份 CSV，复制到 `data/raw/`，保留下载原件：

- `sales_train_validation.csv`
- `calendar.csv`
- `sell_prices.csv`

激活虚拟环境后，从项目根目录运行：

```sh
python scripts/audit_m5.py
python scripts/prepare_m5.py --raw-dir data/raw --items FOODS_3_586 FOODS_3_252 HOUSEHOLD_1_535 HOUSEHOLD_1_334 HOBBIES_1_147 --stores CA_1 --days 365
python run_phase1.py
python run_phase2.py
```

然后重启网站，在 **Explore Demo** 查看恢复的数据。固定五组配置用于已有真实数据回归；其他商品需要自行选择并验证，不能据此声称原回归覆盖新配置。

生成文件包括 `source_audit.json`、`processed_sales.csv`、`processed_sales.validation.json`、含回测的 `forecast_results.json`、单独未来预测 `forecast_results_future.json` 及 Phase 2 模拟结果，均留在本地。M5 预处理拒绝缺日、负销量、重复键、全零序列，并保留明确零销量；上传流程对未知数据和全零测试历史有独立报告规则，不能混同两种校验路径。

Phase 1/2 CLI 使用 Python 标准库，仍可独立运行。修改情景假设时复制默认文件到另一个本地文件，再运行：

```sh
python run_phase2.py --parameters /path/to/my_assumptions.json --output /path/to/my_result.json
```

M5 来源见 [data/DATA_SOURCE.md](data/DATA_SOURCE.md)。公开展示及再分发许可目前未确认；本机有合法文件不自动意味着允许公开上传。最终打包排除原始数据、派生记录和预测，并不删除原项目文件。

## 7. ABS Market Intelligence 与离线复现

访问 **http://127.0.0.1:5050/market**。页面使用 `data/abs/` 已处理快照，运行时不解析 Excel；更新快照后需重启 Flask。

使用的发布快照为：MHSI 2026 年 8 月、Business Indicators 2026 年第 2 季度、Business Counts 截至 2026 年 6 月。它们是已固定的历史快照，**不是自动更新的实时数据**。每项指标保留各自参考期、频率、单位、分类、调整方式、发布日期及来源。详细表格与 Series ID 见 `data/abs/sources.json`、`market_catalog.json` 及 [PHASE4A_REPORT.md](PHASE4A_REPORT.md)。

- 月环比/季环比和同比由 Python 计算，公式为 `(本期/对应前期−1)×100`；缺失或非正比较基期返回 `null`，不补零。
- Original、Seasonally Adjusted、Trend 分开；Monthly、Quarterly、Financial Year 不混用。
- MHSI Table 19 始终标记 **Experimental**，不拼接旧 Retail Trade；COICOP 与 ANZSIC 分开。
- ABS Business Gross Operating Profits 不是商品毛利润。官方库存销售比率是季末存量与季度流量之比，不是库存天数或企业风险评分。
- 企业数量不等于门店数量，退出不等于破产；两个存续 cohort 分开解释。
- ABS 金额为 AUD。My Business 为所选 AUD/USD；没有跨源货币换算或直接市场对标。

只读 API：`/api/market/catalog`、`overview`、`series`、`compare`、`business-counts`、`sources`。参数对应目录中已存在的序列和口径，不接受任意本地路径。来源、筛选与 API 细节见 [PHASE4B_REPORT.md](PHASE4B_REPORT.md)。

离线重新读取已下载 Excel 需要额外依赖：

```sh
python -m pip install -r requirements-abs.txt
python scripts/prepare_abs.py --dataset all --research-dir ../../research/datasets --as-of 2026-10-28 --overwrite
```

此命令仅用于有原始研究文件并明确需要重建的环境。原工作簿不随最终 ZIP 附送；路径可指定到合法下载文件的父目录。生成器校验 `sources.json` 中的 SHA-256，不自动重新下载。`--overwrite` 明确替换选中的 ABS 输出；要保留旧输出请改用新的 `--output-dir`。可用 `--dataset market` 或 `counts` 独立处理。`--as-of` 是资料可用截止日期，不会还原另一个发布版本。

ABS 来源为 Australian Bureau of Statistics，保留官方 [版权及署名条款](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer)；一般 CC BY 4.0 授权受其排除条款约束。项目不使用 ABS 标志或暗示 ABS 背书。

## 8. 测试与最终打包

完整 Python 测试需要 Flask 及 ABS 测试依赖：

```sh
python -m pip install -r requirements-abs.txt
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
python -m pip check
```

原有 193 项测试保持保留，新增上传、隔离、安全、币种、参数保留和打包测试。**最新执行数量、通过/跳过情况及具体环境统一见 [FINAL_QA_REPORT.md](FINAL_QA_REPORT.md)**，避免把历史阶段的 61/109/141 等数量误当作当前总数。

前端输入草稿有独立的 Node 测试；Node 仅用于开发测试，不是网页运行依赖。若本机已安装支持 `node:test` 的 Node，可执行：

```sh
node --test tests/business_context.test.js
```

没有 M5 本地数据或原始 ABS 研究 Excel 时，对应集成测试会明确跳过；这不等于完成该数据的真实文件验证。合成测试只验证软件行为。五页实际浏览器交互及移动布局结果也单独记录在最终 QA，不以 HTTP 200 代替界面验收。

生成新的最终交付包：

```sh
python scripts/package_final.py
```

默认写入项目同级的 `MarginGuard_COMP9001_Final.zip`（在当前工作结构中即 `outputs/`）。已有同名 ZIP 时拒绝覆盖；可用 `--output /path/to/a/new-name.zip` 选择新文件。打包采用明确文件白名单，写入逐文件 SHA-256 的 `MANIFEST.json` 与 `PACKAGE_SCOPE.md`，保留所需目录结构。

排除：全部 M5 记录及预测、真实企业上传、临时数据库、密钥、日志、缓存、虚拟环境、研究大文件、旧 ZIP 和未审核文件。只允许明确合成或 ABS 截图。历史 Phase 1/3 打包脚本与归档仅保留原目录历史用途，不应用于当前最终交付。

## 9. 生产运行与公开部署

生产配置包括 `.python-version`（**3.12.14**）、`requirements-production.txt`、`wsgi.py`、`gunicorn.conf.py`、`runtime_config.py`、`render.yaml`。GitHub 使用私有仓库 `cici-rwei/MarginGuard`，仓库根目录对应当前项目目录，Render Root Directory 留空。构建使用 `pip install -r requirements-production.txt`，启动使用 `gunicorn -c gunicorn.conf.py wsgi:app`，健康检查 `/api/features`。当前上线状态以 [PUBLIC_DEPLOYMENT_REPORT.md](PUBLIC_DEPLOYMENT_REPORT.md) 为准；历史准备证据见 [DEPLOYMENT_REPORT.md](DEPLOYMENT_REPORT.md) 与 [DEPLOYMENT_EVIDENCE.md](DEPLOYMENT_EVIDENCE.md)。

用已安装的 Python 3.12.14 创建独立生产验证环境，再安装：

```sh
python3.12 -m venv .venv-production
.venv-production/bin/python -m pip install -r requirements-production.txt
.venv-production/bin/python -m pip check
.venv-production/bin/gunicorn -c gunicorn.conf.py wsgi:app
```

Gunicorn 默认监听 `0.0.0.0:8000`，由 `PORT` 调整；此命令是 WSGI 启动示例，不等于公开安全部署。不要把 Flask 开发服务器直接暴露到互联网。生产应固定 Python 版本，使用平台 TLS、正确的主机校验与受信任代理拓扑。

| 环境变量 | 作用 |
|---|---|
| `MARGINGUARD_PUBLIC=true` | 开启公开环境约束，关闭 Debug，使用 Secure cookie |
| `MARGINGUARD_SECRET_KEY` | 至少 32 字符的随机密钥，由部署平台注入，不写入仓库或报告 |
| `ENABLE_BUSINESS_UPLOAD` | 公开配置默认 `false`；生产安全验收后才显式启用 |
| `ENABLE_SYNTHETIC_DEMO` | 独立开关；Render 已部署配置为 `true`，本地默认 `false` |
| `ENABLE_M5_DEMO` | 公开配置默认 `false` |
| `M5_PUBLIC_LICENSE_CONFIRMED` | 只有已核实实际展示/再分发权利才能设为 `true`；开关本身不授予许可 |
| `MARGINGUARD_PRIVATE_DIR` | 仓库外的私有临时目录，不属于静态目录或公开挂载 |
| `TRUST_REVERSE_PROXY` | 仅在已确认可信 TLS 终止代理时启用 |

默认 Render 配置开放合成经营演示与 ABS，关闭企业上传及 M5 数据接口。上传安全与 M5 许可是两个独立闸门。生产访问日志只记录状态与耗时，不记录 URL 查询、cookie、请求正文或企业销售明细。合成演示不创建上传会话或 SQLite，也不保存访问者的计算结果；输入草稿仅按来源隔离保存在当前标签页。公开部署使用免费单实例方案；服务可能休眠和冷启动，不承诺企业生产 SLA。

合成演示固定读取 `examples/business_csv/synthetic_84_days.csv`，历史为 2024-01-01–2024-03-24，模拟预测区间为 2024-03-25–2024-04-07。此数据是人工构造的教学样本，不是真实企业交易，固定周模式产生的 MAE 不能证明真实泛化能力。币种上下文明确定义为 AUD，并作为参数传入现有财务引擎；不进行换汇。库存、售价、成本、采购及折扣增量均为可修改的演示假设，结果由现有 Python 引擎计算。

本地查看该公开演示入口：

```sh
ENABLE_SYNTHETIC_DEMO=true ENABLE_M5_DEMO=false ENABLE_BUSINESS_UPLOAD=false python app.py
```

打开 `http://127.0.0.1:5050/?mode=synthetic`。这是本地功能检查；公开环境仍须设置 `MARGINGUARD_PUBLIC=true`、由平台生成密钥并通过 HTTPS 验收。固定样本 API 为 `/api/demo/catalog`、`/api/demo/analysis`、`/api/demo/inventory`、`/api/demo/scenarios`，不接受客户端文件路径或自定义预测序列。

后续更新先运行全部测试，按 `deployment_files.json` 审核并暂存必要文件，检查 `git diff --cached` 后再提交和推送。不得执行未经审计的 `git add .`。GitHub Actions 提供不含受限 M5/原 Excel 的 CI；Render 已启用 **After CI Checks Pass**，第二次自动部署已验证。免费服务位于 Singapore；公网地址为 [MarginGuard Online](https://marginguard-lkno.onrender.com)。仅根目录 Markdown 与 `deployment_files.json` 变更受构建过滤规则排除，不重启应用；代码、依赖、数据和配置仍经 CI 后部署。回滚可恢复已验证的历史部署，或提交 `git revert` 经测试后推送；不要用强制推送覆盖历史。

清理脚本可在与服务相同的系统用户和私有目录下执行：

```sh
python scripts/cleanup_business_data.py --storage-root /absolute/private/directory
```

正式课程 rubric、认可的 Advanced Topics 和 AI 披露要求仍需对照官方文件确认。提交材料见 [COMP9001_COMPLIANCE.md](COMP9001_COMPLIANCE.md)、[AI_USE_DECLARATION.md](AI_USE_DECLARATION.md)、[PADLET_DRAFT.md](PADLET_DRAFT.md) 和 [DEMO_SCRIPT_3MIN.md](DEMO_SCRIPT_3MIN.md)；未确认项不能写成已获课程批准。
