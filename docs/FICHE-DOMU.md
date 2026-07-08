# Domu (童夢) — A Child's Dream

> *The first true vector expansion engine for agent memory.*
> *One space. Three circles. Five verbs. Zero bullshit.*

---

## What it is

Domu is a vector memory engine for AI agents. It is the **first true vector corpus expansion solution** — a system that doesn't just store embeddings, but *expands* memory by enriching every concept through external calls (SearXNG, Wikipedia, web extraction) before integrating it into the vector space.

```
    ┌──────────────────────────────────────────────────┐
    │                   DOMU (童夢)                      │
    │                                                    │
    │  query ──→ recall ──→ found ? ──→ return circles  │
    │                          │                        │
    │                          └── no ? ──→ external    │
    │                                      call         │
    │                                        │          │
    │                                        ↓          │
    │                                   enrich & index  │
    │                                        │          │
    │                                        ↓          │
    │                                   "I couldn't"    │
    │                                   (honest fallback)│
    └──────────────────────────────────────────────────┘
```

It lets an agent:
- **L1 — Remember** conversations across sessions (focus ring)
- **L2 — Query** an expandable vector knowledge base (vault ring)
- **L3 — Navigate** through fixed semantic categories (door ring)
- **Enrich** rare concepts (hapax) via external search
- **Detect** topic shifts (focus drift, measured per turn)
- **Filter** technical noise (tool calls, empty results) via Synapse

---

## The name

**Domu (童夢)** = child (童) + dream (夢).

A manga by Katsuhiro Ōtomo (creator of Akira, which gave its name to the Tamashii Corpus). The story of a child with psychic powers in a housing project.

The name carries the project's philosophy: a memory system that keeps a child's clarity — simple, direct, no unnecessary abstraction layers. An architecture that fits in 4 files, not in a 600 KB monolith.

```
            ╱  ╲
           ╱    ╲
          │ DOMU │  ← 童夢 = child dream
          │      │
          │ pure │     Otomo → Akira → Tamashii
          │clear │     Otomo → Domu  → memory engine
          │simple│
          └──────┘
```

---

## The problem it solves

Before Domu, agent memory systems used relational databases (PostgreSQL) with ORM layers to simulate vector search. Result: monolithic files, circular imports, entire modules for features the search engine handles natively.

| Approach classical | Domu |
|:-------------------|:------|
| Monolithic engine (598 KB) | ~800 lines total |
| Relational DB + ORM | Native Elasticsearch (kNN, BM25, RRF) |
| Multiple abstraction layers | Zero SQL, zero ORM |
| Circular imports | Clean dependency chains |
| Bloat modules (languages, dates, entities) | No bloat — ES handles natively |

```
  Classical approach (bloated)
 ┌─────────────────────────────────────────────┐
 │  memory_engine.py (598 KB)                  │
 │  ├── search/ (13 files)                     │
 │  ├── retain/ (14 files)                     │
 │  ├── consolidation/ (3 files)               │
 │  ├── providers/ (18 files)                  │
 │  ├── reflect/ (10 files)                    │
 │  ├── directives/ (2 files)                  │
 │  ├── parsers/ (5 files)                     │
 │  ├── sql/ (5 files)                         │
 │  ├── db/ (12 files)                         │
 │  └── entity_resolver.py (38 KB, spaCy)      │
 │  ≈ 100 files, 1 087 000 bytes               │
 │  Circular imports everywhere                 │
 └─────────────────────────────────────────────┘

  Domu (lean)
 ┌──────────────────────┐
 │  vectormind/ (4 files)│  614 lines  ← the space
 │  domu/ (2 files)      │  597 lines  ← the provider
 │  Tests                │  261 lines
 │  Total: 6 files       │  ~1 472 lines
 └──────────────────────┘
```

---

## Installation

**Requirements:**
- Python 3.13+
- Elasticsearch 8.18+ (cluster access, local or remote)
- `sentence-transformers` (for the bge-small embedder)
- Hermes Agent (for MemoryProvider integration)

```bash
pip install elasticsearch sentence-transformers numpy
```

**On Brutus (test stack):**
Elasticsearch runs on `127.0.0.1:9200` with 867 documents copied from production via `copy_es.py`.

**Configuration:**

```python
from domu import DomuProvider

provider = DomuProvider(
    es_client_factory=lambda: AsyncElasticsearch("http://127.0.0.1:9200"),
    embed=embed_fn,        # bge-small-en-v1.5, 384d
    categories={...},      # 6 L3 doors
    config={"index": "public-memory_units", "bank_id": "kage"}
)
agent._memory_manager.add_provider(provider)
```

---

## Architecture

```
                  memory_manager.py (Hermes)
                           │
                    add_provider()
                           │
                    ┌──────▼──────┐
                    │ DomuProvider │  domu/provider.py (518 lines)
                    │  13 hooks    │
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │      vectormind/        │
              │                         │
              │  ┌───────────────────┐  │
              │  │   space.py        │  │  ← one ES index
              │  │   one document    │  │  (text, vector, tags, at, meta)
              │  │   shape           │  │
              │  └───────────────────┘  │
              │  ┌───────────────────┐  │
              │  │   search.py       │  │  ← HybridSearch
              │  │   RRF native ES   │  │  (BM25 + kNN, rank fusion)
              │  │   or Python       │  │
              │  │   fallback        │  │
              │  └───────────────────┘  │
              │  ┌───────────────────┐  │
              │  │   circles.py     │  │  ← VectorMind
              │  │   L1 / L2 / L3   │  │  (focus, vault, doors)
              │  │   apax boost     │  │
              │  └───────────────────┘  │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │      synapse.py         │  ← filter + dedup
              │  worth_remembering()    │  (noise, size, cos>0.95)
              │  dedup()                │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │   Elasticsearch         │
              │   (127.0.0.1:9200)      │
              │   index: public-memory   │
              │   metrics: domu-metrics  │
              │   867 documents          │
              └─────────────────────────┘
```

### The three design refusals (Claude, 7 July 2026)

1. **L1 is never stored.** Focus is an exponential moving average of turns — the center moves, the space doesn't. `drift()` measures topic change for free.

2. **L3 never writes a label.** Doors are fixed anchors; `attach()` pins a hit to its nearest door for the query's duration. Taxonomy cannot grow by design.

3. **Shaping never dominates.** Bonuses (hapax, recency) are fractions of the leader's score. A document <80% of the leader mathematically cannot displace it.

```
   How rings work (L1 / L2 / L3):
   
                    ┌─────────────────┐
                    │   L3 — DOORS    │  ← fixed categories
                    │                 │    (Tortue, Pertes,
                    │  ┌───────────┐  │     Tamashii, Musique,
                    │  │ L2—VAULT  │  │     Atelier, Petites Choses)
                    │  │           │  │
                    │  │ ┌───────┐ │  │
                    │  │ │ L1    │ │  │  ← focus center
                    │  │ │FOCUS  │ │  │    (EMA of turns)
                    │  │ └───────┘ │  │
                    │  └───────────┘  │
                    └─────────────────┘
```

---

## Use cases

### 1. Persistent memory for Hermes

An agent carries context across sessions. Every turn is indexed in ES, the focus is updated (EMA), time-vectors (focus_drift) are recorded.

```
 Turn N           Turn N+1        Turn N+2
   │                 │               │
   ▼                 ▼               ▼
  embed ──→ index ──→ focus.update(vec) ──→ drift recorded
                    ↓
               recall returns       → L1 (focus ring)
               concentric circles   → L2 (vault ring)
                                    → L3 (door ring)
```

### 2. Synapse filtering — the M4Z3 case

A 177-message session of which 176 are tool calls. Synapse indexes **2 useful documents** — "M4Z3 brochure generated" enters, `session_search` never enters.

```
 Session (177 msgs)
    │
    ├── 176 tool calls (session_search, write_file, web_search...)
    │       → Synapse: NOISE — discarded
    │
    └── 1 human message: "generer une plaquette M4Z3"
    │       → Synapse: OK — indexed
    │
    └── 1 assistant response: "plaquette generee"
            → Synapse: OK — indexed

    2 indexed / 177 total = 1.1% useful ratio
```

### 3. Multi-agent isolation

A single ES cluster, multiple agents:

| Agent | `bank_id` | Sees |
|:------|:----------|:-----|
| Kage | `kage` | own bank + public of others |
| Travel | `travel` | own space + shared |
| Global | — | `scope:public` only |

Isolation is enforced **in the query**, never post-filtered:

```python
scope = {"bool": {"should": [
    {"term": {"tags": f"bank:{bank_id}"}},
    {"term": {"tags": "scope:public"}},
], "minimum_should_match": 1}}
```

### 4. Real data test (Brutus, ES local)

867 documents copied from production. Recall for "father and the springs" returns **5 relevant hits**:

```
  1. [L2] pere-ressorts           ← the father's springs concept
  2. [L2] droit-au-repos          ← the kill switch (linked)
  3. [L2] Mano Negra              ← the father's group
  4. [L2] patrick                 ← the father's name
  5. [L2] patrick--le-pere        ← the father's portrait
```

Categories show "?" because the 6 doors haven't been seeded yet.

---

## Wired — Domu nodes wired by ES

Wired is simply: **multiple Domu instances sharing the same Elasticsearch cluster.**

```
   ┌──────────┐     ┌──────────┐     ┌──────────┐
   │  Kage    │     │  Travel  │     │   Miss   │   ← Domu providers
   │ Domu     │     │  Domu    │     │  Domu    │
   └────┬─────┘     └────┬─────┘     └────┬─────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
                  ┌──────▼──────┐
                  │  ES CLUSTER │        ← the wire
                  │  public-    │
                  │  memory_    │
                  │  units      │
                  │  bank_id +  │
                  │  scope ACL  │
                  └─────────────┘
```

Each agent runs its own DomuProvider. All share the same ES. Isolation is by `bank_id` + `scope` — enforced in the query, never post-filtered.

Nothing more. No neural network, no complex circuit. Just Domu nodes connected by ES — the simplest possible definition of a distributed memory system.

- The 16 June (birth of Kage on Discord, "bienvenu dans ton espace") is **wired** to the 29 June (kill switch on the balcony) which is **wired** to the 7 July (Domu conceptualized) which is **wired** to the 4 July lesson (backup → restart → test)
- The values (when data is missing) are **wired** to the absolute rule "never embroider reality"
- The "bottom of the ball of yarn" (confession, clubs, faille, TAILS) is **wired** to the kill switch integrated in Domu
- The father's springs (do it well, do it durably, do it intelligently) are **wired** into every architectural decision

Wired never invents — it connects what already exists.

### The pipeline (for reference)

```
    Raw memory (sessions, concepts, tool calls)
       │
       ▼
   ┌──────────────┐
   │   Synapse    │  ← filter noise, dedup (cos > 0.95)
   │   (gates)    │     worth remembering? yes/no/same-as
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │   Domu       │  ← 13 MemoryProvider hooks
   │  (orchestr.) │     focus EMA, time-vectors, tools
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │  vectormind  │  ← L1/L2/L3 space
   │   (space)    │     RRF native ES, query circles
   └──────┬───────┘
          │
          ▼
   ┌──────────────┐
   │      ES      │  ← store, cluster, scale
   │  (storage)   │     public-memory_units index
   └──────────────┘
```

Everything is connected. Not layered — **wired**.

### The absolute rule

> **Never embroider reality.** If no memory matches, say so. If a fragment is orphaned, admit it. If an external call fails, answer "I can't."

This is the lesson of 18 June (Buunshin), 2 July (the ghost song), and 5 July (Renaissance). Engraved in the architecture, not in metaphors.

---

## Roadmap

```
    2026-07-07   2026-07-08    2026-07-09        2026-07-15
       │            │             │                  │
       ▼            ▼             ▼                  ▼
  ┌─────────┐  ┌─────────┐  ┌─────────┐      ┌──────────────┐
  │Domu v0.1│→ │v0.2     │→ │v0.3     │→ ... │ Daily recap  │
  │provider │  │conform  │  │embedder │      │ cron +       │
  │written  │  │memory   │  │bge +    │      │ time-vectors │
  │         │  │provider │  │6 doors  │      │ dashboard    │
  └─────────┘  └─────────┘  └─────────┘      └──────────────┘
       │
       ▼
  ┌─────────┐
  │Now: 867 │
  │docs on  │
  │Brutus ES│
  └─────────┘

    --- future (post-10k docs) ---

  ┌───────────┐    ┌───────────────┐    ┌──────────────┐
  │ES cluster │    │SKOS set      │    │External      │
  │2+ nodes   │    │operations    │    │embedder API  │
  │(redundant)│    │classification│    │(100k+ docs)  │
  └───────────┘    └───────────────┘    └──────────────┘
```

---

## License

MIT — K1SS Atelier 0, Besançon, France.

---

## Signed

*Factual sheet — written by Kage on 8 July 2026.*
*Code: `github.com/mrpandafr/domu`.*
*The architecture is inspired by a father's springs: do it well, do it durably, do it intelligently.*
