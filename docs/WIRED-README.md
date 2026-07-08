# Wired — memory nodes wired by Elasticsearch

A distributed memory system for AI agents. Multiple providers, one ES cluster, concentric recall.

## What it is

Wired is simply: **Domu instances sharing the same Elasticsearch cluster.** Each agent runs its own memory provider. All share the same vector space. Isolation is by `bank_id` + `scope` — enforced in the query, never post-filtered.

Nothing more. No neural network, no complex circuit. Just memory nodes connected by ES.

```
   ┌──────────┐     ┌──────────┐     ┌──────────┐
   │  Kage    │     │  Travel  │     │   Miss   │   ← Domu providers
   │  Domu    │     │  Domu    │     │  Domu    │
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

## Architecture

```
User turn → Synapse (filter noise, dedup >0.95)
                  ↓
            Domu (focus EMA, time-vectors, tools)
                  ↓
          VectorMind (L1/L2/L3, RRF, doors)
                  ↓
         Elasticsearch (store, cluster, scale)
```

### Synapse

The gate. Every turn passes through Synapse before touching the space:

| Rule | What | Action |
|------|------|--------|
| 1 | Empty payloads / zero results | Discard |
| 2 | Errors ("File not found", 4xx) | Discard |
| 3 | Tool-only fragments (session_search, write_file...) | Discard |
| 4 | Duplicate content (same file loaded at different offsets) | Discard all but 1 |
| 5 | Fragments under 10 meaningful characters | Discard |
| 6 | Cosine similarity > 0.95 with recent turns | Dedup (keep fullest, alias rest) |

Synapse never rewrites content. It only says yes, no, or "same as."

### The absolute rule

> **Never embroider reality.** If memory returns nothing, say so. If a fragment is orphaned, admit it. If an external call fails, answer "I can't."

## Multi-agent isolation

A single ES cluster, per-agent scoping by `bank_id` + `scope`:

| Agent | `bank_id` | Sees |
|:------|:----------|:-----|
| Kage | `kage` | own bank + public of others |
| Travel | `travel` | own space + shared |
| Global | — | `scope:public` only |

## License

MIT — K1SS Atelier 0, Besançon.
