# MarginGuard 批量库存风险升级报告

日期：2026-10-29。批量库存功能已部署到既有 Render 免费服务，并完成本地测试、公网 HTTPS 检查和实际浏览器验收。本文分别记录各环境的证据，不将本地通过当成公网通过。

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

最终完整本地 Python：453/453通过（最终复跑39.579秒），原348项保留，新增105项；JavaScript：51/51通过，原29项保留，新增22项。原始测试未删改逻辑。生产依赖 pip check 通过。28个受保护核心及数据文件SHA-256与升级前一致。

本地实际 HTTP：92/92检查通过，明确合成数据；最大20组合/1680条销售与20条库存整个流程约0.347秒（本地时间，不代表Render性能）。三组验收会话删除成功。

本地浏览器已检查：销售三组合确认、库存预览/确认、KPI 1缺货/1过剩/1充足、风险筛选、商品准确跳转、财务导入前差异及预算保留；390×844视口无横向溢出、风险卡片可读。B商品财务实跑在价格10、成本4、折扣10%、提升20%、预算200等明确假设下，三策略毛利均AUD924，原平手规则推荐Wait；这说明初步Review Discount Strategy没有被冒充财务最终推荐。

### 公网 API 验收

2026-10-29 06:02:44–06:03:23 UTC，在真实 HTTPS 地址完成 **92/92检查**：64个HTTP响应检查与28个内容/数值断言，不是92次API请求。全程使用明确合成数据。

- 销售确认、库存预览/确认、批量与单品原引擎数值一致、AUD/USD分别计算通过。
- 错期快照保持Not assessed，待确认数据不改变当前风险；旧版本409、非法查询400、错误CSRF403、超过1MiB文件413及恢复通过。
- 独立CookieJar客户A/B验证：B不能读取、上传、确认或删除A的库存，A不能读取B的风险清单，返回404；不把两套HTTP客户端称为两个浏览器。
- 20组合、1680销售行与20库存行端到端流程耗时 **6.054秒**，包含网络往返；整轮39.464秒。单次成功不等于负载基准或免费实例容量保证。
- 三个API测试数据集和会话均删除成功，旧风险与预测链接不可访问。删除销售级联库存草稿的专项检查在本地通过，未把其称为公网物理擦除验证。
- Synthetic Demo与ABS API正常；公开上传开启，M5公开模式仍关闭。

### 真实浏览器验收

在同一公网地址实际操作五个页面、销售上传、库存文件选择/验证/确认、风险筛选、门店筛选、商品搜索、需求排序与单品跳转。只上传销售先显示3个预测、3个库存未评估；确认配套库存后变成1缺货、1过剩、1充足、0缺失。筛选只改变清单，不改变全数据KPI。

手机视口390×844完成库存上传及确认，风险卡片和计算详情可读，没有页面横向溢出；这是浏览器视口测试，不是实体手机测试。桌面检查五页；市场页12个SVG图表正常，Experimental与AUD声明仍在。切换门店后不会沿用另一门店库存；库存/采购量分别审阅与确认，已填预算保留。验收中一次同名按钮定位未命中目标，改用准确控件后复验通过，没有因此修改公式或绕过确认。

公网合成A商品/门店1：当前库存3、交货7天、备用5、在途0；预测14天42件、交货期21件、建议额外补货23件。用户确认将23作为情景采购量，再分别采用售价AUD10、已有/新采购单位成本AUD4、运费及其他费用0、MOQ5、折扣10%、假设需求提升20%、预算AUD200：

| 策略 | 收入 AUD | 毛利润 AUD | 期末库存 件 | 采购现金 AUD | 可行性 |
|---|---:|---:|---:|---:|---|
| Wait | 30 | 18 | 0 | 0 | 可行 |
| Reorder | 240 | 144 | 2 | 92 | 可行、被推荐 |
| Discount | 27 | 15 | 0 | 0 | 可行 |

Reorder到第8天才可卖新货，仍有18件未满足需求；推荐依据是本次三个可行情景中毛利润最高，不声称23件是最优订货量。最后通过页面删除自己的合成测试数据，返回空上传入口；未删除用户数据。

### GitHub与Render

- 私有仓库仍为 `cici-rwei/MarginGuard`，没有更改可见性。
- 主功能提交：`4d5cce2c667989117e16c4a81b5045f1777be287`。
- [GitHub CI 40826559540](https://github.com/cici-rwei/MarginGuard/actions/runs/40826559540)通过：Python3.12.14，**434项实际通过、19项因受限M5/可选原始ABS文件未上传而未执行**；日志汇总为Ran437 / skipped5（含两个类级跳过）。Node51/51通过，依赖检查正常。
- Render原服务 `srv-dbgr9e7f3r2c73afsic0`，部署 `dep-dbhe24lckfvc73f9hdg0` 已在控制台显示Live；公网验收针对该主功能版本。
- 地址：[MarginGuard](https://marginguard-lkno.onrender.com/)，上传入口：[Analyse My Business](https://marginguard-lkno.onrender.com/?mode=business)。Python/Gunicorn及免费套餐配置未改动；继续使用CI通过后自动部署。
- 后续仅补充主风险分类解释及验收文档；最终部署记录见本报告末尾。审计后的部署清单包含133个文件，没有用户CSV、私有SQLite、密钥、日志、M5记录或大型研究数据。

## 8. 已知限制与回滚

- 没有自动连接POS/ERP；库存和采购参数由用户提供，来源未独立核实。
- 日期不一致不自动修复；需要对应时点库存或明确的单品假设。
- 没有订单到货日明细、多商品联合预算优化、预测区间不确定性或长期保存。
- 每个组合独立判断，初步建议未经财务约束验证；业务判断仍需用户确认。
- 压力耗尽、真实手机硬件、Render底层物理擦除不能由功能测试保证；不以固定限流代替完整DDoS防护。
- 本轮未在公网强制重启、等待完整TTL、触发内存/磁盘耗尽或并发版本冲突；对应TTL、容量拒绝、worker超时及并发冲突有本地自动化证据。以前阶段的部署/重启结果仍是历史证据，不冒充本轮测试。浏览器后续遇到临时数据不可用时明确拒绝并需重新上传，不能据此判断底层清理原因。
- 此前稳定应用提交为 `091dd76bec16f071d3d489ce5299780570d39fb2`。如新版本出现问题，可在同一Render服务回滚到该部署，或通过测试后的git revert与原GitHub→Render CI流程恢复。回滚可能使临时会话丢失，不能恢复已删除上传。

验收证据仅保存在忽略的 `.runtime/deployment-evidence/`，不把用户数据、SQLite、日志或大型研究文件提交。现阶段无需要用户购买服务或提供凭据的步骤；按销售模板及库存模板顺序上传即可试用。超出20组合、需要长期保存或到货明细的业务需后续设计，不能通过放宽生产限制绕过。

## 9. 最终上线确认

在主功能验收后，提交 `36dfb6933bdf3b9974eb27b06583c1c2c7e8a442` 仅补充总览中“主分类互斥、原始警告可重叠”的解释，并更新说明及报告；预测、库存、财务、上传API和资源配置与92项公网验收时相同。

- [CI 40831706370](https://github.com/cici-rwei/MarginGuard/actions/runs/40831706370)成功：Python实际434项通过、19项未执行，Node51/51通过，生产依赖无冲突。
- Render部署 `dep-dbheq7o473hc73cfvqp0` 已显示 **Live**，Last successfully deployed commit为上述36dfb69；仍为原Free服务和原HTTPS地址。
- 部署后补查 **10/10公网页面/API/静态资源**：五页、上传入口、功能开关、ABS目录API、库存风险JS及CSS均正常；页面包含新解释，JS/CSS哈希与本地一致。随后真实浏览器刷新，上传入口可用且无可见错误。
- 最后一次完整本地复跑453/453 Python、51/51 Node通过；28个受保护算法及数据文件哈希不变，原测试文件只有新增、没有删除或修改。
- 此节是上线后的文档补记，不改变运行代码；Render配置会忽略根目录Markdown及部署清单的纯文档提交，因此GitHub文档HEAD可以比运行提交更新。

本轮开发、测试、现有仓库推送和原站部署已完成。没有开启下一阶段功能，也没有升级付费套餐。
