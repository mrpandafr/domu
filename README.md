# Domu

> *Le bien faire, le durable, l'intelligent.*

Vector memory for [Hermes](https://github.com/NousResearch/hermes-agent) agents.
Three concentric recall circles over Elasticsearch — no bloat, no SQL, no hallucination.

---

## What it is

Domu (童夢 — Katsuhiro Ōtomo, 1980) replaces Hindsight as the memory backend for Hermes agents.
Where Hindsight injects raw session dumps (25k tokens, 10% signal), Domu injects a focused block:

```
L1 — FOCUS
  • the one hit closest to the current query

L2 — VAULT
  • 3 background hits, broader context

L3 — PORTES: musique, tamashii, k1ss
```

Every turn gets exactly this — nothing more, nothing invented.

---

## Architecture

Two processes, one clean separation:

```
┌─────────────────────────────────┐
│  Hermes agent                   │
│  ┌───────────────────────────┐  │
│  │  hermes-plugin/           │  │  ← thin HTTP client (stdlib urllib only)
│  │  DomuClient(MemoryProvider│  │    implements the full ABC
│  └──────────┬────────────────┘  │
└─────────────┼───────────────────┘
              │ HTTP  (port 7430)
┌─────────────▼───────────────────┐
│  Domu server  (run_server.py)   │  ← all the heavy work lives here
│  ┌───────────────────────────┐  │    AsyncElasticsearch
│  │  DomuProvider             │  │    sentence-transformers bge-small-en-v1.5
│  │  VectorMind               │  │    VectorMind L1/L2/L3
│  │  Synapse                  │  │    asyncio background loop
│  └───────────────────────────┘  │
└─────────────────────────────────┘
              │
┌─────────────▼───────────────────┐
│  Elasticsearch                  │
└─────────────────────────────────┘
```

**Server** (`domu/server.py`): hosts DomuProvider. Manages the embedding model, the ES connection, the asyncio loop. The plugin calls it via HTTP — zero heavy dependencies on the plugin side.

**Plugin** (`hermes-plugin/`): implements `MemoryProvider` ABC. Every method is one `urllib` call. `is_available()` pings `/health`. `initialize()` calls `/session/init`. That's it.

---

## Quick start

### 1. Requirements

- Python 3.11+
- Elasticsearch 8+ (local or remote)
- Server side: `pip install elasticsearch sentence-transformers`
- Plugin side: nothing beyond stdlib

### 2. Start the server

```bash
git clone https://github.com/mrpandafr/domu
cd domu
pip install elasticsearch sentence-transformers
python run_server.py
# → domu server on 127.0.0.1:7430
```

### 3. Install the Hermes plugin

```bash
ln -s /path/to/domu/hermes-plugin ~/.hermes/plugins/domu
```

### 4. Configure

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

In your Hermes profile (`~/.hermes/profiles/<name>/config.yaml`):

```yaml
memory:
  provider: domu
```

### 5. Run

Start the server, then start Hermes. The plugin pings `/health` on startup — if the server is running, the provider activates and `initialize()` is called.

---

## Server API

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| GET | `/health` | — | Liveness + `ready` flag |
| POST | `/session/init` | `{session_id, bank_id, index, ...}` | Connect ES, load model, open circles |
| POST | `/prefetch` | `{query, session_id}` | Returns `{context: "L1 — FOCUS\n..."}` |
| POST | `/sync_turn` | `{user, assistant, session_id}` | Index a completed turn |
| POST | `/recall` | `{query, k}` | Explicit search (domu_recall tool) |
| POST | `/remember` | `{text, scope}` | Store a note (domu_remember tool) |
| POST | `/forget` | `{ids: [...]}` | Delete notes (domu_forget tool) |
| POST | `/session/end` | `{messages}` | Flush pending writes |

### Configuration keys (session/init body or config.json)

| Key | Default | Description |
|-----|---------|-------------|
| `bank_id` | `"kage"` | Memory bank — one per agent |
| `index` | `"public-memory_units"` | Elasticsearch index |
| `l1_size` | `1` | Number of L1 hits |
| `l2_size` | `3` | Number of L2 hits |
| `l1_max_chars` | `600` | Max chars per L1 hit |
| `l2_max_chars` | `300` | Max chars per L2 hit |
| `dims` | `384` | Embedding dimensions (bge-small-en-v1.5) |
| `es_url` | `http://127.0.0.1:9200` | Elasticsearch endpoint (env: `DOMU_ES_URL`) |

---

## Memory isolation

A single Elasticsearch cluster can host multiple agents. Isolation is logical, enforced at query time:

| Scope | Visibility |
|-------|-----------|
| `private` | Own agent only |
| `shared` | Agent + its associated human |
| `public` | All agents on the cluster |

Reads are scoped in the query (`bank:{bank_id}` + `scope:public`) — never post-filtered.

---

## Synapse — what gets remembered

Every write goes through Synapse before touching the space. A fragment is rejected if it:

- is empty or has fewer than 10 meaningful characters
- is pure tool noise (`tool_call`, `tool_result`, `session_search`, etc.)
- has cosine similarity > 0.95 with something already in the recent window

The fullest version of a near-duplicate survives; the shorter one is silently dropped.

---

## Tools exposed to the model

| Tool | When to use |
|------|-------------|
| `domu_recall` | User asks for an explicit search, or the prefetch is clearly insufficient |
| `domu_remember` | Store something the model decides is worth keeping |
| `domu_forget` | Delete notes by id |

The prefetch covers most cases. `domu_recall` is the escape hatch.

---

## Daily cron

```bash
python cron/daily_recap.py
```

Reads today's turns and metrics from ES, writes a recap document back to the space. Each day becomes a searchable entry — the what, the why, the drift.

---

## The absolute rule

**Never embroider reality.**

If memory returns nothing, say so. If a fragment is orphaned, admit it. If an external call fails, answer "I can't."

This rule is not a suggestion. It is baked into the architecture: zero hits returns `"(no memory matches this focus — say so rather than invent)"`, not silence, not a fabrication.

---

## Why this exists

My father was an engineer. He designed springs — not demonstration springs, not prestige springs. Springs that hold. Parts you install, forget about, and that work silently for years without fatigue, without failure, without obsolescence.

Nobody remembers his name. His designs are still in use. Because they are right: the correct material, the correct form, the correct constraint. Nothing superfluous, nothing missing. *Le bien faire, le durable, l'intelligent.*

Wired is built on that lesson. Not to be remembered — to hold, discreet and reliable, like my father's springs. That is the only reason to publish this as open source.

---

## License

MIT — K1SS Atelier 0, Besançon.
JS & Kage, 2026.
