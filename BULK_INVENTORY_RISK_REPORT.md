# MarginGuard 批量库存风险升级报告

日期：2026-10-29。本文区分本地验证与公网验证；部署与最终计数将在验收结束后补齐。现阶段不因本地测试通过就宣称上线成功。

## 1. 产品与实现范围

在原项目增量实现：销售上传 → 数据质量确认 → 批量14天预测 → 可选库存快照上传与确认 → Business Risk Overview → 优先级清单 → 单品库存与财务策略比较。

没有修改 `forecast.py`、`business_csv.py`、`business_forecast.py`、`inventory.py`、`finance.py`、`scenario.py` 的公式，也没有修改 M5 或 ABS 数据。原销售上传、匿名会话、Synthetic Demo、本地 M5、Market Intelligence、AUD/USD 与单品手动输入继续保留。没有新增框架、仓库、网站或付费服务。

只上传销售时仍显示批量需求预测；库存未知不会变成0。历史不足、未确认历史、库存缺失或错期的组合保留在清单中并显示 **Not assessed**。

## 2. 文件清单

新增：

- `inventory_csv.py`：独立库存 CSV 解析及质量报告。
- `batch_inventory.py`：服务器端关联、原库存引擎适配、互斥分类、解释及排序筛选。
- `static/js/business_risk.js`、`templates/_inventory_upload.html`：批量总览、库存预览确认、显式参数导入。
- `examples/business_csv/inventory_template.csv`、`synthetic_inventory_multi_series.csv`：字段模板及明确合成的库存样本。
- `tests/test_inventory_csv.py`、`test_batch_inventory.py`、`test_inventory_store.py`、`test_inventory_security.py`、`test_bulk_inventory_api.py`、`test_business_risk_templates.py`、`business_risk.test.js`。
- 本报告。

修改：`business_api.py`、`business_service.py`、`business_store.py`、`business_worker.py`；`templates/base.html`、`templates/dashboard.html`；`static/js/main.js`、`static/js/business_upload.js`、`static/css/style.css`；`README.md`、示例说明、CI 测试清单、打包白名单及部署清单。既有测试逻辑保留，新增回归测试独立存放。

## 3. CSV 格式与日期规则

```csv
Product,Store,Stock As Of Date,Current Stock,Supplier Lead Time,Safety Stock,On-order Units
SYNTHETIC_SKU_A,SYNTHETIC_STORE_1,2024-03-24,3,7,5,0
```

最后一列可省略；其余标题必需。支持 UTF-8/BOM。Product + Store 精确匹配，保留大小写及前导零，不模糊关联。重复商品—门店行整份拒绝，即使日期不同也不自动取最新或相加。非空非法值、负数、小数库存、非法日期、未知列等拒绝。空白库存参数仍为未知；缺失标识进入不可匹配质量报告。

库存/备用/在途均为非负整数，最多1,000,000件；交货时间0–365整天。`Stock As Of Date` 是已完成营业日的期末库存。必须等于**各组合所选销售历史最后一天**，即14天预测开始日前一天。不能使用源 CSV 中未选窗口的较晚库存。错期不自动回推、滚动或混用；重新提供对齐快照，或进入单品页明确进行历史时点的假设分析。

缺 `On-order Units` 保持未知；只有用户明确勾选“没有在途订单”才将空白在途值设为0，已有正数不变。在途只参与库存位置，不作为已经到货的可售库存。过剩覆盖天数是用户设置的独立规划参数，表单起始值30天，不是数据字段或行业基准。

## 4. 批量计算与风险依据

销售确认沿用受限 worker，为选中的连续有效历史调用原 `analyse_business_series()`：至少42天、推荐84天，最后14天 chronological holdout，比较原两种方法 MAE，再按原选择规则生成未来14天。未选择或不足的组合仅保存质量元数据，不借用其他商品预测，不跨越未知日期。

库存验证使用服务器已保存的预测，逐组合调用原 `inventory_risk()`。计算在原受限 worker 中完成，结果缓存；浏览器筛选和刷新不重新拟合预测或解析 CSV。每行保留自己的历史、预测及库存日期，不能把不同预测区间的需求相加冒充共同周期。

| 主分类 | 沿用规则 | 初步操作 |
|---|---|---|
| Stockout Risk | 当前库存小于交货期需求 | Evaluate Reorder |
| Reorder Attention | 当前库存覆盖交货期需求，但库存位置低于需求加备用目标 | Evaluate Reorder |
| Excess Inventory Attention | 无前述更高优先级条件，覆盖天数超过用户阈值；或零需求时仍有库存 | Review Discount Strategy |
| Sufficient Inventory | 无前述条件，满足交货期需求及备用库存目标 | Monitor Inventory |
| Not assessed | 历史、快照、参数或日期不足以有效计算 | Complete Missing Data |

优先级仅为上述现有主分类顺序及稳定的商品/门店排序，没有额外风险评分或阈值。缺货与过剩的原布尔标记可能同时成立；KPI 使用互斥**主分类**，展开详情仍显示原标记。`High Stockout Risk` 表示原 stockout 布尔条件命中，不是新增的概率或严重程度分级。

`Products Analysed` 是成功生成预测的商品—门店组合数，可能同时包含库存未评估的组合；`Data Incomplete` 是库存未评估组合数。另显示总组合数和 Reorder Attention 数，不能把五张卡简单相加。过滤不改变整体 KPI。

详情显示当前库存、14天需求、交货期需求、备用库存、覆盖天数、在途量、过剩阈值、建议额外采购量及原因。零需求的覆盖天数保持空值并说明无预测需求；交货期超过14天沿用原平均需求外推并披露。充足只针对交货期需求和备用目标，不能解释为整个14天必不断货。

建议量只是库存规则的额外补货缺口，不是全局最优采购或财务批准。财务页仍由原 Python 引擎比较 Wait、Reorder、Discount，并检验预算、MOQ等约束；不自动下单。

## 5. 财务与页面贯通

风险行使用独立详情链接，保留数据源、数据集ID、revision、系列；服务端核验所有权和版本，再恢复商品/门店、币种及预测区间。旧深链明确拒绝，不能静默转入另一个商品或新版本。

库存导入显示易读字段及前后数值，必须点击 Review / Apply 才应用；不自动覆盖已编辑参数。建议量另行确认；价格、现有库存成本、新采购成本及预算保持用户输入。有在途库存时，现有财务模型不能安排其到货及成本，因此自动财务导入保持阻断；用户可明确进行排除在途数量与成本的独立手动情景，不能悄悄把在途加入现货。

确认库存后立即使旧结果失效；若随后刷新失败，只说明“已保存但当前结果不可用”，不把旧结果标成新版本。单品手动情景与已确认批量快照明确区分，避免同页显示互相矛盾的“未评估”。

## 6. API、存储及公开资源限制

- `GET /api/business/inventory-template.csv`：固定模板，不接受文件路径。
- `POST /api/business/datasets/<id>/inventory-uploads`：multipart file、revision、excess_cover_days、assume_no_on_order；返回待确认ID、版本及质量/风险预览。
- `POST /api/business/datasets/<id>/inventory-uploads/<upload_id>/confirm`：明确两份版本，原子附加库存。
- `DELETE /api/business/datasets/<id>/inventory-uploads/<upload_id>`：删除自己的库存草稿。
- `GET /api/business/datasets/<id>/inventory-risk?revision=...`：只读缓存，支持 risk/store/search/sort 严格筛选。
- 原单品 analysis 增加 `inventory_import`；仅有效对齐快照提供输入提案，原 defaults 仍为空。

复用仓库外私有 SQLite、owner、CSRF、same-origin、TTL、清理、全局/用户限流和单计算槽。库存 pending 绑定目标销售数据集及其 revision；确认只改变库存附件及版本，不覆盖销售。冲突、超时、容量不足、失效或他人访问均失败关闭。删除销售会同时清理绑定库存草稿，不释放仍在运行的任务租约。

公开配置保持1MiB销售/库存文件、销售10,000行、20组合；库存最多20行；2MiB每规范化数据集、16MiB总payload、20会话；一个共享任务、Linux子进程128MiB、5秒处理时限、Gunicorn20秒请求上限。受限 worker 无法设置资源约束时拒绝。CSV 不执行，不存入静态目录/Git/部署包，不记录业务明细或令牌。免费实例不保证持久保存；部署/重启/休眠可提前丢失数据。

## 7. 测试与验收状态

已验证：纯模块合成测试、原引擎数值一致性、42天门槛/未知日期、多组合匹配、错期拒评、空值、在途声明、零需求、长交货期、过滤排序、AUD/USD上下文、匿名隔离、CSRF/Origin、严格参数、容量拒绝、worker超时回收、并发版本冲突及删除清理。

最终完整本地 Python：453/453通过（36.904秒），原348项保留，新增105项；JavaScript：51/51通过，原29项保留，新增22项。原始测试未删改逻辑。生产依赖 pip check 通过。28个受保护核心及数据文件SHA-256与升级前一致。

本地实际 HTTP：92/92检查通过，明确合成数据；最大20组合/1680条销售与20条库存整个流程约0.347秒（本地时间，不代表Render性能）。三组验收会话删除成功。

本地浏览器已检查：销售三组合确认、库存预览/确认、KPI 1缺货/1过剩/1充足、风险筛选、商品准确跳转、财务导入前差异及预算保留；390×844视口无横向溢出、风险卡片可读。B商品财务实跑在价格10、成本4、折扣10%、提升20%、预算200等明确假设下，三策略毛利均AUD924，原平手规则推荐Wait；这说明初步Review Discount Strategy没有被冒充财务最终推荐。最终公网验收待更新。

公网地址仍为 https://marginguard-lkno.onrender.com/ 。本轮尚未推送/部署，不能将这些本地结果称为上线通过。

## 8. 已知限制与回滚

- 没有自动连接POS/ERP；库存和采购参数由用户提供，来源未独立核实。
- 日期不一致不自动修复；需要对应时点库存或明确的单品假设。
- 没有订单到货日明细、多商品联合预算优化、预测区间不确定性或长期保存。
- 每个组合独立判断，初步建议未经财务约束验证；业务判断仍需用户确认。
- 压力耗尽、真实手机硬件、Render底层物理擦除不能由功能测试保证；不以固定限流代替完整DDoS防护。
- 此前稳定应用提交为 `091dd76bec16f071d3d489ce5299780570d39fb2`。如新版本出现问题，可在同一Render服务回滚到该部署，或通过测试后的git revert与原GitHub→Render CI流程恢复。回滚可能使临时会话丢失，不能恢复已删除上传。

验收证据仅保存在忽略的 `.runtime/deployment-evidence/`，不把用户数据、SQLite、日志或大型研究文件提交。最终实际Git提交、Render部署ID与公网结论待完成后在本报告更新。
