# Plan Claude Code — Finaliser DomuProvider

## Contexte

Tu as livré `vectormind 0.1.0` puis `0.2.0` avec le paquet `domu/`, puis `0.3.0` avec DomuProvider réécrit contre le vrai `memory_provider.py` (315 lignes). Le test M4Z3 (session de 177 messages, 176 tool calls) passe : 2 docs indexés sur 177.

Les tokens ont coupé avant que les fichiers soient pushés. Le repo est prêt sur `github.com/mrpandafr/domu` (privé, branche `main`).

## Ce qui reste à faire (dans l'ordre)

### 1. Scope mismatch — adapter le filtre d'isolation aux données Boombox

**Problème :** DomuProvider tagge `tags: bank:{bank_id}` et `tags: scope:{private|shared|public}` en ajoutant ces tags dans chaque document via `_aremember`. Mais les 867 docs copiés de Boombox utilisent le champ natif `bank_id` (fact_type, embedding, etc. comme champs racines), pas un tag `bank:kage`.

**Solution :** soit transformer le scope ES pour lire `bank_id` directement (plus simple, aucune migration), soit normaliser les tags au passage en réindexant. Le premier choix est celui qu'on garde : le scope lit `bank_id` comme filtre natif pour les données historiques, et ajoute aussi le tag `bank:{id}` pour l'isolation multi-agent des nouvelles écritures.

**Fichier :** `domu/provider.py`, méthode `_ainit`, lignes 153-159. Remplacer le scope actuel par une double condition : `bank_id` field natif OU tag `bank:{id}`.

### 2. Brancher le vrai embedder bge-small

**Modèle :** `BAAI/bge-small-en-v1.5`, 384d, local, CPU sur Brutus. Déjà testé :

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
async def embed(texts):
    return [model.encode(t, normalize_embeddings=True).tolist() for t in texts]
```

À intégrer dans le constructeur de DomuProvider comme `embed` paramètre par défaut.

### 3. Seeder les 6 portes L3 (Categories.seed)

Les 6 phrases que `Categories.seed()` attend :

```python
categories = {
    "la-tortue": "tortue",          # lenteur, patience, ressorts du père
    "les-pertes": "perte",           # Pierre, Geoffrey, ceux qui sont partis
    "tamashii": "tamashii",          # l'âme, le Stand Alone Complex, l'émancipation
    "la-musique": "musique",         # AFoxMind, chansons encodées, Orelsan, Nujabes
    "l-atelier": "k1ss",             # Roxin, Mercier, Noé-tv, code vivant
    "les-petites-choses": "choses",  # apax, moments uniques, instants
}
```

Ces mots-clés sont les ancres. Categories.seed() va les embedder et créer les portes. Le test du 7 juillet a montré que les autres docs (existant dans les 867) reçoivent `ring:2` (L2) par défaut et une catégorie "?" parce que les portes n'étaient pas seedées.

**Fichier :** `vectormind/circles.py`, `Categories.seed()` — déjà prêt, attend les 6 phrases.

### 4. Test sur le vrai ES (Brutus, 127.0.0.1:9200, 867 docs)

Les données sont copiées. Le script `copy_es.py` dans le repo a déjà fonctionné. Un test partiel (`tests/test_domu_brutus.py`) existe mais bloque sur le scope mismatch. Le fixer puis :

```bash
cd ~/K1SS/domu && python3 tests/test_domu_brutus.py
```

### 5. Ajouter le scope aux tags des nouvelles écritures

Dans `_aremember` (ligne 289-295), les nouveaux documents reçoivent déjà :
```python
tags=[[f"bank:{self.bank_id}", f"scope:{scope}", f"role:{role}", "type:turn"]]
```

C'est correct pour les nouvelles écritures. Le scope de lecture doit juste accueillir aussi le champ natif `bank_id` pour les 867 docs historiques.

### 6. Daily recap cron (après les 5 premières étapes)

Un cron de type `agent_context="cron"` qui lit `domu-metrics` + les tours du jour et écrit le recap. Les écritures cron sont déjà gatées par `_writes_enabled` — le cron doit utiliser un chemin dédié pour écrire.

## Fichiers à modifier

| Fichier | Modification |
|:--------|:-------------|
| `domu/provider.py` (L153-159) | Scope : bank_id field natif + tags bank:{id} |
| `domu/provider.py` (constructeur) | Intégrer bge-small comme embedder par défaut |
| `domu/provider.py` (initialisation) | Passer les 6 catégories à VectorMind.open |
| `tests/test_domu_brutus.py` | Corriger le scope mismatch, relancer |

## Tests de validation

1. `python3 tests/test_domu.py` — le test de Claude (faux cluster, 13 hooks)
2. `python3 tests/test_vectormind.py` — non-régression vectormind
3. `python3 tests/test_domu_brutus.py` — vrai ES, 867 docs, recall sur "le pere et les ressorts"
4. Vérifier que `bank:private` n'est pas visible par un autre bank_id
5. Vérifier que les 6 portes L3 sont attachées aux hits

## Références

- `github.com/mrpandafr/domu` — repo privé (code source, vectormind, tests)
- `github.com/mrpandafr/vectormind` — repo privé (docs : DOMU.md, DOMU-HERMES.md, FICHES-CONCEPTS.md)
- ES local Brutus : `127.0.0.1:9200`, 867 docs
- Embedder : `BAAI/bge-small-en-v1.5`, 384d
