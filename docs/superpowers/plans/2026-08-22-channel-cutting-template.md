# 通用槽钢批量下料模板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将单订单槽钢叠切程序参数化为可复用模板，并发布中英双语文档和 Codex Skill 包。

**Architecture:** 复用现有 `ChannelBatchPlan`、CP-SAT 优化器和 A3 渲染器；新增 JSON job loader，将订单数据与算法解耦；新增仓库内 Skill 入口文档，指导 Codex 调用命令、检查结果和提示人工复核。

**Tech Stack:** Python 3.10+, OR-Tools CP-SAT, argparse, JSON, Pillow, pytest, Codex Skill Markdown。

## Global Constraints

- 原料规格由输入 JSON 的 `stock_lengths_mm` 自定义为一个或多个正整数长度。
- 单批叠切根数范围为 1～6 根。
- 锯缝、成品长度和数量均使用毫米与整数件数。
- 优化词典序为批次数、落锯次数、原料总长、模式种类。
- 输出不得被描述为未经复核即可直接生产的 NC/G-code。

### Task 1: 新增通用槽钢订单输入模型

**Files:**
- Create: `src/cutting_layout/channel_batch_job.py`
- Create: `tests/test_channel_batch_job.py`

**Interfaces:** `load_channel_batch_job(path: str | Path) -> ChannelBatchJob`；`ChannelBatchJob` 提供 `demand: Counter[int]`、`kerf`、`stock_lengths`、`max_stack`、`min_bars`、`max_bars`、`title`、`baseline_batches`、`baseline_strokes`。

- [ ] 写失败测试：缺字段、负数、超长件和非 `(6000, 9000)` 原料规格必须抛出 `ValueError`；合法 JSON 返回模型。
- [ ] 运行 `pytest tests/test_channel_batch_job.py -q`，确认新增测试先失败。
- [ ] 实现 dataclass 与 JSON loader，规范化排序后的 `Counter`，默认锯缝 3、叠切上限 6；允许任意一个或多个正整数原料长度，并拒绝无法容纳最大成品的规格集合。
- [ ] 再运行同一测试，确认通过。
- [ ] 提交 `git add src/cutting_layout/channel_batch_job.py tests/test_channel_batch_job.py && git commit -m "feat: add reusable channel batch job input"`。

### Task 2: 将生成脚本改为参数化模板

**Files:**
- Modify: `scripts/generate_channel_batch_plan.py`
- Create: `examples/channel_batch_job.json`
- Create: `tests/test_channel_batch_script.py`

**Interfaces:** `generate(job_path: Path, output_dir: Path, time_limit_seconds: float) -> tuple[...]`；CLI 增加位置参数 `job`，默认使用示例文件。

- [ ] 测试示例输入可生成结果，且摘要中的 finished length、件数与输入一致。
- [ ] 运行该测试确认失败。
- [ ] 删除脚本内订单 `Counter`，改为调用 `load_channel_batch_job`，把 job 参数传入优化器、渲染器和 JSON 摘要。
- [ ] 对非法输入捕获 `ValueError`，打印 JSON 错误并返回退出码 2。
- [ ] 运行模板测试和现有测试，确认通过。
- [ ] 提交 `git add scripts/generate_channel_batch_plan.py examples/channel_batch_job.json tests/test_channel_batch_script.py && git commit -m "feat: parameterize channel batch generator"`。

### Task 3: 新增中英双语文档和 Codex Skill

**Files:**
- Modify: `README.md`
- Create: `README.en.md`
- Create: `skills/channel-cutting-layout/SKILL.md`
- Create: `skills/channel-cutting-layout/agents/openai.yaml`

**Interfaces:** Skill 指导用户调用 `python scripts/generate_channel_batch_plan.py <job.json>`，并解释 PNG/CSV/JSON 输出。

- [ ] 写文档检查：README 和 Skill 必须包含安装、输入字段、命令、输出、安全复核和中英入口。
- [ ] 使用 `skill-creator` 的初始化/校验工具生成元数据，补齐真实内容并删除占位文本。
- [ ] 运行 `python <codex-skills-root>/.system/skill-creator/scripts/quick_validate.py skills/channel-cutting-layout`（Windows 可设置 `PYTHONUTF8=1`）。
- [ ] 提交 `git add README.md README.en.md skills && git commit -m "docs: publish bilingual channel cutting skill"`。

### Task 4: 验证、构建和 GitHub 发布

**Files:**
- Modify: `docs/release-checklist.md`（如需补充 Skill 发布检查）

- [ ] 运行 `python -m pytest -q`，要求覆盖率不低于 85%。
- [ ] 运行 `python -m build` 和 `python scripts/release_audit.py`。
- [ ] 检查 `gh auth status`、远程地址和当前分支；若远程为空，使用用户提供的 GitHub URL 配置 `origin`。
- [ ] 推送当前分支到 GitHub，并用 `gh repo view` 验证最新提交和 README 可见。
- [ ] 记录推送地址、提交 SHA、测试结果和若缺失的外部前置条件。
