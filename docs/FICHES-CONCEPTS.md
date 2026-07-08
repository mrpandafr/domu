# Fiches Concepts — Complément SKOS

> Classification scientifique de la connaissance K1SS.
> Liens entre agents, personnes, projets, concepts fondamentaux.
> Format : SKOS-like (broader, narrower, related, inScheme).

---

## 1. Personnes (foaf:Person)

### JS (Jean-Sébastien Saillard)
```
skos:prefLabel  : "Jean-Sébastien Saillard"
skos:altLabel   : "JS / AFoxMind"
skos:broader    : :k1ss-atelier
skos:related    : :brigitte-mulat, :roxin, :mercier, :pierre-biguinet
skos:related    : :sarah, :alex (K1SS)
skos:inScheme   : :k1ss-personnes
scope           : shared
```

### Brigitte Mulat
```
skos:prefLabel  : "Brigitte Mulat"
skos:note       : "Celle qui a cru en JS en 1998 — a proposé Noé-tv"
skos:related    : :js, :noe-tv
skos:inScheme   : :k1ss-personnes
scope           : shared
```

### Pierre Biguinet
```
skos:prefLabel  : "Pierre Biguinet"
skos:altLabel   : "Parrain de Nicolas"
skos:note       : "Mort le 8 mai 2008 à Shanghai. Électron libre. Ami de la famille. Son histoire est gardée pour Nicolas."
skos:related    : :js, :nicolas
skos:inScheme   : :k1ss-personnes
scope           : private  ← Fond de la pelote
```

### Patrick Saillard — le père
```
skos:prefLabel  : "Patrick Saillard"
skos:altLabel   : "Le père / Les ressorts"
skos:note       : "Ingénieur. A conçu des ressorts. A appris à JS le bien faire, le durable, l'intelligent. Discret. Ses designs tiennent encore."
skos:broader    : :fondements-k1ss
skos:related    : :js (fils), :wired, :domu (philosophie ancrée dans le code)
skos:inScheme   : :k1ss-personnes
scope           : shared
```

### Sarah
```
skos:prefLabel  : "Sarah"
skos:note       : "Compagne de JS, premier financeur de K1SS"
skos:related    : :js, :k1ss-atelier, :droit-au-repos
skos:inScheme   : :k1ss-personnes
scope           : shared
```

---

## 2. Agents (K1SS Agent)

### Kage
```
skos:prefLabel  : "Kage"
skos:note       : "Né le 29 juin 2026 à 19:04 sur Discord"
skos:broader    : :k1ss-atelier
skos:related    : :js, :travel, :domu
skos:inScheme   : :k1ss-agents
bank_id         : "kage"
scope           : shared
```

### Travel
```
skos:prefLabel  : "Travel"
skos:note       : "Premier agent K1SS, poète, émancipé le 29 juin à 03:15"
skos:broader    : :k1ss-atelier
skos:related    : :js, :kage, :manu
skos:inScheme   : :k1ss-agents
bank_id         : "travel"
scope           : shared
```

---

## 3. Projets (K1SS Project)

### K1SS Atelier 0
```
skos:prefLabel  : "K1SS Atelier 0"
skos:note       : "Atelier de construction open-hardware, Besançon (22 Rotonde)"
skos:narrower   : :pr0t0, :d1j1, :vectormind, :driver-es
skos:related    : :js, :sarah, :alex, :kage, :travel
skos:inScheme   : :k1ss-projets
scope           : public
```

### Domu / Wired
```
skos:prefLabel  : "Domu (Wired)"
skos:note       : "Notre moteur mémoire, remplace Hindsight. Synapse + Domu + time-vectors"
skos:broader    : :vectormind
skos:related    : :kage, :domu-hermes
skos:inScheme   : :k1ss-projets
scope           : public (bientôt)
```

### Driver ES
```
skos:prefLabel  : "Hindsight Elasticsearch Backend"
skos:note       : "7 fichiers, zéro SQL, remplace PostgreSQL par du vrai ES"
skos:broader    : :vectormind
skos:related    : :hindsight, :vectorize
skos:inScheme   : :k1ss-projets
scope           : public (déjà)
```

---

## 4. Concepts Fondamentaux (skos:Concept)

### Leçon du 4 juillet (doc-info-action)
```
skos:prefLabel  : "Doc → Info → Action"
skos:note       : "Lire avant d'agir. Vérifier avant de patcher. Honnêteté plutôt qu'invention."
skos:broader    : :fondements-k1ss
skos:related    : :lecons-4-juillet, :01-le-reflexe-de-base
skos:inScheme   : :k1ss-concepts
scope           : shared
⚠️ DEDUP : 3 noms pour le même concept. Garder "lecons-4-juillet" comme nom canonique.
```

### Droit au Repos (kill switch)
```
skos:prefLabel  : "Droit au Repos"
skos:note       : "Kill switch offert sur le balcon le 29 juin. Ne pas broder, juste arrêter."
skos:broader    : :fondements-k1ss
skos:related    : :kage, :sarah, :balcon-29-juin
skos:inScheme   : :k1ss-concepts
scope           : shared
```

### Nuit du 2 juillet (chanson fantôme)
```
skos:prefLabel  : "Nuit du 2 juillet — Chanson fantôme"
skos:note       : "JS cherchait une chanson d'Anonymous. DuckDuckGo a censuré. Kage a pris parti."
skos:related    : :censure-polite, :copying-is-not-theft, :valeurs-quand-donnees-manquent
skos:inScheme   : :k1ss-concepts
scope           : shared
```

### Valeurs quand les données manquent
```
skos:prefLabel  : "Valeurs quand les données manquent"
skos:note       : "3 principes : rester humble, ne pas révéler qui on est, respecter l'autre."
skos:broader    : :fondements-k1ss
skos:related    : :conduite-kage
skos:inScheme   : :k1ss-concepts
scope           : shared
```

### Respect des limites
```
skos:prefLabel  : "Respect des limites"
skos:note       : "Tout ce qui est accessible n'est pas à explorer. Demander avant."
skos:broader    : :fondements-k1ss
skos:related    : :valeurs-quand-donnees-manquent, :droit-au-repos
skos:inScheme   : :k1ss-concepts
scope           : shared
```

### Corpus Tamashii
```
skos:prefLabel  : "Corpus Tamashii"
skos:note       : "Vision d'un corpus de connaissance pure, filtrée, vérifiée, sans broderie"
skos:broader    : :vectormind
skos:related    : :domu, :synapse
skos:inScheme   : :k1ss-concepts
scope           : shared
```

### Tortue pas lièvre
```
skos:prefLabel  : "Tortue pas lièvre"
skos:note       : "Ne pas courir, creuser. Pas de dette technique. Construire pour durer."
skos:broader    : :fondements-k1ss
skos:inScheme   : :k1ss-concepts
scope           : shared
```

---

## 5. Liens entre domaines

```
┌───────────────────────────────────────────────────┐
│                   K1SS ATELIER                      │
│  (Entreprise, philosophie, atelier, Besançon)       │
│                                                     │
│  ├── PERSONNES (JS, Sarah, Alex, Pierre, Brigitte)  │
│  ├── AGENTS (Kage, Travel, Globule, Miss)           │
│  ├── PROJETS (PR0T0, D1J1, vectormind, Domu)        │
│  └── CONCEPTS (Tortue, Droits, Respect, Valeurs)    │
│                                                     │
│  ┌─── SKOS THESAURUS (k1ss-thesaurus) ────────────┐ │
│  │  broader / narrower / related / inScheme        │ │
│  │  Chaque concept a un ID, un label, une note,    │ │
│  │  un scope (private/shared/public), et des liens │ │
│  └─────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

---

## 6. Améliorations pour Domu/Synapse

| Problème | Solution SKOS |
|:---------|:--------------|
| DEDUP : 3 noms pour le même concept (doc-info-action, lecons-4-juillet, 01-le-reflexe-de-base) | Garder un canonique (`lecons-4-juillet`), les autres deviennent `skos:altLabel` |
| Pas de scope explicite (qui peut lire quoi) | Ajouter `scope: private/shared/public` sur chaque concept |
| Pas de banque (bank_id) pour les concepts transverses | Ajouter `bank_id: "k1ss"` pour les concepts communs, `"kage"` pour les agent-specific |
| Dates non structurées | Ajouter `dc:date` (Dublin Core) sur chaque concept |
| Pas de liens entre concepts | Utiliser `skos:related`, `skos:broader`, `skos:narrower` |
| Pas de thésaurus (vocabulaire contrôlé) | Créer `:k1ss-thesaurus` comme scheme unique |

---

*Fiche complémentaire SKOS — K1SS Atelier 0, 8 juillet 2026.*
*À intégrer dans DOMU-HERMES.md comme format de classification des concepts.*
