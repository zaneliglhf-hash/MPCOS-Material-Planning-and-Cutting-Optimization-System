# MPCOS 内部下料工作台 · 交付与运行说明

第一版把已有下料算法与模型工具接入正式的订单流程。适用范围为同材质、同截面规格的槽钢、方管、矩形管长度下料。当前交付的是可本地运行、可演示和验收的内部试用版本；公司服务器部署、真实工艺审核和员工试用需要另行实际完成。

首次配置或更换自己的官方模型密钥，见 [配置自己的 DeepSeek API 并使用工作台](deepseek-setup.md)，包含 macOS / Linux、Windows 命令及环境变量优先级说明。

首次使用与服务停止后的再次打开，见 [完整运行流程](first-run.md)。网页账号由维护人员开通，GitHub 页面不承载本机服务。

## 5 分钟启动

在项目根目录执行（macOS / Linux，Python 3.10–3.13；当前实测为 macOS Python 3.12）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[channel,web,dev]'
.venv/bin/python -m cutting_layout.workbench create-user employee --role employee
.venv/bin/python -m cutting_layout.workbench create-user manager --role manager
.venv/bin/python -m cutting_layout.workbench serve
```

账号创建时在终端输入至少 12 字符的密码，不接受命令行明文密码。浏览器打开 <http://127.0.0.1:8765>。每次部署均须自行创建账号；本仓库不包含预设账号、有效密码、模型密钥或业务数据库。

网页人工填参、计算、导出、复核无需模型密钥。中文对话继续使用项目配置的 `DEEPSEEK_API_KEY` 环境变量或项目根目录 `.env`，不需要再次复制密钥。模型连接复用 `deepseek_connection.py`，固定 API 域名；模型只获取当前订单元数据、对话和草稿，不接收数据库、账号密码、历史其他订单或本地文件路径。

数据默认在 `var/workbench/`。可通过 `MPCOS_DATA_DIR` 或命令最前面的 `--data-dir /absolute/path` 改变目录。使用安装后的命令 `mpcos-workbench` 与上述模块调用等价。

## 员工与负责人怎样使用

1. 员工建立订单，填写订单名、材质、截面规格。不同材质或规格分别建单。
2. 用中文提供需求，Agent 补问缺失字段并调用参数整理工具。可分次补充，修改单个字段会沿用其余已知参数；修改成品清单时须说明完整的新清单，删除的长度不会被重新合并。完整草稿须通过组合校验，不合法的修改保留原草稿。模型草稿填入右侧表单，也可直接手填；未说明的工艺参数没有默认值。
3. 核对需求长度和数量、原料长度、锯缝、叠切上限，注明作业卡、设备确认或其他参数来源，勾选确认后生成。
4. 后台计算保存为 V1，提供需求成品总长度、批次、落锯、采购、余料、利用率，以及 A3 PNG、CSV、输入/结果 JSON。状态为待复核。
5. 负责人用另一账号查看订单与本版本参数、图纸及来源，填写意见并通过或退回。员工不能审核；负责人不能审核自己提交的版本。复核意见、人员、时间以及本版下载文件的 SHA-256 均可追溯，也可下载版本复核记录。
6. 修改后再次确认生成 V2，V1 及其复核记录保留；V2 必须重新复核。复核接口只接受最新的待复核版本。

修改参数或确认依据后，页面会取消原确认勾选，需要重新核对。发送对话或提交计算期间，当前输入暂时锁定；网络失败后恢复编辑，未改参数的重试沿用同一提交编号。快速切换订单时，迟到的响应不会覆盖当前页面；历史订单链接可直接打开，不受首页 200 条列表限制。

优化目标按现有算法排序：先减少上下料批次，再减少落锯次数，再减少采购长度，最后减少切割模式数。因此利用率不一定是材料利用率优先方案的最大值。每批原料采用同一顺序连续切割。最终结果仍为计划辅助，不能代替合格人员的制造与设备安全检查。

首版服务范围：最多 20 种成品长度、500 件、5 种原料长度；长度不超过 30000 mm，叠切上限 1–100，锯缝 0–100 mm。超出时提示拆分；这些是软件资源边界，不代表设备能力。整次求解含导出最多 90 秒，最多同时运行 2 个、排队与运行合计 8 个任务。没有超时自动重试或重复计费。

## 权限、恢复与维护

- 员工仅能读写自己订单；负责人可读全部订单和复核，不能改他人参数。身份来自服务端会话，不从模型或请求字段读取。
- 密码通过独立盐值的 scrypt 哈希保存；会话令牌仅保存 SHA-256，8 小时过期。浏览器 Cookie 使用 HttpOnly、SameSite=Strict；写请求校验来源及 CSRF。生产 HTTPS 须启用 Secure Cookie。
- 登录失败达到 15 分钟窗口 10 次时暂时限流；模型预算在数据库按订单 40 次、账号滚动 24 小时 100 次持久化，失败请求也占用。数字是请求次数，不是费用金额或 token 数。
- 同一提交编号和相同参数返回同一版本；编号被不同参数复用会拒绝。参数改变形成新版本，不覆盖旧文件。
- 程序崩溃或重启时，排队/运行任务标为“中断”，解除对话占用锁；由员工核对后明确提交新版本。失败和中断记录保留，已完成版本不受影响。
- 文件下载必须先通过订单权限，再检查登记路径、符号链接及 SHA-256；文件异常会停止下载和复核。工作台没有公开挂载业务文件目录。
- 业务操作按时间追加到审计表；数据库触发器拒绝通过普通 UPDATE/DELETE 修改审计。具有操作系统/数据库管理权限的人仍可改变数据，这不属于外部不可篡改审计服务。
- 本版本仅支持单台机器、单服务进程、SQLite 本地磁盘。文件锁防止第二个进程同时服务同一目录；不要使用多 worker、共享网络盘、多副本或滚动部署。

```bash
# 重置密码会使此账号所有旧会话失效
.venv/bin/python -m cutting_layout.workbench reset-password employee
# 停用离职账号，保留其业务和复核历史
.venv/bin/python -m cutting_layout.workbench disable-user employee
```

### 备份与恢复

先停止服务，等待当前任务结束。备份使用 SQLite backup API 及文件校验清单；恢复会校验 ZIP、路径、SHA-256、数据库完整性和 schema 版本，并作废旧会话。不会把 `.env`、API 密钥或本地访问说明装入业务备份。备份包含业务信息和账号密码哈希，应该由维护人员控制访问并复制到独立的受控存储。

```bash
.venv/bin/python -m cutting_layout.workbench backup backups/mpcos-2026-10-04.zip
.venv/bin/python -m cutting_layout.workbench --data-dir var/restored-check restore backups/mpcos-2026-10-04.zip
.venv/bin/python -m cutting_layout.workbench --data-dir var/restored-check serve --port 8766
```

恢复目标必须是不存在的新目录，不能覆盖运行中的原数据。用原账号重新登录恢复服务，抽查订单、版本、复核记录和下载资料；恢复成功再安排切换实际数据目录。备份不是自动定时执行，维护人员须建立实际备份责任和周期。

更新前停服并备份，保存旧应用包/源码版本和依赖环境；先对备份副本试运行新版本，再更换服务。若更新失败，停止新服务，使用匹配的旧应用和更新前备份启动到新目录；禁止让旧程序直接操作未来 schema。当前没有数据库跨版本迁移器，schema 版本不匹配会拒绝启动。恢复路径有自动化回放，目标公司环境的升级回退仍待演练。

### 公司内网部署

仓库提供 `deploy/Dockerfile`、`compose.yaml` 和 `deploy/Caddyfile.example`。容器非 root 运行、只读应用目录，数据和备份独立卷；默认只映射宿主机 `127.0.0.1:8765`，避免开发服务直接向全网暴露。本次不替公司选择域名或开放端口。

```bash
docker compose build
docker compose run --rm app create-user employee --role employee
docker compose run --rm app create-user manager --role manager
docker compose up -d
docker compose ps
```

多人试用需维护人员配置实际内网域名、受信任 HTTPS 证书/反向代理，并将 `MPCOS_ALLOWED_HOSTS` 设为实际域名和健康检查使用的 `127.0.0.1`，`MPCOS_SECURE_COOKIE=1`。如无正式域名，仍可先在本机演示。容器未验证实际构建与目标环境运行，必须在目标机器按说明执行验收。

`GET /healthz` 检查服务和数据库连接；不检查模型余额或生成业务任务。日志不打印密码、密钥或订单正文，只记录错误类型及任务号；详细业务事件通过订单操作记录查询。

## 原历史与教学兼容

既有 `examples/agent_lesson_04.py`、`output/agent-lesson-04` 历史目录和已学代码保持不变，可继续通过原 CLI 查询。本版没有自动把无身份、无确认来源的教学历史导成已批准的正式订单。需要重用旧需求时，在工作台明确建立订单、确认材料与工艺来源，重新生成；旧记录保留作为来源，不伪造历史审批。


## 工程结构与依据

- `workbench/app.py`：HTTP 校验、会话边界、路由与静态页面。
- `workbench/store.py`：SQLite 表、事务、账号、用量与审计。
- `workbench/service.py`：订单、草稿、版本、计算队列、复核及文件完整性。
- `workbench/worker.py`：独立进程运行原有 `plan_cutting`，控制整体计算时间。
- `workbench/maintenance.py`：单进程锁、离线备份与安全恢复。
- `workbench/static/`：中文网页，无前端构建步骤与外部 CDN。
- `tests/test_workbench.py`：业务与安全边界、模型故障、真实求解与恢复验收。
- `tests/test_workbench_ui.cjs`：用 Node.js 内置测试验证迟到响应、重新确认、表单锁定和重试编号，无额外前端依赖；运行 `node --test tests/test_workbench_ui.cjs`。

Web 生命周期、静态资源和测试依照 FastAPI 官方文档：[Lifespan](https://fastapi.tiangolo.com/advanced/events/)、[Static files](https://fastapi.tiangolo.com/tutorial/static-files/)、[Testing](https://fastapi.tiangolo.com/tutorial/testing/)。现有确定性求解器和导出实现复用，未宣称重新发明算法。
