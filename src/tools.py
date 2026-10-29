"""Business tools: search_docs and read_chunk, with optional failure injection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import corpus


class ToolError(RuntimeError):
    pass


class ToolBox:
    def __init__(
        self,
        docs: Optional[List[Dict[str, Any]]] = None,
        inject_fail_on: Optional[str] = None,
        fail_times: int = 1,
    ):
        self.docs = docs if docs is not None else corpus.load_documents()
        self.inject_fail_on = inject_fail_on  # "search" | "read" | None
        self.fail_times = fail_times
        self._fail_remaining = fail_times if inject_fail_on else 0
        self.call_count = 0

    def _maybe_fail(self, tool_name: str) -> None:
        if self.inject_fail_on == tool_name and self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise ToolError(f"injected failure on {tool_name}")

    def search_docs(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        self.call_count += 1
        self._maybe_fail("search")
        hits = corpus.search_documents(self.docs, query, top_k=top_k)
        return {"ok": True, "query": query, "hits": hits, "count": len(hits)}

    def read_chunk(self, doc_id: str, chunk_id: Optional[str] = None) -> Dict[str, Any]:
        self.call_count += 1
        self._maybe_fail("read")
        result = corpus.read_chunk(self.docs, doc_id, chunk_id)
        if not result.get("ok"):
            return result
        return result

    def execute(self, action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "search":
            return self.search_docs(params.get("query") or "")
        if action_name == "read":
            return self.read_chunk(params.get("doc_id") or "", params.get("chunk_id"))
        raise ValueError(f"unknown tool: {action_name}")
