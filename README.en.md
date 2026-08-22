# Cutting Layout | Rectangular Sheets and Generic Channel-Steel Batches

`cutting-layout` is a local Python CLI for validated rectangular sheet layouts and labor-first stacked channel-steel cutting plans. It runs offline and exports visual A3 sheets, CSV details, and JSON verification data.

## Install

```bash
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
.\\.venv\\Scripts\\Activate.ps1     # Windows PowerShell
python -m pip install -e ".[dev,channel]"
```

## Generic channel job

Create a UTF-8 JSON file. `stock_lengths_mm` is user-configurable; the example uses 6000 and 9000 mm:

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
  "title": "Channel batch plan"
}
```

Run:

```bash
python scripts/generate_channel_batch_plan.py examples/channel_batch_job.json \
  --output output/channel-batch-demo
```

The optimizer minimizes, in order: handling batches, saw strokes, purchased stock length, and pattern groups. Each batch uses identical bars and one repeated cut sequence. The output directory contains A3 PNG pages, `channel-batch-cutting.csv`, and `channel-batch-cutting.json`.

## Safety

This is a planning aid, not structural or process approval. Verify dimensions, orientation, kerf, end allowance, weld/assembly clearances, machine capacity, and lifting safety before cutting. It does not generate NC or G-code.

## Rectangular sheet layouts

The existing sheet-layout workflow remains available:

```bash
python -m cutting_layout run examples/minimal.json --output output/minimal-demo
```

See the Chinese guide in [README.md](README.md), the reusable Codex Skill in [skills/channel-cutting-layout/SKILL.md](skills/channel-cutting-layout/SKILL.md), and the example job in [examples/channel_batch_job.json](examples/channel_batch_job.json).
