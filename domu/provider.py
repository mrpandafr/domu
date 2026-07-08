"""domu.provider — the first link of Wired: vectormind wired into Hermes.

Implements the MemoryProvider contract described in DOMU-HERMES.md
(13 methods). The provider owns nothing clever: vectormind holds the
circles, Synapse holds the filter, Elasticsearch holds the memory. Domu
only orchestrates — and enforces the one absolute rule:

    **Never embroider reality.** Zero hits -> say so. Orphan apax -> admit
    it. The memory context never contains anything the space didn't return.

Signatures note: memory_provider.py (315 lines) wasn't available when this
was written; every hook accepts a tolerant ``**kwargs`` tail and the base
class is imported defensively. Ship memory_provider.py for the exact
one-pass conformity check (the base.py lesson, applied preemptively).

Isolation (one cluster, N agents) rides on tags, the field the space
already indexes:

    bank:{bank_id}     physical-ish separation (native filter)
    scope:{private|shared|public}

An agent reads: its own bank (all scopes) + other banks' ``scope:public``.
``scope:private`` of others never passes the door — enforced in the query,
not in post-processing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from vectormind import Focus, Hit, Recall, VectorMind

from .synapse import dedup, worth_remembering

try:  # inside a Hermes checkout
    from agent.memory_provider import MemoryProvider  # type: ignore
except ImportError:  # standalone / tests
    class MemoryProvider:  # type: ignore
        pass

logger = logging.getLogger(__name__)

_ABSOLUTE_RULE = (
    "Absolute rule: never embroider reality. If memory returns nothing, "
    "say so. If a fragment is orphaned, admit it. If an external call "
    "fails, answer \"I can't\"."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DomuProvider(MemoryProvider):
    """One space, three circles, thirteen hooks."""

    def __init__(
        self,
        *,
        es_client_factory: Callable[[], Any] | None = None,
        es_client: Any = None,
        embed: Callable[[list[str]], Any],
        bank_id: str,
        index: str = "vm-space",
        metrics_index: str = "domu-metrics",
        categories: dict[str, str] | None = None,
        dims: int | None = None,
        l1_size: int = 3,
        l2_size: int = 7,
        focus_alpha: float = 0.35,
        read_public_of_others: bool = True,
    ) -> None:
        self._client_factory = es_client_factory
        self._client = es_client
        self._embed = embed
        self.bank_id = bank_id
        self.index = index
        self.metrics_index = metrics_index
        self._categories_seed = categories
        self._dims = dims
        self.l1_size, self.l2_size = l1_size, l2_size
        self._focus_alpha = focus_alpha
        self._read_public = read_public_of_others

        self.mind: VectorMind | None = None
        self.focus = Focus(alpha=focus_alpha)
        self.turn = 0
        self._prefetched: tuple[str, str] | None = None   # (query, block)
        self._bg: set[asyncio.Task] = set()
        self._recent: list[tuple[str, list[float]]] = []  # dedup window

    # ------------------------------------------------------------------
    # identity & lifecycle
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "domu"

    @property
    def is_available(self) -> bool:
        return self.mind is not None

    async def initialize(self, **kwargs: Any) -> None:
        """Connect ES, open the circles, stamp the isolation scope."""
        if self._client is None:
            if self._client_factory is None:
                raise RuntimeError("DomuProvider needs es_client or es_client_factory")
            self._client = self._client_factory()
        self.mind = await VectorMind.open(
            self._client, self._embed, index=self.index, dims=self._dims,
            categories=self._categories_seed,
        )
        # isolation: reads are scoped in the query, never post-filtered
        visibility: dict = {"bool": {"should": [
            {"term": {"tags": f"bank:{self.bank_id}"}},
        ], "minimum_should_match": 1}}
        if self._read_public:
            visibility["bool"]["should"].append(
                {"term": {"tags": "scope:public"}})
        self.mind.space.scope = [visibility]
        self.mind.search.scope = [visibility]
        logger.info("domu ready: index=%s bank=%s", self.index, self.bank_id)

    async def shutdown(self, **kwargs: Any) -> None:
        for t in list(self._bg):
            t.cancel()
        self._bg.clear()
        if self._client is not None and hasattr(self._client, "close"):
            await self._client.close()
        self.mind = None

    # ------------------------------------------------------------------
    # the agent-facing surface
    # ------------------------------------------------------------------

    def system_prompt_block(self, **kwargs: Any) -> str:
        doors = ", ".join(self.mind.categories.names) if (
            self.mind and self.mind.categories) else "—"
        return (
            "You have access to Domu, a vector memory over one shared "
            "space with three concentric readings: L1 the current focus, "
            "L2 the vault, L3 the doors ({doors}). A <memory-context> "
            "block precedes each turn; tools domu_recall / domu_remember / "
            "domu_forget are available for explicit access. {rule}"
        ).format(doors=doors, rule=_ABSOLUTE_RULE)

    async def prefetch(self, query: str, **kwargs: Any) -> str:
        """The per-turn L1 context (blocking path). Returns the
        <memory-context> block — honest by construction: empty space,
        empty block that says so."""
        if self._prefetched and self._prefetched[0] == query:
            block = self._prefetched[1]
            self._prefetched = None
            return block
        return await self._build_context(query)

    def queue_prefetch(self, query: str, **kwargs: Any) -> None:
        """Background path: warm the next turn's context."""
        async def _job() -> None:
            try:
                self._prefetched = (query, await self._build_context(query))
            except Exception:
                logger.warning("queue_prefetch failed", exc_info=True)
        task = asyncio.get_event_loop().create_task(_job())
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    async def sync_turn(self, content: str, *, role: str = "user",
                        scope: str = "shared", **kwargs: Any) -> str | None:
        """Index one turn — through Synapse's gates, never around them.

        Returns the stored id, or None when Synapse said no (noise, too
        small, duplicate). Also moves the focus and records its drift as a
        time-vector."""
        if self.mind is None or not worth_remembering(content):
            return None
        vec = await self.mind.embed_one(content)
        # dedup against the recent window (cosine > 0.95 -> same thought)
        window_texts = [t for t, _ in self._recent] + [content]
        window_vecs = [v for _, v in self._recent] + [vec]
        outcome = dedup(window_texts, window_vecs)
        if len(window_texts) - 1 in outcome.aliases:
            return None                       # a redite of something recent
        self._recent = [(window_texts[i], window_vecs[i])
                        for i in outcome.kept][-20:]

        previous_drift = self.focus.last_drift
        self.focus.update(vec)
        await self._record_metric("focus_drift", self.focus.last_drift,
                                  delta=self.focus.last_drift - previous_drift,
                                  context=content[:80])
        ids = await self.mind.remember(
            [content],
            tags=[[f"bank:{self.bank_id}", f"scope:{scope}", f"role:{role}",
                   "type:turn"]],
            meta=[{"turn": self.turn, "role": role}],
        )
        return ids[0]

    # ------------------------------------------------------------------
    # tools
    # ------------------------------------------------------------------

    def get_tool_schemas(self, **kwargs: Any) -> list[dict]:
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

    async def handle_tool_call(self, name: str, arguments: dict,
                               **kwargs: Any) -> Any:
        if self.mind is None:
            return {"error": "domu is not initialized"}
        if name == "domu_recall":
            recall = await self.mind.recall(
                arguments["query"], focus=self.focus,
                k=int(arguments.get("k", 8)),
                tags=arguments.get("tags"),
            )
            if not len(recall):
                return {"hits": [], "note": "no memory matches — say so, "
                                             "do not invent"}
            return {"hits": [self._hit_dict(h) for h in recall]}
        if name == "domu_remember":
            stored = await self.sync_turn(arguments["text"], role="agent",
                                          scope=arguments.get("scope", "shared"))
            return {"id": stored} if stored else {
                "id": None, "note": "rejected by Synapse (noise/dup/too small)"}
        if name == "domu_forget":
            return {"deleted": await self.mind.forget(arguments["ids"])}
        return {"error": f"unknown domu tool {name!r}"}

    # ------------------------------------------------------------------
    # session hooks
    # ------------------------------------------------------------------

    def on_turn_start(self, **kwargs: Any) -> None:
        self.turn += 1

    async def on_session_end(self, **kwargs: Any) -> None:
        for t in list(self._bg):
            try:
                await t
            except Exception:
                pass
        self._bg.clear()

    def on_session_switch(self, **kwargs: Any) -> None:
        """/new, /resume — the center of attention resets; the space stays."""
        self.focus = Focus(alpha=self._focus_alpha)
        self._prefetched = None
        self._recent.clear()
        self.turn = 0

    async def on_pre_compress(self, **kwargs: Any) -> str:
        """What survives context compression: the L1 reading of the current
        focus, nothing invented."""
        if self.mind is None or self.focus.vector is None:
            return ""
        return await self._build_context("(current focus)",
                                         query_vector=self.focus.vector)

    async def on_memory_write(self, content: str, **kwargs: Any) -> None:
        """A Hermes-side memory tool wrote something: mirror it (gated)."""
        await self.sync_turn(content, role="agent", scope="shared")

    async def on_delegation(self, result: str, *, task: str = "",
                            **kwargs: Any) -> None:
        """A subagent finished: its outcome becomes memory (gated)."""
        text = f"[delegation] {task}: {result}" if task else result
        await self.sync_turn(text, role="subagent", scope="shared")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    @staticmethod
    def _hit_dict(h: Hit) -> dict:
        return {"id": h.id, "text": h.text, "ring": h.ring,
                "category": h.category, "score": round(h.score, 6),
                "tags": h.tags}

    async def _record_metric(self, mtype: str, value: float, *,
                             delta: float | None = None,
                             context: str = "") -> None:
        """Time-vectors (DOMU-HERMES): the numeric trace of time passing."""
        try:
            await self._client.index(index=self.metrics_index, document={
                "at": _now().isoformat(), "type": mtype, "agent": self.bank_id,
                "value": round(float(value), 6),
                "delta": round(float(delta), 6) if delta is not None else None,
                "context": context,
            })
        except Exception:
            logger.debug("metric %s dropped", mtype, exc_info=True)

    async def _build_context(self, query: str,
                             query_vector: list[float] | None = None) -> str:
        """Render the <memory-context> block — L1/L2/L3, and the honest
        empty form. Nothing enters this block that the space didn't return."""
        if self.mind is None:
            return ""
        if query_vector is not None:
            # focus-driven variant (pre-compress): recall around the center
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
            return ("<memory-context>\n"
                    "(no memory matches this focus — say so rather than "
                    "invent)\n</memory-context>")

        l1 = (recall.l1 or recall.hits)[:self.l1_size]
        l1_ids = {h.id for h in l1}
        l2 = [h for h in recall.hits if h.id not in l1_ids][:self.l2_size]
        doors = sorted({h.category for h in recall.hits if h.category})
        lines = ["<memory-context>", "L1 — FOCUS"]
        lines += [f"  • {h.text}" for h in l1]
        if l2:
            lines.append("L2 — VAULT")
            lines += [f"  • {h.text[:160]}" for h in l2]
        if doors:
            lines.append(f"L3 — PORTES: {', '.join(doors)}")
        lines.append("</memory-context>")
        return "\n".join(lines)
