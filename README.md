# vectormind

**One space. Three circles. Five verbs.**

A memory layer built to showcase what Elasticsearch does best — and to do
nothing else. No tables, no layers, no junction indexes: L1/L2/L3 are
*queries over a single index*, never schema.

```python
vm = await VectorMind.open(client, embed,
                           categories={"la-tortue": "…", "l-atelier": "…"})
await vm.remember(["the driver ships tonight"], tags=[["atelier"]])

focus = Focus().update(await vm.embed_one("what we're building right now"))
recall = await vm.recall("where were we?", focus=focus, k=8)

recall.l1            # inside the focus circle
recall.l2            # the vault ring
recall.by_category   # the L3 doors
```

## The three circles

| Circle | What it is | Where it lives |
|---|---|---|
| **L1 — Focus** | The moving center of attention: an exponential moving average of turn embeddings. `drift()` detects topic changes for free. | Computed. **Never stored.** |
| **L2 — Vault** | The space itself, read through fused retrieval. | The one index. |
| **L3 — Categories** | A *fixed* set of named doors. A hit is attached to its nearest door at query time — labels are computed, never written, so the taxonomy cannot swell. | Anchor vectors, seeded once. |

The hierarchy is radii, not schema: every hit carries a `ring` and a
`category`, both derived from vectors at query time. Same space for
everyone — different radii around the center.

## The one design rule

> **Fusion belongs to Elasticsearch. Shaping belongs to the client.**

*Fusion* — combining the lexical and semantic views — runs inside ES through
the native `rrf` retriever (8.14+): one request, zero Python merging.
Because the native retriever has sat behind a licensed tier, a faithful
Python RRF (same `k=60`, same window, same formula `1/(k+rank)`) stands as
an automatic fallback: the first 4xx flips a per-instance switch, and the
two paths are equivalence-tested.

*Shaping* — the small, opinionated adjustments — happens once, client-side,
after fusion, identically on both paths:

- **apax bonus** — rare-but-close documents surface. Rarity is measured
  honestly from the retrieved neighborhood (how isolated a hit is from the
  other hits), not from a corpus statistic we don't have.
- **recency** — exponential half-life decay.

Both are **additive and capped as fractions of the leader's fused score**
(`apax_cap=0.15` reads "at most +15% of the top fused score"). Shaping is
subordinate to fusion *by construction*: it can break near-ties toward
recency and rarity — its entire job — but a document below 80% of the
leader can never displace it. Every hit carries its audit trail (`rrf`,
per-view `ranks`, `bonuses`).

## Layout

```
vectormind/
├── space.py     the substrate — one index, mappings, remember/forget
├── search.py    fusion (native RRF + fallback) and shaping
├── circles.py   Focus, Categories, Recall, the VectorMind facade
└── __init__.py
tests/
└── test_vectormind.py   native/fallback equivalence, subordination
                         invariant, rings, doors, drift — no cluster needed
```

Four files, ~600 lines, zero SQL, zero external dependency beyond
`elasticsearch>=8` and your embedder (`async (list[str]) -> list[list[float]]`).

## Requirements

- Elasticsearch 8.x (native RRF needs 8.14+ and may require a licensed
  tier — the fallback covers basic/OSS deployments transparently)
- Python 3.11+

## License

MIT — © 2026 K1SS Atelier 0.

## Domu — the Hermes link (Wired)

`domu/` wires the circles into an agent runtime implementing the
MemoryProvider contract (DOMU-HERMES.md): per-turn `<memory-context>`
blocks rendered from L1/L2/L3, Synapse gates on every write (noise, size,
cosine-0.95 dedup — nothing enters the space around them), bank/scope
isolation enforced *in the query*, three tools (`domu_recall` /
`domu_remember` / `domu_forget`), focus-drift time-vectors, and the one
absolute rule stamped in the system prompt: **never embroider reality** —
an empty space yields an honest empty block.

> Signatures were written against the DOMU-HERMES contract table;
> ship `memory_provider.py` for the exact one-pass conformity check.
