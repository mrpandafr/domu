"""domu.provider — vectormind wired into Hermes, conformant to the real ABC.

Implements ``agent.memory_provider.MemoryProvider`` exactly (the 315-line
source, not the summary table). Two structural consequences of that source:

* **The interface is synchronous.** Hermes calls plain methods and expects
  them fast; the ABC itself says "use background threads for the actual
  recall and return cached results here". Domu therefore runs its async
  core (vectormind + AsyncElasticsearch) on a dedicated event loop in a
  daemon thread; sync methods submit coroutines with
  ``run_coroutine_threadsafe``. ``prefetch`` serves the cached result from
  ``queue_prefetch`` when present, else does a bounded recall
  (``prefetch_timeout``, default 1.5s) and returns "" on timeout — honest,
  never blocking the turn.
* **Writes are context-gated.** ``initialize`` receives ``agent_context``;
  anything other than "primary" (cron, subagent, flush) makes every write
  path a no-op, per the ABC's warning that cron prompts would corrupt user
  representations.

The one absolute rule stays structural: nothing enters a context block that
the space didn't return. Zero hits -> the block says so.

Isolation rides on tags the space already indexes:
``bank:{agent_identity}`` + ``scope:{private|shared|public}``; reads are
scoped in the query (own bank + others' scope:public), never post-filtered.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from concurrent.futures import Future
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from vectormind import Focus, Hit, Recall, VectorMind

from .synapse import dedup, worth_remembering

try:  # inside a Hermes checkout
    from agent.memory_provider import MemoryProvider  # type: ignore
except ImportError:  # standalone / tests
    class MemoryProvider:  # type: ignore
        pass

logger = logging.getLogger(__name__)

_default_embed_fn: Optional[Callable] = None


def _load_default_embed() -> Callable:
    """Lazy-load bge-small-en-v1.5 once, cache at module level."""
    global _default_embed_fn
    if _default_embed_fn is None:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")

        async def _embed(texts: List[str]) -> List[List[float]]:
            return [_model.encode(t, normalize_embeddings=True).tolist()
                    for t in texts]

        _default_embed_fn = _embed
    return _default_embed_fn


_ABSOLUTE_RULE = (
    "Absolute rule: never embroider reality. If memory returns nothing, "
    "say so. If a fragment is orphaned, admit it. If an external call "
    "fails, answer \"I can't\"."
)


class DomuProvider(MemoryProvider):
    """One space, three circles, one synchronous face for Hermes."""

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        *,
        es_client: Any = None,
        es_client_factory: Callable[[], Any] | None = None,
        embed: Callable[[List[str]], Any] | None = None,
        categories: Dict[str, str] | None = None,
        fields: Any = None,
    ) -> None:
        self.config = dict(config or {})
        self._es_client = es_client
        self._client_factory = es_client_factory
        self._embed = embed or self.config.get("embed")
        self._categories_seed = categories or self.config.get("categories")
        self._fields = fields or self.config.get("fields")
        self.index = self.config.get("index", "vm-space")
        self.metrics_index = self.config.get("metrics_index", "domu-metrics")
        self.l1_size = int(self.config.get("l1_size", 3))
        self.l2_size = int(self.config.get("l2_size", 7))
        self.l1_max_chars = int(self.config.get("l1_max_chars", 400))
        self.l2_max_chars = int(self.config.get("l2_max_chars", 160))
        self._focus_alpha = float(self.config.get("focus_alpha", 0.35))
        self._prefetch_timeout = float(self.config.get("prefetch_timeout", 1.5))
        self._read_public = bool(self.config.get("read_public_of_others", True))

        # runtime (set by initialize)
        self.bank_id: str = self.config.get("bank_id", "")
        self.session_id: str = ""
        self.agent_context: str = "primary"
        self.mind: VectorMind | None = None
        self.focus = Focus(alpha=self._focus_alpha)
        self.turn = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._prefetched: tuple[str, str] | None = None
        self._pending: set[Future] = set()
        self._recent: list[tuple[str, list[float]]] = []

    # ------------------------------------------------------------------
    # identity & lifecycle (ABC: name, is_available, initialize, shutdown)
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "domu"

    def is_available(self) -> bool:
        """Config/deps check only — no network, per the ABC contract."""
        if self._embed is None:
            try:
                import sentence_transformers  # noqa: F401
            except ImportError:
                return False
        if self._es_client is not None or self._client_factory is not None:
            return True
        if self.config.get("es_url") or os.getenv("DOMU_ES_URL"):
            try:
                import elasticsearch  # noqa: F401
                return True
            except ImportError:
                return False
        return False

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        """Start the background loop, connect ES, open the circles.

        Honors the documented kwargs: ``agent_identity`` becomes the bank
        (per-profile scoping), ``agent_context`` gates every write path.
        """
        self.session_id = session_id
        self.agent_context = kwargs.get("agent_context", "primary")
        self.bank_id = (self.bank_id or kwargs.get("agent_identity")
                        or kwargs.get("agent_workspace") or "hermes")
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever,
                                        name="domu-loop", daemon=True)
        self._thread.start()
        self._run(self._ainit(), timeout=30)
        logger.info("domu ready: index=%s bank=%s context=%s",
                    self.index, self.bank_id, self.agent_context)

    async def _ainit(self) -> None:
        if self._embed is None:
            self._embed = _load_default_embed()
        if self._es_client is None:
            if self._client_factory is not None:
                self._es_client = self._client_factory()
            else:
                from elasticsearch import AsyncElasticsearch  # type: ignore
                url = self.config.get("es_url") or os.environ["DOMU_ES_URL"]
                kwargs: Dict[str, Any] = {"hosts": [url], "retry_on_timeout": True,
                                          "max_retries": 3, "http_compress": True}
                api_key = self.config.get("api_key") or os.getenv("DOMU_ES_API_KEY")
                if api_key:
                    kwargs["api_key"] = api_key
                self._es_client = AsyncElasticsearch(**kwargs)
        if not await self._es_client.ping():
            raise RuntimeError("Elasticsearch not reachable")
        self.mind = await VectorMind.open(
            self._es_client, self._embed, index=self.index,
            dims=self.config.get("dims"), fields=self._fields,
            categories=self._categories_seed,
        )
        visibility: dict = {"bool": {"should": [
            {"term": {"tags": f"bank:{self.bank_id}"}},
            {"term": {"bank_id.keyword": self.bank_id}},
        ], "minimum_should_match": 1}}
        if self._read_public:
            visibility["bool"]["should"].append({"term": {"tags": "scope:public"}})
        self.mind.space.scope = [visibility]
        self.mind.search.scope = [visibility]

    def shutdown(self) -> None:
        """Flush pending writes, close the client, stop the loop."""
        for fut in list(self._pending):
            try:
                fut.result(timeout=10)
            except Exception:
                pass
        self._pending.clear()
        if self._loop is not None:
            if self._es_client is not None and hasattr(self._es_client, "close"):
                try:
                    self._run(self._es_client.close(), timeout=10)
                except Exception:
                    pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=5)
        self._loop = None
        self._thread = None
        self.mind = None

    # ------------------------------------------------------------------
    # loop plumbing
    # ------------------------------------------------------------------

    def _run(self, coro: Any, *, timeout: float | None = None) -> Any:
        """Submit to the domu loop and wait (bounded)."""
        if self._loop is None:
            raise RuntimeError("domu is not initialized")

        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _submit(self, coro: Any) -> None:
        """Fire-and-forget on the domu loop; tracked for shutdown flush."""
        if self._loop is None:
            return
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        self._pending.add(fut)
        fut.add_done_callback(self._pending.discard)

    @property
    def _writes_enabled(self) -> bool:
        return self.agent_context == "primary" and self.mind is not None

    # ------------------------------------------------------------------
    # system prompt / prefetch (ABC-exact signatures)
    # ------------------------------------------------------------------

    def system_prompt_block(self) -> str:
        return (
            "Domu — vector memory active. A memory context block precedes each turn "
            "(L1 focus / L2 vault / L3 doors). Trust it. "
            "Use domu_recall only if the user asks for an explicit search "
            "or the prefetch is clearly insufficient. "
            f"{_ABSOLUTE_RULE}"
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Fast path per the ABC: cached result if queue_prefetch warmed it,
        else a bounded recall; "" on timeout (and the recall is re-queued
        so the *next* turn gets it)."""
        if self.mind is None:
            return ""
        if self._prefetched and self._prefetched[0] == query:
            block = self._prefetched[1]
            self._prefetched = None
            return block
        try:
            return self._run(self._build_context(query),
                             timeout=self._prefetch_timeout)
        except Exception:
            self.queue_prefetch(query, session_id=session_id)
            return ""

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        async def _job() -> None:
            try:
                self._prefetched = (query, await self._build_context(query))
            except Exception:
                logger.debug("queue_prefetch failed", exc_info=True)
        if self._loop is not None:
            self._submit(_job())

    # ------------------------------------------------------------------
    # writes (ABC: sync_turn; hooks: on_memory_write, on_delegation)
    # ------------------------------------------------------------------

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Persist a completed turn — non-blocking, through Synapse's gates.

        The M4Z3 case is the design target: a 111-message session that is
        80% tool calls. Only ``user_content`` and ``assistant_content`` are
        candidates; the raw ``messages`` (tool calls, tool results) are
        deliberately ignored — rule 3 at the architecture level. Each
        candidate then still faces Synapse (noise markers, 10-char floor,
        cosine-0.95 dedup) before touching the space.
        """
        if not self._writes_enabled:
            return
        self._submit(self._aremember(user_content, role="user",
                                     session_id=session_id or self.session_id))
        self._submit(self._aremember(assistant_content, role="assistant",
                                     session_id=session_id or self.session_id))

    async def _aremember(self, content: str, *, role: str,
                         scope: str = "shared", session_id: str = "") -> str | None:
        if self.mind is None or not worth_remembering(content):
            return None
        vec = await self.mind.embed_one(content)
        window_texts = [t for t, _ in self._recent] + [content]
        window_vecs = [v for _, v in self._recent] + [vec]
        outcome = dedup(window_texts, window_vecs)
        if len(window_texts) - 1 in outcome.aliases:
            return None
        self._recent = [(window_texts[i], window_vecs[i])
                        for i in outcome.kept][-20:]
        previous = self.focus.last_drift
        self.focus.update(vec)
        await self._record_metric("focus_drift", self.focus.last_drift,
                                  delta=self.focus.last_drift - previous,
                                  context=content[:80])
        ids = await self.mind.remember(
            [content],
            tags=[[f"bank:{self.bank_id}", f"scope:{scope}", f"role:{role}",
                   "type:turn"]],
            meta=[{"turn": self.turn, "role": role,
                   "session_id": session_id or self.session_id}],
        )
        return ids[0]

    def on_memory_write(self, action: str, target: str, content: str,
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        """Mirror built-in memory writes ('add'/'replace'); 'remove' is not
        mirrored — the space keeps history, forgetting is explicit."""
        if action in ("add", "replace") and self._writes_enabled:
            self._submit(self._aremember(content, role="memory-tool"))

    def on_delegation(self, task: str, result: str, *,
                      child_session_id: str = "", **kwargs: Any) -> None:
        if not self._writes_enabled:
            return
        text = f"[delegation] {task}: {result}" if task else result
        self._submit(self._aremember(text, role="subagent",
                                     session_id=child_session_id))

    # ------------------------------------------------------------------
    # tools (ABC: schemas + JSON-string results)
    # ------------------------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {"name": "domu_recall",
             "description": "Search the memory space. Returns the concentric "
                            "circles (L1 focus / L2 vault / L3 doors). Honest "
                            "by design: an empty result means no memory.",
             "parameters": {"type": "object", "properties": {
                 "query": {"type": "string"},
                 "k": {"type": "integer", "default": 8},
                 "tags": {"type": "array", "items": {"type": "string"}},
             }, "required": ["query"]}},
            {"name": "domu_remember",
             "description": "Store a note in the space (goes through "
                            "Synapse's gates).",
             "parameters": {"type": "object", "properties": {
                 "text": {"type": "string"},
                 "scope": {"type": "string",
                            "enum": ["private", "shared", "public"],
                            "default": "shared"},
             }, "required": ["text"]}},
            {"name": "domu_forget",
             "description": "Delete notes by id.",
             "parameters": {"type": "object", "properties": {
                 "ids": {"type": "array", "items": {"type": "string"}},
             }, "required": ["ids"]}},
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any],
                         **kwargs: Any) -> str:
        """ABC contract: MUST return a JSON string."""
        try:
            result = self._run(self._atool(tool_name, args), timeout=30)
        except Exception as exc:
            result = {"error": f"domu tool failed: {exc}"}
        return json.dumps(result, ensure_ascii=False)

    async def _atool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if self.mind is None:
            return {"error": "domu is not initialized"}
        if name == "domu_recall":
            recall = await self.mind.recall(
                args["query"], focus=self.focus, k=int(args.get("k", 8)),
                tags=args.get("tags"))
            if not len(recall):
                return {"hits": [], "note": "no memory matches — say so, "
                                             "do not invent"}
            return {"hits": [self._hit_dict(h) for h in recall]}
        if name == "domu_remember":
            if not self._writes_enabled:
                return {"id": None, "note": f"writes disabled in "
                                             f"{self.agent_context!r} context"}
            stored = await self._aremember(args["text"], role="agent",
                                           scope=args.get("scope", "shared"))
            return {"id": stored} if stored else {
                "id": None, "note": "rejected by Synapse (noise/dup/too small)"}
        if name == "domu_forget":
            return {"deleted": await self.mind.forget(args["ids"])}
        return {"error": f"unknown domu tool {name!r}"}

    # ------------------------------------------------------------------
    # optional hooks (ABC-exact signatures)
    # ------------------------------------------------------------------

    def on_turn_start(self, turn_number: int, message: str, **kwargs: Any) -> None:
        self.turn = turn_number
        if message and self.mind is not None:
            self.queue_prefetch(message)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Session boundary: wait for the queued writes to land."""
        for fut in list(self._pending):
            try:
                fut.result(timeout=10)
            except Exception:
                pass
        self._pending.clear()

    def on_session_switch(self, new_session_id: str, *,
                          parent_session_id: str = "", reset: bool = False,
                          rewound: bool = False, **kwargs: Any) -> None:
        """The ABC's semantics, honored precisely: the focus only resets on
        a genuinely new conversation (``reset=True``). /resume, /branch and
        compression continue the same logical conversation — the center of
        attention survives the id rotation."""
        self.session_id = new_session_id
        self._prefetched = None
        if reset:
            self.focus = Focus(alpha=self._focus_alpha)
            self._recent.clear()
            self.turn = 0
        if rewound:
            self._recent.clear()

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Extract from the messages about to be discarded: run their user/
        assistant contents through Synapse (so the salient ones become
        memory before they vanish), and return the L1 reading of the
        current focus for the compression prompt. Nothing invented."""
        salvaged = 0
        if self._writes_enabled:
            for m in messages or []:
                if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
                    if worth_remembering(m["content"]):
                        self._submit(self._aremember(m["content"],
                                                     role=m["role"]))
                        salvaged += 1
        if self.mind is None or self.focus.vector is None:
            return ""
        try:
            block = self._run(
                self._build_context("(current focus)",
                                    query_vector=self.focus.vector),
                timeout=self._prefetch_timeout * 2)
        except Exception:
            return ""
        if salvaged:
            block += f"\n({salvaged} fragments salvaged to memory before compression)"
        return block

    # ------------------------------------------------------------------
    # setup / backup (ABC)
    # ------------------------------------------------------------------

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {"key": "es_url", "description": "Elasticsearch endpoint URL",
             "required": True, "env_var": "DOMU_ES_URL",
             "default": "http://localhost:9200"},
            {"key": "api_key", "description": "Elasticsearch API key (optional)",
             "secret": True, "env_var": "DOMU_ES_API_KEY"},
            {"key": "index", "description": "Space index name",
             "default": "vm-space"},
            {"key": "bank_id", "description": "Memory bank (defaults to the "
                                               "agent identity)"},
        ]

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        path = os.path.join(hermes_home, "domu.json")
        os.makedirs(hermes_home, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(values, f, indent=2, ensure_ascii=False)

    def backup_paths(self) -> List[str]:
        """Memory lives in Elasticsearch, config lives under HERMES_HOME —
        nothing external on disk."""
        return []

    # ------------------------------------------------------------------
    # cron — dedicated read/write paths that bypass _writes_enabled
    # ------------------------------------------------------------------

    def read_daily_summary(self, date: str | None = None) -> Dict[str, Any]:
        """Return today's turns + metrics for the bank (sync, for cron use)."""
        return self._run(self._adaily_summary(date), timeout=30)

    def write_cron_recap(self, text: str, date: str | None = None) -> Optional[str]:
        """Write a recap document — cron-dedicated path, always permitted.

        Normal writes are gated by _writes_enabled (cron context blocks
        them to protect user representations). Recap documents are *about*
        what happened, not conversational turns — they explicitly belong in
        the space and must survive the gate.
        """
        from datetime import date as _date
        today = date or _date.today().isoformat()
        return self._run(self._awrite_recap(text, today), timeout=30)

    async def _adaily_summary(self, date: str | None = None) -> Dict[str, Any]:
        from datetime import date as _date
        today = date or _date.today().isoformat()
        since = f"{today}T00:00:00Z"
        turns: List[Dict] = []
        metrics: List[Dict] = []
        if self._es_client is None:
            return {"date": today, "turns": turns, "metrics": metrics}
        try:
            resp = await self._es_client.search(
                index=self.index,
                body={
                    "query": {"bool": {"filter": [
                        {"term": {"tags": f"bank:{self.bank_id}"}},
                        {"range": {"at": {"gte": since}}},
                    ]}},
                    "_source": ["text", "tags", "at", "meta"],
                    "size": 200,
                    "sort": [{"at": "asc"}],
                    "track_total_hits": False,
                },
            )
            turns = [h["_source"] for h in resp["hits"]["hits"]]
        except Exception:
            logger.debug("daily_summary: turn query failed", exc_info=True)
        try:
            mresp = await self._es_client.search(
                index=self.metrics_index,
                body={
                    "query": {"bool": {"filter": [
                        {"term": {"agent": self.bank_id}},
                        {"range": {"at": {"gte": since}}},
                    ]}},
                    "_source": ["type", "value", "delta", "context", "at"],
                    "size": 500,
                    "sort": [{"at": "asc"}],
                    "track_total_hits": False,
                },
            )
            metrics = [h["_source"] for h in mresp["hits"]["hits"]]
        except Exception:
            pass  # metrics index may not exist yet
        return {"date": today, "turns": turns, "metrics": metrics}

    async def _awrite_recap(self, text: str, date: str) -> Optional[str]:
        if self.mind is None:
            return None
        ids = await self.mind.remember(
            [text],
            tags=[[f"bank:{self.bank_id}", "type:recap", f"date:{date}"]],
            meta=[{"date": date, "role": "cron", "bank_id": self.bank_id}],
        )
        return ids[0]

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    @staticmethod
    def _hit_dict(h: Hit) -> Dict[str, Any]:
        return {"id": h.id, "text": h.text, "ring": h.ring,
                "category": h.category, "score": round(h.score, 6),
                "tags": h.tags}

    async def _record_metric(self, mtype: str, value: float, *,
                             delta: float | None = None,
                             context: str = "") -> None:
        try:
            await self._es_client.index(index=self.metrics_index, document={
                "at": datetime.now(timezone.utc).isoformat(),
                "type": mtype, "agent": self.bank_id,
                "value": round(float(value), 6),
                "delta": round(float(delta), 6) if delta is not None else None,
                "context": context,
            })
        except Exception:
            logger.debug("metric %s dropped", mtype, exc_info=True)

    async def _build_context(self, query: str,
                             query_vector: list[float] | None = None) -> str:
        if self.mind is None:
            return ""
        if query_vector is not None:
            hits = await self.mind.search.search(
                query_text=query, query_vector=query_vector,
                k=self.l1_size + self.l2_size)
            for h in hits:
                h.ring = 1
                if self.mind.categories:
                    h.category, _ = self.mind.categories.attach(h.vector)
            recall = Recall(hits)
        else:
            recall = await self.mind.recall(
                query, focus=self.focus, k=self.l1_size + self.l2_size)
        if not len(recall):
            return "(no memory matches this focus — say so rather than invent)"
        l1 = (recall.l1 or recall.hits)[:self.l1_size]
        l1_ids = {h.id for h in l1}
        l2 = [h for h in recall.hits if h.id not in l1_ids][:self.l2_size]
        doors = sorted({h.category for h in recall.hits if h.category})
        lines = ["L1 — FOCUS"]
        lines += [f"  • {h.text[:self.l1_max_chars]}" for h in l1]
        if l2:
            lines.append("L2 — VAULT")
            lines += [f"  • {h.text[:self.l2_max_chars]}" for h in l2]
        if doors:
            lines.append(f"L3 — PORTES: {', '.join(doors)}")
        return "\n".join(lines)
