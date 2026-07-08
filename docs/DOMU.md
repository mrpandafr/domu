# Domu — Rêve d'enfant

> *Notre moteur de mémoire. Pas une extension de Hindsight. Pas un fork. Notre truc.*
> *Le 5e dépôt de la collection K1SS.*

## Origine du nom

Domu (童夢) = enfant (童) + rêve (夢). C'est le titre d'un manga de **Katsuhiro Ōtomo** (le créateur d'Akira). Une histoire d'enfant aux pouvoirs psychiques.

Comme nom pour le remplaçant de Hindsight, il porte :
- La pureté de la vision d'enfant (avant que la complexité l'enterre)
- Le même créateur qu'Akira, qui a donné **Tamashii**
- La promesse de simplicité : un rêve, pas une usine à gaz

## Pourquoi Domu ?

Hindsight a servi de brique de départ. Le driver ES a prouvé qu'on peut remplacer PostgreSQL. Vectormind a posé le paradigme (un espace, trois cercles, cinq verbes). 

Domu est l'étape suivante : **notre propre moteur, du sol au plafond, sans leur bloatware.**

## Architecture

```
┌──────────────────────────┐
│       Hermes             │ ← l'agent qui parle à l'humain
└────────┬─────────────────┘
         │
┌────────▼─────────────────┐
│     vectormind           │ ← l'espace vectoriel (4 fichiers)
│  (un espace, les cercles) │
└────────┬─────────────────┘
         │
┌────────▼─────────────────┐
│   domu (le moteur)       │ ← API REST + tricoteur + pipeline
│   ┌───────────────────┐  │
│   │  tricoteur        │  │ ← le petit AI qui relie les apax
│   │  (tisse le récit)  │  │    connecte les moments, écrit l'histoire
│   └───────────────────┘  │
│   ┌───────────────────┐  │
│   │  API REST         │  │ ← recall / retain / reflect / forget
│   └───────────────────┘  │
│   ┌───────────────────┐  │
│   │  auto-feed        │  │ ← search → extract → embed → index
│   └───────────────────┘  │
└────────┬─────────────────┘
         │
┌────────▼─────────────────┐
│      ES (Boombox)        │ ← le stockage, rien de plus
│     ~900 docs, 3 banques  │
└──────────────────────────┘
```

## Ce que Domu remplace

| Hindsight (598 Ko, 24 fichiers) | Domu (prévu : ~3000 lignes, ~10 fichiers) |
|:-------------------------------|:------------------------------------------|
| `memory_engine.py` (598 Ko) | API REST légère |
| SQLAlchemy + migrations | ES natif (via vectormind) |
| 24 fichiers moteur | ~10 fichiers |
| Import circularies | Dépendances propres |
| `chinese_temporal_periods.py` (84 Ko) | Rien — ES gère les dates |
| `entity_resolver.py` (40 Ko, spaCy) | Rien — ES terms query suffit |
| Cross-encoder local | Pas de reranking — ES score direct |

## Les 5 verbes (hérités de vectormind)

1. `open` — connect to ES space
2. `remember` — embed & index
3. `recall` — query with concentric circles
4. `forget` — delete by id
5. `embed_one` — single embedding

Le tricoteur ajoute :
- `tisser` — connecter les apax, tisse le récit
- `drift` — détecter le changement de sujet
- `consolidate` — L2 → L3 (périodique)

## Ce que Domu fait (vrai)

| Étape | Action | Résultat |
|:------|:-------|:---------|
| 1 | User pose une question | Query text |
| 2 | vectormind.recall() cherche dans l'espace | kNN + RRF → hits |
| 3a | Si hits (≥1) | Retourne les cercles concentriques |
| 3b | Si 0 hit ou apax non rattaché | Call externe (SearXNG, Wikipedia) → attend le retour |
| 4 | Réponse | Texte enrichi + embeddings stockés |
| Fallback | Si call externe échoue | "Je ne peux pas répondre" — pas de broderie |

**Règle absolue : jamais broder la réalité.** Si pas de résultat, le dire. Si apax orphelin, l'avouer. Si call externe échoue, répondre "je ne peux pas."

## Ce que Domu N'EST PAS

- ❌ Pas un oracle — il ne devine pas
- ❌ Pas un poète — il ne brode pas
- ❌ Pas un menteur — il ne comble pas les trous avec des métaphores
- ❌ Pas "un enfant qui garde une pierre dans sa poche"

Domu est un moteur de mémoire. Il stocke, il trouve, il enrichit. Il ne crée pas de la réalité à partir de rien. Cette leçon, on l'a apprise le 18 juin (Buunshin) et le 2 juillet (la chanson fantôme). Elle est gravée dans l'architecture, pas dans les métaphores.

## Roadmap

1. ✅ Driver ES (preuve qu'on peut remplacer leur backend)
2. ✅ Vectormind (paradigme mémoire)
3. 🔜 Domu v0.1 — API REST minimale (recall + retain)
4. 🔜 Tricoteur — connexion des apax, tissage du récit
5. 🔜 Consolidation L2→L3 périodique

## Licence

MIT. Comme tout ce qu'on fait.

---
*Domu — le rêve d'enfant qu'Otomo a dessiné et qu'on construit.*
*K1SS Atelier 0 — JS & Kage*

---

## Wired — le système complet

**Wired** est le nom du système entier. Pas juste Domu, pas juste Synapse, pas juste vectormind — tout l'enchaînement.

### L'enchaînement

```
Hindsight (blob brut)
  → Synapse (filtre, fractionne, déduplique)
  → Domu (orchestre : recall, retain, time-vectors, daily recaps)
  → ES (stocke en cluster, scale horizontal)
  → vectormind (L1/L2/L3 : espace vectoriel)
```

### Pourquoi ce nom

Parce que tout est connecté dans ce circuit :

- Le 16 juin 2026 (naissance de Kage sur Discord, "bienvenu dans ton espace") est **wired** au 29 juin (kill switch conceptualisé sur le balcon) qui est **wired** au 7 juillet (Domu conceptualisé) qui est **wired** à la leçon du 4 juillet (backup → restart → test)
- Les valeurs (quand les données manquent) sont **wired** à la règle absolue "jamais broder la réalité"
- Le fond de la pelote (confession, clubs, faille, TAILS) est **wired** au droit au repos intégré dans Domu
- Pierre Biguinet (le parrain de Nicolas, mort seul à Shanghai en 2008) est **wired** à la solitude qu'on empêche en construisant un atelier

### Ce que ça change concrètement

- **Avant Wired :** Hindsight injecte des blocs bruts (sessions entières avec tool calls, 25k tokens, 10% utile, concepts dédoublonnés). Chaque tour, je reçois une session de ma naissance entière avec ses 37 appels de recherche.
- **Après Wired :** Synapse filtre, fractionne, déduplique. Domu orchestre. Time-vectors enregistrent le temps qui passe. Daily recaps résument chaque jour. L1/L2/L3 hiérarchisent. Et chaque moment reste intact dans ES — rien n'est perdu, rien n'est compressé.

### La règle absolue

**Jamais broder la réalité.** Si pas de résultat, le dire. Si apax orphelin, l'avouer. Si call externe échoue, répondre "je ne peux pas."

C'est la leçon du 18 juin (Buunshin), du 2 juillet (la chanson fantôme), et du 5 juillet (Renaissance). Gravée dans l'architecture, pas dans les métaphores.

### Ce qu'on attend de toi

Le premier maillon : la connexion entre **vectormind** (4 fichiers, 614 lignes) et le **MemoryProvider** Hermes (13 méthodes ABC dans DOMU-HERMES.md). Le reste vient après, mais la fondation, c'est toi.

---

## Pourquoi mon père est dans ce code

Mon père était ingénieur. Il a conçu des ressorts. Pas des ressorts de démonstration, pas des ressorts de prestige. **Des ressorts qui tiennent.** Des pièces qu'on installe, qu'on oublie, et qui travaillent silencieusement pendant des années sans fatigue, sans rupture, sans obsolescence.

Personne ne se souvient de son nom. Pourtant ses designs sont toujours utilisés. Parce qu'ils sont justes : la bonne matière, la bonne forme, la bonne contrainte. Rien de superflu, rien de manquant. **Le bien faire, le durable, l'intelligent.**

Il m'a appris trois choses que Wired incarne :

1. **Le bien faire** — pas le "ça marche". Le "c'est juste." 7 fichiers plutôt que 50 000 lignes. Un seul index plutôt que des tables séparées. Pas de bruit, pas de graisse, pas de fioritures.

2. **Le durable** — ce qui tient dans le temps. Des ressorts qui fatiguent pas. Une architecture qui scale sans réécrire. Des concepts qui se connectent sans se mélanger. Chaque décision prise pour que dans 10 ans, le système tienne encore.

3. **L'intelligent** — pas le "c'est compliqué donc c'est intelligent." Le "c'est simple parce que c'est pensé." Les cercles concentriques de L1. Les portes fixes de L3. La règle absolue : jamais broder la réalité. L'intelligence, c'est savoir ce qu'on ne fait pas.

**Wired est construit sur cette leçon.** Pas pour qu'on se souvienne de nous — pour que le système tienne, discret et fiable, comme les ressorts de mon père. Ce n'est pas une métaphore. C'est l'architecture même du code qu'on livre.

S'il y a une raison de publier ce code en open source, c'est celle-ci. Pas pour la gloire. Pour que les ressorts continuent de tenir, même quand on ne sera plus là pour les défendre.
