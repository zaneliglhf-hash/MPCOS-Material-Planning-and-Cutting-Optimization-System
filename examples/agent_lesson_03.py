"""第三课：用一条简短问候测试大模型连接（会调用一次计费 API）。"""

import json
from pathlib import Path

from cutting_layout.deepseek_connection import DeepSeekConnectionError, probe_connection


def main() -> int:
    print("正在发送一次简短问候，仅测试连接；按平台规则计费，不发送订单。", flush=True)
    try:
        result = probe_connection(Path(__file__).resolve().parents[1])
    except DeepSeekConnectionError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
