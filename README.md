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
├── domu/                    ← Server-side package
│   ├── provider.py          ← DomuProvider: 13 MemoryProvider hooks (518 lines)
│   ├── synapse.py           ← Gate filter: noise, size, cosine dedup (79 lines)
│   ├── server.py            ← HTTP server wrapping DomuProvider (185 lines)
│   └── __init__.py
│
├── vectormind/              ← Vector engine (standalone, 614 lines)
│   ├── space.py             ← One ES index, one document shape
│   ├── search.py            ← HybridSearch: RRF native or Python fallback
│   ├── circles.py           ← VectorMind: L1/L2/L3, doors, hapax boost
│   └── __init__.py
│
├── hermes-plugin/           ← Thin Hermes plugin (no heavy deps)
│   ├── __init__.py          ← DomuClient: MemoryProvider ABC over HTTP (209 lines)
│   └── plugin.yaml
│
├── cron/
│   └── daily_recap.py       ← Daily summary → space (run as cron job)
│
├── tests/
│   ├── test_domu.py         ← Simulated Hermes session (13 hooks, fake cluster)
│   ├── test_vectormind.py   ← Non-regression (RRF equivalence, rings, doors)
│   └── test_domu_brutus.py  ← Real ES test (867 docs, Brutus cluster)
│
├── docs/
│   ├── DOMU.md              ← Full vision, rules, architecture
│   ├── DOMU-HERMES.md       ← Technical contract (Synapse rules, clustering)
│   └── FICHES-CONCEPTS.md   ← SKOS classification (agents, people, projects)
│
├── run_server.py            ← Entry point: starts the Domu server
├── copy_es.py               ← Utility: copy ES data between clusters
└── README.md                ← This file
```

**Two processes, zero shared state. Zero SQL. Zero circular imports.**

---

## Quick start

Domu runs as two processes: a **memory server** and a **Hermes plugin**. The server holds all the heavy dependencies (Elasticsearch, sentence-transformers, asyncio). The plugin is stdlib-only and talks to the server over localhost HTTP.

### 1. Requirements

```
Python 3.11+
Elasticsearch 8+
```

### 2. Start Elasticsearch

```bash
# Docker (single node, no auth)
docker run -d --name domu-es \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  docker.elastic.co/elasticsearch/elasticsearch:8.18.0

curl http://127.0.0.1:9200  # → {"name":"...","cluster_name":"..."}
```

### 3. Start the Domu server

```bash
git clone https://github.com/mrpandafr/domu
cd domu
pip install elasticsearch sentence-transformers
python run_server.py
# → domu server on 127.0.0.1:7430
```

The server exposes `GET /health` and a set of `POST` routes. It stays running in the background — one process per machine, shared by all Hermes sessions.

```bash
# Override defaults
DOMU_ES_URL=http://192.168.1.10:9200 DOMU_BANK_ID=kage python run_server.py --port 7430
```

### 4. Install the Hermes plugin

```bash
ln -s /path/to/domu/hermes-plugin ~/.hermes/plugins/domu
```

The plugin is a single file with zero non-stdlib imports. It implements the full `MemoryProvider` ABC and delegates every call to the server via `urllib`.

### 5. Configure

```bash
mkdir -p ~/.hermes/domu
cat > ~/.hermes/domu/config.json << 'EOF'
{
  "bank_id": "your-agent-name",
  "index": "public-memory_units",
  "server_url": "http://127.0.0.1:7430"
}
EOF
```

Activate in your Hermes profile:

```yaml
# ~/.hermes/profiles/<name>/config.yaml
memory:
  provider: domu
```

### 6. Run

```bash
# Terminal 1 — server (keep running)
python run_server.py

# Terminal 2 — agent
hermes --profile your-profile
```

On startup, the plugin calls `GET /health`. If the server responds, `is_available()` returns `True`, Hermes calls `initialize()` → `POST /session/init`, and the provider is live. Every subsequent turn: `prefetch()` → `POST /prefetch` → L1/L2/L3 block injected before the model sees the message.

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

### Server — environment variables

| Variable | Default | Description |
|:---------|:--------|:------------|
| `DOMU_ES_URL` | `http://127.0.0.1:9200` | Elasticsearch endpoint |
| `DOMU_BANK_ID` | `"kage"` | Default memory bank |
| `DOMU_INDEX` | `"public-memory_units"` | ES index |
| `DOMU_ES_API_KEY` | — | ES auth (optional) |
| `DOMU_SERVER_URL` | `http://127.0.0.1:7430` | Server URL (read by the plugin) |

### Plugin — `~/.hermes/domu/config.json`

All keys are optional (env vars take precedence):

```json
{
  "server_url": "http://127.0.0.1:7430",
  "bank_id": "kage",
  "index": "public-memory_units",
  "l1_size": 1,
  "l2_size": 3,
  "l1_max_chars": 600,
  "l2_max_chars": 300
}

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


