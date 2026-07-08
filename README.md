# Domu — vector memory for Hermes agents

The first implementation of the **Wired** architecture. A drop-in MemoryProvider for Hermes Agent that replaces the built-in memory with vector-powered concentric recall over Elasticsearch.

```
domu/
├── provider.py    ← MemoryProvider ABC (518 lines, 13 hooks)
├── synapse.py     ← Gate filter (noise, size, dedup >0.95)
├── vectormind/    ← Vector engine (4 files, 614 lines, zero SQL)
├── memory_provider.py ← ABC reference (315 lines)
├── docs/
│   ├── DOMU.md       → vision, rules, architecture
│   ├── WIRED-README.md → the network concept
│   ├── FICHE-DOMU.md → English factual sheet with diagrams
│   └── domu-for-alex.html → presentation page
└── tests/
    ├── test_domu.py        ← simulated Hermes session (13 hooks)
    ├── test_vectormind.py  ← non-regression
    └── test_domu_brutus.py ← real ES test (867 docs)
```

## Quick start

```bash
pip install elasticsearch sentence-transformers

# Create ES index, copy data, configure Hermes profile
cp copy_es.py ~/ && python3 copy_es.py
hermes -p domu-test chat
```

```python
from domu import DomuProvider

provider = DomuProvider(
    es_client_factory=lambda: AsyncElasticsearch("http://localhost:9200"),
    embed=embed_fn,        # bge-small-en-v1.5, 384d
    categories={...},      # 6 semantic doors
    config={"index": "public-memory_units", "bank_id": "kage"}
)
agent._memory_manager.add_provider(provider)
```

## Configuration

| Env var | Default | Description |
|:--------|:--------|:------------|
| `DOMU_ES_URL` | `http://127.0.0.1:9200` | Elasticsearch endpoint |
| `DOMU_BANK_ID` | `kage` | Memory bank (per-agent namespace) |
| `DOMU_INDEX` | `public-memory_units` | ES index name |

Also reads from `~/.hermes/domu/config.json`.

## What Domu gives you

- **L1/L2/L3 context** — before every turn, a `<memory-context>` block with focus (L1), vault (L2), and doors (L3)
- **Synapse filtering** — tool calls, empty results, duplicates are filtered before indexing
- **Time-vectors** — focus drift recorded per turn in `domu-metrics` index
- **Multi-agent isolation** — `bank_id` + `scope` enforced in the query
- **3 tools** — `domu_recall`, `domu_remember`, `domu_forget`
- **Daily recap cron** — auto-generated summary of each day's activity

## Design values

- **One file per concern.** 6 files total. No circular imports.
- **Zero SQL.** ES is the backend — kNN, BM25, RRF natively.
- **The absolute rule:** never embroider reality.

## License

MIT — K1SS Atelier 0, Besançon.
