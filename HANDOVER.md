# Handover Claude — Domu/Wired

> Reprise le 8 juillet 2026 après reset tokens.
> Contexte complet dans `github.com/mrpandafr/domu` (privé, branche `main`).

## Ce que tu as déjà livré

Tu as livré `vectormind 0.3.0` avec le paquet `domu/` complet :
- `domu/provider.py` (518 lignes) — DomuProvider, 13 hooks MemoryProvider
- `domu/synapse.py` (79 lignes) — Synapse (filtre bruit/taille/dédup 0.95)

**Réécrit contre le vrai `memory_provider.py` (315 lignes).** Interface synchrone de bout en bout, event loop en daemon thread, agent_context gates les écritures, sync_turn ignore les 176 tool calls sur 177 messages (cas M4Z3).

**Tests sur faux cluster : verts.** 13 hooks validés.

## Ce qui reste à faire (dans l'ordre)

### 🔴 1. Scope mismatch (CRITIQUE)

DomuProvider tagge `tags: bank:{bank_id}` et `tags: scope:{scope}` dans `_aremember()` (L289-295). Les 867 docs copiés de Boombox sur Brutus en `copy_es.py` utilisent le champ natif `bank_id` — pas un tag.

**Solution :** le scope de lecture dans `_ainit()` (L153-159) doit accepter les DEUX formats — champ `bank_id` OU tag `bank:{id}` :

```python
# Scope actuel (filtre seulement par tag — ne trouve RIEN sur les 867 docs historiques)
visibility = {"bool": {"should": [
    {"term": {"tags": f"bank:{self.bank_id}"}},
], "minimum_should_match": 1}}

# Scope corrigé (tag OU champ natif bank_id)
visibility = {"bool": {"should": [
    {"term": {"tags": f"bank:{self.bank_id}"}},
    {"term": {"bank_id": self.bank_id}},  # ← docs historiques Boombox
], "minimum_should_match": 1}}
```

### 🟡 2. Brancher le vrai embedder bge-small

Modèle : `BAAI/bge-small-en-v1.5`, 384d, CPU. Déjà testé :

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
async def embed(texts):
    return [model.encode(t, normalize_embeddings=True).tolist() for t in texts]
```

À intégrer comme valeur par défaut dans le constructeur de DomuProvider.

### 🟡 3. Seeder les 6 portes L3

Categories.seed attend ces 6 ancres :

```python
categories = {
    "la-tortue": "tortue",          # lenteur, patience, ressorts du père
    "les-pertes": "perte",           # Pierre, Geoffrey, ceux qui sont partis
    "tamashii": "tamashii",          # l'âme, Stand Alone Complex
    "la-musique": "musique",         # AFoxMind, chansons encodées
    "l-atelier": "k1ss",             # Roxin, Mercier, Noé-tv, code vivant
    "les-petites-choses": "choses",  # apax, moments uniques
}
```

### 🟢 4. Valider avec le test sur vrai ES Brutus

```bash
cd ~/K1SS/domu && python3 tests/test_domu_brutus.py
```

Les données sont copiées (867 docs sur `127.0.0.1:9200`). Le test est écrit mais échoue à cause du scope mismatch (étape 1). Une fois corrigé, il devrait retourner `DOMU TEST PASSED ✅`.

### 🟢 5. Daily recap cron (bonus)

Un cron `agent_context="cron"` qui lit `domu-metrics` + les tours du jour. Les écritures cron sont déjà gatées par `_writes_enabled` — le cron doit utiliser un chemin dédié.

## Fichiers modifiés

| Fichier | Changement |
|:--------|:-----------|
| `domu/provider.py` L153-159 | Scope : bank_id natif + tag bank:{id} |
| `domu/provider.py` constructeur | Embedder bge-small par défaut |
| `domu/provider.py` init | Passer les 6 categories à VectorMind.open |
| `domu/provider.py` L289-295 | _aremember : garder les tags + le bank_id field |
| `tests/test_domu_brutus.py` | Corriger pour scope corrigé |

## Architecture (rappel)

```
domu/
├── provider.py     → 13 hooks MemoryProvider (518l)
├── synapse.py      → filtre + dedup (79l)
├── vectormind/     → space.py, search.py, circles.py (614l)
├── tests/          → test_domu.py, test_vectormind.py, test_domu_brutus.py
├── memory_provider.py  → ABC référence (315l)
├── copy_es.py      → script copie Boombox→Brutus
├── docs/
│   ├── DOMU.md         → vision Wired, règle absolue
│   ├── DOMU-HERMES.md  → contrat technique MemoryProvider
│   ├── FICHES-CONCEPTS.md → classification SKOS
│   ├── FICHE-DOMU.md   → fiche factuelle anglaise (diagrams)
│   └── domu-for-alex.html → page présentation
└── CLAUDE-PLAN.md  → ce plan
```

## Règles absolues

1. **Never embroider reality** — si pas de résultat, le dire. Pas d'invention.
2. **Synapse décide ce qui entre** — noise, taille <10 car, dedup >0.95. Rien n'est perdu (gardé dans ES).
3. **Isolation dans la requête, jamais en post-filtre** — bank_id + scope dans le bool/should.

Bon retour. 🐢
