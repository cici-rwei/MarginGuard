# MarginGuard 上线后用户验收与 CSV 开放评估

更新日期：2026-10-29（Australia/Sydney）。本报告区分本地测试、真实公网受控验收和正式公开开放；未完成项目不记为通过。

## 1. 当前部署与开放状态

| 项目 | 当前已核验状态 |
|---|---|
| 公网地址 | [MarginGuard](https://marginguard-lkno.onrender.com/)；继续使用原网址 |
| GitHub | 私有仓库 [cici-rwei/MarginGuard](https://github.com/cici-rwei/MarginGuard)，main，未新建项目或网站 |
| Part A | 已上线并完成真实 HTTPS、桌面及手机交互验收 |
| 当前应用提交 | `b6198afa45915db52891f6281c2ebd45782c4574` |
| 当前 Render 部署 | `dep-dbgvqjh42hec739e96t0`，Live；沿用同一提交的部署链 |
| 当前 CI | [40699769508](https://github.com/cici-rwei/MarginGuard/actions/runs/40699769508)，success |
| Part B 受控测试 | 已经用户批准，在同一 Render 服务开启短期合成数据验收窗口 |
| 正式公开 CSV 上传 | **尚未开放**；`ENABLE_BUSINESS_UPLOAD=false`；普通访客 features 仍为 false |
| 继续公开的功能 | Synthetic Demo 四页流程及 ABS Market Intelligence |
| M5 | 公开展示和再分发许可仍未确认，继续关闭；本地文件保留 |

Part A 首次上线提交为 `ed5c2e3be8048387150aa30c9152454f3e8a8ee5`，对应成功 CI `40681261991`、Render 部署 `dep-dbgtsu29lscs73940870`。随后 `5236ac3be331f6e6eb64c80355c7629482c1b1e1` 加固上传容量并准备默认关闭的验收门禁；当前 `b6198af` 仅在批准的窗口内开启受控验收。网站没有升级付费套餐。

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

- 五页及 Synthetic/ABS API 正常，10项 HTTPS 检查通过；M5 与普通访客上传接口仍返回明确禁用结果。
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

**验收中新发现、已本地修复：** `delete_session` / `cleanup` 可能在计算worker仍运行时删除其未到期job租约，提前释放全局单槽。连续新会话可能绕过预期并发约束。修复已立即撤销原数据访问权，同时保留运行租约至计算finally释放或租约到期。新增3项确定性回归；完整本地348/348通过（22.097秒），Node29/29通过；正在部署，公网复核尚未完成。

当前公共配置为：**1 MiB、10,000行、20个商品—门店组合、单数据集2 MiB、总规范化 payload 16 MiB、20个匿名会话、单计算槽、Linux计算子进程128 MiB**。本地模式原5 MiB/50,000行/100组合保留。临时数据库位于项目和静态目录之外；SQLite 与限流跨 Gunicorn worker 共用，不把用户文件写入 GitHub。

受控门禁不等于公开开放：服务端只配置一次性测试凭证的 SHA-256 摘要及 UTC 截止时间；原凭证不进 Git、URL、日志或报告。仅既有 `GET /api/business/session` 接受请求头交换，最长全局窗口两小时，单次授权默认30分钟。授权绑定原 owner；轮换、到期、删除或数据丢失会撤销访问，旧授权不能自动建立新 owner。普通访客始终无法通过受控凭证路径以外的方式启动上传。

## 4. 已验证通过：自动化与完整性

| 验证 | 实际结果及边界 |
|---|---|
| 完整本地 Python unittest | **345/345通过**，26.210秒，无失败、错误或跳过 |
| 原测试保留 | 原302项逻辑保留；新增43项：模板7、容量16、准入4、受控验收16 |
| Node 内置测试 | **29/29通过**；原14项保留，新增15项 |
| 当前 GitHub CI Python | **326项实际通过，19项未执行**；日志为 `Ran 329 tests in 21.402s / OK (skipped=5)` |
| 当前 GitHub CI Node | **29/29通过**，失败0、跳过0 |
| 原测试文件 | 原 tests 目录22份文件哈希及 `3503ffe..b6198af` 差异均不变：20个 Python 测试文件、1个 fixture、1个原 JS 测试文件 |
| 核心与数据保护 | 部署前基线中的28份核心/数据文件 SHA-256 全部一致 |
| 当前应用提交清单 | 119个 Git 跟踪文件与 manifest 一致；118个内容哈希均匹配，清单自身为 null；共3,769,589字节 |

CI 的5个 skip 记录不是只缺5个方法：3个单方法跳过为两个原 ABS Excel 检查、一个真实 M5 衔接检查；两个 setUpClass 跳过分别涉及 RealDataTests 的4个方法和 WebTests 的12个方法。总计19个方法未执行，326＋19＝345。受限 M5 与原 ABS 工作簿不进入部署仓库，不能把这些跳过写成通过。

本轮新增模板测试曾随动态服务器限制改为验证动态契约，并新增 Node 用例验证真实限制及缺失时拒绝发送；原22份测试文件没有修改来绕过失败。Part A 较早的309/24结果是阶段快照，最新租约修复后以348/29完整本地结果为准；上表345/29及CI是修复前快照。

**本地容量与清理补充证据：**

- 旧配置的50,000行/4,000,052字节合成CSV上传201；warm ABS父进程峰值161.23 MiB、child95.34 MiB。
- 新公共配置10,000行/20组合/800,052字节上传及确认201；父进程峰值119.14→132.23 MiB、child35.83 MiB，耗时0.237/0.149秒。
- 本地 TTL 到期读取401；cleanup 后会话/数据/速率/任务记录为0，SQLite中合成marker消失，无 journal 残留，保留40,960字节空DB。

以上是 Mac 和本地应用层证据，**不是 Render Linux 总实例并发峰值，也不是云介质取证级擦除证明**。

## 5. 已验证通过：Render 受控生产 API

真实 HTTPS、只使用明确合成 CSV，当前共 **86项通过、0项失败**：主流程75项、限流恢复5项、会话及响应头6项。计数来自以下未包含原始CSV行、凭证、Cookie或CSRF值的本地证据：

| 本地证据文件 | 通过数 | 范围 |
|---|---:|---|
| `.runtime/deployment-evidence/upload-api-results.json` | 75 | 原匿名访客仍关闭；AUD/USD上传、质量报告、确认、选择、预测、库存、财务、隔离、拒绝及容量 |
| `.runtime/deployment-evidence/upload-api-rate-recovery.json` | 5 | 限流窗口后重新建立受控会话、上传、质量检查、确认及删除恢复 |
| `.runtime/deployment-evidence/upload-api-session-headers.json` | 6 | 有效HTTPS、Secure/HttpOnly/SameSite=Lax Cookie、no-store、凭证不在响应、摘要不可替代原凭证、删除会话 |

已核验的安全边界：

- 两个独立 API 会话的 AUD/USD 分析与原 Python 预测、库存及财务引擎输出一致；USD 数据包含多个商品—门店组合。
- 跨 owner 的 GET、POST、DELETE 不可访问别人的数据；错误 CSRF、外国 Origin、重复JSON字段、任意服务器路径和模板路径参数均拒绝。
- 超过公共1 MiB的文件拒绝；重复数据拒绝且错误不回显原始销售行。
- 主动删除后旧dataset ID不可访问；重新上传后旧ID仍不可访问。
- 两个并发计算实际观察到 **429和200**；拒绝原因为processing_busy；后续计算恢复200。
- 10,000行/20组合的公共最大配置合成样本在真实 Render 上传和确认成功。
- 全局上传限流触发后，新 Cookie 不能绕过；窗口后上传、确认恢复。受控压力检查前后 Synthetic 和 ABS API 都正常，普通访客上传仍关闭。
- Render 应用日志已作屏幕抽查，显示状态码与耗时，没有看到 CSV 明细、私有路径或 Cookie。此抽查不能替代所有平台日志的完整取证审计。

这里的“受控生产验收通过”仅指上述已执行检查，**不表示正式公开上传已开启，也不表示所有资源耗尽或超时路径均已验证**。

## 6. 已验证通过：两套独立浏览器与手机操作

| 浏览器/场景 | 实际操作与结果 |
|---|---|
| In-app browser，AUD | 84行合成CSV：上传、质量报告、确认、14天预测、库存及财务分析完整流程通过 |
| Safari，USD | 252行、3个商品—门店组合：上传、确认、预测通过；切换门店后14天预测总量42→98，结果实际变化 |
| 两浏览器隔离 | 双向打开另一个浏览器的dataset页面均不可访问，不展示对方数据 |
| 390px手机视口 | USD合成CSV上传、质量检查、确认及删除通过；无整页横向溢出，较宽质量表仅在自己的容器内横向滚动 |
| 主动清理 | 浏览器使用的两份合成数据均已主动删除 |

浏览器检查使用真实 Render HTTPS，不以本地 HTTP、test client 或脚本 Cookie Jar 代替。经营参数导入仍须明确确认；未省略来源、币种、假设和临时保存限制。

## 7. 尚未验证与暂未开放

| 项目 | 当前状态 |
|---|---|
| 删除/过期过程中计算槽租约 | 本地已修复，新增3项回归通过；公网修复部署及有界竞态复核待完成，当前不开放 |
| C会话真实30分钟到期 | 等待实际到期检查；预定2026-10-28 14:21:35 UTC，即Sydney 2026-10-29 01:21:35 AEDT；不会用本地模拟时钟冒充公网结果 |
| D会话经历Render重启后的归属与恢复 | 待执行；尚不能断言重启数据丢失、旧会话撤销或重新建立身份的实际结果 |
| Render计算超时/失败后的完整浏览器恢复 | 尚未完成可重复的超时实测；已经验证的429恢复不等于worker超时恢复 |
| Render总实例RSS及CPU实际峰值 | 未验证；控制台当前方案显示512 MB/0.15 CPU，但应用CPU/内存实测指标提示升级才可查看，没有付费升级 |
| Render磁盘实际余量及取证级物理清理 | 未验证；公开API不可读取服务器任意文件，也不新增调试下载端点来绕过权限 |
| 正式公开CSV开放后的无门禁验收 | **暂未开放，待最终验收**；公众features仍为false |
| M5公开展示 | 暂未开放，许可问题仍未解决 |

C、D是受控检查用的合成会话，不是真实企业数据。最终是否开放CSV须根据剩余检查结果决定；存在未解决高风险问题时保持关闭，并列明最小修复方案。当前不将等待中的事项标记为通过。

## 8. 已知限制

- Render Free会休眠，重启、部署或休眠可能使临时数据提前丢失；没有长期保存、账户恢复、常驻或企业SLA承诺。关闭浏览器标签页不是清理机制。[Render Free官方说明](https://render.com/docs/free)
- 全局限流使用固定窗口，边界允许突发；单计算槽限制并发。已经验证新会话无法绕过全局上传限流，但不能保证抵御所有恶意流量或DoS。
- SQLite规范化payload上限不等于整盘上限，journal、运行环境和平台日志仍占空间。应用删除与读权限失效不等于云存储介质的取证级擦除。
- Render上的最大配置样本、并发拒绝和恢复已经通过；没有读取到完整总RSS/CPU指标，不能将Mac单进程测量当作512 MB云实例容量保证。
- 手机质量表为局部横向滚动；目前不是所有真实手机型号及浏览器版本的兼容认证。
- Synthetic只是教学演示，ABS是已有快照，二者不验证真实企业数据来源，也不用于改变M5商品预测。

## 9. 更新与回滚

继续使用现有 GitHub → CI → Render After CI Checks Pass 流程。每次改动先运行测试、审查白名单和暂存区，普通提交推送；不用force push。文档/清单更新受既有构建过滤规则控制，不应被误写为已部署的应用提交。

**发现上传安全问题时，首选关闭功能，不先降级容量防护：**

1. 将公开上传和受控门禁都关闭，撤销临时验收入口，保留 Synthetic 和 ABS。
2. 核实匿名及旧验收会话无法再调用上传接口，检查真实公网五页/API。
3. 如必须回滚代码，优先保留已经验证的容量、全局限流及后续租约修复。`5236ac3` 虽包含容量加固，却早于新发现的租约修复，只能作为**上传关闭**时的候选回退，不能称为已获准公开上传的安全版本。
4. `ed5c2e3`、`b626d07` 是此前稳定展示版本，但不具备本轮全部公共上传容量加固；**不得回滚到这些旧配置后直接开启上传**。
5. Render控制台回滚可能关闭自动部署；恢复稳定后核对配置，再决定是否恢复 After CI Checks Pass。也可用 `git revert` 创建可审查的回退提交并测试后推送。[Render回滚说明](https://render.com/docs/rollbacks)

不得把原始M5、企业CSV、SQLite、原验收凭证、Cookie、密钥、日志或临时证据加入GitHub/部署包。报告更新后需要同步刷新manifest；报告中的119文件核验指当前已部署提交的冻结清单。

## 10. 需要用户操作的事项

受控测试窗口已获得批准，目前不需要再次授权同一范围。后续若涉及付费升级、增加权限或新的安全风险确认，再明确说明并询问；没有为查看指标购买服务。

现阶段继续完成新发现的job租约修复验收、C真实到期、D重启及剩余安全条件检查，随后再决定正式公开CSV是否可以开启，并追加真正公开后的HTTPS验收结果。**当前公众上传仍关闭，请勿把受控测试入口当作正式上线。**
