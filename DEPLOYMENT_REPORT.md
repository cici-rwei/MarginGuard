# 公开部署准备报告

日期：2026-10-28。用户确认“尚未配置，先完成部署准备”。**尚未发布，没有真实公网HTTPS网址。** 本轮没有创建GitHub仓库、Render服务、付费资源或提交课程平台。

## 已保存配置

| 文件 | 用途 |
|---|---|
| `.python-version` | 生产候选Python 3.12.14 |
| `requirements-production.txt` | Flask依赖及Gunicorn 26.2.0 |
| `wsgi.py` | 导出现有Flask app |
| `gunicorn.conf.py` | 生产WSGI，默认2 worker、20秒timeout、PORT、请求头限制、只记状态与耗时的访问日志 |
| `runtime_config.py` | 本地/公开模式、环境密钥、功能开关、Secure cookie、Host与可信代理配置 |
| `render.yaml` | Render Blueprint候选配置；不会自行创建服务 |
| `.gitignore` | 排除密钥、上传、SQLite、venv、缓存和ZIP |
| `scripts/package_final.py` | 显式白名单源码/ABS/合成数据交付包 |
| `tests/test_release_config.py` | 公开配置和日志保护回归 |

公开模式必须提供至少32字符的 `MARGINGUARD_SECRET_KEY`；Render Blueprint使用平台生成随机值。不要将密钥贴入聊天、Git、截图或命令记录。Debug强制关闭。

`ENABLE_BUSINESS_UPLOAD=false`、`ENABLE_M5_DEMO=false` 为公开默认；M5还要求独立的 `M5_PUBLIC_LICENSE_CONFIRMED=true`，该变量只能在取得并记录许可后设置。不能将配置开关视为取得许可。当前部署候选只具备开放ABS和功能状态提示的条件。

生产临时目录由 `MARGINGUARD_PRIVATE_DIR` 指定或使用系统临时目录中的私有子目录。它必须在项目及静态目录之外。单实例多worker共享SQLite；多实例横向扩展尚未实现。`TRUST_REVERSE_PROXY=true` 仅用于已确认单层TLS终止代理；只信任协议头，不信任代理传来的Host或客户端IP作为身份。

## 实际完成的验证

1. 建立独立Python3.12.14生产测试venv，安装Flask3.1.2/Gunicorn26.2.0，`pip check`通过。
2. 在本机 `127.0.0.1:5051` 使用Gunicorn实际启动两worker，Debug关闭。该回环HTTP测试不是公网HTTPS部署。
3. `/api/features` 返回public=true、upload=false、demo=false；`/market`与ABS catalog返回200。
4. 上传session接口返回503和明确disabled提示；M5 catalog返回503和许可待核实提示。没有暴露数据或伪造Demo。
5. 独立浏览器访问Gunicorn `/market`，SVG与官方数据正常；My Business展示关闭原因。
6. 11项release配置测试通过，包括密钥/许可/Host闸门、安全头、私有缓存、cookie、意外异常不泄漏或写入日志。部署与打包合计22项新增测试。

完整本地功能使用5050，详见 `FINAL_QA_REPORT.md`。本地Gunicorn冒烟服务仅用于验收，验收结束后关闭。

## 上线前仍缺少的证据

- **M5许可未验证**：官方Kaggle条款未取得可核验正文。原始CSV、处理后逐日记录、回测actuals、派生预测均不进入提交包/公开仓库；原本地数据完整保留。详见 `DEPLOYMENT_EVIDENCE.md`。
- **公开匿名上传未完成生产安全验收**：需Linux资源/内存实际限制、磁盘及journal容量、代理/平台层入口限速、防新cookie重复建会话占满容量、高并发、重启/清理与日志策略验收。本地测试不替代这些项目。
- **HTTPS未验证**：没有服务账号/URL，不声称TLS、域名或公网跨浏览器通过。
- **课程要求未核实**：缺正式rubric、Advanced Topics认可清单及AI政策。

## 用户后续操作步骤（本轮不执行）

1. 阅读并确认 `DEPLOYMENT_EVIDENCE.md` 的M5权利与上传安全闸门。先保留两个公开功能开关关闭。
2. 登录自己的GitHub与Render。将最终白名单包中的MarginGuard内容作为仓库根目录；不要直接上传含原始数据和研究下载的整个本地工作目录。
3. 在Render选择New Blueprint并连接该仓库，检查 `render.yaml`。若仓库保留嵌套目录，需要显式将Root Directory和Blueprint路径指向项目；本配置默认源码位于仓库根目录。
4. 检查Build Command `pip install -r requirements-production.txt`，Start Command `gunicorn -c gunicorn.conf.py wsgi:app`，Health Check `/api/features`。密钥由平台安全生成/保存；`MARGINGUARD_PUBLIC=true`，两功能开关false。
5. 完成平台所需的登录/条款/资源选择。免费计划只能作课程预览，可能休眠和冷启动；不代表适合企业生产服务。
6. 取得真实 `https://...onrender.com` 后，独立浏览器检查ABS、静态资源/API、手机布局、HTTP→HTTPS、错误提示和服务日志，再记录实际公网地址。
7. 只有M5许可明确且合法轻量数据准备完成后启用Demo；只有上传生产验收完成后启用上传。平台运行时敏感数据不放Git或自动快照长期保留。

Render平台能力已按 [官方Flask指南](https://render.com/docs/deploy-flask)、[Web Services](https://render.com/docs/web-services)、[TLS](https://render.com/docs/tls)、[免费服务限制](https://render.com/docs/free)核对。ABS使用说明见[官方版权页面](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer)。这些文档说明平台与许可规则，不证明本项目已经上线。
