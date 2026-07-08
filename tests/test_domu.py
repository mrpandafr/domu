"""Simulated Hermes session — the 13 DomuProvider hooks, no cluster needed.

Covers: lifecycle, the honest empty context (never embroider), Synapse's
gates (noise / size / dedup), the L1-L2-L3 context block, bank/scope
isolation enforced in the query, the three tools, focus-drift time-vectors,
pre-compress, session switch, background prefetch, shutdown.

Run from the repo root:  python tests/test_domu.py
"""
import sys, asyncio, math
sys.path.insert(0, ".")
import vectormind as vm  # noqa: F401
from domu import DomuProvider

WORDS = {"tortue": [1, 0], "driver": [0, 1], "musique": [0.72, 0.69], "domu": [0.3, 0.95]}


async def embed(texts):
    out = []
    for t in texts:
        v = [0.0, 0.0]; n = 0
        for w, vec in WORDS.items():
            if w in t.lower():
                v = [v[0] + vec[0], v[1] + vec[1]]; n += 1
        if n == 0:
            h = abs(hash(t)) % 100 / 100
            v = [0.4 + h * 0.05, 0.6 - h * 0.05]
        norm = math.hypot(*v) or 1
        out.append([v[0] / norm, v[1] / norm])
    return out

DOCS = {}; META = {}; METRICS = []


class FakeIndices:
    async def exists(self, index): return index in META
    async def create(self, index=None, mappings=None): META[index] = mappings


class FakeES:
    def __init__(self): self.indices = FakeIndices()
    async def index(self, index=None, document=None, **kw): METRICS.append(document)
    async def close(self): pass
    async def bulk(self, operations=None, refresh=None):
        i = 0; items = []
        while i < len(operations):
            action = list(operations[i].keys())[0]; _id = operations[i][action]["_id"]
            if action == "index":
                DOCS[_id] = operations[i + 1]; i += 2; items.append({"index": {"status": 201}})
            else:
                ex = _id in DOCS; DOCS.pop(_id, None); i += 1
                items.append({"delete": {"result": "deleted" if ex else "not_found"}})
        return {"errors": False, "items": items}
    def _visible(self, flt):
        def ok(d):
            for f in flt:
                b = f.get("bool")
                if b and "should" in b:
                    if not any(s.get("term", {}).get("tags") in d["tags"] for s in b["should"]):
                        return False
                elif "term" in f and "tags" in f["term"]:
                    if f["term"]["tags"] not in d["tags"]: return False
                elif "terms" in f and "tags" in f["terms"]:
                    if not set(f["terms"]["tags"]) & set(d["tags"]): return False
            return True
        return [d for d in DOCS.values() if ok(d)]
    async def search(self, index=None, body=None, **kw):
        r = body["retriever"]["rrf"]; K = r["rank_constant"]
        knn = r["retrievers"][1]["knn"]
        docs = self._visible(knn.get("filter", []))
        def cos(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            return dot / ((math.hypot(*a) or 1) * (math.hypot(*b) or 1))
        q = r["retrievers"][0]["standard"]["query"]["bool"]["must"][0]["match"]["text"]
        toks = set(q.lower().split())
        lex = [d for s, d in sorted(((len(toks & set(d["text"].lower().split())), d)
                                     for d in docs), key=lambda x: -x[0]) if s > 0]
        sem = sorted(docs, key=lambda d: -cos(knn["query_vector"], d["vector"]))
        scores = {}
        for view in (lex, sem):
            for rank, d in enumerate(view, 1):
                scores[d["id"]] = scores.get(d["id"], 0) + 1 / (K + rank)
        return {"hits": {"hits": [{"_id": i, "_score": s, "_source": DOCS[i]}
                for i, s in sorted(scores.items(), key=lambda x: -x[1])][:body["size"]]}}


async def main():
    p = DomuProvider(es_client=FakeES(), embed=embed, bank_id="kage",
                     categories={"la-tortue": "tortue", "l-atelier": "driver",
                                 "la-musique": "musique"})
    await p.initialize()
    assert p.is_available and "never embroider" in p.system_prompt_block().lower()
    p.on_turn_start()
    assert "no memory matches" in await p.prefetch("où en est le driver ?")
    assert await p.sync_turn("[...session_search result...]") is None       # règle 3
    assert await p.sync_turn("ok 42") is None                               # règle 5
    assert await p.sync_turn("le driver elasticsearch de la tortue est validé")
    assert await p.sync_turn("le driver elasticsearch de la tortue est validé") is None  # dédup
    await p.sync_turn("on écoute la musique du soir en codant domu")
    await p.sync_turn("domu orchestre vectormind et le tricoteur tisse")
    p.on_turn_start()
    ctx = await p.prefetch("parle-moi du driver de la tortue")
    assert "L1 — FOCUS" in ctx and "L3 — PORTES" in ctx
    DOCS["intrus"] = {"id": "intrus", "text": "secret driver de miss", "vector": [0, 1],
                      "tags": ["bank:miss", "scope:private"],
                      "at": "2026-07-07T00:00:00+00:00", "meta": {}}
    DOCS["pub"] = {"id": "pub", "text": "annonce driver publique", "vector": [0, 1],
                   "tags": ["bank:js", "scope:public"],
                   "at": "2026-07-07T00:00:00+00:00", "meta": {}}
    out = await p.handle_tool_call("domu_recall", {"query": "secret annonce driver"})
    ids = [h["id"] for h in out["hits"]]
    assert "intrus" not in ids and "pub" in ids                             # isolation
    r = await p.handle_tool_call("domu_remember",
        {"text": "note explicite sur la musique de la tortue au crépuscule",
         "scope": "private"})
    assert r["id"]
    assert (await p.handle_tool_call("domu_forget", {"ids": [r["id"]]}))["deleted"] == 1
    drifts = [m for m in METRICS if m["type"] == "focus_drift"]
    assert drifts and drifts[-1]["agent"] == "kage"                          # time-vectors
    assert "memory-context" in await p.on_pre_compress()
    p.on_session_switch()
    assert p.focus.vector is None and p.turn == 0
    p.queue_prefetch("domu et la musique")
    await asyncio.sleep(0)
    await p.on_session_end()
    assert "memory-context" in await p.prefetch("domu et la musique")
    await p.shutdown()
    print("DOMU : 13 hooks verts")

asyncio.run(main())
