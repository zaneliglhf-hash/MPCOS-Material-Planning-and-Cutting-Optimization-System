# Public Release Checklist

## Repository state

- [ ] `git status --short` 只显示预期内容；根目录 CAD/BAK 文件没有被跟踪。
- [ ] README、截图、样例和 issue 模板不含真实业务或个人数据。
- [ ] `LICENSE`、`CONTRIBUTING.md` 和安全警告存在且内容正确。
- [ ] GitHub 仓库 URL 确定后再写入包元数据。

## Tests and package

- [ ] GitHub Actions 上 Python 3.10、3.11、3.12、3.13 全部通过。
- [ ] `python -m pytest` 通过，分支覆盖率不低于 85%。
- [ ] `python -m build` 成功生成 wheel 和源码包。
- [ ] 在全新虚拟环境安装 wheel，并运行：

```bash
python -m cutting_layout run examples/minimal.json --output smoke-output
```

- [ ] PNG、DXF、XLSX、PDF 和 JSON 均生成，并来自同一份已校验结果。

## Privacy and secrets

- [ ] 当前树审查通过：`python scripts/release_audit.py`。
- [ ] 历史审查已运行：`python scripts/release_audit.py --history`。
- [ ] GitGuardian 审查通过：`ggshield secret scan repo .`。
- [ ] 已人工复核图片、PDF、工作簿、DXF 和其他二进制文件。
- [ ] 若私有历史包含真实订单或个人信息，公开仓库从清理后的工作树建立全新历史。
- [ ] GitHub Actions secret `GITGUARDIAN_API_KEY` 已在公开仓库中配置。

## Final publication

- [ ] 新公开仓库没有继承含真实数据的私有 Git 历史。
- [ ] 默认分支保护要求 CI 和 GitGuardian 检查通过。
- [ ] 发布标签与 `src/cutting_layout/__init__.py`、`pyproject.toml` 版本一致。
- [ ] 未提交 `dist/`、`build/`、输出目录、虚拟环境或本地审查禁词表。

