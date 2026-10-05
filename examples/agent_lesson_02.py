"""第二课：直接调用一个工具函数。全部参数均为虚构教学设定。"""

import argparse
import json
from pathlib import Path

from cutting_layout.agent_tools import plan_cutting


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent 第二课：工具调用")
    parser.add_argument("--missing-kerf", action="store_true", help="演示缺少锯缝参数")
    args = parser.parse_args()

    # 1. 准备输入：Python 字典，用字段名称保存订单参数。
    job = {
        "demand": {"1200": 6, "1800": 6},
        "stock_lengths_mm": [4000],
        "kerf_mm": 3,
        "max_stack": 6,
        "min_bars": 1,
        "max_bars": 12,
        "title": "Agent 第二课：虚构教学订单 / Tool Calling Demo",
    }
    if args.missing_kerf:
        del job["kerf_mm"]

    # 2. 调用工具：把 job 交给 plan_cutting，把返回的数据命名为 result。
    project_root = Path(__file__).resolve().parents[1]
    result = plan_cutting(job, output_root=project_root / "output" / "agent-lesson-02")

    # 3. 显示输出：转成便于阅读的 JSON 文字。
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"success", "needs_input"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
