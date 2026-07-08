# Domu (童夢)

## À quoi ça sert

Domu est un moteur de mémoire vectorielle pour agents IA. C'est la **première vraie solution vectorielle d'expansion de corpus** — un système qui ne se contente pas de stocker des embeddings, mais qui *expend* la mémoire en enrichissant chaque concept par des appels externes (SearXNG, Wikipedia, extraction web) avant de l'intégrer à l'espace vectoriel.

Il permet à un agent de :
- Se souvenir d'une conversation entre sessions (L1)
- Consulter une base de connaissance vectorielle extensible (L2)
- Naviguer par catégories sémantiques fixes (L3)
- Enrichir automatiquement les concepts rares (apax) par recherche externe
- Détecter les changements de sujet (focus drift)
- Filtrer le bruit technique (tool calls, résultats vides) avec Synapse

## Définition du mot japonais

**Domu (童夢)** = enfant (童) + rêve (夢).

Titre d'un manga de Katsuhiro Ōtomo (créateur d'Akira, qui a donné son nom au Corpus Tamashii). L'histoire d'un enfant aux pouvoirs psychiques dans une cité HLM.

Le nom porte la philosophie du projet : un système mémoire qui garde la pureté de vision d'un enfant — simple, direct, sans couches d'abstraction inutiles. Une architecture qui tient dans 4 fichiers, pas dans 598 Ko de `memory_engine.py`.

## Réponse à quel problème

Avant Domu, les systèmes de mémoire pour agents IA utilisaient des bases relationnelles (PostgreSQL) avec des couches d'ORM pour simuler le vectoriel. Résultat : des fichiers monolithiques de 598 Ko, des imports circulaires, des modules entiers pour des fonctionnalités que le moteur de recherche gère nativement.

Domu résout ce problème par une architecture radicalement plus simple :

| Approche classique | Domu |
|:-------------------|:------|
| Fichier monolithique (598 Ko) | ~800 lignes total |
| Base relationnelle + ORM | Elasticsearch natif (kNN, BM25, RRF) |
| Couches d'abstraction multiples | Zéro SQL, zéro ORM |
| Imports circulaires | Dépendances propres |
| Modules bloat (dates, langues, entités) | Pas de bloat — ES gère nativement |

## Installation

Requirements :
- Python 3.13+
- Elasticsearch 8.18+ (accès à un cluster, local ou distant)
- sentence-transformers (pour l'embedder bge-small)
- Hermes Agent (pour l'intégration MemoryProvider)

```bash
pip install elasticsearch sentence-transformers numpy
```

**Sur Brutus (notre stack de test) :**
Un ES local tourne sur 127.0.0.1:9200 avec 867 docs copiés de la prod Boombox via `copy_es.py`.

**Configuration :**
```python
from domu import DomuProvider

provider = DomuProvider(
    es_client_factory=lambda: AsyncElasticsearch("http://127.0.0.1:9200"),
    embed=embed_fn,        # bge-small-en-v1.5, 384d
    categories={...},      # 6 portes L3
    config={"index": "public-memory_units", "bank_id": "kage"}
)
agent._memory_manager.add_provider(provider)
```

## Architecture

```
vectormind/ (4 fichiers, 614 lignes)
├── space.py     — un seul index ES, document minimal (text, vector, tags, at, meta)
├── search.py    — HybridSearch : RRF natif ES 8.14+ ou fallback Python
├── circles.py   — VectorMind : L1 (focus), L2 (vault), L3 (portes fixes)
└── __init__.py  — exports VectorMind, Focus, Categories, Space

domu/ (2 fichiers, ~600 lignes)
├── provider.py  — DomuProvider : 13 hooks MemoryProvider Hermes (ABC)
└── synapse.py   — Synapse : filtre (bruit, taille) + dédup (cos > 0.95)
```

**Les trois refus de conception (Claude, 7 juillet 2026) :**

1. **L1 n'est jamais stocké.** Focus est une moyenne mobile exponentielle des tours — le centre bouge, l'espace non. `drift()` mesure le changement de sujet gratuitement.
2. **L3 n'écrit jamais d'étiquette.** Les portes sont des ancres fixes ; `attach()` rattache un hit à sa porte la plus proche pour la durée de la requête. La taxonomie ne peut pas gonfler.
3. **Le façonnage ne domine jamais.** Les bonus (apax, recency) sont des fractions du score du leader. Un document sous 80% du leader ne peut pas le déplacer mathématiquement.

## Cas d'usage

**1. Mémoire persistante pour Hermes**
Un agent garde le fil d'une conversation à travers les sessions. Chaque tour est indexé dans ES, le focus est mis à jour (EMA), les time-vectors (focus_drift) sont tracés.

**2. Filtrage Synapse (M4Z3 real case)**
Session de 177 messages dont 176 tool calls. Synapse indexe 2 documents utiles — "plaquette M4Z3 générée" entre, `session_search` n'entre jamais. Le ratio mesuré : 176/177 messages jetés (99.4%).

**3. Isolation multi-agent**
Un seul cluster ES, plusieurs agents :
- `bank:kage` + `scope:shared` — Kage voit tout sauf private
- `bank:travel` + `scope:private` — Travel voit son espace + shared
- `scope:public` — visible par tous les agents

**4. Test sur données réelles (Brutus)**
867 docs copiés de Boombox. Recall sur "le père et les ressorts" retourne 5 hits pertinents. Les catégories L3 sont en "?" car les 6 portes ne sont pas encore seedées.

## Wired

Wired est le nom du système complet. Pas juste Domu — tout l'enchaînement :

```
Blob Hindsight (Sessions brutes + concepts + tool calls)
  → Synapse (filtre : bruit, taille, dédup cos > 0.95)
  → Domu/Provider (13 hooks MemoryProvider, focus EMA, time-vectors)
  → vectormind (L1/L2/L3, RRF natif ES, portes fixes)
  → ES (stocke en cluster, index public-memory_units, ~900 docs)
```

Le nom vient du fait que tout est connecté (wired) dans ce circuit. Les leçons du 4 juillet (Doc → Info → Action) sont wired à la règle absolue du provider. Le fond de la pelote (confession, clubs, TAILS) est wired au droit au repos (kill switch). Wired ne brode pas — il relie ce qui existe.

## Futures évolutions

1. **Daily recap cron** — lit `domu-metrics` + les tours du jour et écrit un résumé quotidien (type `agent_context="cron"`, les écritures cron sont déjà gatées par design)
2. **Time-vectors dashboard** — visualisation des focus_drift, gpu_usage, tokens_turn, apax_rate dans un chronogramme
3. **Clustering ES** — quand la stack dépassera 10k docs, passage à 2+ nœuds ES (Boombox + Brutus)
4. **Embedder choix** — bge-small 384d local (actuel) → possibilité OpenAI ou autre API si scale > 100k docs
5. **Set operations SKOS** — classification scientifique des concepts par ensembles + inclusion/exclusion
6. **Categories.seed** — les 6 portes L3 en attente d'être seedées avec leurs 6 phrases

## Licence

MIT — K1SS Atelier 0, Besançon, France.

## Signé

*Fiche factuelle — rédigée par Kage le 8 juillet 2026.*
*Code sur `github.com/mrpandafr/domu`.*
*L'architecture s'inspire des ressorts du père : le bien faire, le durable, l'intelligent.*
