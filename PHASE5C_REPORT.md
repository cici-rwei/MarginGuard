# Phase 5C：企业上传界面与 AUD/USD

完成日期：2026-10-28。保留 `/`、`/forecasting`、`/inventory`、`/scenarios`、`/market` 五条页面路由；前四页复用两种数据模式，ABS仍独立。

## 功能与文件

新增 `templates/_business_upload.html`、`static/js/business_upload.js`、`currency.py`、`tests/test_currency.py`、`tests/test_business_ui.py` 及多组合合成示例。修改 `app.py`、`templates/base.html`、`dashboard.html`、`inventory.html`、`scenarios.html`、`static/js/main.js`、`static/css/style.css` 和两个 README。跨页草稿使用同一 `business_context.js`，详见 `RESTRUCTURE_B_REPORT.md`。

Explore Demo保留本地真实M5、USD和历史预测日期。Analyse My Business支持模板、CSV选择、AUD/USD/时区/税额口径/销量与授权声明、服务端审查、缺失/未知/零销量/成本价格缺失信息、预览、连续区间选择、确认、商品与门店切换、四页分析以及删除。来源始终标为 `User-uploaded data · Source not independently verified`。

未填写库存显示Not assessed；未填写财务假设不输出利润。历史价格及成本提供单独的显式采用按钮；不自动等同于未来价格、现有库存账面成本或新采购报价。库存日期必须与预测原点匹配或声明为该原点的假设；页面不将历史CSV的未来14日预测冒称为今日预测。

## 币种实现

`finance.procurement`、`finance.gross_profit`、`scenario.simulate`、`scenario.compare_strategies` 增加向后兼容的 keyword-only `currency='USD'`。仅接受AUD/USD，校验在计算入口执行，正常及不可行情景均返回明确币种。`lost_sales`作为内部金额计算继承父情景币种，不换汇。

采购、FIFO、COGS、交货日、毛利润/毛利率、预算/MOQ和推荐排序公式不变；新增 `budget_satisfied` 只是已有预算约束的明确返回。USD旧调用继续有效。前端用声明币种格式化输入单位、表格、SVG图表提示、审计表和决策摘要。币种冲突由API拒绝；缺失金额保持空白，不能以0补齐。

## Purchasing Decision Summary

展示推荐策略、基础14日需求、预计收入与毛利润、采购现金、未满足需求、期末库存、预算/MOQ状态、Python推荐原因及三策略权衡。只比较当前输入的Wait/Reorder/Discount，不搜索全局最优数量，不生成真实采购订单。在途订单必须声明为单独排除这些存量及成本的情景，否则不能计算。

## 实际浏览器案例（明确合成）

`synthetic_84_days.csv`：2024-01-01至03-24共84日，504单位、12个显式零日。14日回测区间03-11至03-24；Moving Average MAE约2.57、Same-Weekday MAE0；未来03-25至04-07共84单位。固定周期样本的0误差不代表真实企业预测能力。

手工假设：AUD、库存20、lead2天、安全库存5、在途0、售价14.50、现有成本8.20、新成本8、采购20、运费5、其他0、MOQ5、预算200、折扣10%、假设增量10%。

| 策略 | 收入AUD | 毛利润AUD | 毛利率 | 未满足单位 | 期末库存 | 采购现金AUD |
|---|---:|---:|---:|---:|---:|---:|
| Wait | 290.00 | 126.00 | 43.45% | 64 | 0 | 0 |
| Reorder | 580.00 | 251.00 | 43.28% | 44 | 0 | 165.00 |
| Discount | 261.00 | 97.00 | 37.16% | 72.4 | 0 | 0 |

推荐Reorder为三者中可行且毛利润最高者。将采购增至30，现金变245、毛利润316，但预算不满足，推荐变Wait。将折扣从10%增至20%，Discount收入变232、毛利润68、毛利率29.31%。这些均为实际浏览器输入后Python返回的测试结果。

另用明确合成的三组合USD CSV验证目录与切换：SKU_A/store1、SKU_A/store2、SKU_B/store1的未来总量分别42、98、154，新的财务假设均为空。旧AUD数据集被替换，没有使用M5预测。删除后恢复空上传入口。

## 验证与限制

新增币种14项、HTML契约4项均通过；原Web与导航测试保留。实际浏览器完成上传→确认→四页→库存/财务修改→刷新→删除→Demo→ABS。390×844响应式视口下无页面横向溢出；实际截图在 `screenshots/`。最终完整测试与未验证项见 `FINAL_QA_REPORT.md`。

当前是每日gross units模型，不接受交易行/净退货推断、税务核算或跨币种合并。用户授权声明无法证明来源真实性。没有注册账户、长期保存或恢复保障，公开上传仍关闭。
