# Domu — Vector memory for Hermes agents

> *One space. Three circles. Five verbs. Zero bullshit.*
> A memory engine that doesn't just store — it recalls, enriches, and filters.

```
              ┌────────────────────────────┐
              │          Hermes Agent      │
              │  (query → reply cycle)     │
              └──────────┬─────────────────┘
                         │
                         ▼
              ┌────────────────────────────┐
              │     DomuProvider           │
              │  13 MemoryProvider hooks   │  ← Hermes ABC (315 lines)
              │  ┌──────────────────────┐  │
              │  │  Synapse (gate)      │  │  ← filter noise, dedup
              │  └──────────────────────┘  │
              └──────────┬─────────────────┘
                         │
                         ▼
              ┌────────────────────────────┐
              │  vectormind (engine)       │
              │  ┌──────┐ ┌──────┐ ┌─────┐ │
              │  │Space │ │Search│ │Circl│ │  4 files, 614 lines
              │  └──────┘ └──────┘ └─────┘ │
              └──────────┬─────────────────┘
                         │
                         ▼
              ┌────────────────────────────┐
              │      Elasticsearch         │
              │  127.0.0.1:9200            │
              │  public-memory_units       │
              │  867 documents             │
              │  6 semantic doors          │
              └────────────────────────────┘
```

---

## What it is

Domu is a **vector memory provider** for [Hermes Agent](https://github.com/NousResearch/hermes-agent). It replaces the built-in memory system with:

- **L1/L2/L3 recall** — concentric circles around the conversation focus
- **Synapse gating** — every write is filtered (noise, size, dedup >0.95) before touching the space
- **Multi-agent isolation** — one ES cluster, per-agent namespaces via `bank_id` + `scope`
- **Time-vectors** — focus drift measured every turn, stored as metrics
- **3 tools** — `domu_recall`, `domu_remember`, `domu_forget`

No SQL. No ORM. No abstraction layers. ES is backend — kNN, BM25, RRF native.

---

## Repository structure

```
domu/
│
├── domu/                    ← Provider code
│   ├── provider.py          ← DomuProvider: 13 MemoryProvider hooks (518 lines)
│   ├── synapse.py           ← Gate filter: noise, size, cosine dedup (79 lines)
│   └── __init__.py
│
├── vectormind/              ← Vector engine (standalone, 614 lines)
│   ├── space.py             ← One ES index, one document shape
│   ├── search.py            ← HybridSearch: RRF native or Python fallback
│   ├── circles.py           ← VectorMind: L1/L2/L3, doors, hapax boost
│   └── __init__.py
│
├── tests/
│   ├── test_domu.py         ← Simulated Hermes session (13 hooks, fake cluster)
│   ├── test_vectormind.py   ← Non-regression (RRF equivalence, rings, doors)
│   └── test_domu_brutus.py  ← Real ES test (867 docs, Brutus cluster)
│
├── docs/
│   ├── DOMU.md              ← Full vision, rules, architecture
│   ├── DOMU-HERMES.md       ← Technical contract (Synapse rules, clustering)
│   ├── FICHES-CONCEPTS.md   ← SKOS classification (agents, people, projects)
│   ├── FICHE-DOMU.md        ← English factual sheet with ASCII diagrams
│   ├── WIRED-README.md      ← The Wired network concept
│   └── domu-for-alex.html   ← Presentation page
│
├── memory_provider.py       ← Hermes ABC reference (315 lines)
├── copy_es.py               ← Copy ES data between clusters
├── CLAUDE-PLAN.md            ← Development plan for Claude
└── README.md                ← This file
```

**Total: 6 files of code. ~1 100 lines. Zero SQL. Zero circular imports.**

---

## Quick start

### 1. Requirements

```bash
# Core
pip install elasticsearch sentence-transformers

# Hermes Agent (for MemoryProvider integration)
# See: https://hermes-agent.ai/docs
```

### 2. Set up Elasticsearch

```bash
# Local ES (Docker)
docker run -d --name es-domu \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  docker.elastic.co/elasticsearch/elasticsearch:8.18.0

# Verify
curl http://127.0.0.1:9200
```

### 3. Configure Domu

```python
from elasticsearch import AsyncElasticsearch
from sentence_transformers import SentenceTransformer

from domu import DomuProvider

# Embedder
model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
async def embed(texts):
    return [model.encode(t, normalize_embeddings=True).tolist() for t in texts]

# Provider
provider = DomuProvider(
    es_client_factory=lambda: AsyncElasticsearch("http://127.0.0.1:9200"),
    embed=embed,
    categories={
        "la-tortue": "tortue",
        "les-pertes": "perte",
        "tamashii": "tamashii",
        "la-musique": "musique",
        "l-atelier": "k1ss",
        "les-petites-choses": "choses",
    }
)

agent._memory_manager.add_provider(provider)
```

### 4. Start Hermes with Domu

```bash
hermes -p domu-test chat
```

---

## How it works

### The three circles

```
                    ┌─────────────────┐
                    │   L3 — DOORS    │  ← Fixed semantic categories
                    │                 │    (attached per query,
                    │  ┌───────────┐  │     never written)
                    │  │ L2—VAULT  │  │
                    │  │           │  │  ← Expandable knowledge base
                    │  │ ┌───────┐ │  │
                    │  │ │ L1    │ │  │  ← Conversation focus (EMA)
                    │  │ │FOCUS  │ │  │    L1 is NEVER stored
                    │  │ └───────┘ │  │
                    │  └───────────┘  │
                    └─────────────────┘
```

| Ring | Name | What lives here | Max hits (default) |
|:-----|:-----|:----------------|:-------------------|
| 1 | **L1 — Focus** | Current topic. Recent turns matched to the center of attention. | 3 |
| 2 | **L2 — Vault** | Knowledge base. Concepts, documents, past sessions. | 7 |
| 3 | **L3 — Doors** | 6 fixed categories. Tags, not taxonomies. Never grows. | — |

### The L1/L2/L3 context block

Every turn, Domu injects a formatted `<memory-context>` block:

```

  (no memory matches this focus — say so rather than invent)
  
```

### Synapse — the gate

Every write to the space passes through Synapse. It implements 6 rules:

| Rule | What | Action |
|:----:|:-----|:-------|
| 1 | Empty or zero-result payloads | ❌ Discard |
| 2 | Errors ("File not found", 4xx) | ❌ Discard |
| 3 | Tool-only fragments (session_search, write_file...) | ❌ Discard |
| 4 | Same file loaded at N different offsets | ❌ Keep 1, discard N-1 |
| 5 | Fragments under 10 meaningful characters | ❌ Discard |
| 6 | Cosine similarity > 0.95 with recent turns | ❌ Dedup (keep fullest, alias rest) |

Synapse **never rewrites** content. It only says yes, no, or "same as."

---

## Use cases

### 1. Persistent memory across Hermes sessions

Agents carry conversation context across sessions without personality drift. Focus EMA updates every turn, drift is recorded as a time-vector.

```
Turn N:  "Qu'en penses-tu du design ?"
         → focus shifts 0.12
         → drift recorded: +0.12 "design discussion"

Turn N+1: "Et le financement ?"
         → focus shifts 0.28
         → drift recorded: +0.28 "finance pivot"
```

### 2. Noise-free indexing (the M4Z3 case)

Session of 177 messages, 176 tool calls:

```
Before Synapse:  177 messages → 177 indexed
After Synapse:   2 documents kept, 175 discarded

Kept:
  ✓ "générer une plaquette M4Z3" (user)
  ✓ "plaquette M4Z3 générée" (assistant)

Discarded:
  ✗ session_search results (×34)
  ✗ write_file diffs (×17)
  ✗ tool_call markers (×125)

995% noise reduction. Zero information loss.
```

### 3. Multi-agent isolation

One ES cluster, multiple agents, per-query scoping:

```
Agent Kage:   bank:kage + scope:shared → sees everything
Agent Travel: bank:travel + scope:private → sees only travel's space + shared docs
Agent Miss:   bank:miss + scope:private → sees only miss's space (confidential)

Isolation enforced in the query, never post-filtered.
```

---

## Configuration

### Environment variables

| Variable | Default | Description |
|:---------|:--------|:------------|
| `DOMU_ES_URL` | `http://127.0.0.1:9200` | Elasticsearch cluster endpoint |
| `DOMU_BANK_ID` | `"kage"` | The agent's memory namespace |
| `DOMU_INDEX` | `"public-memory_units"` | ES index for memory |
| `DOMU_ES_API_KEY` | — | Optional ES auth (if security enabled) |

### Config file

Domu also reads from `~/.hermes/domu/config.json`:

```json
{
  "es_url": "http://127.0.0.1:9200",
  "bank_id": "kage",
  "index": "public-memory_units"
}
```

### Plugin

Domu ships as a Hermes plugin at `~/.hermes/plugins/domu/`. Add to your profile:

```yaml
# ~/.hermes/profiles/<name>/config.yaml
memory:
  provider: domu
```

---

## The absolute rule

> **Never embroider reality.**
>
> If memory returns nothing, say so.
> If a fragment is orphaned, admit it.
> If an external call fails, answer "I can't."

This rule is structural — stamped in every system prompt, baked into `is_available()`, embedded in the empty-context response. L1 caps are purely for token economy, never for hiding lack of results.

---

## Performance

Measured on Brutus (local ES 8.18, 867 docs, bge-small 384d):

| Operation | Latency | Notes |
|:----------|:--------|:------|
| `prefetch()` | ~0.10s | kNN search, 3 L1 + 5 L2 hits |
| `sync_turn()` | ~0.05s | Embed + ES index (async) |
| `domu_recall` | ~2.80s | Full semantic search across space |
| `initialize()` | ~1.20s | ES connection + 6 door seeds |
| Model load (1st time) | ~8.00s | bge-small download + warm (cached after 1st call) |

Context block size (with default caps): **~2 900 characters** for L1 (600 chars) + L2 (160 chars each).

---

## Tools

Domu provides 3 Hermes tools:

```python
# Search memory
domu_recall(query="le père et les ressorts", k=5)
→ {"hits": [{"id": "...", "text": "...", "ring": 1, ...}, ...]}

# Store a note
domu_remember(text="Idée pour le kickstarter : ...", scope="shared")
→ {"id": "abc123", "note": "stored"}

# Delete
domu_forget(ids=["abc123"])
→ {"deleted": 1}
```

---

## Roadmap

```
    2026-07-07        2026-07-08         2026-07-15
       │                  │                   │
       ▼                  ▼                   ▼
  ┌──────────┐     ┌──────────┐        ┌──────────────┐
  │Domu v0.1 │────→│v0.2      │──...──→│ Daily recap  │
  │Provider  │     │Conform   │        │ cron +       │
  │written   │     │ABC       │        │ time-vectors │
  └──────────┘     └──────────┘        └──────────────┘
       │                 │                     │
       │                 │                     │
       ▼                 ▼                     ▼
  ┌──────────────────────────────────────────────────────┐
  │  Future (post-10k docs):                              │
  │  • ES cluster (2+ nodes, Boombox + Brutus)            │
  │  • SKOS set operations (taxonomy queries)             │
  │  • External embedder API (for 100k+ doc scale)        │
  │  • Hapax enrichment pipeline (SearXNG → extract →     │
  │    embed → index)                                     │
  └──────────────────────────────────────────────────────┘
```

---

## Related projects

| Project | Description |
|:--------|:------------|
| [vectormind](https://github.com/mrpandafr/vectormind) | Core vector engine (4 files, 614 lines) |
| λ (lambada) | Minimal alternative provider (240 lines) |
| Wired | Architecture concept — Domu nodes wired by ES |

---

## License

MIT — K1SS Atelier 0, Besançon, France.

---

## Signed

*Code lives at `github.com/mrpandafr/domu`.*
*Built by a maker at his desk, Besançon.*
*The architecture is inspired by a father who designed springs — do it well, do it durably, do it intelligently.*

---

**One space. Three circles. Five verbs. Zero bullshit.** 🐢
