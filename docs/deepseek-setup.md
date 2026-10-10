# 配置自己的 DeepSeek API 并使用工作台

这份说明适用于下载 MPCOS 源码后，在自己的电脑或服务器运行内部工作台的用户。每套工作台使用部署方配置的 DeepSeek API Key；源码不包含项目作者的密钥、可登录账号或业务数据。

| 使用方式 | 模型调用使用的密钥 |
| --- | --- |
| 下载源码，在自己的电脑或服务器运行 | 自己在该部署中配置的密钥 |
| 登录公司统一部署的工作台 | 公司服务器配置的密钥 |

工作台登录账号与 DeepSeek 账户分别管理。当前网页没有 API 设置页，也没有让每位登录用户保存个人密钥的功能；公司统一部署时，由维护人员配置一次，员工直接登录使用。

第一次使用或浏览器打不开时，先按 [首次运行与再次打开](first-run.md) 检查安装、账号和本机服务。网页“连接被拒绝”与模型认证问题分别处理；手工参数流程无需 API Key。

## 1. 获取自己的 API Key

进入 [DeepSeek 官方 API Key 页面](https://platform.deepseek.com/api_keys)，登录或注册自己的 DeepSeek 平台账户，创建 API Key，并确认账户具有可用额度。官方接入说明见 [DeepSeek API 文档](https://api-docs.deepseek.com/)。

在自己的终端中输入密钥，不要把密钥发到聊天、GitHub issue、截图或公开文档中。下面的配置脚本不会调用 API；之后向 Agent 发送消息会使用配置的 DeepSeek 账户发起模型请求。

应用已连接官方接口 `https://api.deepseek.com/chat/completions`，当前代码使用模型 `deepseek-flash`。使用自己的官方密钥时，无需修改接口地址或代码。

## 2. 下载并安装应用

从本仓库下载源码并解压，或使用 Git 克隆。安装 Python 3.10–3.13，然后在终端进入项目根目录，即包含 `pyproject.toml`、`scripts/` 和 `src/` 的目录。当前本地验收环境为 macOS / Python 3.12。

首次安装执行以下命令；已有安装可以直接进入第 3 步。

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

后续命令均在项目根目录执行，不需要先激活虚拟环境。

## 3. 配置自己的密钥

在自己的交互式终端中运行以下命令。

macOS / Linux：

```bash
.venv/bin/python scripts/setup_deepseek.py
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe scripts/setup_deepseek.py
```

出现“请粘贴 DeepSeek API Key”提示后，粘贴自己的密钥，再按回车。输入不会显示字符，这是正常行为。

脚本将密钥保存到本机项目根目录的 `.env`。macOS / Linux 下文件权限限制为当前系统账户读写；Windows 下还需按本机文件访问权限管理。`.env` 已被 Git、源码包和 Docker 构建上下文排除。公开示例 `.env.example` 不包含密钥。

如果提示“已有本地 .env 配置，已保留”，说明脚本没有覆盖原配置。更换密钥时使用第 6 步的命令。

## 4. 开通内部账号并启动

首次部署由维护人员开通员工与负责人账号。网页提供登录入口，账号由维护人员创建。下面的 `employee`、`manager` 是示例账号名，可替换为实际内部用户名；已有账号无需重复创建。

macOS / Linux：

```bash
.venv/bin/python -m cutting_layout.workbench create-user employee --role employee
.venv/bin/python -m cutting_layout.workbench create-user manager --role manager
.venv/bin/python -m cutting_layout.workbench serve
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m cutting_layout.workbench create-user employee --role employee
.\.venv\Scripts\python.exe -m cutting_layout.workbench create-user manager --role manager
.\.venv\Scripts\python.exe -m cutting_layout.workbench serve
```

创建账号时输入至少 12 字符的密码，并重复输入确认；密码不会显示。启动服务后保持该终端运行，浏览器打开 <http://127.0.0.1:8765>，用刚创建的内部账号登录。

此地址用于运行服务的本机。其他电脑访问需要完成公司内网部署，见 [工作台交付说明](workbench-delivery.md#公司内网部署)。

服务不会自动随电脑开机启动。关闭运行服务的终端或重启电脑后，在原项目文件夹重新执行本节的 `serve` 命令即可，已有账号不重复创建；详见 [再次打开步骤](first-run.md#6-以后重新打开每次服务停止后)。

## 5. 验证 API 与日常使用

1. 用员工账号登录，点击“新建订单”，填写一个虚构演示订单的名称、材质和截面规格。
2. 在“订单助理”中输入：“你好，请说明建立下料方案需要填写哪些参数。”
3. 点击“发送给 Agent”。正常收到回复，说明工作台能够完成这次模型请求；若报错，按下表检查。
4. 实际使用时，提供订单需求，让 Agent 整理参数草稿；核对参数及工艺来源后，点击“确认参数，生成方案”。
5. 查看并下载本版本资料，再由另一位负责人使用独立账号复核。

模型只整理草稿，计算和复核各有确认步骤。人工填写参数、计算、导出和复核无需 API Key。公司环境部署、实际工艺确认与员工试用仍需实际验收，详见 [工作台交付说明](workbench-delivery.md)。

## 6. 更换密钥与环境变量

更换时运行以下命令，并在隐藏输入提示中粘贴新的密钥。脚本只更换 `.env` 中的密钥项，保留其他配置。

macOS / Linux：

```bash
.venv/bin/python scripts/setup_deepseek.py --replace
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe scripts/setup_deepseek.py --replace
```

加载顺序为：**运行服务进程的 `DEEPSEEK_API_KEY` 环境变量优先，其次读取项目根目录 `.env`**。如果更换了 `.env` 但仍在使用旧密钥，检查是否存在优先级更高的环境变量。

希望改用 `.env` 时，先用 `Ctrl+C` 停止自己运行的服务，再在用于启动服务的同一个终端移除该环境变量并重新启动：

macOS / Linux：

```bash
unset DEEPSEEK_API_KEY
.venv/bin/python -m cutting_layout.workbench serve
```

Windows PowerShell：

```powershell
Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m cutting_layout.workbench serve
```

公司通过服务管理器或容器注入环境变量时，由维护人员在实际部署配置中更新密钥，并重新启动对应服务。容器不会自动包含本机 `.env`。

## 7. 常见提示

| 提示 | 处理方式 |
| --- | --- |
| 尚未配置密钥 | 在项目根目录运行第 3 步的配置脚本 |
| 401：密钥认证失败 | 检查密钥是否完整、有效；用 `--replace` 更换，并检查环境变量优先级 |
| 402：账户余额不足 | 在配置该密钥的 DeepSeek 平台账户中检查可用额度 |
| 429：请求过于频繁 | 等待后再试；工作台自身也设有请求次数限制 |
| 网络连接失败或超时 | 检查运行服务的电脑能否访问 DeepSeek 官方接口；请求超时不代表供应商未计费 |
| 请在自己的终端运行 | 配置脚本需要交互式终端，不能通过无交互输入或聊天消息传入密钥 |
| 浏览器打不开本地地址 | 检查服务终端是否仍在运行，以及实际监听端口是否为 8765 |

交付给其他使用者时，提供源码和这份说明，由对方开通账号、配置密钥。不要复制原部署的 `.env`、本机账号说明、`var/` 业务数据或备份。隔离范围见 [隐私与发布说明](privacy-and-release.md)。
