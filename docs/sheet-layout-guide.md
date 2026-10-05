# 离线矩形板材工具说明

本流程通过 `cutting-layout` CLI 使用，与 [内部 Agent 工作台](../README.md) 的型材长度下料分别运行。它将多个箱体和矩形附件展开为板件，在兼容标准板与矩形余料上混排，从同一份已校验结果导出 PNG、DXF、XLSX、PDF 和 JSON。核心板材流程无需模型、数据库或网络连接。

## 主要能力

- 箱体外形尺寸与内部净尺寸展开，单面尺寸和数量覆盖。
- 矩形附件、标准板、矩形余料；只在材料、厚度、表面和方向规则一致时混排。
- 旋转限制、板边留量、零件间距与切缝参数。
- 无法整板容纳的矩形箱面可生成可追溯分片。
- 按新标准板数量、余料使用、废料、可保留余料、空移距离和产品分散程度择优。
- 导出前检查漏件、重复、重叠、间距、越界、非法旋转、材料与统计一致性。
- 输出目录采用事务：任一选定格式失败时，原输出目录保持不变。

算法采用可复现的启发式方法。相同输入、版本与模式产生可复现结果，不保证数学意义上的全局最优。

## 安装与运行

Python 3.10–3.13，在项目根目录创建并激活虚拟环境后执行：

```bash
python -m pip install -e .
python -m cutting_layout run examples/minimal.json --output output/minimal-demo
python -m cutting_layout run examples/mixed_batch.json --output output/mixed-demo
python -m cutting_layout --version
```

安装后可用 `cutting-layout` 代替 `python -m cutting_layout`。

![虚构混排样例总览](assets/mixed-batch-overview.png)

## 选择格式与输出

默认生成全部五种格式；可按需要选择，名称不区分大小写，重复项去重：

```bash
python -m cutting_layout run examples/minimal.json --output output/json-and-dxf --formats json,dxf
```

支持 `png`、`dxf`、`xlsx`、`pdf`、`json`；空列表或未知格式属于输入错误，退出码为 `2`。

| 文件 | 内容 |
| --- | --- |
| `previews/preview-overview.png` | 批次总览、材料组、板材缩略图与指标 |
| `previews/sheet-*.png` | 每张板材的 A3 横向比例图 |
| `layout-all.dxf` | 板材、板件、编号与余料分图层 CAD 文件 |
| `parts.xlsx` | 批次汇总、板件清单、排料坐标、板材与余料 |
| `cutting-report.pdf` | A3 横向下料评审报告 |
| `result.json` | 所有导出共同使用的已校验结果 |

## 输入格式

输入为 UTF-8 JSON，尺寸单位为毫米，最多两位小数。完整结构见 [JSON Schema](../src/cutting_layout/schemas/cutting-layout-job.schema.json)；可运行示例见 [minimal.json](../examples/minimal.json) 和 [mixed_batch.json](../examples/mixed_batch.json)。

| 字段或概念 | 含义 |
| --- | --- |
| `dimension_basis` | `outer` 为外形尺寸，`inner` 为内部净尺寸 |
| 箱体面 | `top`、`bottom`、`front`、`back`、`left`、`right` |
| `panel_overrides` | 覆盖指定产品面的尺寸、数量、材料或方向 |
| `accessories` | 直接录入门板、盖板等矩形件 |
| `stocks` | `standard` 标准板或 `remnant` 矩形余料 |
| `rotation_allowed=false` | 禁止板件旋转 90° |
| `mode=fast` / `mode=deep` | 固定候选较少 / 增加固定随机种子候选 |

展开规则需结合实际连接结构复核。程序不会自动计算折边、搭接、焊缝收缩、坡口或装配公差。

## 错误与范围

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `2` | 输入、Schema、展开、库存、排料或安全校验错误 |
| `3` | 导出或输出目录提交失败 |

成功信息以 JSON 写入标准输出，错误以 JSON 写入标准错误；不把漏件或未完成导出记为成功。

当前处理完整矩形板件与矩形余料，目标上限约为单批 100 种产品、2,000 块板件。不支持孔洞、任意 DXF 轮廓导入、异形套料、折弯展开、三维结构、焊接工艺规划或 NC/G-code。

正式切割前，由合格人员确认尺寸口径、板厚、切缝、板边留量、连接方式、焊接余量、折弯及装配间隙。本工具提供规划与评审资料，不能代替结构、工艺或设备人员的复核。
