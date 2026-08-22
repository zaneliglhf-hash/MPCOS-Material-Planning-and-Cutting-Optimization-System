# Project-local agent instructions

## Automatic skill scope

This repository owns the `channel-cutting-layout` workflow. When a task in this repository involves rectangular sheet nesting, channel-steel cutting, stock lengths, kerf, stacked sawing, A3 cutting sheets, or cutting-plan CSV/JSON output, load and follow [`skills/channel-cutting-layout/SKILL.md`](skills/channel-cutting-layout/SKILL.md).

Do not install or invoke this repository's cutting skill as a global/default skill for unrelated repositories. The automatic routing rule applies only while working under this repository root.

## Safety

Treat generated layouts as manufacturing planning aids. Preserve the manual review requirements in the Skill and README; never describe output as approved NC/G-code.
