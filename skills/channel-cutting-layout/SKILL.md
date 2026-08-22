---
name: channel-cutting-layout
description: Generate labor-first stacked channel-steel cutting plans from piece lengths, quantities, customizable stock lengths, kerf, and stack limits; use for shop-ready A3 diagrams plus CSV/JSON verification, not for NC/G-code.
metadata:
  short-description: Labor-first channel cutting layouts
---

# 通用槽钢批量下料 / Generic Channel Cutting

Use this skill when the user provides channel-steel piece lengths and quantities and needs an actionable cutting plan that reduces loading/unloading cycles first, saw strokes second, and material waste third.

## Workflow / 工作流

1. Confirm every requested piece as `length × quantity`, the saw kerf, maximum stacked bars, and available raw stock lengths. Stock lengths are configurable; do not assume 6000/9000 unless the user says so.
2. Create a UTF-8 JSON job using this shape:

```json
{
  "demand": {"7150": 4, "2674": 8},
  "kerf_mm": 3,
  "stock_lengths_mm": [6000, 9000],
  "max_stack": 6,
  "min_bars": 1,
  "max_bars": 100,
  "baseline_batches": 0,
  "baseline_strokes": 0,
  "title": "槽钢批量叠切方案 / Channel batch plan"
}
```

3. Run from the repository root:

```bash
python scripts/generate_channel_batch_plan.py path/to/job.json --output output/my-plan
```

4. Deliver the generated A3 PNG pages, `channel-batch-cutting.csv`, and `channel-batch-cutting.json`. Explain procurement counts, batch count, saw strokes, offcut, and utilization in the user's language.

## Decision rules / 决策规则

- The optimizer uses lexicographic objectives: minimum handling batches, minimum saw strokes, minimum purchased stock length, then minimum pattern groups.
- Every batch contains identical bars and one repeated cut sequence. Tell the shop to load, align, cut the whole batch, and unload once; do not split a batch midway.
- Reject or clarify missing dimensions, non-positive quantities, stock that cannot fit the longest piece plus kerf, or a stack limit outside 1–100.

## Safety boundary / 安全边界

The result is a planning aid, not a structural or process approval. Before cutting, a qualified person must verify dimension basis, channel orientation, kerf compensation, end allowance, weld/assembly clearance, machine capacity, and lifting safety. Never present the output as NC/G-code or as permission to skip shop inspection.

For repository details and English documentation, read [`README.en.md`](../../README.en.md) and the JSON example [`examples/channel_batch_job.json`](../../examples/channel_batch_job.json).
