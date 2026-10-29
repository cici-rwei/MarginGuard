# MarginGuard 上线后用户验收与 CSV 开放评估

> **历史阶段记录：** 本报告保留首次上线后体验优化与 CSV 正式开放阶段的验收证据，对应下文 `091dd76` 等当时版本。文中的“当前”仅指该阶段，不代表最新应用状态。最新批量库存风险版本、部署与验收请阅读 [BULK_INVENTORY_RISK_REPORT.md](BULK_INVENTORY_RISK_REPORT.md)；此处的安全检查不能计作新一轮复验。

更新日期：2026-10-29（Australia/Sydney）。本报告区分本地测试、真实公网受控验收和正式公开开放；未完成项目不记为通过。

## 1. 当前部署与开放状态

| 项目 | 当前已核验状态 |
|---|---|
| 公网地址 | [MarginGuard](https://marginguard-lkno.onrender.com/)；继续使用原网址 |
| GitHub | 私有仓库 [cici-rwei/MarginGuard](https://github.com/cici-rwei/MarginGuard)，main，未新建项目或网站 |
| Part A | 已上线并完成真实 HTTPS、桌面及手机交互验收 |
| 当前应用提交 | `091dd76bec16f071d3d489ce5299780570d39fb2` |
| 当前 Render 部署 | `dep-dbh0go0piisc738dfjb0`，Live，已无 In progress；同提交首个成功部署为 `dep-dbh0gb59fdbs73d7sifg` |
| 当前 CI | [40707432916](https://github.com/cici-rwei/MarginGuard/actions/runs/40707432916)，success |
| Part B 受控测试 | 已完成125/125项合成数据检查；受控门禁现已关闭 |
| 正式公开 CSV 上传 | **已正式开放受限临时CSV分析**；`ENABLE_BUSINESS_UPLOAD=true`；无需验收凭证，最终公开API与两套浏览器复验通过 |
| 本轮真实HTTPS检查 | **189/189通过，失败0**：受控125项＋正式公开无凭证64项；不将这些检查与本地单元测试混计 |
| 继续公开的功能 | Synthetic Demo 四页流程及 ABS Market Intelligence |
| M5 | 公开展示和再分发许可仍未确认，继续关闭；本地文件保留 |

Part A 首次上线提交为 `ed5c2e3be8048387150aa30c9152454f3e8a8ee5`，对应成功 CI `40681261991`、Render 部署 `dep-dbgtsu29lscs73940870`。随后 `5236ac3` 加固容量，`b6198af` 在批准的窗口内开启受控验收，`23d8ca4b43fdb81fc5e15670f6a53d3b375ba9be` 修复运行任务租约并通过公网竞态检查。完成受控检查后，依照用户条件授权提交 `091dd76`：公开上传true、review=false、验收摘要清空、截止时间0，M5=false、Synthetic=true、Debug=false。该精确YAML的本地配置smoke通过，当前Render部署Live，公开无凭证API和浏览器已完成复验。网站没有升级付费套餐。

**验收结论：** 本轮发现的容量、跨会话限流和运行租约问题均已修复并完成对应验证；当前没有已发现但尚未解决的高风险开放阻塞。此结论限于已执行的检查，不替代独立安全审计或未执行的压力、资源及取证测试。

## 2. 已修复：Part A 用户体验

所有修改复用原五页和 Python 引擎，内部 API 字段、返回结构及预测/财务公式不变。

| 修复 | 对应文件 |
|---|---|
| 上传关闭时清楚显示 Temporarily unavailable、引导 Synthetic Demo；可用时自动恢复正常说明 | `templates/base.html`、`templates/_business_upload.html`、`static/js/business_upload.js` |
| 手机改为 Wait、Reorder、Discount 三张卡片；桌面保留完整表格；推荐、预算、最低采购量及不可行原因全部保留 | `templates/scenarios.html`、`static/css/style.css`、`static/js/main.js` |
| 显示库存与财务输入差异，例如 Current stock: 30 → 5；必须确认导入，取消不覆盖原值，输入变化使旧结果失效 | `templates/scenarios.html`、`static/js/main.js`、`static/js/business_context.js` |
| 手机缩短重复导航，较长数据来源、假设和草稿说明移入 Details，保留必要披露 | `templates/base.html`、`static/css/style.css` |
| 库存充足文案限定为交货期需求与备用库存；另外展示14天需求，不暗示已覆盖整个预测周期 | `templates/inventory.html`、`static/js/main.js` |
| 解释 Synthetic 周期模式产生零 MAE，不宣称真实业务预测完美 | `templates/dashboard.html`、`templates/forecasting.html` |
| Supplier Delivery Time、Backup Stock、Minimum Order Quantity、Average Forecast Error 等业务名称，以及单位、术语帮助、可操作的纠错提示 | 四页模板、`main.js`、`business_context.js`、`business_upload.js` |

**Part A 公网验证结果：**

- Part A首次上线时，五页及Synthetic/ABS API的10项HTTPS检查通过；当时M5和普通访客上传接口返回禁用结果。这是当时的安全开关检查，不代表当前已配置开放的上传状态。
- 390px 手机视口显示三张策略卡片，整页 scrollWidth 为390。默认收入435/1218/391.50、毛利润189/556.20/145.50保持与既有 Python 引擎一致。
- 采购量80时，采购现金612超过预算500，Reorder 不可行，推荐 Wait；该情景毛利润558.90仍按原引擎展示。采购量10时显示最低采购量失败及纠正建议。
- Inventory 输入5，展示交货期需求10、备用库存10、14天预测需求84。Financial Decision Lab 显示30→5差异；取消保留30，不自动替换采购量、价格或成本。
- Forecast 保留合成零误差解释；ABS 12个SVG、Experimental、参考期及单位完整。浏览器 Console 检查无 error/warn。
- 部分首次自动读取发生在异步响应完成前，等待结果完成后再复核；没有把旧的隐藏结果记为新计算证据。

## 3. 已修复：Part B 容量与受控验收准备

原上传 API、匿名会话、CSRF、owner+dataset 校验、事务、TTL、主动删除和后台清理已经存在，本轮没有重写 CSV 解析器或另建上传 API。

初次审计发现，旧公共候选允许两个计算槽、每个 Linux 子进程384 MiB，与512 MB免费实例和两个 Gunicorn worker 的 ABS 缓存不匹配；原每 owner 限流还可被新会话绕过。已进行以下增量加固：

| 文件 | 加固内容 |
|---|---|
| `runtime_config.py` | 公共容量固定上限，只可收紧，不能无界放大 |
| `business_store.py` | 跨 owner/worker 的事务全局限流；删除会话不重置全局窗口 |
| `business_service.py` | 单计算槽覆盖父进程编码、worker计算、响应解析及保存 |
| `business_worker.py` | 复用原解析器，校验公共行数/组合上限；Linux限额设置失败即拒绝；限制输出大小 |
| `business_api.py` | 在读取 multipart 前执行准入；返回当前限制；保留既有会话、CSRF及所有权机制 |
| `upload_review.py`、`app.py` | 默认关闭的短期验收授权，绑定 owner、凭证版本及期限 |
| `templates/_upload_review.html`、`static/js/upload_review.js`、`templates/base.html` | 明确受控入口，凭证不进入 URL、Web Storage 或普通业务表单 |
| `business_upload.js`、`business_context.js`、`templates/_business_upload.html` | 界面从服务器读取容量/TTL，缺少可信限制时不发送 CSV |

**验收发现的任务租约问题已修复并经公网验证：** 原 `delete_session` / `cleanup` 可能在worker仍运行时删除未到期租约，提前释放全局单槽。`23d8ca4` 保持原数据访问权立即撤销，同时保留运行租约至finally释放或租约到期。新增3项确定性回归。公网单次有界竞态实际撞中：A确认仍处理时删除会话204，A确认安全失败401；另一用户B得到429 processing_busy，之后恢复200。删除owner不能提前释放运行计算槽。

当前公共配置为：**1 MiB、10,000行、20个商品—门店组合、单数据集2 MiB、总规范化 payload 16 MiB、20个匿名会话、单计算槽、Linux计算子进程128 MiB**。本地模式原5 MiB/50,000行/100组合保留。临时数据库位于项目和静态目录之外；SQLite 与限流跨 Gunicorn worker 共用，不把用户文件写入 GitHub。

受控阶段只配置随机测试凭证的SHA-256摘要及UTC截止时间，原凭证不进Git、URL、日志或报告；通过既有 `GET /api/business/session` 交换绑定owner的短期授权。该阶段普通访客始终关闭。**正式开放配置已关闭review，并清空验收摘要和截止时间**；普通使用仍须先建立各自匿名会话，所有上传/计算/删除继续执行CSRF、所有权、容量和限流检查，不把验收密钥作为公开功能的前提。

## 4. 已验证通过：自动化与完整性

| 验证 | 实际结果及边界 |
|---|---|
| 完整本地 Python unittest | **348/348通过**，22.097秒，无失败、错误或跳过 |
| 原测试保留 | 原302项逻辑保留；新增46项：模板7、容量19（含租约3）、准入4、受控验收16 |
| Node 内置测试 | **29/29通过**；原14项保留，新增15项 |
| 租约修复CI Python | [40705253636](https://github.com/cici-rwei/MarginGuard/actions/runs/40705253636)：**329项实际通过，19项未执行**；日志为 `Ran 332 tests in 20.788s / OK (skipped=5)` |
| 租约修复CI Node | **29/29通过**，失败0、跳过0；后续公开配置CI40707432916亦success |
| 原测试文件 | 原tests目录22份文件在核验时哈希不变：20个Python测试文件、1个fixture、1个原JS测试文件；没有修改旧逻辑来绕过失败 |
| 核心与数据保护 | 部署前基线中的28份核心/数据文件 SHA-256 全部一致 |
| 部署清单 | 核验时119个Git跟踪文件与manifest一致；118个内容哈希匹配，清单自身为null；已按最终文档刷新清单 |

CI 的5个 skip 记录不是只缺5个方法：3个单方法跳过为两个原 ABS Excel 检查、一个真实 M5 衔接检查；两个 setUpClass 跳过分别涉及 RealDataTests 的4个方法和 WebTests 的12个方法。总计19个方法未执行，329＋19＝348。受限 M5 与原 ABS 工作簿不进入部署仓库，不能把这些跳过写成通过。

本轮新增模板测试曾随动态服务器限制改为验证动态契约，并新增 Node 用例验证真实限制及缺失时拒绝发送；原22份测试文件没有修改来绕过失败。此前309/24、345/29均为较早阶段快照，最终完整本地结果以348/29为准。

**本地容量与清理补充证据：**

- 旧配置的50,000行/4,000,052字节合成CSV上传201；warm ABS父进程峰值161.23 MiB、child95.34 MiB。
- 新公共配置10,000行/20组合/800,052字节上传及确认201；父进程峰值119.14→132.23 MiB、child35.83 MiB，耗时0.237/0.149秒。
- 本地 TTL 到期读取401；cleanup 后会话/数据/速率/任务记录为0，SQLite中合成marker消失，无 journal 残留，保留40,960字节空DB。

以上是 Mac 和本地应用层证据，**不是 Render Linux 总实例并发峰值，也不是云介质取证级擦除证明**。

## 5. 已验证通过：Render HTTPS API

本轮只使用明确合成CSV，真实HTTPS检查合计 **189/189通过、0失败**。其中受控阶段 **125/125通过**：主流程96项、删除竞态18项、限流恢复5项、会话及响应头6项。计数来自以下未包含原始CSV行、凭证、Cookie或CSRF值的本地证据：

| 本地证据文件 | 通过数 | 范围 |
|---|---:|---|
| `.runtime/deployment-evidence/upload-api-results.json` | 96 | 受控时匿名访客仍关闭；AUD/USD完整业务链、隔离、容量、真实30分钟到期及Render重启 |
| `.runtime/deployment-evidence/upload-api-delete-race.json` | 18 | A确认中删除会话、B计算拒绝与恢复；运行租约不因owner撤销而提前释放 |
| `.runtime/deployment-evidence/upload-api-rate-recovery.json` | 5 | 限流窗口后重新建立受控会话、上传、质量检查、确认及删除恢复 |
| `.runtime/deployment-evidence/upload-api-session-headers.json` | 6 | 有效HTTPS、Secure/HttpOnly/SameSite=Lax Cookie、no-store、凭证不在响应、摘要不可替代原凭证、删除会话 |

已核验的安全边界：

- 两个独立 API 会话的 AUD/USD 分析与原 Python 预测、库存及财务引擎输出一致；USD 数据包含多个商品—门店组合。
- 跨 owner 的 GET、POST、DELETE 不可访问别人的数据；错误 CSRF、外部 Origin、重复JSON字段、任意服务器路径和模板路径参数均拒绝。
- 超过公共1 MiB的文件拒绝；重复数据拒绝且错误不回显原始销售行。
- 主动删除后旧dataset ID不可访问；重新上传后旧ID仍不可访问。
- 两个并发计算实际观察到 **429和200**；拒绝原因为processing_busy；后续计算恢复200。
- 10,000行/20组合的公共最大配置合成样本在真实Render上传和确认成功。
- C会话经历真实30分钟到期后，旧授权请求503；重新明确建立新owner时没有活动数据，旧dataset返回404。这个结果证明逻辑访问失效，不等于物理擦除。
- Render Events记录Sydney 2026-10-29 01:29及01:31的两次服务重启。D会话重启后旧授权503，新owner没有活动数据，旧dataset404；Synthetic和ABS仍200。没有将本机模拟重启冒充云端结果。
- `23d8ca4` 的删除竞态在真实公网单次有界试验中观察到删除204、旧确认401、其他用户429 processing_busy，随后200恢复，验证未到期运行租约不被owner删除提前释放。
- 全局上传限流触发后，新 Cookie 不能绕过；窗口后上传、确认恢复。受控压力检查前后 Synthetic 和 ABS API 都正常，普通访客上传仍关闭。
- Render 应用日志已作屏幕抽查，显示状态码与耗时，没有看到 CSV 明细、私有路径或 Cookie；最近一小时的ERROR查询未检索到匹配项。此抽查不能替代所有平台日志的完整取证审计。

正式开放后的独立无凭证检查另有 **64/64通过，失败0**：

| 本地证据文件 | 通过数 | 范围 |
|---|---:|---|
| `.runtime/deployment-evidence/upload-api-public-final.json` | 51 | 普通匿名AUD/USD会话、上传/质量/确认/预测/库存/财务、原引擎一致性、双向隔离、CSRF、删除、五页及Synthetic/ABS回归；不发送review key |
| `.runtime/deployment-evidence/upload-api-public-limits.json` | 13 | 公开后foreign Origin、重复JSON、任意路径、超过1 MiB拒绝；失败后原dataset仍可正常分析，随后主动删除 |

公开features、容量与Cookie保护正确；受控review表单及提示不再出现。两个普通会话不能读取或删除对方dataset；各自删除后旧ID不可访问。受控125项和公开64项分别记录，合计189项；**不据此宣称所有资源耗尽、worker超时或底层存储清理路径都已验证**。

## 6. 已验证通过：两套独立浏览器与手机视口

受控阶段已完成IAB的AUD84行完整分析、Safari的USD252行3组合上传/确认/预测及42→98门店切换；双向dataset隔离、390px视口上传/确认/删除和局部质量表滚动均通过，测试dataset已主动删除。

正式开放后，又在同一Render HTTPS地址以**不提供review key的普通匿名会话**实际操作：

| 浏览器/场景 | 正式公开后的实际结果 |
|---|---|
| In-app browser，390px视口，AUD | 84行合成CSV上传、质量报告和确认通过；预测页历史/回测/未来3个SVG加载；库存输入30、Supplier Delivery Time 3天、Backup Stock 10单位并计算 |
| 参数贯通与财务 | 明确确认后导入库存假设；Financial Decision Lab显示三张手机策略卡片。Reorder收入AUD1,218、毛利润556.20、采购现金462、期末库存6，与Python输出一致 |
| Safari，USD | 252行、3个商品—门店组合上传、确认和预测通过，所选组合14天预测42单位 |
| 双向浏览器隔离 | 分别替换为对方dataset页面均显示不可用，不泄漏对方数据；返回自己的dataset后可以恢复分析 |
| 实际繁忙错误与重试 | IAB确认时真实遇到processing_busy，页面给出明确错误，所选范围和输入保留；再次点击Confirm成功。此项是繁忙拒绝恢复，不是worker超时试验 |
| 主动删除 | 两浏览器的公开测试dataset均通过确认删除操作移除 |
| 版面与入口 | 无review key要求或review提示；390px无整页横向溢出，宽质量表只在自身容器内横滚 |

最终公开回归也确认ABS的12个SVG、Experimental及AUD标注完整、Console无error/warn；Synthetic首页展示504历史单位、84预测单位及正确来源标签。受控凭证已从本机临时文件移除，临时5051验收服务与本轮创建的测试标签页已关闭，用户原5050服务保留。

截图保存在忽略目录 `.runtime/deployment-evidence/uat-public-upload-strategy-cards.png`，不加入Git或部署包。所有浏览器操作均在真实Render HTTPS完成；不以HTTP 200、test client或脚本Cookie Jar代替。390px是桌面浏览器的手机视口，不是真实手机设备实测。来源、币种、假设、显式导入确认及短期保存限制保留。

## 7. 尚未验证 / 暂未开放

| 项目 | 当前状态 |
|---|---|
| Render真实worker计算超时及其浏览器恢复 | 尚未执行可重复的真实超时试验；已验证的429恢复不等于worker超时恢复 |
| Render总实例RSS及CPU实际峰值 | 未验证；控制台方案显示512 MB/0.15 CPU，应用CPU/内存实测指标提示升级才可查看，没有付费升级 |
| Render磁盘实际余量及取证级物理清理 | 未验证；逻辑失效、删除和重启后不可访问不等于底层介质擦除，也不新增任意文件/调试读取端点 |
| 全手机设备兼容性 | 仅完成390px视口检查；不宣称已覆盖真实手机型号或所有浏览器 |
| 暂未开放：M5公开展示 | 许可问题仍未解决；保持关闭，不因CSV开放而改变 |

C真实到期、D云端重启、运行租约竞态，以及正式公开后的无凭证API和双浏览器复验均已完成，记录在“已验证通过”。CSV正式开放；本节仅列仍未测试的边界及继续关闭的M5，不以公开入口可用代替这些验证。

## 8. 已知限制

- 当前公开Free服务是作品集与短期分析工具，不适合保存长期敏感商业数据。Render Free会休眠，重启、部署或休眠可能使临时数据提前丢失；没有长期保存、账户恢复、常驻或企业SLA承诺。关闭浏览器标签页不是清理机制。[Render Free官方说明](https://render.com/docs/free)
- 全局限流使用固定窗口，边界允许突发；单计算槽限制并发。已经验证新会话无法绕过全局上传限流，但不能保证抵御所有恶意流量或DoS。
- SQLite规范化payload上限不等于整盘上限，journal、运行环境和平台日志仍占空间。应用删除与读权限失效不等于云存储介质的取证级擦除。
- Render上的最大配置样本、并发拒绝和恢复已经通过；没有读取到完整总RSS/CPU指标，不能将Mac单进程测量当作512 MB云实例容量保证。
- 手机质量表为局部横向滚动；目前不是所有真实手机型号及浏览器版本的兼容认证。
- Synthetic只是教学演示，ABS是已有快照，二者不验证真实企业数据来源，也不用于改变M5商品预测。

## 9. 更新与回滚

继续使用现有 GitHub → CI → Render After CI Checks Pass 流程。每次改动先运行测试、审查白名单和暂存区，普通提交推送；不用force push。后续仅报告/README/清单提交受既有构建过滤规则控制，不触发应用部署，不应被误写为新的运行版本。线上应用保持 `091dd76bec16f071d3d489ce5299780570d39fb2`，部署 `dep-dbh0go0piisc738dfjb0`。

**发现上传安全问题时，首选关闭功能，不先降级容量防护：**

1. 将公开上传和受控门禁都关闭，撤销临时验收入口，保留 Synthetic 和 ABS。
2. 核实匿名及旧验收会话无法再调用上传接口，检查真实公网五页/API。
3. 如必须回滚代码，优先保留已验证的容量、全局限流及 `23d8ca4` 租约修复，再显式关闭公开上传及review。不要仅恢复旧受控配置而遗留访问权限。`5236ac3` 早于租约修复，只能作为**上传关闭**时的候选回退。
4. `ed5c2e3`、`b626d07` 是此前稳定展示版本，但不具备本轮全部公共上传容量加固；**不得回滚到这些旧配置后直接开启上传**。
5. Render控制台回滚可能关闭自动部署；恢复稳定后核对配置，再决定是否恢复 After CI Checks Pass。也可用 `git revert` 创建可审查的回退提交并测试后推送。[Render回滚说明](https://render.com/docs/rollbacks)

不得把原始M5、企业CSV、SQLite、原验收凭证、Cookie、密钥、日志或临时证据加入GitHub/部署包。报告更新后已同步刷新manifest；报告中的119文件为核验时的冻结清单计数，不用固定旧字节数代表后续文档版本。

## 10. 需要用户操作的事项

本轮不需要新增账号授权、密钥或支付操作。用户可以直接打开 [MarginGuard](https://marginguard-lkno.onrender.com/) 或 [Analyse My Business](https://marginguard-lkno.onrender.com/?mode=business) 检查；无需安装Python或保持Mac/Codex运行。

本次公开目标已完成，等待用户检查线上效果。后续若需要长期保存、敏感商业数据处理、更多并发或压力验收，应另行规划存储、权限和运行资源；付费升级及扩大权限须先取得确认。Free版本继续作为作品集与短期分析工具，不承诺企业SLA。未验证事项保留原状态，没有因开放按钮而改写为通过。
