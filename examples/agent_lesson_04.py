"""第四课的对话入口，以及第五课的本地历史查询。"""

import argparse
from pathlib import Path

from cutting_layout.agent_tools import REVIEW_NOTICE
from cutting_layout.cutting_agent import CuttingAgent
from cutting_layout.deepseek_connection import DeepSeekConnectionError, load_api_key
from cutting_layout.plan_history import list_plan_history, read_plan_details


def show_tool_result(result: dict | None) -> None:
    if result is None:
        print("工具状态：本轮未运行下料计算。")
        return
    print(f"工具状态：{result['status']}")
    if result["status"] != "success":
        print(result["message"])
        return
    print(f"方案编号：{result['run_id']}")
    summary = result["summary"]
    print(
        f"工具实算：原料 {summary['bar_count']} 根；上下料 {summary['batch_count']} 批；"
        f"落锯 {summary['saw_strokes']} 次；总余料 {summary['offcut_mm']} mm；"
        f"成材利用率 {summary['utilization_percent']}%。"
    )
    print("方案状态：等待人工复核。")
    for label, key in (("订单参数", "input"), ("CSV 表格", "csv"), ("JSON 结果", "json")):
        print(f"{label}：{result['files'][key]}")
    for page in result["files"]["images"]:
        print(f"A3 下料图：{page}")
    print(REVIEW_NOTICE)


def show_history(output_root: Path, *, query: str = "") -> int:
    history = list_plan_history(output_root, query=query)
    if history["status"] == "error":
        print(history["message"])
        return 2
    entries = history["entries"]
    if history["query"]:
        print(f"查找条件：{history['query']!r}")
        print(
            f"共 {history['total']} 份可读取记录，匹配 {history['matched']} 份，"
            f"显示最近 {len(entries)} 份。"
        )
        if not entries:
            print("没有找到匹配的方案，可输入“查看历史”查看全部记录。")
    elif not entries:
        print("暂无可读取的历史方案，请先生成一份教学方案。")
    else:
        print(f"历史方案：共 {history['total']} 份可读取记录，显示最近 {len(entries)} 份。")
    if entries:
        print("以下按结果文件修改时间倒序排列；本地读取，不调用模型。")
        for entry in entries:
            summary = entry["summary"]
            print(f"\n方案名称：{entry['title']}")
            print(f"方案编号：{entry['run_id']}")
            print(f"文件修改时间：{entry['modified_at']}")
            print(
                f"原料 {summary['bar_count']} 根；上下料 {summary['batch_count']} 批；"
                f"落锯 {summary['saw_strokes']} 次；总余料 {summary['offcut_mm']} mm；"
                f"成材利用率 {summary['utilization_percent']}%。"
            )
            print(f"方案目录：{entry['directory']}")
        print("\n历史摘要须人工复核；查询记录不代表方案已经获批，也不会恢复对话上下文。")
    if history["skipped"]:
        print(f"已跳过 {history['skipped']} 份缺失、损坏或格式不正确的记录。")
    return 0


def calculate_total_length(demand):
    total_length = 0
    for length, count in demand.items():
        total_length = total_length + int(length) * count
    return total_length
def show_plan(output_root: Path, run_id: str) -> int:
    result = read_plan_details(output_root, run_id)
    if result["status"] == "error":
        print(result["message"])
        return 2
    entry = result["entry"]
    parameters = result["parameters"]
    summary = entry["summary"]
    print(f"方案名称：{entry['title']}")
    print(f"方案编号：{entry['run_id']}")
    print("保存的订单需求：")
    for length, count in parameters["demand"].items():
        print(f"  {length} mm × {count} 件")
    total_pieces = sum(parameters["demand"].values())
    print(f"需求总数：{total_pieces} 件")
    total_length = calculate_total_length(parameters['demand'])
    print(f"需求成品总长度：{total_length} mm (不含锯缝和余料，和非采购长度)")
    print("可用原料长度：" + "、".join(str(length) for length in parameters["stock_lengths_mm"]) + " mm")
    print(f"锯缝：{parameters['kerf_mm']} mm；叠切上限：{parameters['max_stack']} 根。")
    print(
        f"保存的计算结果：原料 {summary['bar_count']} 根；上下料 {summary['batch_count']} 批；"
        f"落锯 {summary['saw_strokes']} 次；总余料 {summary['offcut_mm']} mm；"
        f"成材利用率 {summary['utilization_percent']}%。"
    )
    print(f"方案目录：{entry['directory']}")
    print("本次只查看本地记录，未重新计算，也未切换当前对话的订单。")
    print(REVIEW_NOTICE)
    return 0

def new_func(parameters):
    total_length = calculate_total_length(parameters['demand'])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="中文下料 Agent 与本地方案历史")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--history", action="store_true", help="只查询本地历史，不读取密钥或调用 API")
    modes.add_argument("--show", metavar="完整编号", help="只查看本地方案详情，不读取密钥或调用 API")
    parser.add_argument("--query", metavar="名称或编号", help="配合 --history 筛选方案")
    args = parser.parse_args(argv)
    if args.query is not None and not args.history:
        parser.error("--query 需要与 --history 一起使用。")
    root = Path(__file__).resolve().parents[1]
    if args.history:
        return show_history(root / "output" / "agent-lesson-04", query=args.query or "")
    if args.show is not None:
        return show_plan(root / "output" / "agent-lesson-04", args.show)
    try:
        load_api_key(root)
    except DeepSeekConnectionError as exc:
        print(str(exc))
        return 2
    agent = CuttingAgent(root)
    print("下料 Agent 第四课：请输入虚构教学订单。")
    print("对话与计算摘要会发给 DeepSeek，API 按用量计费；文件保存在本地。")
    print("每条消息最多 2 次模型请求、1 次工具调用；每次启动最多 20 次模型请求。")
    print("输入 /help 或 帮助 查看命令，/history 查看历史，/new 开始新订单，/exit 退出。")
    while True:
        try:
            text = input("\n你：").strip()
            if text in {"/exit", "退出"}:
                break
            if text == "/help" or text == "帮助":
                print("/history 或 查看历史：查看已有方案")
                print("查找方案 名称或编号：筛选历史，例如 查找方案 教学订单 A")
                print("查看方案 完整编号 或 /show 完整编号：查看保存的订单参数和结果")
                print("/new：开始新订单，清空对话")
                print("/exit 或 退出：结束程序")
                continue
            if text == "/history" or text == "查看历史":
                show_history(root / "output" / "agent-lesson-04")
                continue
            parts = text.split(maxsplit=1)
            if parts and parts[0] in {"/show", "查看方案"}:
                if len(parts) < 2:
                    print("请提供完整方案编号，用法：查看方案 完整编号")
                else:
                    show_plan(root / "output" / "agent-lesson-04", parts[1])
                continue
            if parts and parts[0] in {"/history", "查看历史", "查找方案"}:
                if len(parts) < 2:
                    print("请提供名称或编号，例如：查找方案 教学订单 A")
                else:
                    show_history(root / "output" / "agent-lesson-04", query=parts[1])
                continue
            if text == "/new":
                agent.reset()
                print("已开始新订单，上下文已清空；已有方案文件保留。")
                continue
            if not text:
                continue
            if text.startswith("/"):
                print("未知命令。可用命令：/history、/new、/exit。")
                continue
            print("正在处理……", flush=True)
            turn = agent.send(text)
        except (EOFError, KeyboardInterrupt):
            break
        print(f"\n助手：{turn['answer']}")
        show_tool_result(turn["tool_result"])
        if turn["status"] == "error":
            print("本轮发生错误；若上方已列出方案文件，文件仍可使用并须复核。")
    print("已结束。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
