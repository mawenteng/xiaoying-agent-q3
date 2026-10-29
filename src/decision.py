"""Decision makers: LLM (OpenAI-compatible) and observation-driven Mock."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from .schemas import ACTIONS, Action


AVAILABLE_ACTIONS_SPEC = """
可用动作（只能选其一，输出 JSON）：
1) {"name":"search","query":"...","rationale":"..."}
2) {"name":"read","doc_id":"D01","chunk_id":"可选","rationale":"..."}
3) {"name":"ask_user","question":"...","rationale":"..."}
4) {"name":"finish","answer":"...","citations":[{"doc_id":"...","chunk_id":"...","quote":"..."}],
    "gaps":["..."],"status":"completed|needs_confirmation|incomplete|out_of_scope","rationale":"..."}

规则：
- 必须先有依据再回答；无依据不得编造。
- 多文档对同一问题给出不同结论且无优先级时：列出冲突与引用，status=needs_confirmation，并 ask 确认；不得擅自选一边。
- 语料外问题：status=out_of_scope，说明资料缺口。
- 工具失败：可重试一次；仍失败则 finish status=incomplete。
"""


def _parse_action(obj: Dict[str, Any]) -> Action:
    name = obj.get("name") or obj.get("action")
    if name not in ACTIONS:
        raise ValueError(f"invalid action name: {name}")
    return Action(
        name=name,
        rationale=str(obj.get("rationale") or ""),
        query=obj.get("query"),
        doc_id=obj.get("doc_id"),
        chunk_id=obj.get("chunk_id"),
        question=obj.get("question"),
        answer=obj.get("answer"),
        citations=list(obj.get("citations") or []),
        gaps=list(obj.get("gaps") or []),
        status=obj.get("status"),
    )


class BaseDecisionMaker:
    mode: str = "base"

    def decide(
        self,
        question: str,
        history: List[Dict[str, str]],
        observations: List[Dict[str, Any]],
        available_actions: List[str],
        step: int,
        max_steps: int,
    ) -> Action:
        raise NotImplementedError


class MockDecisionMaker(BaseDecisionMaker):
    """
    Offline decisioner that branches on observation content.
    Not a fixed script: next action depends on hits / reads / failures seen so far.
    Boundary: validates control-flow & tool wiring only; does NOT prove real LLM quality.
    """

    mode = "mock"

    def __init__(self) -> None:
        self._rewritten = False
        self._retried_fail = False

    def decide(
        self,
        question: str,
        history: List[Dict[str, str]],
        observations: List[Dict[str, Any]],
        available_actions: List[str],
        step: int,
        max_steps: int,
    ) -> Action:
        effective_q = self._effective_question(question, history)

        if step >= max_steps:
            return Action(
                name="finish",
                status="incomplete",
                answer="达到步数上限，未能完成可靠回答。",
                gaps=["max_steps_reached"],
                rationale="步数耗尽，返回未完成状态。",
            )

        # Tool failure handling from last observation
        if observations:
            last = observations[-1]
            if not last.get("ok"):
                if not self._retried_fail and last.get("tool") == "search":
                    self._retried_fail = True
                    return Action(
                        name="search",
                        query=effective_q,
                        rationale="上次 search 失败，重试一次相同检索。",
                    )
                if not self._retried_fail and last.get("tool") == "read":
                    self._retried_fail = True
                    params = last.get("params") or {}
                    return Action(
                        name="read",
                        doc_id=params.get("doc_id"),
                        chunk_id=params.get("chunk_id"),
                        rationale="上次 read 失败，重试一次读取。",
                    )
                return Action(
                    name="finish",
                    status="incomplete",
                    answer="工具连续失败，无法完成知识问答。",
                    gaps=["tool_failure"],
                    rationale="已重试仍失败，结束为 incomplete。",
                )

        searches = [o for o in observations if o.get("tool") == "search" and o.get("ok")]
        reads = [o for o in observations if o.get("tool") == "read" and o.get("ok")]

        # No search yet → search
        if not searches:
            return Action(
                name="search",
                query=effective_q,
                rationale="尚无检索结果，先按用户问题（含上下文）检索制度/FAQ。",
            )

        # Clear out-of-corpus topics: do not answer from unrelated hits
        if self._is_clear_ooc(effective_q):
            return Action(
                name="finish",
                status="out_of_scope",
                answer="该问题涉及融资/估值等，不在当前制度与产品 FAQ 资料范围内，无法给出有依据的答复。",
                gaps=["out_of_corpus_topic"],
                citations=[],
                rationale="问题主题明确超出合成语料覆盖范围，停止并报告资料缺口。",
            )

        last_search = searches[-1]
        hits = ((last_search.get("raw") or {}).get("hits")) or []

        # Empty hits → rewrite once or ask / out_of_scope
        if not hits:
            if not self._rewritten:
                self._rewritten = True
                alt = self._rewrite_query(effective_q)
                return Action(
                    name="search",
                    query=alt,
                    rationale="首轮检索为空，改写查询后再搜一次。",
                )
            return Action(
                name="finish",
                status="out_of_scope",
                answer="现有制度与产品资料中未检索到相关内容，无法给出有依据的答复。",
                gaps=["no_documents_found"],
                citations=[],
                rationale="改写后仍无命中，判定为资料外问题。",
            )

        hit_ids = [h["doc_id"] for h in hits]
        read_ids = set()
        for r in reads:
            raw = r.get("raw") or {}
            if raw.get("doc_id"):
                read_ids.add(raw["doc_id"])

        # Conflict pair D01/D02 both in hits and question about 报销期限
        conflict_pair = {"D01", "D02"}
        about_reimburse_deadline = self._is_reimburse_deadline(effective_q)
        if about_reimburse_deadline and conflict_pair.issubset(set(hit_ids)):
            for did in ("D01", "D02"):
                if did not in read_ids:
                    return Action(
                        name="read",
                        doc_id=did,
                        rationale=f"检索同时命中可能冲突的 {did}，读取原文核实。",
                    )
            # Both read → finish with conflict
            citations = self._citations_from_reads(reads, prefer=("D01", "D02"))
            return Action(
                name="finish",
                status="needs_confirmation",
                answer=(
                    "资料存在冲突：D01《费用报销管理制度》写明报销期限为费用发生之日起 30 日；"
                    "D02《差旅费用报销补充说明》写明差旅相关费用报销期限为 15 日。"
                    "两份材料均未给出适用范围与优先级。请确认应适用哪份制度后再答复。"
                ),
                citations=citations,
                gaps=["conflicting_policies_no_priority"],
                question="请问您的费用属于一般费用还是差旅费用？应优先适用 D01 还是 D02？",
                rationale="已读 D01/D02 原文，结论冲突且无优先级，不能擅自选一边。",
            )

        # Need to read top relevant docs not yet read
        priority_ids = self._rank_docs_for_question(effective_q, hit_ids)
        for did in priority_ids[:2]:
            if did not in read_ids:
                return Action(
                    name="read",
                    doc_id=did,
                    rationale=f"检索命中 {did}，读取原文片段以支撑回答。",
                )

        if not reads:
            # Should not happen, but safe
            return Action(
                name="read",
                doc_id=hit_ids[0],
                rationale="有命中但未读取，先读排名最高文档。",
            )

        # Build answer from reads
        return self._finish_from_reads(effective_q, reads, hit_ids)

    def _effective_question(self, question: str, history: List[Dict[str, str]]) -> str:
        if not history:
            return question
        # Follow-up: merge last user turns for context
        prev_users = [h.get("content", "") for h in history if h.get("role") == "user"]
        if not prev_users:
            return question
        # If current question looks like a short follow-up, prepend prior topic
        if len(question) <= 20 or any(
            k in question for k in ("那", "这个", "还有", "多久", "几天", "多少")
        ):
            return f"{prev_users[-1]}；追问：{question}"
        return question

    def _rewrite_query(self, q: str) -> str:
        # Simple synonym / focus rewrite
        mapping = [
            ("多久", "期限 天数"),
            ("年假", "带薪年休假 天数"),
            ("字幕", "字幕导出 SRT"),
            ("弹性", "核心时段 工时"),
        ]
        out = q
        for a, b in mapping:
            if a in q:
                out = f"{q} {b}"
                break
        if out == q:
            out = q + " 制度 规定"
        return out

    def _is_reimburse_deadline(self, q: str) -> bool:
        keys = ("报销", "期限", "多久", "几天", "多少天")
        return ("报销" in q) and any(k in q for k in ("期限", "多久", "几天", "多少天", "几日"))

    def _rank_docs_for_question(self, q: str, hit_ids: List[str]) -> List[str]:
        prefer: List[str] = []
        if any(k in q for k in ("年假", "带薪")):
            prefer.append("HR01")
        if any(k in q for k in ("字幕", "导出", "SRT", "srt")):
            prefer.append("P01")
        if any(k in q for k in ("弹性", "核心时段", "工时")):
            prefer.append("HR02")
        if "报销" in q:
            prefer.extend(["D01", "D02"])
        ordered = [d for d in prefer if d in hit_ids]
        for d in hit_ids:
            if d not in ordered:
                ordered.append(d)
        return ordered

    def _citations_from_reads(
        self, reads: List[Dict[str, Any]], prefer: Optional[tuple] = None
    ) -> List[Dict[str, str]]:
        cites: List[Dict[str, str]] = []
        for r in reads:
            raw = r.get("raw") or {}
            did = raw.get("doc_id")
            if prefer and did not in prefer:
                continue
            if "chunks" in raw:
                for c in raw["chunks"]:
                    cites.append(
                        {
                            "doc_id": did,
                            "chunk_id": c.get("chunk_id", ""),
                            "quote": c.get("text", "")[:160],
                        }
                    )
            elif raw.get("text"):
                cites.append(
                    {
                        "doc_id": did,
                        "chunk_id": raw.get("chunk_id") or "",
                        "quote": raw.get("text", "")[:160],
                    }
                )
        return cites

    def _finish_from_reads(
        self, q: str, reads: List[Dict[str, Any]], hit_ids: List[str]
    ) -> Action:
        texts = []
        for r in reads:
            raw = r.get("raw") or {}
            if "chunks" in raw:
                for c in raw["chunks"]:
                    texts.append((raw.get("doc_id"), c.get("chunk_id"), c.get("text", "")))
            elif raw.get("text"):
                texts.append((raw.get("doc_id"), raw.get("chunk_id"), raw.get("text", "")))

        blob = " ".join(t[2] for t in texts)
        citations = [
            {"doc_id": d or "", "chunk_id": c or "", "quote": t[:160]} for d, c, t in texts
        ]

        # Out-of-corpus if reads don't support the ask
        if self._looks_unsupported(q, blob):
            return Action(
                name="finish",
                status="out_of_scope",
                answer="已检索并阅读相关文档，但其中未包含足以回答该问题的依据。",
                citations=citations,
                gaps=["evidence_insufficient"],
                rationale="读取结果与问题不匹配，避免无依据作答。",
            )

        answer = self._compose_answer(q, texts)
        return Action(
            name="finish",
            status="completed",
            answer=answer,
            citations=citations,
            gaps=[],
            rationale="已有原文依据且未见冲突，给出有引用的明确答案。",
        )

    def _is_clear_ooc(self, q: str) -> bool:
        ooc_keys = ("股价", "市值", "融资", "估值", "竞品", "市场份额", "期权", "上市", "并购")
        return any(k in q for k in ooc_keys)

    def _looks_unsupported(self, q: str, blob: str) -> bool:
        # Topics clearly outside the synthetic corpus
        ooc_keys = (
            "股价", "市值", "融资", "估值", "竞品", "市场份额",
            "期权", "上市", "并购",
        )
        if any(k in q for k in ooc_keys):
            return True
        if "报销" in q and ("日" not in blob and "天" not in blob):
            return True
        # If question asks a concrete fact keyword absent from evidence
        return False

    def _compose_answer(self, q: str, texts: List[tuple]) -> str:
        # Prefer explicit known facts from corpus
        for did, cid, text in texts:
            if did == "HR01" and ("年假" in q or "带薪" in q):
                return (
                    "依据 HR01《员工年假管理制度》：员工连续工作满一年后，"
                    "可享受每年五个工作日的带薪年休假。"
                )
            if did == "P01" and any(k in q for k in ("字幕", "导出", "SRT", "srt")):
                return (
                    "依据 P01《小影产品功能 FAQ》：小影支持字幕导出；"
                    "可在导出面板勾选「导出字幕」，生成与成片同名的 .srt 文件。"
                )
            if did == "HR02" and any(k in q for k in ("弹性", "核心时段", "工时")):
                return (
                    "依据 HR02《弹性工作时间试行办法》：工作日 10:00–16:00 为核心在岗时段；"
                    "其余可在 08:00–20:00 自行安排，每日合计不少于 8 小时。"
                )
            if did == "D01" and "报销" in q and "D02" not in [t[0] for t in texts]:
                return (
                    "依据 D01《费用报销管理制度》：员工应在费用发生之日起三十（30）日内提交报销申请。"
                )
        # Fallback: quote first snippet
        did, cid, text = texts[0]
        return f"依据 {did}：{text}"


class LLMDecisionMaker(BaseDecisionMaker):
    """OpenAI-compatible chat decisioner. Requires OPENAI_API_KEY."""

    mode = "llm"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY missing; use --mock or set the key")

    def decide(
        self,
        question: str,
        history: List[Dict[str, str]],
        observations: List[Dict[str, Any]],
        available_actions: List[str],
        step: int,
        max_steps: int,
    ) -> Action:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        payload = {
            "question": question,
            "history": history,
            "observations": observations,
            "available_actions": available_actions,
            "step": step,
            "max_steps": max_steps,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是企业知识问答 Agent 的决策器。根据观察轨迹选择下一步动作。"
                    "只输出一个 JSON 对象，不要 Markdown。"
                    + AVAILABLE_ACTIONS_SPEC
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ]
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        obj = _extract_json(content)
        return _parse_action(obj)


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def build_decision_maker(mock: bool) -> BaseDecisionMaker:
    if mock:
        return MockDecisionMaker()
    return LLMDecisionMaker()
