"""Load and index synthetic corporate documents."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "documents.json"


def load_documents(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = path or DEFAULT_DATA
    with p.open(encoding="utf-8") as f:
        docs = json.load(f)
    if not isinstance(docs, list):
        raise ValueError("documents.json must be a list")
    return docs


def _tokenize(text: str) -> set:
    # Character bigrams + whitespace-split tokens for Chinese/English mix.
    text = text.lower()
    toks = set(re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", text))
    chars = re.sub(r"\s+", "", text)
    bigrams = {chars[i : i + 2] for i in range(max(0, len(chars) - 1))}
    return toks | bigrams


def search_documents(docs: List[Dict[str, Any]], query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    q = _tokenize(query)
    if not q:
        return []
    scored: List[Dict[str, Any]] = []
    for doc in docs:
        blob = " ".join(
            [doc.get("title", ""), " ".join(doc.get("tags", []))]
            + [c.get("text", "") for c in doc.get("chunks", [])]
        )
        dt = _tokenize(blob)
        score = len(q & dt)
        # Soft boost for exact keyword hits in title/tags
        title_tags = _tokenize(doc.get("title", "") + " " + " ".join(doc.get("tags", [])))
        score += 2 * len(q & title_tags)
        if score < 3:
            continue
        preview = doc["chunks"][0]["text"][:80] if doc.get("chunks") else ""
        scored.append(
            {
                "doc_id": doc["doc_id"],
                "title": doc.get("title"),
                "version_date": doc.get("version_date"),
                "score": score,
                "preview": preview,
            }
        )
    scored.sort(key=lambda x: (-x["score"], x["doc_id"]))
    return scored[:top_k]


def get_document(docs: List[Dict[str, Any]], doc_id: str) -> Optional[Dict[str, Any]]:
    for d in docs:
        if d["doc_id"] == doc_id:
            return d
    return None


def read_chunk(
    docs: List[Dict[str, Any]], doc_id: str, chunk_id: Optional[str] = None
) -> Dict[str, Any]:
    doc = get_document(docs, doc_id)
    if doc is None:
        return {"ok": False, "error": f"unknown doc_id: {doc_id}"}
    chunks = doc.get("chunks") or []
    if chunk_id:
        for c in chunks:
            if c["chunk_id"] == chunk_id:
                return {
                    "ok": True,
                    "doc_id": doc_id,
                    "title": doc.get("title"),
                    "version_date": doc.get("version_date"),
                    "chunk_id": chunk_id,
                    "text": c["text"],
                }
        return {"ok": False, "error": f"unknown chunk_id: {chunk_id} in {doc_id}"}
    # Return all chunks concatenated with ids
    return {
        "ok": True,
        "doc_id": doc_id,
        "title": doc.get("title"),
        "version_date": doc.get("version_date"),
        "chunks": [{"chunk_id": c["chunk_id"], "text": c["text"]} for c in chunks],
    }
