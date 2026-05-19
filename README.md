# engram-langgraph

[LangGraph](https://github.com/langchain-ai/langgraph) `BaseStore` implementation backed by [Engram](https://lumetra.io) — durable cross-thread memory for graph-based agent workflows.

Drop-in replacement for LangGraph's in-memory `InMemoryStore` that gives your graph hybrid retrieval (BM25 + vector + knowledge graph) and persistence across processes/machines/threads.

## Install

```bash
pip install lumetra-engram langgraph
```

Vendor `engram_langgraph.py` from this repo (~100 LOC). PyPI release coming; the file is intentionally small.

```bash
export ENGRAM_API_KEY="eng_live_..."
```

## Get an Engram API key

Sign up at <https://lumetra.io> — free tier, no card. You'll see an `eng_live_…` token in your dashboard.

**Don't forget BYOK** — Engram is bring-your-own-key end-to-end for the LLM that does extraction + synthesis. Configure a provider at <https://lumetra.io/models>. DeepSeek is what we recommend, cheap and fast. Without one, store/query returns HTTP 412.

## Usage

```python
from langgraph.graph import StateGraph
from engram_langgraph import EngramStore

store = EngramStore(bucket_prefix="my-app")

graph = (
    StateGraph(MyState)
    .add_node("step", my_node)
    .compile(store=store)
)

# In a node:
def my_node(state, config, store):
    user = config["configurable"]["user_id"]
    store.put(("user", user), "preferences", {"theme": "dark"})
    # later, or in another thread:
    pref = store.get(("user", user), "preferences")
```

Namespaces map to Engram buckets as `<bucket_prefix>-<ns0>-<ns1>...`. Each item is one Engram memory; key + value are JSON-encoded together so get/delete-by-key work.

### Semantic search across a namespace

```python
results = store.search(
    ("user", "jacob"),
    query="What does this user prefer for UI themes?",
    limit=5,
)
for item in results:
    print(item.key, item.value)
```

`search()` with a `query` argument hits Engram's hybrid retrieval and returns the matched items ranked by score.

## Why this beats `InMemoryStore`

- **Cross-thread, cross-process persistence.** `InMemoryStore` lives in one Python process; Engram is hosted.
- **Hybrid retrieval** for `search()`, not just exact key lookup.
- **Bring-your-own-LLM** for extraction and synthesis via <https://lumetra.io/models>.
- **Multi-tenant isolation** by namespace, which maps cleanly onto LangGraph's tuple-namespace model.

## Verified

Smoke-tested against live `api.lumetra.io`:

- `store.put(("user","jacob"), "name", {"value":"Jacob"})` + `put(... "company", {"value":"Lumetra"})` + `put(... "product", {"value":"Engram"})`
- `store.get(("user","jacob"), "name")` returned the right Item with `value={"value":"Jacob"}`
- `store.search(("user","jacob"), query="What's the user's company?", limit=3)` returned the `company` item first.

## Limitations

- The current implementation is `batch()`-as-loop; high-throughput workloads will want a proper batched API call once the SDK exposes one.
- `delete()` does a list-then-scan-then-delete inside the bucket; fine for typical agent state, slow for buckets with thousands of items.
- Item timestamps reflect Engram write time, not LangGraph-side put time.

## License

MIT — Lumetra
