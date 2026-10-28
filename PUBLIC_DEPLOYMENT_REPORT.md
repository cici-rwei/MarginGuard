# MarginGuard 公开部署报告

验收日期：2026-10-28（Australia/Sydney）。**公开部署已完成，真实 HTTPS 页面和 API 已通过验收。**

## 1. 线上地址与版本

| 项目 | 实际核验结果 |
|---|---|
| 公开网站 | [https://marginguard-lkno.onrender.com](https://marginguard-lkno.onrender.com) |
| 私有仓库 | [cici-rwei/MarginGuard](https://github.com/cici-rwei/MarginGuard)，GitHub API 确认为 PRIVATE，默认分支 main |
| Render 服务 | marginguard；`srv-dbgr9e7f3r2c73afsic0`；状态 Live |
| 方案与地区 | Free，$0/month、0.1 CPU、512 MB RAM；Singapore；均在实际控制台核实 |
| 当前应用提交 | `b626d078e65e261112eff292e7bef3221085dfc4` |
| 当前部署 | `dep-dbgreoivcj2c73docha0`；2026-10-28 19:50:42 AEDT；Auto-Deploy；45.4 秒成功 |
| 当前提交 CI | [GitHub Actions 40659621537](https://github.com/cici-rwei/MarginGuard/actions/runs/40659621537)，成功 |
| 首个成功部署提交 | `296ae9b11632cb8827dca9aaba81c305dd08598d`；[CI 40658160453](https://github.com/cici-rwei/MarginGuard/actions/runs/40658160453) 成功 |
| 自动更新 | After CI Checks Pass，已在 Render 实际设置和第二次自动部署中验证 |

最终报告与 README 属于文档更新；它们所在的 Git 提交可能晚于上述运行中的应用提交。不能把仓库最新文档提交误写成已部署的应用版本。

用户批准后，原私有空仓库 `-MarginGuard` 改名为 `MarginGuard`。初始化前 API 确认空仓库，没有覆盖已有历史；推送没有使用 force。用户亲自完成 GitHub CLI 浏览器授权及 Render GitHub App 授权，Render 仅选择此仓库。官方 CLI 2.103.3 经下载哈希校验，凭据存入 keyring；没有索取、输出或提交密码及令牌。没有将仓库改为 Public，没有选择付费资源。

## 2. 已部署架构与配置

| 项目 | 配置 |
|---|---|
| Runtime / Python | Render Python 3；`.python-version` 固定 3.12.14，构建成功；GitHub CI 亦使用 3.12.14 |
| 直接生产依赖 | Flask 3.1.2、Gunicorn 26.2.0；见 `requirements.txt`、`requirements-production.txt` |
| Root Directory | 留空；仓库根目录就是现有 MarginGuard 项目内容 |
| Build Command | `pip install -r requirements-production.txt` |
| Start Command | `gunicorn -c gunicorn.conf.py wsgi:app` |
| WSGI | `wsgi.py` 导出 `app.py` 的 app；不是 Flask 开发服务器 |
| Worker / timeout | 2 个同步 worker；20 秒；监听 `0.0.0.0:$PORT` |
| Health check | `/api/features` |
| HTTPS / Debug | Render 平台 HTTPS；HTTP 跳转 HTTPS；Debug 关闭 |
| 静态文件 | 本地 CSS、Vanilla JavaScript、SVG；核心图表不依赖 CDN |
| 数据路径 | 模块相对路径读取 `data/abs/` 和固定合成示例；不引用 Mac 绝对路径 |
| 持久存储 | 无持久盘、无外部数据库；公开演示不创建上传 SQLite |

生产网页不导入 Pandas/openpyxl，离线重建和完整测试使用 `requirements-abs.txt`。本机 Python 3.12 的生产安装实际间接依赖为 blinker 1.9.0、click 8.5.0、itsdangerous 2.2.0、Jinja2 3.1.6、MarkupSafe 3.0.4、Werkzeug 3.1.9；间接版本未逐个锁定，不把本机清单当作 Render 运行时逐包取证。

**环境变量名称（不记录秘密值）：** `MARGINGUARD_PUBLIC`、`TRUST_REVERSE_PROXY`、`MARGINGUARD_SECRET_KEY`、`ENABLE_SYNTHETIC_DEMO`、`ENABLE_M5_DEMO`、`ENABLE_BUSINESS_UPLOAD`、`M5_PUBLIC_LICENSE_CONFIRMED`、`PYTHONDONTWRITEBYTECODE`。Render 提供 `PORT`、`RENDER_EXTERNAL_HOSTNAME`。密钥由平台生成，保留在平台环境。

ABS 六份轻量文件共 2,603,774 字节；压缩主文件 1,557,978 字节，展开 JSON 文本约 9.47 MB。Mac 单进程实际访问页面/API 后峰值约 120.5 MiB；它不是 Linux 双 worker 的总实例压力测试。免费实例已完成启动和低频交互验收；高并发、长期内存及流量容量仍需观察，不能保证企业生产容量，更不能自动升级付费方案。

## 3. 公开功能与关闭项

**已开放：** 四页 My Business 的合成经营决策流程，以及独立的 ABS Market Intelligence。

- `/`：Business Overview。
- `/forecasting`：Demand Forecasting，历史回测与未来模拟分开。
- `/inventory`：Inventory & Risk，可修改库存假设并重新计算。
- `/scenarios`：Financial Decision Lab，Wait、Reorder、Discount 比较及可行性推荐。
- `/market`：Australian Retail Market Insights，保留来源、参考期、AUD、Experimental 和统计口径。

**Synthetic Demo** 使用已有 `examples/business_csv/synthetic_84_days.csv`，固定一个商品—门店组合，币种 AUD；历史为 2024-01-01–03-24，模拟未来 2024-03-25–04-07。它不是实时预测或真实企业交易。库存、价格、成本、采购、交货期及促销增量明确为可修改的演示假设。样本的重复周模式使 Same-Weekday MAE 为 0，不是现实预测能力证据。公开演示不提供币种切换；现有本地上传 AUD/USD 能力保留，无汇率换算。

独立 `synthetic_demo.py` 通过 `/api/demo/catalog`、`analysis`、`inventory`、`scenarios` 调用既有 CSV 校验、预测、库存及财务引擎，不使用写死结果，不接受任意文件路径或客户端预测序列。结果不在服务器持久保存；假设草稿仅在当前标签页按来源及上下文隔离。

**保持关闭：**

| 功能 | 原因及实际行为 |
|---|---|
| Walmart M5 Demo | 公开再分发及展示许可尚未确认；原始、处理后、派生数据均未上传；接口返回明确禁用状态 |
| 企业 CSV 上传 | 尚未完成匿名上传的生产安全验收；页面解释关闭原因，上传接口拒绝访问 |
| 真实账户、实际下单 | 本项目未连接真实企业账户，也不执行采购交易 |

ABS 是独立市场统计，不调整合成或 Walmart 商品预测，不与商品金额混算。没有重做 ABS 模块或修改核心公式。

## 4. 文件与数据审计

部署使用 `deployment_files.json` 的 **110 文件明确白名单**，不是无差别上传。109 项有内容 SHA-256；清单自身哈希为 null，避免递归自哈希，其内容由 Git 提交固定。最终文档修改后同步刷新大小和哈希。

排除：M5 原始及派生记录、旧 M5 数值报告/截图、企业 CSV、`.env`、密钥/Cookie、授权配置、虚拟环境、SQLite、缓存、日志、大型研究下载和 ZIP。实际 Git 跟踪路径与清单一致，敏感路径忽略探针 24 项通过；已知凭证/私钥/本机用户路径扫描无匹配。扫描不能保证识别所有未知秘密格式。

**28 份受保护核心和数据文件的部署前后 SHA-256 全部一致**，包括 forecast、inventory、finance、scenario、CSV 适配及 ABS 模块/数据。原 M5 文件未删除或覆盖。`scripts/package_phase1.py`、`scripts/package_phase3.py` 两个旧打包脚本保持未跟踪，不用于后续发布；它们的排除规则不足。后续只使用 `scripts/package_final.py` 的白名单并重新审计结果。

原 `MarginGuard_COMP9001_Final.zip` 未覆盖，SHA-256 仍为 `44aa17451bf51ec1b9204b40690256d415d376000e96cd26fce5a4e6e42b16e4`。这是此前版本的历史备份，不是本次云端发布包。本轮最新版通过 Git 提交交付。

## 5. 自动化测试

| 环境 | 结果 |
|---|---|
| 完整本地项目 | unittest **302/302 通过**，0 失败/错误/跳过；原 278 项保留，新增 24 项 |
| JavaScript 内置测试 | **14/14 通过** |
| 本机 Python 3.12 生产配置子集 | **47/47 通过** |
| 后续仅构建过滤配置变更 | **11/11** 生产配置回归通过 |
| 干净白名单快照 | 283 个方法实际通过、19 个缺少外部输入未执行；0 失败/错误 |
| GitHub Linux CI | 两次代码/配置提交均 success；无受限数据的检查明确跳过，部署不下载它们 |

完整本地 unittest 用时 19.622 秒；干净快照 13.899 秒。干净环境输出 `Ran 286, OK (skipped=5)`：3 个单方法跳过（2 个原 ABS Excel 检查、1 个真实 M5 衔接检查），2 个 M5 类在 setUpClass 跳过，涉及另外 16 个方法。共 19 个方法没有执行，不能称为通过。GitHub 首次 CI 为相同跳过结构、13.348 秒。Node 只用于测试，不是运行网站的依赖。

## 6. 真实公网验收

使用真实 Render HTTPS、正常证书校验完成 **35/35 API/页面/安全响应检查，0 应用失败**。其中验证五页、六个实际引用的静态文件、features、合成业务 API、ABS catalog/overview/series/counts/sources，以及错误输入和功能关闭状态。ABS 响应与本地 Phase 4A 快照一致，合成响应与既有 Python 引擎一致。HTTP 返回 HTTPS 跳转；HSTS、CSP、nosniff 等响应头有效；非法输入响应未暴露本机路径、密钥或 Debug traceback。

另执行真实浏览器交互，不能只以 HTTP 200 代表验收：

- 首页历史销量 504、未来 14 天 84，图表和页面导航携带合成来源及商品/门店 ID。
- 预测页 Moving Average MAE 2.57、Same-Weekday MAE 0；历史、回测、未来日期独立。
- 库存 30→0 后风险 Sufficient→Stockout，建议量 0→20。
- 三策略默认值如下；采购 60→80 后现金支出 462→612，超过 AUD 500 预算，Reorder 不可行、推荐改为 Wait。
- 折扣 10%→20% 后 Discount 收入 391.50→348，毛利率 37.16%→29.31%。
- Market 页面 12 个 SVG 正常加载；月份和 Original 筛选实际更新，2026-07 Original 家庭消费为 82,642.2、环比 2.30%、同比 7.48%；州/行业筛选可操作，分类和 Experimental 标签保留。
- 浏览器 Console 检查无 error/warn。390×844 手机视口下首页宽度与 scrollWidth 均为 390；市场页及手机导航亦已检查。不是所有手机型号的兼容认证。

| 默认策略（AUD） | Revenue | Gross Profit | Ending Inventory | Procurement Cash Outlay |
|---|---:|---:|---:|---:|
| Wait | 435.00 | 189.00 | 0 | 0.00 |
| Reorder | 1,218.00 | 556.20 | 6 | 462.00 |
| Discount | 391.50 | 145.50 | 0 | 0.00 |

默认推荐 Reorder：在当前预算/MOQ/交货假设下可行且预计毛利润最高。结果只是教学情景，不构成真实企业采购结论。

35 项完整公网检查针对首个应用提交；后续提交只增加构建过滤及审计文档，未改应用代码。第二次部署 Live 后，另复核五页及 features/demo catalog/market overview。停止本轮本机 5051 预览服务后，公网仍正常；原有用户本地 5050 服务未停止。Render 云端构建、Gunicorn 服务及公开 HTTPS 不依赖 Mac 或 Codex 持续运行。

本地验收证据在忽略的 `.runtime/deployment-evidence/`，包含公网检查 JSON 和截图，不将浏览器控制台账户截图推送 GitHub。公网 API 不公开 Git SHA；应用提交依据 Render 控制台的成功部署记录核验。

## 7. 持续更新与回滚

1. 在当前项目修改，保留算法和数据边界。
2. 运行相关检查及完整本地测试；没有本地受限数据时明确记录跳过。
3. 更新白名单的大小和哈希；只暂存已审计路径，检查 `git diff --cached`。禁止无差别 `git add .`，更不要提交私有数据或运行凭据。
4. 普通提交并推送私有 main，不 force push。
5. GitHub Actions 成功后，Render 的 **After CI Checks Pass** 自动部署。
6. 核对 Render Live 的 Git SHA，再验证真实 HTTPS 页面/API。CI 通过不等于部署成功。

第二次提交已实际走完此链路。Blueprint 的 `buildFilter.ignoredPaths` 包含 `*.md` 和 `deployment_files.json`，同步详情已显示应用该过滤；仅修改根目录报告/清单不重启应用。代码、模板、静态资源、数据、依赖和配置变更仍需部署；手动部署及 Blueprint 配置同步另按平台规则处理。[Render 构建过滤](https://render.com/docs/monorepo-support)

回滚可以在 Render 的 Deploys 中选择已验证的稳定部署（例如首次成功版本），或使用 `git revert` 创建回退提交、测试后推送，不改写历史。控制台回滚会关闭自动部署，确认恢复后再按需要启用 After CI Checks Pass。[Render 回滚说明](https://render.com/docs/rollbacks)

## 8. 限制与需要用户操作的事项

- 当前无需进一步 GitHub/Render 授权即可访问网站；请用上方真实地址检查效果。私人仓库和控制台仅由已授权账号管理。
- Free 会空闲休眠，首次恢复可能需要较长时间；没有购买常驻实例，没有企业 SLA。平台额度和政策可能变化，后续升级、付款或增加资源必须先取得用户同意。[Render Free](https://render.com/docs/free)
- 当前只开放单商品合成演示及 ABS 快照；ABS 不自动获取新发布，M5 和上传的关闭原因如上。
- 尚未做长期压力、全手机型号或独立安全审计；本轮没有对关闭的公开上传执行生产隔离验收，不能据本次部署直接开放上传。
- 没有自定义域名；`onrender.com` 已提供 HTTPS。没有新增产品阶段或高级功能。

**本阶段完成后暂停，等待用户检查线上网站。**
