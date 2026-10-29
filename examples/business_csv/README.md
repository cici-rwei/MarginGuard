# 企业每日销量 CSV 模板与完整流程演示

- `template.csv` 只有表头，供填写；空模板本身不能预测。
- `synthetic_multi_series.csv` 提供三个**人工合成**商品—门店序列，用于切换与草稿隔离验收；详情见下表。
- `synthetic_84_days.csv` 是**明确人工构造的合成样本**，不是 Walmart、ABS 或真实企业记录。固定周模式仅用于接口、演示和测试，不代表真实预测准确率。

## 浏览器体验

从 MarginGuard 项目根目录运行 `./start.command`，然后打开 **http://127.0.0.1:5050/?mode=business**：

1. 选择 `synthetic_84_days.csv`。
2. 选择 **AUD** 或 **USD**，确认经营时区、统一税额口径、销售数量定义和数据使用权限。一个数据集只使用一个币种，无汇率转换。
3. 点击 **Validate CSV**，检查缺失情况、价格/成本覆盖、记录预览及连续日期区间。
4. 确认所选历史，再进入 Forecast → Inventory → Financial Decision Lab。
5. 完成后可点击 **Delete uploaded data** 删除临时数据。默认待确认数据保留 15 分钟；会话在空闲 30 分钟或创建 2 小时后失效，不提供长期保管或账户恢复。

不需要 M5 文件即可运行这个流程；页面会标注 **User-uploaded data · Source not independently verified**，不会将合成文件命名为 Walmart Demo。ABS 市场页面也可以单独打开。

样本商品为 `SYNTHETIC_SKU_001`、门店为 `SYNTHETIC_STORE_A`；连续 84 天，2024-01-01 至 2024-03-24。每周销量循环 `[0, 4, 6, 8, 5, 12, 7]`。零销量日的价格、成本留空；其他日的 `14.50 / 8.20` 也是人工参考，不是未来售价或采购报价。选择全部历史时，未来区间为 **2024-03-25 至 2024-04-07**，不是当前日期预测。

## 多商品、多门店切换样本

`synthetic_multi_series.csv` 的三个组合各有 2024-01-01 至 2024-03-24 的 84 个连续日期；全部数值均由人工构造，没有真实企业来源。

| 商品 | 门店 | 每日销量 | 人工单位价格 / 成本 |
|---|---|---:|---:|
| SYNTHETIC_SKU_A | SYNTHETIC_STORE_1 | 3 | 10.00 / 4.00 |
| SYNTHETIC_SKU_A | SYNTHETIC_STORE_2 | 7 | 10.00 / 4.00 |
| SYNTHETIC_SKU_B | SYNTHETIC_STORE_1 | 11 | 10.00 / 4.00 |

上传时仍须**独立选择 AUD 或 USD**；CSV 数字本身不确定币种，也不发生换汇。确认全部三个组合后，可以切换同一商品的不同门店、再切换商品，检查 Python 结果是否更新以及草稿是否隔离。固定销量的测试结构只便于核对软件行为，不代表现实需求模型的表现。

## 可输入的合成经营假设

以下数值仅为操作演示，**不属于 CSV 中已观察的库存或真实企业数据**。选择 AUD 时金额均为 AUD，选择 USD 时均为 USD；这不是把两种货币换算为相同价值。

Inventory & Risk 可填写：

| 参数 | 演示假设 |
|---|---:|
| Current Stock | 30 |
| Supplier Lead Time | 3 |
| Safety Stock | 10 |
| On-order Units | 0 |
| Excess Cover Threshold | 30 |

选择 **Use explicitly hypothetical stock at 2024-03-24**，再计算。进入 Financial Decision Lab 后可通过 **Use inventory assumptions** 和 **Use suggested quantity** 查看待转移字段，再决定是否应用。它们不会未经确认覆盖已有财务输入。

财务演示可使用以下假设（也可以自行修改）：

| 参数 | 演示假设 |
|---|---:|
| Current Stock | 30 |
| Selling Price | 14.50 |
| Existing Inventory Cost | 8.20 |
| New Purchase Cost | 7.50 |
| Order Quantity | 60 |
| Freight Cost | 12 |
| Other Procurement Costs | 0 |
| MOQ | 20 |
| Supplier Lead Time | 3 |
| Discount Percentage | 10 |
| Assumed Demand Uplift | 20 |
| Procurement Budget | 500 |
| Maximum Unmet Demand | 留空（未设置额外服务约束） |
| Existing On-order Units | 0 |

库存日期同样选择明确的历史原点假设。点击 **Run Simulation**，由 Python 计算三策略结果；本说明不预先写死 KPI 或保证推荐哪一种。新采购量与库存建议量可以不同，比较只针对用户实际输入的三种策略。历史成本如需引用，应分别确认现有库存和新采购成本，不自动同时填入。

输入草稿仅保留在当前标签页，并按数据集、版本、序列、预测原点及币种隔离。返回页面后，完整草稿会重新请求 Python 计算。Reset 清除当前上下文草稿；换币种需要用新的明确声明重新上传，不能仅更改金额标签。

## CSV 格式与校验

```csv
Date,Product,Store,Units Sold,Unit Price,Unit Cost
2024-01-01,SYNTHETIC_SKU_001,SYNTHETIC_STORE_A,0,,
2024-01-02,SYNTHETIC_SKU_001,SYNTHETIC_STORE_A,4,14.50,8.20
```

上面两行只是字段说明，**不足以预测**；请使用随附 84 天文件或自己的合格历史。

- 必需表头：Date、Product、Store、Units Sold；Unit Price、Unit Cost 可选。
- 支持 UTF-8 / UTF-8 BOM；日期严格为 `YYYY-MM-DD`。按商品—门店—日汇总，一日一行，重复记录不会自动相加。
- 销量是非负整数字面量，如 `3`，不接受 `3.0` 或负销量。空白销量是未知；显式 `0` 才是零销量，缺失日期不会补零。
- 当前不支持退货或净销量。用户必须确认销量与退货分开；系统不能仅凭正数证明来源及业务含义。
- 金额为非负十进制，最多六位小数，允许空白；空白价格/成本不变成零。
- 至少 42 个连续有效日，84 天以上推荐。缺口两侧不能直接连接，可明确选择其中合格连续区间。
- 仅接受经营时区内已结束的日期；未来/当日未完成的记录不能当成完整历史。
- 上限为 5 MiB、50,000 行、100 个商品—门店组合；每组日期跨度最多 1,096 天。

当前库存、交货期、安全库存可以通过独立库存 CSV 提供，也保留单品手动输入；MOQ、运费、采购预算及需求增长仍是财务页假设，不混入销量 CSV。一个数据集的金额须采用同一币种与税额口径；页面不做汇率换算、税务计算或真实库存验证。

## 双文件批量库存演示

先上传 `synthetic_multi_series.csv` 并确认全部三组84天历史，再展开库存面板上传 `synthetic_inventory_multi_series.csv`。两个文件都是明确构造的合成数据，不是任何真实企业的销售或库存。使用30天过剩覆盖阈值，结果为：

| 商品 / 门店 | 期末库存 | 未来14天需求 | 交货期需求 | 备用库存 | 建议额外补货 | 主分类 |
|---|---:|---:|---:|---:|---:|---|
| SYNTHETIC_SKU_A / SYNTHETIC_STORE_1 | 3 | 42 | 21 | 5 | 23 | Stockout Risk |
| SYNTHETIC_SKU_A / SYNTHETIC_STORE_2 | 70 | 98 | 49 | 10 | 0 | Sufficient Inventory |
| SYNTHETIC_SKU_B / SYNTHETIC_STORE_1 | 500 | 154 | 77 | 20 | 0 | Excess Inventory Attention |

库存日期均为2024-03-24，预测为2024-03-25至2024-04-07；交货时间7天、在途0。第二组“充足”只针对交货期需求及备用目标，不代表70件能覆盖全部98件的14天需求。

空白 `inventory_template.csv` 只含标题，可填写自己的库存记录。Product + Store 必须和销售文件精确一致；Stock As Of Date 必须是所选销售历史最后一天的期末库存。重复组合和非法非空值拒绝，缺失保留未知；不能把日期改成今天来代表当前实时风险。缺少 On-order Units 时，需要补充数据或明确声明没有在途订单。库存确认不覆盖销售文件。

上述5MiB/50,000行/100组合是本地默认；公开免费服务更严格：1MiB、销售10,000行、20组合、库存最多20行。销售和库存共用每会话10分钟3次上传额度；数据可能因过期或重启提前消失。详见根目录 README 与 BULK_INVENTORY_RISK_REPORT。

## 直接调用 Python 模块

网页之外，预测适配模块仍可独立运行。在项目根目录、已启动虚拟环境时执行：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from business_csv import load_business_csv
from business_forecast import analyse_business_series

dataset = load_business_csv(
    'examples/business_csv/synthetic_84_days.csv',
    currency='AUD', sales_basis='gross_units',
)
result = analyse_business_series(dataset, 'SYNTHETIC_SKU_001', 'SYNTHETIC_STORE_A')
print(dataset['report']['summary'])
print('Currency:', result['currency'])
print('Method:', result['analysis']['selected_method'])
print('MAE:', {name: values['mae'] for name, values in result['analysis']['backtest'].items()})
print('Forecast dates:', result['forecast_start'], result['forecast_end'])
print('Forecast units:', result['analysis']['total_forecast_demand'])
PY
```

该适配函数只返回预测，不调用财务模块；完整网页会在用户提供财务假设后调用独立的财务/策略 API。预测结果中的 `financial_analysis_available=False` 是这一模块边界，不代表当前网站尚未支持 AUD/USD 财务分析。

默认 `as_of_date` 为本机当天，只接受此前的完整日。直接 Python 调用时，如经营时区不同，可显式传入相应 Python date；网页根据上传声明的 IANA 时区确定截止日期，不擅自改变 CSV 的日期含义。

不要把真实企业 CSV 放入 examples、tests 或 Git 仓库；也不要上传客户、支付或其他个人信息。Python 本地读取可传入仓库外路径，并且不写回原文件。网页上传仅在仓库外私有临时存储处理，不能代替自己的原始数据备份。完整安全限制、运行方法和最终测试记录见项目 [README.md](../../README.md) 与 [FINAL_QA_REPORT.md](../../FINAL_QA_REPORT.md)。
