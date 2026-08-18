# Contributing

感谢你为 `cutting-layout` 做出贡献。项目面向可能影响实际材料与生产决策的场景，因此可复现性、数据隐私和安全校验与功能本身同等重要。

## 开发环境

项目支持 Python 3.10–3.13。建议在虚拟环境中安装开发依赖：

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

Windows PowerShell 使用 `.\.venv\Scripts\Activate.ps1` 激活；macOS/Linux 使用 `source .venv/bin/activate`。

## 提交前检查

```bash
python -m pytest
python scripts/release_audit.py
python -m build
```

测试必须满足 `pyproject.toml` 中的 85% 分支覆盖率门槛。涉及输入字段的修改必须同步更新 JSON Schema、领域解析器、样例和测试；涉及输出的修改必须保持 PNG、DXF、XLSX、PDF 与 JSON 来自同一份已校验方案。

## 数据与隐私规则

- 不得提交真实客户图纸、订单、产品尺寸、公司名称、联系人、私人邮箱、电话号码、身份证号、访问令牌或连接串；
- 不得用真实生产数据制作测试、截图、issue 或性能样例；
- 根目录 DWG、DXF、BAK 和本地私有目录已被忽略，不要强制暂存；
- 如需本地禁词，在被忽略的 `.release-audit.local.txt` 中每行写一个精确值；
- 公开前运行 `python scripts/release_audit.py --history` 和 `ggshield secret scan repo .`；
- 审查器发现历史隐私内容时，应从清理后的工作树创建全新公开历史，不要自动改写私有仓库历史。

## 安全与兼容性

- 不得绕过 `validation.validate_plan` 后直接导出生产结果；
- 新增排料策略必须保持相同输入可复现，并明确说明无法证明全局最优；
- 输出失败必须保持原目标目录不变；
- 新依赖必须支持 Python 3.10–3.13，且不得让测试依赖网络或真实外部服务。

## 提交与 Pull Request

提交应保持单一目的，并包含相应测试。公开安全的实现身份可以使用：

```text
cutting-layout contributors <contributors@users.noreply.github.com>
```

Pull Request 描述应说明行为变化、验证命令和数据是否完全虚构。不要粘贴未经脱敏的输入或输出。

