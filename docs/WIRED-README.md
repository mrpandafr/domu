# WIRED — Memory nodes wired by Elasticsearch

> *The simplest possible distributed memory system: Domu instances sharing an ES cluster.*

WIRED is not a product. It's an **architecture** — multiple memory providers (Domu, λ, or any ABC-compliant provider) connected by the same Elasticsearch cluster. Each agent owns its `bank_id`. All share the same vector space. Isolation is by `bank_id` + `scope` — enforced in the query, never post-filtered.

```
   ┌──────────┐     ┌──────────┐     ┌──────────┐
   │  Kage    │     │  Travel  │     │   Miss   │   ← Memory providers
   │  Domu    │     │  Domu    │     │  Domu    │   (Hermes ABC)
   └────┬─────┘     └────┬─────┘     └────┬─────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
                  ┌──────▼──────┐
                  │  ES CLUSTER │        ← The wire
                  │  public-    │
                  │  memory_    │
                  │  units      │
                  │              │
                  │  bank_id     │  ← Per-agent namespace
                  │  + scope     │  ← private | shared | public
                  └─────────────┘
```

---

## Components

```
┌──────────────────────┐
│     User / Agent     │
└──────────┬───────────┘
           │ query
           ▼
┌──────────────────────┐
│     Synapse (gate)   │  ← Filter noise, dedup >0.95
│  worth_remembering?  │
│  dedup()             │
└──────────┬───────────┘
           │ clean text
           ▼
┌──────────────────────┐
│   Domu / λ / any     │  ← MemoryProvider (Hermes ABC)
│   13 lifecycle hooks │
│   prefetch, sync,    │
│   tools, metrics     │
└──────────┬───────────┘
           │ recall / remember
           ▼
┌──────────────────────┐
│    Vectormind        │  ← Vector engine
│   L1/L2/L3 space     │
│   RRF fusion         │
│   Doors, hapax       │
└──────────┬───────────┘
           │ kNN / BM25 / RRF
           ▼
┌──────────────────────┐
│  Elasticsearch 8.x   │  ← The wire
│  127.0.0.1:9200     │
│  public-memory_units │
│  867 docs, 3 banks   │
└──────────────────────┘
```

---

## How it works

### Per-agent namespace

Every document in ES carries tags:

```python
tags = [
    f"bank:{bank_id}",   # Which agent owns this
    f"scope:{scope}",    # private | shared | public
    f"role:{role}",      # user | assistant | subagent
    "type:turn",         # What kind of document
]
```

### Query-time isolation

The scope is enforced **in the query**, never post-filtered:

```python
scope = {"bool": {"should": [
    {"term": {"tags": f"bank:{self.bank_id}"}},   # Own bank
    {"term": {"tags": "scope:public"}},             # Public docs
], "minimum_should_match": 1}}
```

### Visibility rules

| Agent accessing | Sees bank | Sees docs | Scopes visible |
|:---------------|:----------|:----------|:---------------|
| Kage | `kage` | Own + public | private, shared, public |
| Travel | `travel` | Own + shared + public | shared, public |
| Miss | `miss` | Own only | private |
| Global | — | public only | public |

---

## The absolute rule

> **Never embroider reality.**
> If memory returns nothing, say so.
> If a fragment is orphaned, admit it.
> If an external call fails, answer "I can't."

This rule is structural — it passes through every component in the chain.

---

## Data flow

### Turn lifecycle

```
1. User sends query
2. Hermes calls prefetch_all()
3. Each provider returns a <memory-context> block (L1/L2/L3)
4. Hermes builds system prompt + injected context
5. Model generates reply
6. Hermes calls sync_turn(user_content, assistant_content)
7. Provider filters through Synapse, indexes in ES
8. Focus updates (EMA). Drift recorded in metrics.
```

### The M4Z3 case (noise filtering in action)

```
Session: 177 messages
  → 176 tool calls (session_search, write_file, web_search...)
  → 2 meaningful contents (user query + assistant response)

Before WIRED:    177 documents indexed
After WIRED:      2 documents kept, 175 filtered by Synapse
Ratio:           1.1% useful, 98.9% noise removed
Zero information loss.
```

---

## Providers

| Provider | Lines | ES | Embedder | Focus | Synapse | Status |
|:---------|:-----|:---|:---------|:------|:--------|:-------|
| [Domu](https://github.com/mrpandafr/domu) | ~600 | Async | bge-small 384d | EMA | ✅ | ✅ Live |
| λ (lambada) | 240 | Sync | bge-small 384d | — | Partial | ✅ Live |

---

## Getting started

```bash
# 1. Start ES
docker run -d -p 9200:9200 -e "discovery.type=single-node" \
  docker.elastic.co/elasticsearch/elasticsearch:8.18.0

# 2. Install a provider (Domu or λ)
pip install git+https://github.com/mrpandafr/domu.git

# 3. Configure Hermes
# Add to ~/.hermes/config.yaml:
# memory:
#   provider: domu

# 4. Chat
hermes chat
```

---

## Development roadmap

```
    Current (July 2026)            Future (Q3-Q4 2026)
    ┌─────────────────────┐     ┌──────────────────────────┐
    │ Single ES node      │ ──→ │ Multi-node cluster       │
    │ 867 docs            │     │ 10k+ docs                │
    │ 3 banks             │     │ N banks (per agent)      │
    │ 6 doors             │     │ Dynamic doors (post-SKOS)│
    │ Focus EMA           │     │ Multi-focus stacking     │
    │ Hapax boost         │     │ Enrichment pipeline     │
    └─────────────────────┘     └──────────────────────────┘
```

---

## License

MIT — K1SS Atelier 0, Besançon.

---

## Signed

*Architecture by K1SS Atelier 0, July 2026.*
*The simplest possible distributed memory: Domu nodes wired by ES.*
*Inspired by a father who designed springs — do it well, do it durably, do it intelligently.* 🐢

---
## License

MIT — ©  

See [LICENSE](LICENSE) for the full text.
