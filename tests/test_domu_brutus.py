"""Test DomuProvider against the real local ES (Brutus, 127.0.0.1:9200).

Requires: elasticsearch, sentence-transformers, vectormind (in path)
Runs the full DomuProvider lifecycle against the 867 docs copied from Boombox.
"""
import sys, os, asyncio, json
sys.path.insert(0, os.path.expanduser("~/K1SS/domu"))

from sentence_transformers import SentenceTransformer
from elasticsearch import AsyncElasticsearch

# Load embedder (bge-small, 384d)
model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
async def embed(texts):
    return [model.encode(t, normalize_embeddings=True).tolist() for t in texts]

# Import DomuProvider
from domu import DomuProvider

async def main():
    print("=" * 50)
    print("DOMU TEST ON BRUTUS (127.0.0.1:9200)")
    print("=" * 50)

    # Create DomuProvider pointing to local ES
    provider = DomuProvider(
        es_client_factory=lambda: AsyncElasticsearch("http://127.0.0.1:9200"),
        embed=embed,
        categories={
            "la-tortue": "tortue",
            "l-atelier": "k1ss",
            "les-pertes": "perte",
            "tamashii": "tamashii",
            "la-musique": "musique",
            "les-petites-choses": "choses",
        },
        config={
            "index": "public-memory_units",
            "metrics_index": "domu-metrics",
            "l1_size": 3,
            "l2_size": 5,
            "bank_id": "kage",
            "dimd": 384,
        }
    )

    # 1. Initialize
    print("\n1. Initialization")
    assert provider.is_available()
    await provider._ainit()  # Direct async init
    assert provider.mind is not None
    print("   ✅ VectorMind open")

    # 2. System prompt (contains absolute rule)
    spb = provider.system_prompt_block()
    assert "never embroider" in spb
    print("   ✅ System prompt has absolute rule")

    # 3. Prefetch (empty ES query)
    print("\n2. Prefetch (empty memory)")
    ctx = await provider._build_context("xyzzy licorne quantique")
    assert "no memory" in ctx
    print(f"   ✅ Empty memory: {ctx[:50]}...")

    # 4. Recall
    print("\n3. Recall (real data)")
    ctx = await provider._build_context("le pere et les ressorts")
    print(f"   Result:")
    for line in ctx.split("\n"):
        print(f"     {line}")

    # 4. Recall test (bypass scope for Boombox data format)
    print("\n4. Direct recall (867 docs, real data)")
    from vectormind import Focus
    focus_vector = await provider.mind.embed_one("tortue pas lievre")
    
    # Bypass scope: Boombox data uses bank_id field, not tags:bank:kage
    provider.mind.space.scope = None
    provider.mind.search.scope = None
    
    recall = await provider.mind.recall(
        "le pere et les ressorts",
        focus=focus_vector and Focus().update(focus_vector),
        k=8
    )
    print(f"   Hits: {len(recall)}")
    for h in recall:
        cat = h.category or "?"
        print(f"     [{h.ring}] {cat:15s} {h.text[:50]}")
    assert len(recall) > 0, "Recall should find hits on 867 docs"

    # 5. Direct context build with query_vector
    print("\n5. Context block with query")
    ctx = await provider._build_context("peres ressorts mecanique", query_vector=focus_vector)
    lines = ctx.split("\n")
    hits = [l for l in lines if l.startswith("  •")]
    doors = [l for l in lines if "PORTES" in l]
    print(f"   Context: {len(lines)} lines, {len(hits)} hits")
    if doors:
        print(f"   Doors: {doors[0]}")
    assert len(hits) >= 1, f"Context should have hits, got {len(hits)}"
    es = AsyncElasticsearch("http://127.0.0.1:9200")
    count = await es.count(index="domu-metrics")
    print(f"   metrics index: {count['count']} docs")

    # 7. Count docs per bank
    for bank in ["kage", "js", "k1ss"]:
        resp = await es.count(index="public-memory_units", body={
            "query": {"term": {"bank_id": bank}}
        })
        print(f"   bank {bank}: {resp['count']} docs")

    await es.close()
    print("\n" + "=" * 50)
    print("DOMU TEST PASSED ✅")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
