"""第三课：在用户自己的终端中配置密钥；不会调用 API。"""

import argparse
import getpass
import os
from pathlib import Path
import sys
import warnings

from cutting_layout.deepseek_connection import DeepSeekConnectionError, save_api_key


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="隐藏输入并保存 DeepSeek API Key")
    parser.add_argument("--replace", action="store_true", help="更换密钥，保留其他配置")
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        print("请在你自己的终端中运行此命令，以便隐藏输入密钥。")
        return 2
    if (ROOT / ".env").exists() and not args.replace:
        print("已有本地 .env 配置，已保留。更换请运行：.venv/bin/python scripts/setup_deepseek.py --replace")
        return 0
    try:
        # Refuse getpass's echoing fallback if a secure terminal is unavailable.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            label = "新的 " if args.replace else ""
            key = getpass.getpass(f"请粘贴{label}DeepSeek API Key（输入不会显示），然后按回车：")
        save_api_key(ROOT, key, replace=args.replace)
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("\n配置已取消。请在你自己的终端重新运行。")
        return 2
    except DeepSeekConnectionError as exc:
        print(str(exc))
        return 2
    except OSError:
        print("无法保存本地配置，请检查项目目录权限。更换失败时原文件保持不变。")
        return 2
    action = "更换" if args.replace else "保存"
    print(f"密钥已{action}到本地 .env，文件权限已限制为当前账户读写。")
    if os.environ.get("DEEPSEEK_API_KEY"):
        print("当前终端存在优先级更高的密钥环境变量；测试新密钥前请运行：unset DEEPSEEK_API_KEY")
    print("配置过程没有调用 API。下一步运行：.venv/bin/python examples/agent_lesson_03.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
