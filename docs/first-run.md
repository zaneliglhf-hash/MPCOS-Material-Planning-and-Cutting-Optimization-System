# 第一次运行、账号开通与再次打开工作台

MPCOS 是需要在电脑或服务器上启动的 Python 应用。GitHub 页面提供源码与说明；下载源码后，浏览器地址 `http://127.0.0.1:8765` 只有在这台电脑的工作台服务运行时才能打开。这里的 `127.0.0.1` 指正在使用的这台电脑，不是公开网站。

**第一次使用需要安装并开通账号；以后只需启动服务和登录。** 网页没有开放注册入口，内部账号由维护人员通过命令开通。MPCOS 登录账号、GitHub 账号和 DeepSeek API 账户各自独立。

## 1. 准备 Python 与项目文件

首次安装建议使用 Python 3.12 或 3.13，项目兼容性测试覆盖 3.10–3.13。官方安装程序可从 [Python 官网](https://www.python.org/downloads/) 获取。确认实际使用的 Python 版本：

```bash
# macOS / Linux
python3 --version
```

```powershell
# Windows PowerShell
python --version
```

版本不在上述范围时，先安装支持的版本。例如已安装 Python 3.12，可用 macOS 的 `python3.12` 或 Windows 的 `py -3.12`，代替本页创建环境时的 `python3` / `python`。不要用不支持的旧版 Python 继续安装。

获取项目有两种方式，选择一种即可：

- GitHub 项目页面点击 **Code → Download ZIP**，解压，进入包含 `pyproject.toml`、`src/` 和 `scripts/` 的文件夹。
- 已安装 Git，可在终端执行：

```bash
git clone https://github.com/zaneliglhf-hash/MPCOS-Material-Planning-and-Cutting-Optimization-System.git
cd MPCOS-Material-Planning-and-Cutting-Optimization-System
```

下载 ZIP 的文件夹通常以 `-main` 结尾。后面的命令都在实际项目文件夹中运行。macOS 可在终端输入 `cd `（保留后面的空格），把解压后的项目文件夹拖入终端，再按回车；Windows 可在该文件夹中打开 PowerShell。

## 2. 首次安装（只做一次）

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[channel,web]'
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[channel,web]"
```

命令中的 `.venv` 是项目的独立 Python 环境。后续直接使用其中的 Python，不需要先激活环境。首次安装需要联网下载依赖；等安装成功后继续。

## 3. 首次开通账号（只做一次）

先创建一个员工账号，再创建一个独立的负责人账号：

macOS / Linux：

```bash
.venv/bin/python -m cutting_layout.workbench create-user employee --role employee
.venv/bin/python -m cutting_layout.workbench create-user manager --role manager
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m cutting_layout.workbench create-user employee --role employee
.\.venv\Scripts\python.exe -m cutting_layout.workbench create-user manager --role manager
```

`employee`、`manager` 是示例用户名，可替换为自己的内部用户名。每条命令都会要求输入新密码并重复确认，至少 12 个字符；输入时不显示字符是正常现象。提示“账号操作完成”表示创建成功。自己妥善保存密码；项目不提供默认密码，密码不会同步到 GitHub。

已有账号不用再次创建。如果提示“账号已存在”，用原账号登录；忘记密码时由维护人员用 `reset-password` 重设，详见 [交付说明](workbench-delivery.md#权限恢复与维护)。

## 4. 启动服务

macOS / Linux：

```bash
.venv/bin/python -m cutting_layout.workbench serve
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m cutting_layout.workbench serve
```

终端会先显示“正在启动工作台并加载依赖”。首次启动加载计算与导出依赖可能需要一些时间，此时网页还不能连接；等看到下面这行，才说明服务已启动：

```text
Uvicorn running on http://127.0.0.1:8765
```

**保持这个终端窗口运行。** 终端看起来一直停在那里是正常的，它正在提供网页服务。现在自己在运行服务的这台电脑的浏览器中输入：

```text
http://127.0.0.1:8765
```

用第 3 步创建的账号与密码登录。此时账号已经开通，不需要再找“注册”按钮。手机或另一台电脑的 `127.0.0.1` 指它们自身；多人访问需要完成 [公司内网部署](workbench-delivery.md#公司内网部署)。

## 5. 先用手工参数走通一笔虚构订单

人工填参、计算、导出和复核不需要模型密钥。先用虚构数据验证软件流程，避免把第一次启动问题与模型账户问题混在一起：

1. 用员工账号登录，新建“首次运行虚构测试”，材质填写 `Q235B`，规格填写“方管 40×40×3 mm”。
2. 在右侧参数表中填写成品需求：`1200 × 3` 和 `1800 × 2`（两行）；原料 `6000`；锯缝 `3`；最大叠切 `2`。
3. 工艺来源填写“虚构软件流程验证，禁止用于生产”，核对后勾选确认并生成。
4. 等待状态从排队/计算中变为“待负责人复核”，核对成品需求总长度 `7200 mm`，下载 A3/CSV/JSON 资料。
5. 退出员工账号，用另一负责人账号登录，查看本版本参数和资料，填写虚构验收意见后通过或退回。

这些数值只用于软件演示，不能当成真实设备参数。生成资料仍需合格人员复核，不构成生产授权。

需要中文 Agent 整理需求时，另按 [DeepSeek 接入说明](deepseek-setup.md) 配置自己部署的 API Key。公司统一部署时由维护人员配置；普通员工直接用内部账号登录。模型请求会使用该部署的 DeepSeek 账户。

## 6. 以后重新打开（每次服务停止后）

重启电脑或关闭运行服务的终端后，浏览器可能提示“无法连接”或“连接被拒绝”。这是服务停止，不代表订单被删掉。回到**原项目文件夹**，执行启动命令即可：

macOS / Linux：

```bash
.venv/bin/python -m cutting_layout.workbench serve
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m cutting_layout.workbench serve
```

再打开 <http://127.0.0.1:8765> 并登录。无需重新安装环境、重复开通账号或重新配置已有密钥。原数据默认保存在项目的 `var/workbench/`，不要删除该目录；自定义数据目录时，要沿用原来的配置。

主动停止服务：在运行它的终端按 **Control + C / Ctrl+C**，等待程序退出。当前提供的是手动启动方式，不会自动随电脑开机启动。浏览器标签页本身不能启动后端服务。

## 7. 常见问题按顺序检查

| 现象 | 怎么处理 |
| --- | --- |
| 第一次就打不开 `127.0.0.1:8765` | 确认完成安装、账号开通，并执行第 4 步；只下载源码或打开 GitHub 不会启动服务 |
| 重启电脑后打不开 | 在原项目文件夹执行第 6 步，并保持服务终端运行 |
| `.venv/bin/python` 或 `python.exe` 找不到 | 确认当前是正确的项目文件夹；首次使用先执行第 2 步 |
| `No module named cutting_layout`、`fastapi` 或 `ortools` | 用本项目 `.venv` 中的 Python 重新执行第 2 步的安装命令 |
| `账号已存在` | 使用原账号登录，不重复开通；忘记密码联系维护人员重置 |
| 登录失败 | 使用本部署创建的内部用户名和密码；GitHub/DeepSeek 的登录密码不是工作台密码 |
| `此数据目录正在使用` | 已有服务或维护任务使用同一数据目录；先检查原服务终端或尝试原登录地址，不要删除 `.service.lock` 或业务数据库 |
| `address already in use` / Windows 端口占用错误 | 端口被其他进程占用，先检查是否是已经运行的工作台；不要直接结束不认识的进程 |
| 必须临时换端口 | 在没有另一个服务使用同一数据目录时，用 `serve --port 8766`，再访问 `http://127.0.0.1:8766` |
| 浏览器中的“连接被拒绝” | 是本机网页服务问题，先查启动终端；不是 DeepSeek 认证失败 |
| Agent 消息报 401/402/429 | 网页已能打开，这是模型账户/额度/请求问题，按 [模型接入说明](deepseek-setup.md#7-常见提示) 检查 |

可在浏览器访问 <http://127.0.0.1:8765/healthz>：返回包含 `"status":"ok"` 的内容，表示该端口上的工作台与数据库连接正常；它不测试模型余额。

账号、订单、`.env` 和备份应留在受控的本地部署，不随源码上传；完整边界见 [隐私与发布说明](privacy-and-release.md)。
