# Domu — Wired memory for Hermes agents

> *Le bien faire, le durable, l'intelligent.*

4 fichiers. ~500 lignes. Zéro SQL. Domu remplace Hindsight comme MemoryProvider Hermes.

## Architecture

```
vectormind/        ← L1/L2/L3 space (4 files)
domu/provider.py   ← MemoryProvider ABC (359 lines)
domu/synapse.py    ← filter + dedup (79 lines)
```

## Quick start

```python
from domu import DomuProvider

provider = DomuProvider(
    es_url="http://localhost:9200",
    bank_id="kage",
    embedder="BAAI/bge-small-en-v1.5",
    categories={"la-tortue": "tortue", "l-atelier": "driver"}
)
agent._memory_manager.add_provider(provider)
```

## La règle absolue

**Jamais broder la réalité.** Si pas de résultat, le dire. Si apax orphelin, l'avouer. Si call externe échoue, répondre "je ne peux pas."

C'est la leçon du 18 juin (Buunshin), du 2 juillet (la chanson fantôme), et du 5 juillet (Renaissance).

## Licence

MIT — K1SS Atelier 0, Besançon.
