# MarginGuard 公开部署报告

更新：2026-10-28（Australia/Sydney）。本文件随本轮实际验收继续更新。

**当前状态：部署进行中，尚未取得真实公网 HTTPS 地址，不标记为部署完成。**

## 1. GitHub 与授权

- 已按用户明确批准，将原私有空仓库 `cici-rwei/-MarginGuard` 改名为 [cici-rwei/MarginGuard](https://github.com/cici-rwei/MarginGuard)。仍为 Private。
- GitHub API 已核实账户、push 权限及空仓库状态（提交接口返回 empty repository），没有覆盖历史提交。
- 用户亲自完成 GitHub CLI 浏览器授权。官方 CLI 2.103.3 的下载 SHA-256 与官方发布元数据一致；工具仅保存在忽略的本地运行目录，不进入部署文件。
- 授权状态核实为 `cici-rwei`、success、keyring，使用可刷新的有效期令牌。未读取或输出令牌；Git 凭据辅助仅设置在当前项目，不修改全局 Git 配置。
- 用户亲自授权 Render 并仅选择 MarginGuard；已在 Render 仓库选择页核实 `cici-rwei / MarginGuard` 可见。
- 本地现有项目已初始化 Git。待提交内容由 `deployment_files.json` 明确列出；最终暂存区审计、提交、推送结果待后续记录。

## 2. 部署配置

| 项目 | 已检查的配置 |
|---|---|
| Runtime | Python |
| Python | `.python-version` = 3.12.14 |
| Runtime dependencies | Flask 3.1.2、Gunicorn 26.2.0，以及安装器解析的间接依赖 |
| Repository root | 当前 MarginGuard 目录内容；Render Root Directory 留空 |
| Build | `pip install -r requirements-production.txt` |
| Start | `gunicorn -c gunicorn.conf.py wsgi:app` |
| WSGI | `wsgi.py` 导出 `app.py` 的 app |
| Bind | `0.0.0.0:$PORT`；两名同步 worker、20 秒超时 |
| Health check | `/api/features` |
| Plan | 仅允许 Free；没有批准付费资源 |
| Region | Blueprint 指定 Singapore；创建时需核实实际资源 |
| Static assets | 随源码提供 HTML/CSS/Vanilla JS、本地 SVG；核心图表无外部 CDN |
| ABS | 六份已审计轻量文件，基于模块相对目录读取；请求不重新解析 Excel |

环境变量名称及公开非秘密开关：`MARGINGUARD_PUBLIC=true`、`TRUST_REVERSE_PROXY=true`、`MARGINGUARD_SECRET_KEY`（平台生成，不在报告记录值）、`ENABLE_SYNTHETIC_DEMO=true`、`ENABLE_M5_DEMO=false`、`ENABLE_BUSINESS_UPLOAD=false`、`M5_PUBLIC_LICENSE_CONFIRMED=false`、`PYTHONDONTWRITEBYTECODE=1`。Render 提供 `PORT` 和 `RENDER_EXTERNAL_HOSTNAME`。不添加持久盘、数据库或其他付费资源。

## 3. 获批的最小功能增量

独立固定样本适配 `/api/demo/*` 复用既有 CSV 校验、预测、库存和财务引擎，维持五条页面路由。数据源明确为 Synthetic Demo，币种 AUD；固定样本历史 2024-01-01–03-24，模拟预测 03-25–04-07。合成数据不是真实企业记录，周模式的低 MAE 不能证明现实预测能力。库存、成本、交货时间、采购及促销增量为可修改的假设。

公开候选开放：四页 My Business 合成决策流程、独立 ABS Market Intelligence。关闭：M5（公开再分发/展示许可未核实）、企业 CSV 上传（未完成生产安全验收）。合成适配不创建匿名会话/SQLite，不接受任意文件路径或客户端预测序列。

## 4. 文件及数据保护

提交依据明确白名单，不执行无差别 `git add .`。排除 M5 原始/处理后/派生数据、旧数值报告及截图、企业 CSV、环境密钥、Cookie、运行授权配置、SQLite、日志、缓存、虚拟环境、研究下载和 ZIP。公开部署只带合成示例及保留来源和许可的 ABS 汇总。

原 `MarginGuard_COMP9001_Final.zip` 不覆盖；其 103 文件清单已复核，原 SHA-256 为 `44aa17451bf51ec1b9204b40690256d415d376000e96cd26fce5a4e6e42b16e4`。本轮源码更新通过 Git 提交交付。

## 5. 测试与线上证据

本轮完整本地 unittest **302 项全部通过**，0 失败/错误/跳过，19.622 秒。原 278 项保留，新增 21 项合成后端及 3 项 UI 测试；release features 测试同步增加独立开关字段。另有 Node 内置测试 **14/14 通过**。Python 3.12 生产环境的合成/UI/导航/公开配置子集 **47/47 通过**。原验收记录见 `FINAL_QA_REPORT.md`。

干净白名单快照不含 M5 和原 ABS Excel：发现 302 个方法，**283 个实际通过，19 个缺少外部输入未运行**；unittest 输出 `Ran 286, OK (skipped=5)`，其中 3 个单方法跳过、2 个整类跳过合计 16 个方法。零失败/错误，13.899 秒。临时快照测试后清理；不将缺失外部数据的检查写成通过。

本机 Python 3.12/Gunicorn 生产配置实际启动于回环 5051，与原 5050 服务隔离。四页源码、合成 API 及 ABS 实际浏览器交互已验证：历史 504 单位、未来 84 单位；MAE 2.57/0；库存 30→0 时风险 Sufficient→Stockout、建议量 0→20；默认 Wait/Reorder/Discount 毛利润分别 AUD 189/556.20/145.50。采购 60→80 后现金 462→612、超 500 预算，推荐由 Reorder→Wait；折扣 10%→20% 后 Discount 收入 391.50→348、毛利率 37.16%→29.31%。合成结果与原引擎对应，ABS 12 个 SVG 已加载，月份与 Original 切换成功。检查时 Console 无 error/warn。

28 份受保护核心/数据文件的部署前后 SHA-256 一致，包括预测、库存、财务、策略、CSV适配及 ABS 模块和数据。没有重算覆盖任何 M5/ABS 源文件。Git/Render 线上结果将另行补记。

公网首页、导航、ABS、静态资源、手机布局、HTTPS、Debug 关闭及错误脱敏：未验证。没有线上地址，不能以本地 HTTP 或 API 测试代替公网验收。

## 6. 持续更新与回滚

已新增只读 GitHub Actions CI：Python 3.12.14、完整 unittest、Node 内置草稿测试。无受限 M5/原 ABS Excel 的检查会明确跳过，不在 CI 下载这些文件，也不把跳过写成通过。部署运行不依赖 Node。

流程：修改现有项目 → 本地测试 → 审核白名单和暂存差异 → 提交推送 → GitHub CI → Render 部署 → 实际 HTTPS 验收。Blueprint 已配置 `autoDeployTrigger: checksPass`（对应 **After CI Checks Pass**）；界面未核实前不声称云端已启用。

回滚优先选择 Render 已验证的稳定部署，或用 `git revert` 生成回退提交并经测试推送。Render 控制台回滚会关闭自动部署，需核实稳定后再恢复。免费服务会休眠，文件系统临时；不承诺可用性 SLA 或保留企业数据。细则以 [免费服务](https://render.com/docs/free)、[部署](https://render.com/docs/deploys)、[回滚](https://render.com/docs/rollbacks) 官方文档为准。

## 7. 尚待完成

最终提交清单与暂存区检查、推送并通过 GitHub CI、Render 免费服务创建及 HTTPS/手机浏览器实测。需要账号授权时由用户在官方页面完成，不索取密码、Access Token 或私钥。不推进其他产品阶段。
