# MarginGuard 上线后用户验收与 CSV 开放评估

日期：2026-10-29（Australia/Sydney）。此报告按实际验收持续更新；未完成事项不记为通过。

## 当前状态

- 公网地址：[MarginGuard](https://marginguard-lkno.onrender.com/)，沿用原 Render 服务和 Private GitHub 仓库。
- 本轮开始时线上稳定应用提交：`b626d078e65e261112eff292e7bef3221085dfc4`；仓库文档提交：`3503ffe9b0ac55e71771f06055f950d69d482875`。
- Part A：已上线 `ed5c2e3be8048387150aa30c9152454f3e8a8ee5`，CI 40681261991 成功，Render 部署 `dep-dbgtsu29lscs73940870` 为 Live；真实 HTTPS 和浏览器验收通过。
- Part B：**公开 CSV 尚未开放**；当前开关仍为 false。

## Part A 修改范围

复用原五页、数据和 Python 引擎。英文界面统一更直白的业务语言，不改变内部 API 字段、结构或公式。

| 要求 | 实现位置 |
|---|---|
| 关闭上传时显示 Temporarily unavailable；开启时恢复正常入口 | templates/base.html、_business_upload.html、static/js/business_upload.js |
| 手机三策略卡片，桌面完整表格；保留预算/MOQ/不可行原因 | templates/scenarios.html、static/css/style.css、static/js/main.js |
| 库存与财务参数差异、可读前后值、显式确认后导入 | templates/scenarios.html、static/js/main.js、business_context.js |
| 手机减少重复导航，较长披露放 Details | templates/base.html、static/css/style.css |
| 风险明确只针对交货期及安全库存目标；展示14天需求 | templates/inventory.html、static/js/main.js |
| Synthetic 零 MAE 的限制说明 | templates/dashboard.html、forecasting.html |
| 可读标签、单位、术语帮助和纠正错误的方法 | 上述模板及 main.js、business_context.js、business_upload.js |

## 已验证通过

- GitHub CLI 授权仍有效，目标仓库 PRIVATE，沿用 main 和既有自动部署。
- 原上传 API/Store/生产配置测试 **56/56通过**（本地 Python 3.12，4.243秒）。这不是公网验收。
- 完整本地 Python unittest **309/309通过**（18.957秒、无跳过），保留原302项，新增7项模板测试。原JavaScript14项及新增10项，**24/24通过**。
- 本地公开配置浏览器：390px三策略卡片不横向溢出；默认收入435/1218/391.50、毛利润189/556.20/145.50均保持；采购80时现金612超过500预算、推荐Wait；库存导入30→5需确认且不覆盖采购量；取消保留原值，改变输入隐藏旧结果；负库存显示可读纠正提示。

## Part B 发现及开放条件

现有匿名会话、CSRF、owner+dataset校验、事务、TTL、主动删除、后台清理已实现，不能通过重新写解析器或翻开关替代验收。

初次审计发现：两个计算槽、每个Linux子进程384 MiB限制，与512 MB免费实例及两个Gunicorn父进程的ABS缓存不匹配；每owner限流可被新会话绕过。容量问题已完成下面的代码加固，但尚未在Render完成最大输入、资源不足拒绝、重启、过期物理清理和双独立浏览器上传验收。

已完成最小修复：公开环境1 MiB / 10,000行 / 20组合 / 单数据集2 MiB / 总payload16 MiB / 20会话；单计算槽贯穿父进程编码、结果解析及保存，Linux子进程128 MiB且设置限制失败即拒绝；读取multipart前全局限流。原本地5 MiB / 50,000行 / 100组合保留。面板从服务器limits读取上限。公众上传及受控门禁均保持关闭。

Render Free 会休眠，临时磁盘在重启、重新部署或休眠后可能丢失，无SSH/one-off支持。不承诺长期保存。清理不能只依靠关闭标签页。[官方Free说明](https://render.com/docs/free)

## 尚未验证 / 暂未开放

当前尚未完成本轮公开上传、双浏览器隔离、Render重启后数据归属、物理清理及资源上限验证，不能标记通过。M5仍不公开，合成演示与ABS继续提供服务。

## 回滚

保留上述稳定提交。若本轮上线回归失败，使用Render已成功的历史部署回滚，或git revert本轮提交、测试、推送；不force push。控制台回滚后核对自动部署开关再恢复。禁止上传用户CSV、SQLite、密钥、日志或临时证据。

## Part A 公网已验证通过

- 原网址五页及Demo/ABS接口正常，10项HTTPS检查通过；包括上传503和M5接口503。关闭结果仅证明未开放，不证明上传安全。
- 手机390px为3张策略卡片，scrollWidth=390，默认财务值保持。采购80的现金612、毛利润558.90与原引擎一致，预算失败不推荐；采购10显示最低采购量失败和纠正建议。
- Inventory输入5，显示交货期需求10、备用库存10、14天需求84。Finance显示30→5差异，取消保持30，不自动替换采购量/价格/成本。
- Forecast解释合成周模式的零MAE；ABS12个SVG、Experimental/参考期/单位完整，Console无error或warn。
- 部分自动化首次读取早于异步响应，等待完成后复核；未将旧隐藏结果当成新计算证据。

## Part B 已修复，但尚未完成生产验收

| 文件 | 最小加固 |
|---|---|
| runtime_config.py | 公共容量固定上限，可收紧而不能无界放大 |
| business_store.py | 跨owner/worker事务全局限流；删除会话不重置窗口 |
| business_service.py | 单槽覆盖父编码、worker、解析及保存；固定内部可信预算 |
| business_worker.py | 复用原parser，公共行/组合检查、Linux限额fail-closed、输出限额 |
| business_api.py | 读取multipart前准入，动态limits，复用原会话/CSRF/owner |
| upload_review.py、app.py | 默认关闭的短期验收授权，绑定owner/凭证版本/期限 |
| _upload_review.html、upload_review.js、base.html | 明确受控入口，无新增上传API，凭证不进URL或Web Storage |
| business_upload.js、business_context.js、_business_upload.html | 从服务器读取容量/TTL，限制缺失时不发送CSV |

完整加固后本地Python **345/345通过**（26.210秒，无失败/错误/跳过），Node **29/29通过**。原302项测试逻辑保留。新增capacity16、admission4、review16项；Part A新增模板7项。本轮模板中的固定TTL文案断言更新为动态限制契约，并由新增Node测试验证真实值及fail-closed。没有改旧测试来绕过失败。

Mac容量实测：旧配置合法50,000行/4,000,052字节合成CSV上传201，warm ABS父峰值161.23MiB、child95.34MiB；新公共配置10,000行/20组合/800,052字节上传及确认201，父峰值119.14→132.23MiB、child35.83MiB，耗时0.237/0.149秒。**不是Linux或Render总实例并发峰值。**

本地TTL清理：到期读取401；cleanup后会话/数据/速率/任务记录为0，SQLite中的合成marker消失，无journal残留，保留40,960字节空DB。只证明应用删除，不承诺云介质取证级擦除。

## 受控生产验收方案（等待确认，尚未启用）

1. 保持 `ENABLE_BUSINESS_UPLOAD=false`。仅在用户确认后启用最长2小时review窗口；测试端生成随机64位hex凭证，Render只配置SHA-256摘要及UTC截止时间。原凭证不进入Git、URL、日志或报告。
2. 仅持凭证者通过既有GET /api/business/session交换短期授权，普通访客features仍false。授权默认30分钟，绑定原owner；轮换、到期、删除或数据丢失撤销访问，旧授权不能自动建立新owner。
3. 同一真实HTTPS服务使用两套独立会话与纯合成CSV，验证AUD/USD完整流程、越权/CSRF/超限/任意文件路径拒绝、删除/过期/重启/资源拒绝与恢复，回归ABS和Demo。
4. 所有必要检查通过后关闭review门禁，再按本次条件授权正式开放；不通过则保持关闭，记录原因。没有购买资源或新建网站。

**需要确认的原因：** 启用门禁会新增一项短期公网访问权限，使持测试凭证者可以建立临时私有上传会话。按照用户本轮“遇到授权或确认安全风险时暂停询问”的要求，在实际启用前取得确认。当前只完成代码及关闭状态准备。

## 已知限制与未验证事项

- 公开上传、双独立浏览器上传隔离、Render重启后的归属、物理清理和资源耗尽恢复尚未完成生产验收，不记为通过。
- Free休眠、重启和部署可能提前丢失数据，不承诺长期保存。
- 全局限流是固定窗口，边界允许突发；单计算槽仍限制并发。匿名容量满时安全拒绝，不承诺抵御所有恶意流量或企业SLA。
- SQLite payload上限不含journal、环境和平台日志的整盘占用，必须在真实环境检查余量。
- M5仍不公开；公众上传和临时受控入口当前均未启用。Part A已在原网址正常运行。
