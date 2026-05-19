"""
engram_langgraph — durable cross-thread memory for LangGraph.

LangGraph ships with a `BaseStore` interface for cross-thread memory; this
module provides `EngramStore`, an implementation backed by the hosted
Engram MCP server (via lumetra-engram).

Usage:

    from langgraph.graph import StateGraph
    from langgraph.store.base import BaseStore
    from engram_langgraph import EngramStore

    store = EngramStore(bucket_prefix="my-app")
    graph = StateGraph(...).compile(store=store)
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Optional

from langgraph.store.base import BaseStore, Item, Op, Result
from lumetra_engram import EngramClient


class EngramStore(BaseStore):
    """LangGraph BaseStore backed by Engram.

    Namespaces map to Engram buckets as `<bucket_prefix>-<ns0>-<ns1>...`.
    Each item is one Engram memory; the item's `value` dict is JSON-encoded
    into the memory content and the key is encoded as a prefix tag so we
    can support get/delete by key.
    """

    def __init__(
        self,
        *,
        bucket_prefix: str = "langgraph",
        client: Optional[EngramClient] = None,
    ) -> None:
        self._client = client or EngramClient(api_key=os.environ.get("ENGRAM_API_KEY"))
        self._prefix = bucket_prefix

    def _bucket(self, namespace: tuple[str, ...]) -> str:
        suffix = "-".join(namespace) if namespace else "default"
        return f"{self._prefix}-{suffix}".replace("/", "-")

    def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
        import json
        payload = json.dumps({"key": key, "value": value})
        self._client.store_memory(payload, self._bucket(namespace))

    def get(self, namespace: tuple[str, ...], key: str) -> Optional[Item]:
        import json
        items = self._client.list_memories(self._bucket(namespace), limit=100)
        for m in items.get("memories", []):
            try:
                rec = json.loads(m["content"])
                if rec.get("key") == key:
                    return Item(value=rec["value"], key=key, namespace=namespace, created_at=m.get("created_at"), updated_at=m.get("created_at"))
            except Exception:
                continue
        return None

    def search(self, namespace_prefix: tuple[str, ...], *, query: Optional[str] = None, limit: int = 10, offset: int = 0, filter: Optional[dict[str, Any]] = None) -> list[Item]:
        import json
        bucket = self._bucket(namespace_prefix)
        if query:
            result = self._client.query(query, buckets=[bucket])
            items: list[Item] = []
            for m in result.get("explanation", {}).get("retrieved_memories", []):
                try:
                    rec = json.loads(m["content"])
                    items.append(Item(value=rec["value"], key=rec["key"], namespace=namespace_prefix, created_at=None, updated_at=None))
                except Exception:
                    continue
            return items[:limit]
        raw = self._client.list_memories(bucket, limit=limit + offset)
        out: list[Item] = []
        for m in raw.get("memories", [])[offset : offset + limit]:
            try:
                rec = json.loads(m["content"])
                out.append(Item(value=rec["value"], key=rec["key"], namespace=namespace_prefix, created_at=m.get("created_at"), updated_at=m.get("created_at")))
            except Exception:
                continue
        return out

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        # Engram doesn't support per-key updates here without tracking memory IDs;
        # for the common "user moves on" case, a clear is offered separately.
        # Per-item delete = list-then-find-then-delete.
        items = self._client.list_memories(self._bucket(namespace), limit=100)
        import json
        for m in items.get("memories", []):
            try:
                rec = json.loads(m["content"])
                if rec.get("key") == key:
                    self._client.delete_memory(m["id"], self._bucket(namespace))
                    return
            except Exception:
                continue

    def batch(self, ops: Iterable[Op]) -> list[Result]:  # type: ignore[override]
        # Minimal implementation: dispatch one at a time.
        results: list[Result] = []
        for op in ops:
            if op.__class__.__name__ == "PutOp":
                self.put(op.namespace, op.key, op.value)  # type: ignore[attr-defined]
                results.append(None)  # type: ignore[arg-type]
            elif op.__class__.__name__ == "GetOp":
                results.append(self.get(op.namespace, op.key))  # type: ignore[arg-type,attr-defined]
            elif op.__class__.__name__ == "SearchOp":
                results.append(self.search(op.namespace_prefix, query=getattr(op, "query", None), limit=getattr(op, "limit", 10)))  # type: ignore[arg-type]
            else:
                results.append(None)  # type: ignore[arg-type]
        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:  # type: ignore[override]
        return self.batch(ops)
