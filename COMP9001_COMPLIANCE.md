# COMP9001 最终交付核对（待官方要求确认）

本文件是证据清单，不是“已满足全部课程要求”的声明。当前未取得正式 rubric、Advanced Topics 官方清单、AI 政策、Padlet 提交格式或课堂演示评分要求。已经向用户请求这些材料；不会替用户提交 Ed 或 Padlet。

| 用户列出的交付项 | 项目证据 | 课程核验状态 |
|---|---|---|
| Python 源代码 | 独立 CSV、预测、库存、财务、情景、ABS 与 Flask 模块 | 已有实现，需对照官方范围 |
| 清楚结构与注释 | 函数/类边界、docstring、输入验证、现有报告 | 已有实现，最终结果见 FINAL_QA_REPORT |
| 至少两个 Advanced Topics | 下方候选与对应源码 | **官方认可尚未核实** |
| README 本地运行 | Python 环境、依赖、启动、合成输入、M5 合法恢复步骤 | 随最终包验收 |
| 第三方依赖 | requirements.txt、requirements-abs.txt、requirements-production.txt | 是否允许须对照 rubric |
| AI 使用声明 | AI_USE_DECLARATION.md | 草稿，必须由学生核对实际使用及课程格式 |
| Padlet 项目介绍 | PADLET_DRAFT.md，明确尚无公网地址 | 草稿，未发布 |
| 代表性截图 | screenshots/synthetic_*、screenshots/abs_* | 仅使用合成案例/官方汇总统计 |
| 三分钟演示 | DEMO_SCRIPT_3MIN.md | 排练脚本，不代表已实际演讲或计时验收 |
| 最终提交文件 | scripts/package_final.py 生成的源码包及清单 | 未取得 rubric 前不能称“课程合规全部通过” |

## Advanced Topics 候选证据

这些是可展示的实际技术，不是未经核实的课程认可结论。取得官方清单后至少选择两个被明确认可的项目，并补充学生自己的解释。

1. **类与自定义异常**：`BusinessStore` 封装临时数据生命周期；`BusinessCSVError` / `BusinessForecastError` / `BusinessError` 传递结构化错误。可解释对象状态、方法与异常继承。
2. **数据库与事务**：`business_store.py` 使用标准库 SQLite、参数化查询、事务、归属检查、并发配额和版本替换。可解释原子提交与跨用户隔离。
3. **进程与资源控制**：`business_service.py` / `business_worker.py` 通过固定子进程执行受限计算，使用 stdin JSON、wall timeout 和 CPU 限额。可解释为什么等待超时不等于后台工作已终止。
4. **第三方库与可视化/Web 应用**：Flask 提供 HTTP 接口；Pandas/openpyxl 用于 ABS 离线处理；本地 SVG 展示 Python 结果。是否属于官方 Advanced Topics 必须确认。

不能把普通列表、循环或仅导入一个库自动算作高级主题；应说明实际用途、代码位置、测试和限制。

## 数据与可重现性

课程包不包含真实企业上传、私有密钥、大型原始 M5 或未核实再分发权限的历史子集。接收者可通过明确的合成 CSV 验证 Analyse My Business 完整流程，ABS 页面使用随包公开汇总快照。Walmart Demo 需要接收者自行合法取得原文件并按 README 恢复；不能宣称解压后无需数据就有完整 M5。

没有 M5 或研究原 Excel 的干净包环境，应明确区分通过的合成/网页/轻量数据测试与因外部输入缺失跳过的集成测试。最终 QA 记录实际执行情况，不把 skipped 写成 passed。

## 学生提交前仍需完成

- 提供并核对正式 rubric、Advanced Topics 与 AI 政策；确认项目允许这些依赖与网站形式。
- 阅读并能解释核心实现，核对 AI 声明，不签署与实际贡献不符的内容。
- 填写学号/姓名等课程要求的身份信息；本项目不代填或杜撰。
- 按官方说明上传最终 ZIP、Padlet 内容并完成课堂演示；这些外部提交未授权自动执行。
- 若有在线展示要求，按 DEPLOYMENT_REPORT 完成账号与发布验证，不能将 localhost 链接当成公网网址。
