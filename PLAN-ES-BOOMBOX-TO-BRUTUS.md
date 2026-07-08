# Plan : Copie ES Boombox → Brutus pour test Domu

## Objectif

Copier les données ES de prod (Boombox) vers Brutus pour tester DomuProvider
sans toucher à la prod.

## Étapes

### 1. Dump de l'index sur Boombox

```bash
# Dump de tous les index memories + metrics
ssh alexandrab@192.168.1.110 '
elasticdump \
  --input=http://127.0.0.1:9200/public-memory_units \
  --output=/tmp/boombox-dump.json \
  --type=data
'
```

### 2. Copier le dump vers Brutus

```bash
scp alexandrab@192.168.1.110:/tmp/boombox-dump.json ~/K1SS/domu/test-data/
```

### 3. Démarrer ES sur Brutus (port 9201)

```bash
docker run -d --name es-domu-test \
  -p 9201:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  docker.elastic.co/elasticsearch/elasticsearch:8.18.0
```

### 4. Restaurer le dump

```bash
elasticdump \
  --input=~/K1SS/domu/test-data/boombox-dump.json \
  --output=http://127.0.0.1:9201/public-memory_units \
  --type=data
```

### 5. Tester DomuProvider sur Brutus

```python
from domu import DomuProvider
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
embed = lambda texts: [model.encode(t, normalize_embeddings=True).tolist() for t in texts]

provider = DomuProvider(
    es_client_factory=lambda: AsyncElasticsearch("http://127.0.0.1:9201"),
    embed=embed,
    categories={
        "la-tortue": "tortue",
        "les-pertes": "perte",
        "tamashii": "tamashii", 
        "la-musique": "musique",
        "l-atelier": "atelier",
        "les-petites-choses": "apax"
    }
)
```

## Matériel

- **Boombox** (192.168.1.110) : ES 8.18.0, 867 docs, hindsight + searcharvester
- **Brutus** (localhost) : ES 8.18.0 (conteneur), port 9201, Ollama disponible
- **Dump** : ~10-50 Mo (867 docs texte + embedding 384d)

## Risques

⚠️ `elasticdump` charge tout en mémoire — vérifier que /tmp a assez d'espace
⚠️ Si run sans `--limit`, ES timeout sur les indices volumineux
⚠️ `elasticsearch-py` synchrone vs `AsyncElasticsearch` — DomuProvider utilise AsyncElasticsearch
