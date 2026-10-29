"""CLI entry: python -m src.main --question "..." [--mock] ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agent import KnowledgeQAAgent
from .decision import build_decision_maker
from .tools import ToolBox


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="小影校招第3题 · 企业知识问答 Agent（CLI）"
    )
    p.add_argument("--question", "-q", required=True, help="用户问题")
    p.add_argument(
        "--history",
        default="",
        help='可选对话历史 JSON，如 \'[{"role":"user","content":"..."}]\'',
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="使用离线 Mock 决策器（只验证流程，不证明真实模型决策效果）",
    )
    p.add_argument("--max-steps", type=int, default=8, help="执行步数上限")
    p.add_argument(
        "--max-tool-calls", type=int, default=10, help="工具调用次数上限"
    )
    p.add_argument(
        "--inject-tool-fail",
        choices=["search", "read"],
        default=None,
        help="注入一次工具失败（search|read）",
    )
    p.add_argument(
        "--output",
        "-o",
        default="",
        help="可选：将完整结果 JSON 写入该路径",
    )
    p.add_argument(
        "--trace-output",
        default="",
        help="可选：单独写出 trace JSON",
    )
    return p.parse_args(argv)


def load_history(raw: str) -> List[Dict[str, str]]:
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("history must be a JSON list")
    return data


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        history = load_history(args.history)
    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": f"invalid --history: {e}"}, ensure_ascii=False))
        return 2

    try:
        dm = build_decision_maker(mock=args.mock)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 2

    toolbox = ToolBox(inject_fail_on=args.inject_tool_fail, fail_times=1)
    agent = KnowledgeQAAgent(
        decision_maker=dm,
        toolbox=toolbox,
        max_steps=args.max_steps,
        max_tool_calls=args.max_tool_calls,
    )
    result = agent.run(question=args.question, history=history)
    payload: Dict[str, Any] = result.to_dict()
    payload["input"] = {"question": args.question, "history": history, "mock": args.mock}

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    if args.trace_output:
        Path(args.trace_output).write_text(
            json.dumps(payload.get("trace"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
