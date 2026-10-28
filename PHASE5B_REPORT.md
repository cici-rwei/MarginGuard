# Phase 5B：企业 CSV 私有上传后端

完成日期：2026-10-28。范围为现有项目内的匿名临时数据 API；没有创建新项目或公开部署。原 Phase 5A 解析/预测适配被直接复用。

## 实现与文件

- `business_api.py`：匿名会话、CSRF、严格 JSON/查询字段、上传审核、确认、目录、预测、库存、财务和删除接口。
- `business_store.py`：仓库外私有 SQLite、所有权检查、事务配额、不可变版本、原子替换、过期与清理。
- `business_service.py`：业务声明验证、输入适配、固定子进程、限时和计算槽。
- `business_worker.py`：复用 `business_csv.py`、`business_forecast.py`、`inventory.py` 和 `scenario.py`，不执行上传内容。
- `scripts/cleanup_business_data.py`：同一存储目录的独立清理命令。
- `tests/test_business_api.py`、`tests/test_business_store.py`：45 项新增测试。
- `app.py`、`runtime_config.py`、`.gitignore`：注册接口、配置密钥/功能开关、排除私有文件。

## 接口

所有私有接口位于 `/api/business`。GET `/session` 返回内存使用的 CSRF token 和临时会话状态；GET `/template.csv` 下载空模板。POST `/uploads` 接受一个 CSV 及币种、时区、gross units/授权声明、税额口径。返回质量报告、最多20行预览、连续区间与不透明系列 ID。

POST `/uploads/<id>/confirm` 接受 revision 与显式选择的连续日期区间；每个区间至少42天。成功后返回新的临时 dataset/revision。GET `/datasets/<id>/catalog` 与 `/analysis?series_id=...&revision=...` 读取本人数据；POST `/datasets/<id>/inventory`、`/scenarios` 使用已有 Python 引擎。DELETE 支持待确认文件、活动数据集及整个会话。用户不能指定服务器文件路径。

确认新数据集会原子替换旧版本；旧 ID 不能继续读取。每次库存/财务请求都检查币种、系列、版本与库存日期。库存应对应预测原点收盘；否则必须明确声明为该日期的假设库存。历史价格/成本只提供带日期的参考，所有企业经营假设初始为空。

## 隐私、限制与清理

| 控制 | 实现 |
|---|---|
| 文件/记录 | CSV 5 MiB；50,000 数据行；100 商品—门店组合；HTTP multipart 总体6 MiB |
| 表单/JSON | 最多8个multipart部分，非文件声明合计16 KiB；普通 JSON 请求32 KiB；拒绝重复字段/键 |
| 计算 | 子进程 wall timeout 默认5秒，超时 kill 并回收管道；CPU6秒；Linux地址空间384 MiB限制代码 |
| 并发/容量 | 全局2个计算槽、最多100临时会话；规范化单数据集20 MiB、全局payload500 MiB；SQLite页数限制 |
| 限流 | 每 owner 120请求/分钟，3次上传/10分钟，30次计算/分钟 |
| 会话 | 签名 HttpOnly/SameSite cookie；公开模式 Secure；原始owner token不入数据库、不入URL |
| 归属 | owner哈希与随机dataset ID，每次访问由服务器检查；浏览器草稿不是授权依据 |
| CSRF | 写操作需 CSRF header，并检查 Origin / Sec-Fetch-Site |
| 保存 | 不持久保存原CSV；只在私有目录保存规范JSON及计算结果，目录0700/数据库0600 |
| 到期 | 待确认15分钟；会话闲置30分钟或绝对2小时；每请求先校验，并每300秒清理 |
| 缓存/日志 | 私有响应 no-store；不记录CSV、金额、cookie、令牌或异常明细；统一安全错误 |

原始流由请求生命周期关闭。SQLite secure_delete开启；删除是应用层记录删除，不承诺底层备份、磁盘快照或云提供商介质的取证级擦除。应用停止时后台清理线程也停止，因此生产必须保证同实例运行和存储策略符合声明。

## 测试与修复

API31项 + Store14项 **45/45通过**。全部使用明确合成输入/临时目录。包含真实超过64 KiB CSV正常上传，5 MiB+文件/6 MiB+请求拒绝，实际50,001行及101组合拒绝，41天确认拒绝/42天成功，跨owner与伪造cookie拒绝、签名轮换、多worker同owner、CSRF、版本、币种冲突、过期删除、限流、并发容量、真正超时终止及槽位回收。资源警告检查通过。

集成中修复 multipart缓冲小于正常文件块、SQLite连接关闭、早期超时stdin管道关闭及非字符串revision校验问题。保留原193项测试，最终全套结果见 `FINAL_QA_REPORT.md`。

## 公开安全验收边界

本地功能测试通过不等于生产安全认证。尚未在Linux托管环境验证地址空间限额、真实高并发、入口请求速率、磁盘与进程总内存配额；SQLite页数和payload限额不等于含journal的物理磁盘总占用上限。新cookie可绕过每owner限流，需要入口防滥用措施。公开模式默认关闭上传，本轮不发布。
