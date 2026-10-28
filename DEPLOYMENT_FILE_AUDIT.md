# MarginGuard 首次部署文件审计

审计日期：2026-10-28（Australia/Sydney）。状态：**首次冻结审计及最终上线复核均已完成**。下文保留首次冻结时的历史检查记录；最终 GitHub/Render 状态及公网证据见 `PUBLIC_DEPLOYMENT_REPORT.md`。

## 1. 结论与范围

当前精确白名单包含 **110 个文件，约 3.64 MB**；必需文件完整。`deployment_files.json` 逐项列出相对路径、字节数、SHA-256、纳入理由和审核状态，精确总字节数以该清单为准。清单也列出自身；自身 `sha256` 为 `null`，明确避免递归自哈希，其完整内容将在 Git 提交对象中固定。其余 109 项均有文件内容 SHA-256，包括本报告。不得将 `null` 冒称为已校验哈希。

用户已批准最小合成演示适配。当前公开候选提供 Synthetic Demo 的四页经营流程和独立 ABS Market Intelligence。M5 和匿名企业上传仍关闭。合成样本经过现有 Python 校验、预测、库存和财务引擎计算，不使用写死结果，不创建上传会话或 SQLite；不接受客户端指定文件路径或预测序列。

已修正 `data/DATA_SOURCE.md` 的本机 Downloads 绝对路径与旧版 ZIP 描述，明确排除全部 M5 原始、处理后与派生结果。已更新打包白名单；新增合成模块被列为必需文件。没有覆盖原 `MarginGuard_COMP9001_Final.zip`，也没有修改原始 M5/ABS 数据或核心公式。

对最终候选执行文件类型、路径及已知私钥/GitHub token 格式检查，未发现企业上传、M5 销量记录/预测 JSON、SQLite、`.env`、凭证格式、缓存、日志、虚拟环境、研究数据或本机用户绝对路径。此扫描不保证识别所有未知秘密格式；首次推送前仍必须核对真实 Git 暂存区及逐文件差异。

## 2. 与原交付 ZIP 的关系

原 ZIP：103 项源文件、2,051,985 字节，CRC 通过，SHA-256 保持为 `44aa17451bf51ec1b9204b40690256d415d376000e96cd26fce5a4e6e42b16e4`。ZIP 不上传 GitHub。初始部署审计时原 103 项与本地文件完全一致；获批的合成适配完成后，当前有 18 个原文件修改、7 个新增文件。因此旧 ZIP 是历史备份，不是本次待部署版本。

7 个新增项：`.github/workflows/ci.yml`、`synthetic_demo.py`、`tests/test_synthetic_demo.py`、`SYNTHETIC_DEMO_MINIMAL_PLAN.md`、`PUBLIC_DEPLOYMENT_REPORT.md`、`DEPLOYMENT_FILE_AUDIT.md`、`deployment_files.json`。修改集中于应用注册、运行开关、现有页面的合成数据入口、来源标识、输入上下文、测试与交付配置。完整提交项和哈希以机器清单为准。

## 3. 运行配置、依赖和路径

| 项目 | 已核对配置 |
|---|---|
| WSGI | `wsgi.py` 导出 `from app import app` |
| Build | `pip install -r requirements-production.txt` |
| Start | `gunicorn -c gunicorn.conf.py wsgi:app` |
| Python | `.python-version` 固定 3.12.14 |
| 直接运行依赖 | Flask 3.1.2、Gunicorn 26.2.0；传递依赖由 pip 安装 |
| 仓库/Root Directory | 白名单文件直接放在仓库根目录，Render Root Directory 留空 |
| Gunicorn | `0.0.0.0:$PORT`，默认 8000；2 个同步 worker、20 秒超时；Debug 关闭 |
| Health check | `/api/features` |
| Render 候选 | `plan: free`、`region: singapore`；创建时还需核实实际资源 |
| 自动部署候选 | `autoDeployTrigger: checksPass`；尚未把配置等同于云端实际启用 |
| 静态资源 | 2 份 CSS、4 份 JavaScript；模板使用本地静态路由和 SVG，无核心图表 CDN |
| ABS | 相对模块目录读取 `data/abs/` 轻量文件；每次请求不解析 Excel |
| 合成样本 | 固定 `examples/business_csv/synthetic_84_days.csv`；AUD、84 天，明确为合成历史模拟 |
| 运行内存依赖 | 生产网页不导入 Pandas/openpyxl；离线重建和完整测试使用 `requirements-abs.txt` |
| 私有上传 | 公开开关关闭；不创建数据库或持久盘服务 |
| 密钥 | `MARGINGUARD_SECRET_KEY` 由平台环境生成/注入；文件和报告不记录值 |
| 公开功能 | `ENABLE_SYNTHETIC_DEMO=true`、`ENABLE_M5_DEMO=false`、`ENABLE_BUSINESS_UPLOAD=false`、`M5_PUBLIC_LICENSE_CONFIRMED=false` |
| Host/代理 | Render hostname 环境配置；只在可信 TLS 终止代理环境启用协议头处理 |

前端请求使用同源 `/api/...`，没有把 Mac 的本地地址作为生产 API。`start.command` 仅供本地运行，Render 不执行。ABS 数据保留来源、日期、单位、许可和统计口径；与合成/M5 商品数据隔离。

## 4. 分发边界与 Git 操作

包含已审查源码、全部测试源码、7 个模板、6 个静态文件、依赖/启动/CI 配置、说明报告、ABS 六份轻量文件、两个明确合成 CSV 和空模板、3 张既有合成/ABS 截图。`data/scenario_defaults.json` 为明确假设，不是 Walmart 真实库存或成本；公开合成适配使用其独立默认假设。

排除 `data/raw/`、M5 原始/处理后 CSV、source_audit、forecast_results、phase2_demo、旧 Phase 1–3 数值报告、M5 历史截图、用户 CSV、数据库、环境文件、认证配置、日志、缓存、venv、研究下载和 ZIP。保留真实 M5 测试源码，但只有本地合法获取的数据存在时才执行相关检查。

`.gitignore` 是第二道保护，不能代替白名单，也不能保护已经跟踪的文件。首次提交必须按 `deployment_files.json` 精确选择 110 个路径，再比较 `git diff --cached --name-only` 和清单，检查每项大小、差异和机密格式。不能使用无差别 `git add .`。后续内容变更应先测试、更新审计清单，再提交；报告中的未来公网证据也会改变哈希，必须同步刷新。

## 5. 测试证据及跳过解释

| 验证环境 | 实际结果 |
|---|---|
| 完整本地项目，Python 3.9.6 | 302 项通过，0 失败/错误/跳过；19.622 秒，由部署主流程运行 |
| 本审计的干净白名单快照，Python 3.9.6 | 发现 302 个方法；283 个实际通过、19 个因无外部输入未执行；0 失败/错误；13.899 秒 |
| 同一干净快照，Node 24.19.0 | 14/14 通过，0 跳过 |
| Python 3.12 生产配置子集 | 合成/UI/导航/公开配置 47/47 通过，由部署主流程运行 |
| 本审计 Python 3.12.14 test client | 五页、features、合成 catalog/analysis、ABS catalog/overview/counts/sources 均 HTTP 200 |
| GitHub Actions / 真实 Render HTTPS | 此次冻结时尚未执行；不以本地结果替代 |

干净快照只复制白名单到系统临时目录，不含 M5 或原 ABS 工作簿；完成后删除临时目录，没有建立新的持久项目副本。unittest 原始输出为 `Ran 286 tests, OK (skipped=5)`：3 个单方法跳过是 2 个原 ABS 工作簿检查和 1 个真实 M5 衔接检查；另外 2 个 M5 测试类在 `setUpClass` 跳过，共 16 个方法不计入 `testsRun`。302−19=283，不把这些未执行检查写成通过。所有原测试保留，新增合成测试不依赖受限数据。

新增 CI 使用 Python 3.12.14，安装 `requirements-abs.txt` 和 `requirements-production.txt` 后执行完整 unittest；Node 24 只运行既有内置测试，不安装前端框架或 npm 依赖。权限为 `contents: read`，checkout 不保留凭据，10 分钟超时；不包含部署秘密、不上传制品或下载 M5/原 ABS 工作簿。Action 用法核对自官方 [checkout](https://github.com/actions/checkout)、[setup-python](https://github.com/actions/setup-python)、[setup-node](https://github.com/actions/setup-node)。

部署主流程另核对 28 份受保护核心/数据文件 SHA-256 前后一致，并完成本地生产 Gunicorn 浏览器交互检查；具体指标见 `PUBLIC_DEPLOYMENT_REPORT.md`。这些仍是本地证据，公网验收尚待完成。

## 6. 磁盘与内存边界

ABS 六文件共 **2,603,774 字节**；market_data 压缩文件 1,557,978 字节，解压 JSON 文本 9,474,641 字节。Python 对象占用大于压缩文件体积。

合成适配完成后，本 Mac Python 3.12.14 单进程 test client 访问上表页面/API：`ru_maxrss` 由 **39,796,736 字节**升至 **126,337,024 字节（约 120.5 MiB）**。`sys.modules` 确认没有 Pandas/openpyxl。此测量不是 Linux/Render 双 worker、并发压力或总实例内存验收；两 worker 各自缓存 ABS，还需 master、响应和系统余量。实际服务需查看 Metrics 的内存、启动时间及重启情况，不能仅凭文件大小保证免费实例足够，不能自行升级付费资源。

ABS 和合成样本作为只读仓库文件，不需要持久盘。Render 免费服务会空闲休眠，运行时文件在重启/重新部署/休眠后丢失，不支持持久盘，不承诺企业生产 SLA。绑定付款方式后超出部分用量可能计费，创建资源时还需核对免费计划及工作空间支出限制。[Render 免费服务官方说明](https://render.com/docs/free)

## 7. 下一步

1. 部署主流程核对 Git 实际暂存区与本清单，确认目标仍为 Private、没有覆盖现有提交。
2. 提交推送后检查 GitHub CI，核实 Render 免费资源及 After CI Checks Pass 设置。
3. 取得真实 HTTPS 后完成页面/API、静态资源、手机、关闭功能说明、Debug/错误脱敏和资源指标验证。
4. 更新公网证据时同步刷新本清单。未取得真实地址与验收结果前，不能标记部署完成。

## 首次上线后的部署配置核验

首次110文件清单已提交为 `296ae9b11632cb8827dca9aaba81c305dd08598d` 并成功推送私有仓库；GitHub CI成功。Render免费服务已Live，实际地址为 https://marginguard-lkno.onrender.com 。后续仅增加构建过滤规则：根目录Markdown报告及 `deployment_files.json` 的单独变动不触发应用重启；代码、配置、ABS/合成数据仍参与构建。11项生产配置回归通过，核心算法及数据无修改。当前逐文件摘要以随提交更新的机器清单为准，前文首次冻结字节数是首次提交前的审计快照。完整公网结果见 `PUBLIC_DEPLOYMENT_REPORT.md`。

## 最终上线复核

实际应用提交 `b626d078e65e261112eff292e7bef3221085dfc4`，Render Live；私有 GitHub CI 成功。提交内110路径与清单一致，109内容哈希/全部大小正确，28份受保护核心和数据哈希与基线一致；24个敏感路径忽略探针通过，两个可达提交未发现禁入路径。公网35项检查全部通过，并完成真实浏览器交互及手机检查，详见部署报告。

两个旧的未跟踪脚本 `scripts/package_phase1.py`、`scripts/package_phase3.py` 可能漏排环境文件、数据库及 M5 派生结果，保持不提交、不执行；后续只使用 `scripts/package_final.py` 的明确白名单。最终报告与README更新后重新刷新机器清单。原始数据、核心算法、原ZIP均不改动。
