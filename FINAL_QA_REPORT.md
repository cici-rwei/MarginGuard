# MarginGuard 最终 QA 与交付状态

验收日期：2026-10-28（Australia/Sydney）。现有 `outputs/MarginGuard` 内继续开发；没有新建长期项目副本。**本地功能与部署准备完成；未公开部署，课程合规结论仍待正式要求。**

## 1. 自动化测试：已通过

| 测试组 | 数量 | 结果 |
|---|---:|---|
| 原Phase1–5A测试 | 193 | 全部保留、通过 |
| 企业API与私有存储 | 45 | 通过 |
| AUD/USD | 14 | 通过 |
| 新页面契约 | 4 | 通过 |
| 公开配置与日志保护 | 11 | 通过 |
| 白名单打包 | 11 | 通过 |
| **完整Python unittest** | **278** | **0失败、0错误、0跳过，9.568秒** |
| JavaScript输入草稿 | 12 | 0失败、0跳过 |

执行：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v`；`node --test tests/business_context.test.js`。本地Python3.9.6、Flask3.1.2，ABS测试依赖Pandas2.2.3/openpyxl3.1.5。Node仅测试工具，网站无Node运行依赖。JS语法检查、两个venv的 `pip check` 均通过。

本轮开始先跑原193项，3.459秒通过。最终新增85项Python测试，没有删除或改写原有测试。集成时发现并修复了一个新测试使用Python3.10才有的assertNoLogs问题，改为3.9兼容且更严格的日志handle断言后重新执行全套。中途失败不计为最终通过，最终结果如上。

## 2. 浏览器实际执行：已通过

使用本机内置浏览器与真实HTTP服务，既有M5和明确合成CSV。没有使用固定数字替代后端计算。

| 操作 | 实际观察 |
|---|---|
| 五条页面路由 | Overview、Forecast、Inventory、Decision Lab、Market均打开；导航及源上下文正常 |
| 上传/审核/确认 | AUD 84日合成CSV返回84记录、12显式零日；确认后历史504单位，未来84单位；初始库存Not assessed |
| 回测/未来隔离 | 2024-03-11至03-24回测，与03-25至04-07未来图分开；MAE分别约2.57和0 |
| 库存输入 | 库存20→0使状态Sufficient→Stockout，建议量0→9；结果由Python计算 |
| 财务输入 | 采购20时Reorder收入580/毛利润251/现金165 AUD；采购30时现金245超预算，推荐Wait |
| 折扣输入 | 折扣10%→20%，Discount收入261→232、毛利润97→68、毛利率37.16%→29.31% |
| 在途订单 | 输入10后没有确认排除则不显示结果；明确确认后显示该独立情景排除存量及成本的限制 |
| 参数贯通 | 库存→财务需显式确认采用；采购30及折扣20跨页/刷新保留并Python重算；修改输入立即隐藏旧结果 |
| 建议采购量 | Python重算后先显示order_quantity=9的确认，再应用；不称全局最优 |
| 重置 | 当前上下文库存/财务草稿清空，上传输入回空白 |
| 替换/隔离 | 新USD三组合数据替换旧AUD，财务输入不继承；组合未来总量42、98、154随商品与门店切换 |
| 删除 | 删除本次合成临时数据后返回空上传入口，无旧分析 |
| Demo回归 | 原M5默认及切换商品的销量/MAE/未来结果正常；USD财务表与建议可计算 |
| ABS回归 | 月份改2026-07、Original后值/同比改变；VIC州、Household goods行业及New entrants cohort切换正常 |
| ABS口径 | Experimental、AUD、参考期、来源、Original/Seasonally Adjusted等标识保留；未插入商品KPI |
| 手机与图表 | 390×844视口Overview宽度=scrollWidth=390；SVG存在，桌面表格与决策截图已目视检查 |
| 浏览器Console | 上述正常流程未观察到error/warn；未做跨所有浏览器的兼容性认证 |

代表性截图：`screenshots/synthetic_aud_decision.png`、`synthetic_mobile_overview.png`、`abs_market_overview.png`。只包含合成经营案例或ABS公开汇总，不把私有上传/原M5逐日截图打包。

浏览器自动化在快速确认后曾读取到更新前的隐藏DOM；等待新状态后观察到正确新数据。该工具时序错误没有被记为产品故障或跳过数据验证。全部金额例子仅用于测试，完整假设见 `PHASE5C_REPORT.md`。

## 3. API、安全与数据：已通过及证据边界

API测试实际覆盖上传、确认、目录、forecast模块一致性、库存/财务、删除，41/42天边界、缺日与零、非有限值与负数、非法字段、重复JSON键、AUD/USD冲突、跨owner、伪造cookie、CSRF、密钥轮换、多worker、TTL、并发槽、配额与限流。5 MiB+、50,001行、101组合实际拒绝；正常约100 KiB上传通过。真实子进程超时后验证已退出、管道关闭且计算槽释放。

本轮前后SHA-256比较的84个既有文件：**72个未变、12个授权文件修改、0个丢失**。其中20个既有data文件（含原始/处理后M5、ABS轻量快照）全部未变；`forecast.py`、`inventory.py`、Phase5A解析/适配、ABS模块和原测试未变。`finance.py`/`scenario.py`只进行批准的向后兼容币种扩展及预算状态元数据；原公式和M5数值由原回归验证。

修改既有文件：`app.py`、`finance.py`、`scenario.py`、`.gitignore`、`README.md`、`examples/business_csv/README.md`、`static/css/style.css`、`static/js/main.js`、`templates/base.html`、`dashboard.html`、`inventory.html`、`scenarios.html`。新增文件详见三个阶段报告、部署报告及最终包MANIFEST。

## 4. 干净交付环境验收：已通过，明确跳过

将当前白名单文件只读复制到系统TemporaryDirectory，未包含M5或私有数据，使用本机已装依赖的Python3.9环境运行。无持久新项目副本，测试后临时目录删除。

unittest输出 **Ran 262 tests，OK (skipped=5)，7.255秒**。细分：**259个测试方法实际通过**；3个单项跳过（2个原ABS工作簿检查、1个Phase2真实M5衔接），另两个M5测试类在setUpClass跳过，其16个方法没有执行；这两个类的skip事件计入skipped但不计入testsRun。278−19=259，不将跳过写成通过。

干净环境五页200、ABS catalog200；M5 catalog明确503及Restore说明。实际用test client上传/确认合成多组合CSV，三组各84日，未来42/98/154；删除204。这证明无需原始大数据即可体验上传全流程及ABS，但不表示ZIP自带M5完整演示。

最终包由 `scripts/package_final.py` 显式白名单创建，包含源码、全部测试、文档、生产配置、ABS六份轻量文件、合成CSV和截图。排除所有原/处理后M5记录及派生预测、历史M5数值报告、用户上传、SQLite、密钥、日志、虚拟环境、缓存、研究下载和旧ZIP；保留空data/raw目录用于合法恢复。脚本拒绝覆盖现有ZIP，逐文件SHA-256/CRC校验并验证源文件未改变。实际归档清单与哈希以包内MANIFEST及交付时校验结果为准。

## 5. 部署准备：已通过本地验证，未公开发布

Python3.12.14 + Flask3.1.2 + Gunicorn26.2.0 在本机回环5051实际启动；ABS页面/API200，公开模式下上传及M5接口均按默认开关503。浏览器验证了图表与禁用原因。代码不将密钥写死，Debug关闭，生产日志不记录URL/正文/cookie。

**没有公网地址，没有HTTPS实测。** 用户明确要求先完成准备；后续账号授权、M5许可、生产上传安全验收见 `DEPLOYMENT_REPORT.md`。本地HTTP成功不能写成公网部署完成。

## 6. 未通过、未验证与已知限制

### 未通过

当前最终自动化套件没有失败或错误；已执行的上述本地验收没有未解决的阻塞性功能故障。下列未执行或缺证项目不被归入“通过”。

### 未验证

- Render真实构建/HTTPS、云端Linux内存限制、主机级负载与磁盘配额、入口反滥用、生产重启及日志保留政策。
- 实际连续等待30分钟/2小时的浏览器会话过期；TTL已通过可控时钟API测试，浏览器清理逻辑已有测试和代码检查。
- Safari/Firefox、真实iOS/Android、全屏幕尺寸/辅助技术的完整可访问性测试；本轮是桌面浏览器与390像素视口。
- M5公开展示、处理后数据或派生数据再分发许可；因此不随包并默认关闭公开访问。
- COMP9001正式rubric、至少两个Advanced Topics认可、AI使用规则及最终课程格式。材料是待学生核对的草稿，未提交Ed/Padlet。

### 已知限制

- 临时匿名演示不等于企业账户系统；同cookie共享owner，标签页草稿仅便利保存。服务重启/临时盘丢失可使数据不可恢复。
- 每owner限流不能防反复新建cookie身份；生产上传保持关闭。Linux384 MiB限制代码未在本Mac实际执行；需要主机总内存/磁盘保护。
- 删除是应用级删除；不承诺云备份/存储介质取证级擦除。所有计算结果均是条件预测，不作真实采购保证。
- 只支持每日非负gross units；退货、交易级聚合、税务、持有费用、预测区间、全局数量优化和已有在途成本层未实现。
- AUD/USD无FX，无混币汇总；ABS行业指标保持独立。合成案例0 MAE不代表真实泛化能力。

## 7. 阶段状态

Phase5B、Phase5C与Restructure B已完成并本地验收；Final QA已执行。部署配置与课程交付材料已准备，实际发布和正式课程合规审查等待用户提供账号授权/官方材料。原项目及数据保留，不自动开始新阶段。
