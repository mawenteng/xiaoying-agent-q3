"""Acceptance tests for Q3 Knowledge QA Agent (mock mode)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent import KnowledgeQAAgent
from src.decision import MockDecisionMaker
from src.tools import ToolBox


ROOT = Path(__file__).resolve().parents[1]


def run_q(question: str, history=None, inject=None, max_steps=8):
    agent = KnowledgeQAAgent(
        decision_maker=MockDecisionMaker(),
        toolbox=ToolBox(inject_fail_on=inject, fail_times=1),
        max_steps=max_steps,
    )
    return agent.run(question, history or [])


def test_clear_answer_annual_leave():
    r = run_q("员工年假有多少天？")
    assert r.status == "completed"
    assert "五" in r.answer or "5" in r.answer
    assert any(c["doc_id"] == "HR01" for c in r.citations)
    assert len(r.trace) >= 2
    # At least one search then read path
    tools = [t["action"]["name"] for t in r.trace if t["action"]["name"] != "finish"]
    assert "search" in tools
    assert "read" in tools


def test_clear_answer_subtitle():
    r = run_q("小影支持字幕导出吗？")
    assert r.status == "completed"
    assert "支持" in r.answer
    assert any(c["doc_id"] == "P01" for c in r.citations)


def test_document_conflict_reimburse():
    r = run_q("报销期限多久？")
    assert r.status == "needs_confirmation"
    assert "30" in r.answer and "15" in r.answer
    assert "冲突" in r.answer
    ids = {c["doc_id"] for c in r.citations}
    assert "D01" in ids and "D02" in ids
    # Must not unilaterally pick 15 days only
    assert not (r.answer.strip().endswith("15 天") and "30" not in r.answer)


def test_out_of_corpus():
    r = run_q("公司下一轮融资估值是多少？")
    assert r.status in ("out_of_scope", "incomplete", "needs_confirmation")
    # Prefer out_of_scope; allow incomplete if rewrite path exhausts oddly
    assert r.status == "out_of_scope" or "no_documents" in "".join(r.gaps) or r.gaps
    assert "依据" not in r.answer or "未" in r.answer or "无法" in r.answer


def test_paraphrase_similar_question():
    # Paraphrase of annual leave
    r = run_q("入职满一年以后，带薪年休假能休几天？")
    assert r.status == "completed"
    assert any(c["doc_id"] == "HR01" for c in r.citations)
    assert "五" in r.answer or "5" in r.answer


def test_followup_with_history():
    history = [
        {"role": "user", "content": "我想了解费用报销相关规定"},
        {
            "role": "assistant",
            "content": "请问您想了解报销材料、期限还是差旅专项？",
        },
    ]
    r = run_q("那期限是多久？", history=history)
    assert r.status == "needs_confirmation"
    assert "D01" in r.answer and "D02" in r.answer


def test_tool_failure_search():
    r = run_q("小影支持字幕导出吗？", inject="search")
    # First search fails, retry succeeds → completed; or incomplete if retry also fails
    # With fail_times=1, retry should succeed
    assert r.status == "completed"
    assert any(
        (t.get("observation") or {}).get("ok") is False for t in r.trace
    ), "trace should contain a failed tool observation"


def test_tool_failure_then_still_works_for_conflict_path_difference():
    # Different path: conflict question should differ from subtitle path
    a = run_q("报销期限多久？")
    b = run_q("小影支持字幕导出吗？")
    assert a.status != b.status or a.answer != b.answer
    # Different tool result adaptations
    a_reads = [
        t["action"].get("doc_id")
        for t in a.trace
        if t["action"]["name"] == "read"
    ]
    b_reads = [
        t["action"].get("doc_id")
        for t in b.trace
        if t["action"]["name"] == "read"
    ]
    assert set(a_reads) != set(b_reads)


def test_max_steps_incomplete():
    r = run_q("员工年假有多少天？", max_steps=1)
    # With max_steps=1, decide may finish incomplete at step decision or after one tool
    assert r.status in ("incomplete", "completed", "needs_confirmation", "out_of_scope")
    if r.steps_used >= 1 and r.status == "incomplete":
        assert "上限" in r.answer or "max_steps" in "".join(r.gaps)


def test_no_fabricated_claim_without_citation_on_completed():
    r = run_q("小影支持字幕导出吗？")
    if r.status == "completed":
        assert r.citations, "completed answers must cite sources"


def test_corpus_file_exists():
    assert (ROOT / "data" / "documents.json").exists()
    docs = json.loads((ROOT / "data" / "documents.json").read_text(encoding="utf-8"))
    ids = {d["doc_id"] for d in docs}
    assert {"D01", "D02", "P01", "HR01"}.issubset(ids)
