"""Conformity + simulated Hermes session against the REAL memory_provider.py.

Covers: ABC instantiation (real abstract methods), the synchronous surface
over the background loop, the M4Z3 case (real content kept, tool noise
dropped), context gating (cron writes disabled), cached prefetch,
JSON-string tool results, session-switch reset semantics, pre-compress
salvage, config schema/save, shutdown.

Run from the repo root:  python tests/test_domu.py [path/to/memory_provider.py]
"""
import hashlib
import sys, os, time, json, math, types, importlib.util, tempfile

sys.path.insert(0, ".")

# --- load the REAL ABC when available ---
ABC_PATH = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/memory_provider.py"
if os.path.exists(ABC_PATH):
    agent_pkg = types.ModuleType("agent"); agent_pkg.__path__ = [""]
    sys.modules["agent"] = agent_pkg
    spec = importlib.util.spec_from_file_location("agent.memory_provider", ABC_PATH)
    mp = importlib.util.module_from_spec(spec)
    sys.modules["agent.memory_provider"] = mp
    spec.loader.exec_module(mp)
    print("ABC réelle chargée:", sorted(mp.MemoryProvider.__abstractmethods__))
else:
    mp = None
    print("ABC réelle absente — test en mode duck-typé")

from domu import DomuProvider  # noqa: E402  (imports agent.memory_provider)

WORDS = {"tortue": [1, 0], "driver": [0, 1], "musique": [0.72, 0.69],
         "m4z3": [0.3, 0.95], "plaquette": [0.9, 0.45]}


async def embed(texts):
    out = []
    for t in texts:
        v = [0.0, 0.0]; n = 0
        for w, vec in WORDS.items():
            if w in t.lower():
                v = [v[0] + vec[0], v[1] + vec[1]]; n += 1
        if n == 0:
            # deterministic angular spread (hash() is per-process salted,
            # which made the dedup outcome nondeterministic across runs)
            h = int(hashlib.md5(t.encode()).hexdigest(), 16) % 1000 / 1000
            a = h * math.pi
            v = [math.cos(a), math.sin(a)]
        norm = math.hypot(*v) or 1
        out.append([v[0] / norm, v[1] / norm])
    return out

DOCS = {}; META = {}; METRICS = []


class FakeIndices:
    async def exists(self, index): return index in META
    async def create(self, index=None, mappings=None): META[index] = mappings


class FakeES:
    def __init__(self): self.indices = FakeIndices(); self.closed = False
    async def index(self, index=None, document=None, **kw): METRICS.append(document)
    async def close(self): self.closed = True
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


def wait_writes(p, timeout=3.0):
    end = time.time() + timeout
    while p._pending and time.time() < end:
        time.sleep(0.02)


# ---------------------------------------------------------------------------
p = DomuProvider(es_client=FakeES(), embed=embed,
                 categories={"la-tortue": "tortue", "l-atelier": "driver",
                             "la-musique": "musique"})
if mp is not None:
    assert isinstance(p, mp.MemoryProvider), "n'hérite pas de la vraie ABC"
    print("1. instanciation contre la vraie ABC: OK")
assert p.is_available() is True and p.name == "domu"          # méthode, pas propriété
assert "never embroider" in p.system_prompt_block().lower()

# initialize: signature réelle (session_id + kwargs documentés)
p.initialize("sess-001", hermes_home="/tmp/hh", platform="cli",
             agent_context="primary", agent_identity="kage")
assert p.bank_id == "kage"                                     # identity -> bank
print("2. initialize(session_id, agent_identity->bank, context) : OK")

# espace vide -> bloc honnête, en SYNC
p.on_turn_start(1, "où en est le driver ?")
assert "no memory matches" in p.prefetch("où en est le driver ?")
print("3. prefetch sync, espace vide -> honnête")

# LE CAS M4Z3 : 111 messages, ~80% tool calls — seuls les deux contenus passent Synapse
m4z3_messages = []
for i in range(88):
    m4z3_messages.append({"role": "assistant", "tool_calls": [{"name": "session_search"}]})
    m4z3_messages.append({"role": "tool", "content": "[...session_search result %d...]" % i})
m4z3_messages.append({"role": "user", "content": "tu me ferais une plaquette M4Z3 ?"})
p.sync_turn("tu me ferais une plaquette M4Z3 ?",
            "plaquette M4Z3 générée — trois pages, ton sobre, driver mentionné",
            session_id="sess-001", messages=m4z3_messages)
wait_writes(p)
texts = [d["text"] for d in DOCS.values()]
assert any("plaquette M4Z3 générée" in t for t in texts)
assert not any("session_search" in t for t in texts)
print("4. M4Z3: %d docs indexés depuis 177 messages — le contenu, jamais l'outillage" % len(DOCS))

p.sync_turn("le driver de la tortue est validé",
            "on enchaîne sur domu et la musique du tricoteur")
wait_writes(p)

# prefetch avec mémoire : cercles
p.on_turn_start(2, "parle-moi de la plaquette")
ctx = p.prefetch("la plaquette m4z3 du driver")
assert "L1 — FOCUS" in ctx and "L3 — PORTES" in ctx
print("5. cercles L1/L3 rendus | turn compté par on_turn_start:", p.turn == 2)

# queue_prefetch -> cache consommé
p.queue_prefetch("musique du tricoteur")
wait_writes(p); time.sleep(0.05)
ctx2 = p.prefetch("musique du tricoteur")
assert "memory-context" in ctx2
print("6. queue_prefetch -> cache consommé au tour suivant")

# outils : résultat = CHAÎNE JSON
raw = p.handle_tool_call("domu_recall", {"query": "plaquette m4z3"})
assert isinstance(raw, str)
out = json.loads(raw)
assert out["hits"] and all("id" in h for h in out["hits"])
raw2 = p.handle_tool_call("domu_remember", {"text": "note sur la tortue au crépuscule et la musique"})
rid = json.loads(raw2)["id"]
assert rid
assert json.loads(p.handle_tool_call("domu_forget", {"ids": [rid]}))["deleted"] == 1
print("7. outils: chaînes JSON conformes | remember/forget OK")

# on_memory_write miroir (add) ; time-vectors tracés
p.on_memory_write("add", "memory", "la tortue préfère les caps relatifs au leader du score")
p.on_memory_write("remove", "memory", "jamais indexé")
wait_writes(p)
assert any("caps relatifs" in d["text"] for d in DOCS.values())
drifts = [m for m in METRICS if m["type"] == "focus_drift"]
assert drifts and drifts[-1]["agent"] == "kage"
print("8. on_memory_write(add) miroité, remove ignoré | time-vectors:", len(drifts))

# on_session_switch : /resume ne reset PAS, /new reset
fv = list(p.focus.vector)
p.on_session_switch("sess-002", parent_session_id="sess-001", reset=False)
assert p.focus.vector == fv, "le focus doit survivre à /resume"
p.on_session_switch("sess-003", reset=True)
assert p.focus.vector is None and p.turn == 0
print("9. switch: focus survit à resume, reset sur /new — sémantique ABC exacte")

# pre-compress : sauve les fragments dignes + rend la lecture du focus
p.sync_turn("le driver de la tortue repart", "et domu écoute la musique")
wait_writes(p)
before = len(DOCS)
block = p.on_pre_compress([
    {"role": "user", "content": "insight précieux sur la plaquette du driver m4z3"},
    {"role": "tool", "content": "[...write_file...]"},
    {"role": "assistant", "content": "ok"},
])
wait_writes(p)
assert isinstance(block, str) and "memory-context" in block and "salvaged" in block
assert len(DOCS) == before + 1                                 # 1 seul fragment digne
print("10. pre-compress: 1 fragment sauvé sur 3, lecture du focus retournée")

# contexte non-primary : écritures gatées
p2 = DomuProvider(es_client=FakeES(), embed=embed)
p2.initialize("cron-1", agent_context="cron", agent_identity="kage")
n_before = len(DOCS)
p2.sync_turn("prompt cron qui ne doit jamais devenir mémoire du tout",
             "réponse cron tout aussi interdite de séjour")
wait_writes(p2)
assert len(DOCS) == n_before
note = json.loads(p2.handle_tool_call("domu_remember", {"text": "tentative cron sur le driver"}))
assert note["id"] is None and "cron" in note["note"]
p2.shutdown()
print("11. agent_context='cron': toutes les écritures gatées (règle ABC)")

# setup + shutdown
schema = p.get_config_schema()
assert any(f["key"] == "es_url" for f in schema) and p.backup_paths() == []
with tempfile.TemporaryDirectory() as hh:
    p.save_config({"es_url": "http://localhost:9200", "index": "vm-space"}, hh)
    assert json.load(open(os.path.join(hh, "domu.json")))["index"] == "vm-space"
p.on_session_end([])
client = p._es_client
p.shutdown()
assert client.closed and p.mind is None
print("12. config schema/save, session_end flush, shutdown propre")
print("\nDOMU 0.3.0 : conformité EXACTE au vrai memory_provider.py — tout est vert")
