import sys, asyncio, math
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "..")
import vectormind as vm
UTC = timezone.utc
WORDS = {"tortue":[1,0],"driver":[0,1],"musique":[0.72,0.69],"apax":[-0.9,0.35]}
async def embed(texts):
    out=[]
    for t in texts:
        v=[0.0,0.0]; n=0
        for w,vec in WORDS.items():
            if w in t.lower(): v=[v[0]+vec[0],v[1]+vec[1]]; n+=1
        if n==0: v=[0.5,0.5]
        norm=math.hypot(*v) or 1
        out.append([v[0]/norm, v[1]/norm])
    return out
DOCS={}; DOCS_META={}
class FakeIndices:
    async def exists(self, index): return index in DOCS_META
    async def create(self, index=None, mappings=None): DOCS_META[index]=mappings
class FakeES:
    def __init__(self, native_rrf=True):
        self.indices=FakeIndices(); self.native_rrf=native_rrf
        self.native_calls=0; self.msearch_calls=0
    async def bulk(self, operations=None, refresh=None):
        i=0; items=[]
        while i < len(operations):
            action=list(operations[i].keys())[0]; _id=operations[i][action]["_id"]
            if action=="index":
                DOCS[_id]=operations[i+1]; i+=2; items.append({"index":{"status":201}})
            else:
                existed=_id in DOCS; DOCS.pop(_id,None); i+=1
                items.append({"delete":{"result":"deleted" if existed else "not_found"}})
        return {"errors":False,"items":items}
    def _bm25(self, q):
        toks=set(q.lower().split())
        scored=[(len(toks & set(d["text"].lower().split())), d) for d in DOCS.values()]
        return [d for s,d in sorted(scored,key=lambda x:(-x[0],x[1]["id"])) if s>0]
    def _knn(self, qv):
        def cos(a,b):
            dot=sum(x*y for x,y in zip(a,b)); return dot/((math.hypot(*a) or 1)*(math.hypot(*b) or 1))
        return sorted(DOCS.values(), key=lambda d:(-cos(qv,d["vector"]), d["id"]))
    async def search(self, index=None, body=None, **kw):
        body=body or {}
        if "retriever" in body:
            if not self.native_rrf:
                e=Exception("retriever unsupported"); e.status_code=400; raise e
            self.native_calls+=1
            r=body["retriever"]["rrf"]; K=r["rank_constant"]
            lex=self._bm25(r["retrievers"][0]["standard"]["query"]["bool"]["must"][0]["match"]["text"])
            sem=self._knn(r["retrievers"][1]["knn"]["query_vector"])
            scores={}
            for view in (lex,sem):
                for rank,d in enumerate(view,1):
                    scores[d["id"]]=scores.get(d["id"],0)+1/(K+rank)
            ranked=sorted(scores.items(), key=lambda x:-x[1])
            return {"hits":{"hits":[{"_id":i,"_score":s,"_source":DOCS[i]} for i,s in ranked][:body.get("size",10)]}}
        q=body.get("query",{})
        if "terms" in q and "id" in q["terms"]:
            return {"hits":{"hits":[{"_source":DOCS[i]} for i in q["terms"]["id"] if i in DOCS]}}
        return {"hits":{"hits":[]}}
    async def msearch(self, searches=None):
        self.msearch_calls+=1; out=[]
        for i in range(1,len(searches),2):
            b=searches[i]
            docs=self._knn(b["knn"]["query_vector"]) if "knn" in b else \
                 self._bm25(b["query"]["bool"]["must"][0]["match"]["text"])
            out.append({"hits":{"hits":[{"_id":d["id"],"_score":1.0,"_source":d} for d in docs[:b["size"]]]}})
        return {"responses":out}

async def scenario(client):
    mind = await vm.VectorMind.open(client, embed, dims=2,
        categories={"la-tortue":"tortue","l-atelier":"driver","la-musique":"musique"})
    now = datetime(2026,7,7,tzinfo=UTC)
    await mind.remember(
        ["la tortue avance","le driver elasticsearch tourne","musique du soir",
         "un apax isolé","le driver et la tortue"],
        ids=["d1","d2","d3","d4","d5"],
        at=[now-timedelta(days=200), now-timedelta(days=1), now-timedelta(days=40),
            now-timedelta(days=400), now])
    focus = vm.Focus().update(await mind.embed_one("driver"))
    r = await mind.recall("le driver de la tortue", focus=focus, k=5,
                          apax_cap=0.15, recency_cap=0.05, now=now)
    return mind, r

async def main():
    es = FakeES(native_rrf=True)
    mind, r = await scenario(es)
    by_rrf = sorted(r.hits, key=lambda h:-h.rrf)
    scale = by_rrf[0].rrf
    print("1. natif — fusion (rrf):", [(h.id, round(h.rrf,4)) for h in by_rrf[:3]])
    print("   façonné:", [(h.id, round(h.score,4)) for h in r])
    assert by_rrf[0].id == "d5"                       # la fusion élit d5
    # INVARIANT : le façonnage départage les quasi-égalités, jamais plus.
    # Budget total = (0.15+0.05)*leader -> nul hit < 80% du leader ne peut le dépasser.
    for h in r.hits:
        assert sum(h.bonuses.values()) <= (0.15+0.05)*scale + 1e-12
        if h.rrf < 0.8*scale:
            assert h.score < by_rrf[0].rrf + (0.15+0.05)*scale
    d2 = next(h for h in r if h.id=="d2")
    print("   d2 dépasse d5 de", round(r.hits[0].score - r.hits[1].score, 6),
          "— quasi-égalité (rrf à", round(d2.rrf/scale*100,1), "% du leader) départagée par recency+apax : le rôle du façonnage")
    assert d2.rrf/scale > 0.9                          # bien une quasi-égalité
    d4=next(h for h in r if h.id=="d4")
    assert 0 < d4.bonuses["apax"] <= 0.15*scale + 1e-12
    assert 0 < d2.bonuses["recency"] <= 0.05*scale + 1e-12
    print("   bonus relatifs OK | L1:", [h.id for h in r.l1],
          "| portes:", {h.id: h.category for h in r})
    assert "d2" in [h.id for h in r.l1]
    assert next(h for h in r if h.id=="d3").category=="la-musique"
    assert d4.category is not None

    DOCS.clear(); DOCS_META.clear()
    es2 = FakeES(native_rrf=False)
    mind2, r2 = await scenario(es2)
    d5f = sorted(r2.hits, key=lambda h:-h.rrf)[0]
    print("2. fallback — flag mémorisé:", mind2.search._native_rrf_available is False,
          "| RRF exact 2/(60+1):", abs(d5f.rrf - 2/61) < 1e-9,
          "| équivalence natif/fallback:", abs(d5f.rrf - by_rrf[0].rrf) < 1e-9)
    assert d5f.id=="d5" and abs(d5f.rrf - 2/61) < 1e-9 and es2.msearch_calls>=1
    assert [h.id for h in r2] == [h.id for h in r]     # même ordre façonné

    f = vm.Focus(alpha=0.35)
    f.update(await mind.embed_one("driver")); f.update(await mind.embed_one("driver"))
    assert not f.drifted()
    f.update(await mind.embed_one("apax"))
    print("3. focus — drift:", round(f.last_drift,3), "| drifted:", f.drifted(0.5))
    assert f.drifted(0.5)
    print("4. forget d3:", await mind.forget(["d3"]))
asyncio.run(main())
print("VECTORMIND v0.1 — fusion souveraine (invariant prouvé), 3 cercles verts")
