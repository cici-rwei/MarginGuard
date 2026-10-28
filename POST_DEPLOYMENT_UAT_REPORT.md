# MarginGuard 上线后用户验收与 CSV 开放评估

日期：2026-10-28（Australia/Sydney）。此报告按实际验收持续更新；未完成事项不记为通过。

## 当前状态

- 公网地址：[MarginGuard](https://marginguard-lkno.onrender.com/)，沿用原 Render 服务和 Private GitHub 仓库。
- 本轮开始时线上稳定应用提交：`b626d078e65e261112eff292e7bef3221085dfc4`；仓库文档提交：`3503ffe9b0ac55e71771f06055f950d69d482875`。
- Part A：界面增量已完成；完整本地测试通过，新版本公网验收待本次部署完成。
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

目前需先解决的生产容量问题：默认两个计算槽、每个Linux子进程384 MiB限制，与512 MB免费实例及两个Gunicorn父进程的ABS缓存不匹配。现有每owner限流可被新会话绕过；全局配额不等于入口全局速率保护。尚未在Render完成最大输入、资源不足拒绝、重启、过期物理清理和双独立浏览器上传验收。

最小候选修复：公开环境收紧上传/行数/组合数/规范化结果/私有总容量；单计算槽和更低子进程限额；读取multipart前全局准入；保留多worker共享SQLite事务和显式短期数据声明。修复后需在同一服务进行受控生产验收，不能先向所有访客开放来测试。

Render Free 会休眠，临时磁盘在重启、重新部署或休眠后可能丢失，无SSH/one-off支持。不承诺长期保存。清理不能只依靠关闭标签页。[官方Free说明](https://render.com/docs/free)

## 尚未验证 / 暂未开放

当前尚未完成本轮公开上传、双浏览器隔离、Render重启后数据归属、物理清理及资源上限验证，不能标记通过。M5仍不公开，合成演示与ABS继续提供服务。

## 回滚

保留上述稳定提交。若本轮上线回归失败，使用Render已成功的历史部署回滚，或git revert本轮提交、测试、推送；不force push。控制台回滚后核对自动部署开关再恢复。禁止上传用户CSV、SQLite、密钥、日志或临时证据。
