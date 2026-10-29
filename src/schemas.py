"""Shared types for actions, observations, and final results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


ACTIONS = ("search", "read", "ask_user", "finish")


@dataclass
class Action:
    name: str
    rationale: str = ""
    query: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    citations: List[Dict[str, str]] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    status: Optional[str] = None  # completed | needs_confirmation | incomplete | out_of_scope

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None and v != [] and v != ""}


@dataclass
class Observation:
    step: int
    tool: str
    params: Dict[str, Any]
    ok: bool
    summary: str
    raw: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "tool": self.tool,
            "params": self.params,
            "ok": self.ok,
            "summary": self.summary,
            "raw": self.raw,
        }


@dataclass
class TraceStep:
    step: int
    action: Dict[str, Any]
    rationale: str
    observation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResult:
    status: str
    answer: str
    citations: List[Dict[str, str]]
    gaps: List[str]
    ask_user: Optional[str]
    trace: List[Dict[str, Any]]
    decision_mode: str
    steps_used: int
    tool_calls: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
