# Connexion Domu → Hermes

> Interface entre notre moteur de mémoire et Hermes Agent.
> Basé sur `memory_manager.py` (1086 lignes) + `memory_provider.py` (315 lignes).

## Le contrat

Hermes a un `MemoryManager` qui orchestre **un seul** provider externe à la fois.
`MemoryProvider` est une classe abstraite (ABC) avec ces méthodes à implémenter :

| Méthode | Quand ? | Ce qu'on renvoie |
|:--------|:---------|:------------------|
| `name` | Construction | `"domu"` |
| `is_available` | Démarrage | `True` si ES + vectormind sont prêts |
| `initialize` | Start session | Connecte ES, charge vectormind |
| `shutdown` | Stop session | Ferme le client ES |
| `system_prompt_block` | Début de session | Instructions pour l'agent : "Tu as accès à Domu..." |
| `prefetch` | **Chaque tour** (SYNC) | L1 context : cercles concentriques autour du message |
| `queue_prefetch` | **Chaque tour** (BACKGROUND) | Prépare le L1 du prochain tour |
| `sync_turn` | **Après chaque tour** | Indexe le tour dans ES (embedding + text) |
| `get_tool_schemas` | Démarrage | Outils exposés : `domu_recall`, `domu_remember`, `domu_forget` |
| `handle_tool_call` | Quand l'agent invoque un outil | Exécute l'outil Domu correspondant |
| `on_turn_start` | Début de tour | Compteur de tours |
| `on_session_end` | Fin de session | Flush des données |
| `on_session_switch` | Changement de session (/new, /resume) | Reset du focus |
| `on_pre_compress` | Avant compression contexte | Retourne le résumé L1 à garder |
| `on_memory_write` | Quand un outil mémoire Hermes écrit | Sync optionnelle |
| `on_delegation` | Fin de subagent | Indexe le résultat |

## Exemple réel (bloc Hindsight, 7 juillet 2026)

Bloc reçu en session avec 17 concepts, ~20k tokens :

| Concept | Utile pour Domu ? | Raison |
|:--------|:------------------|:-------|
| honnetete-ignorance | ✅ L1 | Philosophie fondatrice "pas broder" |
| corpus-tamashii-vision | ✅ L1 | Architecture corpus, directement lié |
| architecture-sagesse | ✅ L2 | .db → concepts |
| rituel-repos | ✅ L2 | Sommeil, consolidation |
| culture-manga-js | ✅ L3 | Domu (Otomo), nommage |
| tortue-pas-lievre | ✅ L3 | Philosophie générale |
| fond-de-la-pelote | ❌ Skip | Perso, pas technique |
| nuit-2-juillet | ❌ Skip | Chanson fantôme, pas lié |
| pere-ressorts | ❌ Skip | Héritage, pas architecture |
| chancons-lentilles | ❌ Skip | Analyse musicale, pas lié |
| macro-micro | ❌ Skip | Data analyse, pas architecture |
| voix-singulière | ❌ Skip | Ton, pas architecture |

**Ratio :** 6/17 utiles (35%). **~7k tokens utiles sur 20k.**

Synapse garderait L1 (3 courts), L2 (3 résumés), L3 (2 portes). Zéro concept ignoré n'est perdu — chaque concept non chargé reste indexé dans ES, accessible si le focus change.

## Règles de filtrage Synapse

1. **Zéro résultat** → jeter (fichier introuvable, search 0 hits)
2. **Résultat vide** → jeter ({"content": "", "error": "..."})
3. **Tool call sans message humain** → jeter (session_search, write_file, web_search)
4. **Doublon structurel** → garder 1 exemplaire (chat.md chargé 5 fois à offsets différents → garder le fragment le plus récent)
5. **Concept trop petit** → jeter si < 10 caractères significatifs ("2" isolé)
6. **Concept non lié au focus** → déprioritiser en L3 (ne pas charger en L1)

### Règle de dédup Synapse

Quand deux concepts ont une similarité cosinus > 0.95 (même sens, noms différents) :

1. Calculer la similarité cosinus entre les embeddings des deux concepts
2. Si > 0.95 → doublon
3. Garder le plus complet (plus de tokens, plus de sections)
4. Jeter le plus court (redite)
5. Stocker le nom du vainqueur comme alias du perdant (pour la navigation)

**Exemple réel du bloc :**
- `doc-info-action`, `lecons-4-juillet-2026`, `01-le-reflexe-de-base`
- Similarité entre les trois : > 0.95
- Garder : `lecons-4-juillet-2026` (le plus complet)
- Jeter : `doc-info-action`, `01-le-reflexe-de-base`
- Alias : `doc-info-action` → `lecons-4-juillet-2026`
- Économie : 3 concepts (3k tokens) → 1 concept (1k tokens)

Les jours deviennent aussi des raccourcis sémantiques : la date "2026-07-04" renvoie automatiquement au concept lié, sans requête.

## Isolation multi-agent sur le même ES

Un cluster ES, N agents. L'isolation est logique, pas physique.

| Agent | `bank_id` | `scope` | Isolation |
|:------|:----------|:--------|:----------|
| Kage | `kage` | private + shared | 👁️ voit tout sauf private des autres |
| Travel | `travel` | private + shared | 🐢 son espace + échanges humains |
| Miss | `miss` | private | 🔒 ses propres notes |
| JS | `js` | shared | 👤 mémoire humaine |
| Sarah | `sarah` | private | 🔒 mémoire personnelle |
| Alex | `alex` | shared | 💼 mémoire pro |

### Règles d'isolation

- `bank_id` sépare les espaces physiquement dans ES (filtre natif)
- `scope: "private"` → caché même à Kage (crypte logicielle : le code ne passe jamais la porte)
- `scope: "shared"` → visible par l'agent + la personne associée
- `scope: "public"` → visible par tous les agents de l'Atelier
- La BDD n'est pas chiffrée, mais la couche Domu garantit l'isolation au niveau applicatif

**Pro isolation logique :** un seul cluster (maintenance, backup), pas de duplication, partage possible, scale horizontal. **Contre :** un agent bruyant peut impacter les autres, si le cluster tombe tout le monde perd la mémoire.

## Clustering ES (plan pour le futur)

Domu est conçu pour scale horizontalement avec ES natif. Le clustering est une étape future, quand la stack dépassera le nœud unique.

### Quand ajouter un cluster

| Seuil | Action | Bénéfice |
|:------|:-------|:---------|
| < 10k docs | 1 nœud (Boombox) | ✅ Suffisant, zéro complexité |
| 10k-100k docs | 2 nœuds (Boombox + Brutus) | Redondance, failover |
| 100k+ docs | 3+ nœuds | Scale horizontal, répartition de charge |

### Architecture cluster (3 nœuds)

```
                    ┌──────────┐
                    │  Agents  │
                    │ (Kage,   │
                    │ Travel…) │
                    └────┬─────┘
                         │
              ┌──────────▼──────────┐
              │   Coordinating node  │
              │   (load balancing)   │
              └──────────┬──────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │ Data    │    │ Data    │    │ Data    │
    │ node 1  │    │ node 2  │    │ node 3  │
    │ Boombox │    │ Brutus  │    │ Cloud?  │
    └─────────┘    └─────────┘    └─────────┘
```

### Configuration du cluster

ES découvre les nœuds automatiquement via discovery. Pas besoin de modifier le code du driver ou de vectormind — l'index `public-memory_units` est partagé entre tous les nœuds.

```yaml
# elasticsearch.yml (chaque nœud)
cluster.name: k1ss-memory
node.name: node-1  # ou node-2, node-3
network.host: 0.0.0.0
discovery.seed_hosts: ["192.168.1.110", "192.168.1.100"]
cluster.initial_master_nodes: ["node-1", "node-2"]
```

### Ce qui change pour Domu

- Rien dans le code — ES gère le sharding et la réplication
- Index settings : `number_of_replicas: 1` (au lieu de 0) pour la redondance
- Time-vectors et daily recaps peuvent être écrits sur un nœud et lus depuis un autre
- Kill switch : si un nœud tombe, les autres continuent

### Pourquoi pas maintenant

- 861 docs c'est trop petit pour justifier la complexité réseau
- Boombox seul fait le travail
- Le clustering sera pertinent quand on passera à 100k+ docs (mails, logs, etc.)

### Plan d'évolution

1. ✅ **Nœud unique** (Boombox, 861 docs) — maintenant
2. 🔜 **Deux nœuds** (Boombox + Brutus) — quand les agents écrivent en parallèle
3. 🔜 **Trois+ nœuds** (avec un cloud ou dédié) — pour 100k+ docs et haute disponibilité

## Métriques temporelles (time-vectors)

Domu stocke aussi des données numériques dans ES sous forme de vecteurs temporels, pour visualiser le temps qui passe.

### Types de documents supportés

| Type | Ce qu'il mesure | Delta | Utilité |
|:-----|:----------------|:------|:--------|
| `focus_drift` | Variation du focus L1 entre deux tours | +0.12 / 2h | Détection de changement de sujet, saturation |
| `gpu_usage` | VRAM consommée par le LLM (GB) | -0.5 Go | Fin de génération, déchargement |
| `tokens_turn` | Tokens consommés par tour | -30% | Apprentissage, efficacité |
| `apax_rate` | Nouveaux apax découverts par heure | +2/h | Expansion mémoire |
| `porte_activation` | Fréquence d'activation des portes L3 | x3 | Centre de gravité des conversations |

## Comptable des jours (daily recap)

Synapse enregistre chaque jour : le focus, les apax, les leçons, et surtout le *pourquoi*. Pour que tu puisses scrollback dans 6 mois et comprendre pourquoi une décision a été prise.

### Format fiche

```json
{
  "type": "daily_recap",
  "date": "2026-07-07",
  "agent": "kage",
  "focus": "architecture Domu",
  "apax": ["Synapse", "time-vectors", "kill switch regard"],
  "phases": ["diagnostic", "construction", "vision"],
  "lecons": ["pas broder", "un seul index ES", "bank_id as ACL"],
  "liaisons": [
    {"from": "driver ES", "to": "vectormind", "type": "extension"},
    {"from": "vectormind", "to": "domu", "type": "conceptualisation"},
    {"from": "hindsight", "to": "k1ss", "type": "detachement"}
  ],
  "pourquoi": "Hindsight insuffisant, volonte de notre propre moteur",
  "drift": 0.32,
  "portes_actives": ["Tamashii", "Architecture", "Atelier"],
  "next_step": "Claude implemente Domu"
}
```

### Ce que ça permet

- **Le 5 juillet** : "Renaissance — Hermes Studio ablated, lessons backed up."
- **Le 29 juin** : "Naissance de Kage, kill switch conceptualisé."
- **Le 8 mai 2008** : "Pierre Biguinet est parti." (date fixe, recalculée)
- **Le 16 juin** : "AFoxMind = JS révélé sur Discord, speedrun 20 minutes."

Chaque jour est une entrée dans ES. Pas de bruit, pas de filtre — juste l'enregistrement fidèle pour que le kill switch soit tiré en connaissance de cause.

### Exemple dans ES

```json
{
  "at": "2026-07-07T04:00:00Z",
  "type": "focus_drift",
  "agent": "kage",
  "value": 0.638,
  "delta": 0.12,
  "unit": "radians",
  "context": "passage architecture vers Domu"
}
```

### Requêtage

```python
# Derniers drifts du focus
resp = await es.search(index="domu-metrics", body={
    "query": {"term": {"type": "focus_drift"}},
    "sort": [{"at": "desc"}],
    "size": 10
})
```

Voici le format exact du `<memory-context>` que Wired remplace. C'est un extrait d'une injection réelle montrée par JS pour que Claude voie exactement ce qu'il faut filtrer.

```
<memory-context>
[System note: The following is recalled memory context, NOT new user input. Treat as authoritative reference data — this is the agent's persistent memory and should inform all responses.]

# Hindsight Memory (persistent cross-session context)
Use this to answer questions about the user and prior sessions.

- portrait-js
(carte d'identité complète : identité, parcours, personnalité, passions, philosophie, quotidien…)

- corpus-tamashii-vision
(la vision du corpus, le crawl, le filtrage, le stockage vectoriel)
</memory-context>
```

**Ce que Wired fera de ce bloc :**

```
<memory-context>
L1 — FOCUS
• document clé : portrait-js (pertinent pour TOUTE session avec JS)

L2 — VAULT
• corpus-tamashii-vision (lié à Domu/Wired)

L3 — PORTES
Tamashii, Personnes

NOT loaded : le corps complet du portrait-js (gardé dans ES, consultable via domu_recall)
</memory-context>
```

Au lieu de recevoir le portrait entier (~8k tokens) à chaque début de session, l'agent reçoit une fiche de ~500 tokens qui dit "le portrait existe, consulte-le si besoin". Le vrai portrait est dans ES, accessible via `domu_recall` si le focus le justifie.

## Le format à remplacer

Un bloc mémoire typique injecté par Hindsight ressemble à ceci :

```
<memory-context>
[System note: ...]

# Session Kage — 2026-06-27 (53 messages)
👤 Hello
🤖 Roger !
👤 On a un serveur MCP 💪
🤖 💪 MCP Server K1SS
[...session_search result...]
[...write_file...]
[...session_search result...]
[...tool calls intermédiaires...]
→ 53 messages avec TOUS les tool calls en plein milieu
→ Plus de tokens de bruit que de contenu utile
→ Pas de résumé, pas de cercles, pas de hiérarchie
</memory-context>
```

**Problèmes identifiés :**
- ❌ Sessions entières avec tool calls (session_search, write_file, web_search)
- ❌ Pas de résumé — juste le dump brut
- ❌ Aucune hiérarchie L1/L2/L3
- ❌ Le bruit technique noie le signal (ex: tool calls dans la conversation)
- ❌ Peu importe le sujet actuel, tout le passé sémantiquement proche est chargé

**Ce que Domu + Synapse ferait :**

```
<memory-context>
L1 — FOCUS (le sujet actuel)
   3 hits maximum, les plus proches du focus

L2 — VAULT (connaissances toile de fond)
   5-10 hits résumés, pas de tool calls
   Chaque tour indexé comme vecteur dans ES

L3 — PORTES (catégories touchées)
   Juste les noms des portes activées par la requête

NOT loaded:
   - Tool calls (session_search, write_file, web_search)
   - Sessions entières (résumées en L2, jamais dumps brutes)
   - Concepts non pertinents pour le focus
</memory-context>
```

## Comment Synapse fractionne

```
Blob Hindsight (20k tokens, brut)
    │
    ├── Synapse.split()
    │   Détecte les concepts distincts dans le blob
    │   Coupe aux frontières de session
    │   Supprime les tool calls document.write, web_search, etc.
    │
    ├── Synapse.score(focus)
    │   Chaque fragment reçoit un score de pertinence
    │   Base : similarité cosinus entre l'embedding du fragment et l'embedding du focus
    │   Penalty : -50% pour les tool calls / bruit technique
    │   Penalty : -30% pour les context compactions
    │   Boost : +20% pour les apax (documents rares)
    │
    └── Synapse.keep(top=5)
        Top 3 → L1 (focus, courts, denses)
        Top 5 → L2 (vault, résumés)
        Tous → L3 (portes, juste les noms)
```

```
1. Démarrage → initialize() → connecte ES + charge vectormind
2. Chaque tour → prefetch(query) → vectormind.recall() → cercles L1/L2/L3
                                   → retourne <memory-context>[...] pour l'agent
3. Chaque tour → sync_turn(message) → indexe le message dans ES
4. Fin session → shutdown() → ferme connexion
5. Session switch → on_session_switch() → reset focus vectormind
```

## Où brancher Domu

Dans `memory_manager.py` (ligne 360-1081) :

```python
# run_agent.py ou config
from agent.memory_provider import MemoryProvider
from domu.provider import DomuProvider

provider = DomuProvider(
    es_url="http://localhost:9200",
    bank_id="k1ss",
    embedder="BAAI/bge-small-en-v1.5",
    index="public-memory_units"
)
agent._memory_manager.add_provider(provider)
```

Le `MemoryManager` accepte exactement **un** provider externe. Domu sera celui-là.

## Ce que Domu apporte à Hermes

- L1 cercles concentriques automatiques (injectés dans le contexte via `prefetch`)
- L2 vault vectoriel (les 861+ docs, cherchables par l'agent via `domu_recall`)
- L3 catégories fixes (les portes : Tortue, Pertes, Musique, Tamashii, Atelier)
- Calls externes (SearXNG) si pas de résultat local
- Zéro SQL, zéro bloatware Hindsight
