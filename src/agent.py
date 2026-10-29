"""ReAct loop: decide → tool → observe → decide again or finish."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .decision import BaseDecisionMaker
from .schemas import Action, AgentResult, Observation, TraceStep
from .tools import ToolBox, ToolError


class KnowledgeQAAgent:
    def __init__(
        self,
        decision_maker: BaseDecisionMaker,
        toolbox: Optional[ToolBox] = None,
        max_steps: int = 8,
        max_tool_calls: int = 10,
    ):
        self.dm = decision_maker
        self.tools = toolbox or ToolBox()
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls

    def run(
        self,
        question: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AgentResult:
        history = history or []
        observations: List[Dict[str, Any]] = []
        trace: List[Dict[str, Any]] = []
        tool_calls = 0

        for step in range(1, self.max_steps + 1):
            if tool_calls >= self.max_tool_calls:
                return self._incomplete(
                    "达到工具调用次数上限，未能完成可靠回答。",
                    ["max_tool_calls_reached"],
                    trace,
                    step - 1,
                    tool_calls,
                )

            action = self.dm.decide(
                question=question,
                history=history,
                observations=observations,
                available_actions=["search", "read", "ask_user", "finish"],
                step=step,
                max_steps=self.max_steps,
            )
            action_dict = action.to_dict()
            step_rec = TraceStep(
                step=step,
                action=action_dict,
                rationale=action.rationale,
            )

            if action.name == "finish":
                step_rec.observation = None
                trace.append(step_rec.to_dict())
                return AgentResult(
                    status=action.status or "completed",
                    answer=action.answer or "",
                    citations=action.citations or [],
                    gaps=action.gaps or [],
                    ask_user=action.question,
                    trace=trace,
                    decision_mode=self.dm.mode,
                    steps_used=step,
                    tool_calls=tool_calls,
                )

            if action.name == "ask_user":
                # Asking user ends this run with needs_confirmation / incomplete pending user
                step_rec.observation = {
                    "summary": "awaiting_user",
                    "question": action.question,
                }
                trace.append(step_rec.to_dict())
                return AgentResult(
                    status="needs_confirmation",
                    answer=action.answer or "需要用户补充信息后才能继续。",
                    citations=action.citations or [],
                    gaps=action.gaps or ["need_user_input"],
                    ask_user=action.question,
                    trace=trace,
                    decision_mode=self.dm.mode,
                    steps_used=step,
                    tool_calls=tool_calls,
                )

            # Execute tool
            params = {}
            if action.name == "search":
                params = {"query": action.query or question}
            elif action.name == "read":
                params = {"doc_id": action.doc_id, "chunk_id": action.chunk_id}
            else:
                return self._incomplete(
                    f"未知动作: {action.name}",
                    ["unknown_action"],
                    trace + [step_rec.to_dict()],
                    step,
                    tool_calls,
                )

            obs = self._run_tool(step, action.name, params)
            tool_calls += 1
            observations.append(obs.to_dict())
            step_rec.observation = obs.to_dict()
            # Attach next-hint fields required by exam: 后续动作由下一轮 decide 产生
            trace.append(step_rec.to_dict())

        return self._incomplete(
            "达到执行步数上限，未能完成可靠回答。",
            ["max_steps_reached"],
            trace,
            self.max_steps,
            tool_calls,
        )

    def _run_tool(self, step: int, name: str, params: Dict[str, Any]) -> Observation:
        try:
            raw = self.tools.execute(name, params)
            ok = bool(raw.get("ok", True))
            if name == "search":
                hits = raw.get("hits") or []
                summary = f"search count={raw.get('count', len(hits))} ids={[h.get('doc_id') for h in hits]}"
            elif name == "read":
                if not ok:
                    summary = f"read error: {raw.get('error')}"
                else:
                    summary = f"read doc_id={raw.get('doc_id')} title={raw.get('title')}"
            else:
                summary = str(raw)[:200]
            return Observation(
                step=step, tool=name, params=params, ok=ok, summary=summary, raw=raw
            )
        except ToolError as e:
            return Observation(
                step=step,
                tool=name,
                params=params,
                ok=False,
                summary=str(e),
                raw={"ok": False, "error": str(e)},
            )

    def _incomplete(
        self,
        answer: str,
        gaps: List[str],
        trace: List[Dict[str, Any]],
        steps_used: int,
        tool_calls: int,
    ) -> AgentResult:
        return AgentResult(
            status="incomplete",
            answer=answer,
            citations=[],
            gaps=gaps,
            ask_user=None,
            trace=trace,
            decision_mode=self.dm.mode,
            steps_used=steps_used,
            tool_calls=tool_calls,
        )
