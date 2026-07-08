"""vectormind.circles — the three concentric circles over one space.

    L1  FOCUS       computed, never stored: an exponential moving average of
                    the conversation's turn embeddings. The center moves;
                    the space doesn't.
    L2  VAULT       the space itself, read through fused retrieval
                    (search.HybridSearch): relevance-weighted knowledge.
    L3  CATEGORIES  a *fixed* set of named doors. A hit is attached to its
                    nearest door at query time — labels are computed, never
                    written, so the taxonomy cannot swell.

The hierarchy is radii, not schema: every hit gets a ``ring`` (1 = inside
the focus circle, 2 = vault) and a ``category`` (its L3 door), both derived
from vectors at query time. Same space for everyone, different radii around
the center.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

from .search import Hit, HybridSearch, cosine
from .space import Embedder, Space


# ---------------------------------------------------------------------------
# L1 — Focus: an ephemeral center of attention
# ---------------------------------------------------------------------------

@dataclass
class Focus:
    """The moving center of the conversation. Never persisted.

    ``update()`` folds each new turn in as an exponential moving average:
    recent turns pull hardest, old ones fade geometrically — the mathematical
    shape of attention. ``drift()`` measures how far the last turn pulled,
    which is a topic-change detector for free.
    """

    vector: list[float] | None = None
    alpha: float = 0.35          # pull of the newest turn
    turns: int = 0
    last_drift: float = 0.0

    def update(self, turn_vector: Sequence[float]) -> "Focus":
        v = list(turn_vector)
        if self.vector is None:
            self.vector, self.turns = v, 1
            self.last_drift = 0.0
            return self
        self.last_drift = 1.0 - cosine(self.vector, v)
        self.vector = [(1 - self.alpha) * a + self.alpha * b
                       for a, b in zip(self.vector, v)]
        self.turns += 1
        return self

    def drifted(self, threshold: float = 0.5) -> bool:
        """True when the last turn moved the center sharply (topic change)."""
        return self.last_drift >= threshold


# ---------------------------------------------------------------------------
# L3 — Categories: fixed doors, query-time attachment
# ---------------------------------------------------------------------------

class Categories:
    """A fixed set of named anchors in the same space.

    Each category is seeded by a short descriptive phrase; its anchor is the
    phrase's embedding, computed once. ``attach()`` finds a hit's nearest
    door. Nothing is ever written back: an apax is *at* a door for the
    duration of a query, not filed under it.
    """

    def __init__(self, anchors: dict[str, list[float]]) -> None:
        self._anchors = dict(anchors)

    @classmethod
    async def seed(cls, embed: Embedder, seeds: dict[str, str]) -> "Categories":
        """Build the doors from ``{name: descriptive phrase}``."""
        names = list(seeds.keys())
        vectors = await embed([seeds[n] for n in names])
        return cls(dict(zip(names, vectors)))

    @property
    def names(self) -> list[str]:
        return list(self._anchors)

    def attach(self, vector: Sequence[float] | None) -> tuple[str | None, float]:
        """Nearest door and its similarity; (None, 0.0) without a vector."""
        if not vector or not self._anchors:
            return None, 0.0
        best_name, best_sim = None, -2.0
        for name, anchor in self._anchors.items():
            sim = cosine(list(vector), anchor)
            if sim > best_sim:
                best_name, best_sim = name, sim
        return best_name, best_sim


# ---------------------------------------------------------------------------
# Recall — one query, three readings
# ---------------------------------------------------------------------------

@dataclass
class Recall:
    """The shaped hits, readable through any circle."""

    hits: list[Hit]
    focus_threshold: float = 0.6

    @property
    def l1(self) -> list[Hit]:
        """Inside the focus circle."""
        return [h for h in self.hits if h.ring == 1]

    @property
    def l2(self) -> list[Hit]:
        """The vault ring."""
        return [h for h in self.hits if h.ring != 1]

    @property
    def by_category(self) -> dict[str, list[Hit]]:
        """The L3 reading: hits grouped by their door."""
        out: dict[str, list[Hit]] = {}
        for h in self.hits:
            out.setdefault(h.category or "∅", []).append(h)
        return out

    def __iter__(self):
        return iter(self.hits)

    def __len__(self) -> int:
        return len(self.hits)


# ---------------------------------------------------------------------------
# The facade
# ---------------------------------------------------------------------------

class VectorMind:
    """One space, three circles, five verbs.

        vm = await VectorMind.open(client, embed,
                                   categories={"la-tortue": "…", ...})
        await vm.remember(["…"], tags=[["atelier"]])
        focus = Focus().update(await vm.embed_one("ce qu'on est en train de faire"))
        recall = await vm.recall("où en est le driver ?", focus=focus, k=8)
        recall.l1, recall.l2, recall.by_category
    """

    def __init__(self, space: Space, categories: Categories | None = None,
                 *, focus_threshold: float = 0.6) -> None:
        self.space = space
        self.search = HybridSearch(space.client, space.index,
                                   fields=space.fields, scope=space.scope)
        self.categories = categories
        self.focus_threshold = focus_threshold

    @classmethod
    async def open(cls, client: Any, embed: Embedder, *,
                   index: str = "vm-space", dims: int | None = None,
                   fields: Any = None,
                   categories: dict[str, str] | None = None,
                   focus_threshold: float = 0.6) -> "VectorMind":
        space = Space(client, embed, index=index, dims=dims, fields=fields)
        await space.ensure()
        doors = await Categories.seed(embed, categories) if categories else None
        return cls(space, doors, focus_threshold=focus_threshold)

    @classmethod
    async def over_hindsight(
        cls, backend: Any, embed: Embedder, *, bank_id: str,
        schema: str = "public", fact_types: Sequence[str] | None = None,
        categories: dict[str, str] | None = None,
        focus_threshold: float = 0.6,
    ) -> "VectorMind":
        """Open the three circles OVER a Hindsight-driver space — no bridge,
        no copy, no second storage: a read-only lens on
        ``{schema}-memory_units``.

        * ``backend``  — the driver's ElasticsearchBackend (its shared client
          is reused: one pool, one auth, one config);
        * ``embed``    — MUST be the same embedding model Hindsight retains
          with (same space, same dims), or every distance is meaningless;
        * ``bank_id``  — stamped on every read (Hindsight's tenancy);
        * ``fact_types`` — optional extra scope, e.g. ("observation",) to
          read only the consolidated ring.

        Writes stay with Hindsight: ``remember()``/``forget()`` raise here,
        pointing at retain — entities, links and consolidation must not be
        bypassed.
        """
        from .space import HINDSIGHT_FIELDS

        client = getattr(backend, "client", None) or backend.get_pool().client
        scope: list[dict] = [{"term": {"bank_id": bank_id}}]
        if fact_types:
            scope.append({"terms": {"fact_type": list(fact_types)}})
        space = Space(
            client, embed,
            index=f"{schema}-memory_units".lower(),
            fields=HINDSIGHT_FIELDS, scope=scope, read_only=True,
        )
        doors = await Categories.seed(embed, categories) if categories else None
        return cls(space, doors, focus_threshold=focus_threshold)

    # -- verbs -------------------------------------------------------------

    async def embed_one(self, text: str) -> list[float]:
        return (await self.space.embed([text]))[0]

    async def remember(self, texts: Sequence[str], **kwargs: Any) -> list[str]:
        return await self.space.remember(texts, **kwargs)

    async def forget(self, ids: Sequence[str]) -> int:
        return await self.space.forget(ids)

    async def recall(
        self,
        query: str,
        *,
        focus: Focus | None = None,
        k: int = 10,
        tags: Sequence[str] | None = None,
        apax_cap: float = 0.15,
        recency_cap: float = 0.05,
        recency_half_life_days: float = 30.0,
        now: datetime | None = None,
    ) -> Recall:
        """One fused query; the circles are readings of its result.

        * fusion + shaping: search.HybridSearch (native RRF or fallback,
          additive capped bonuses);
        * ring: 1 when the hit sits inside the focus circle
          (cosine to the focus center ≥ focus_threshold), else 2;
        * category: nearest L3 door, attached in passing.
        """
        query_vector = await self.embed_one(query)
        filters = [{"terms": {self.space.fields.tags: list(tags)}}] if tags else []
        hits = await self.search.search(
            query_text=query, query_vector=query_vector, k=k, filters=filters,
            apax_cap=apax_cap, recency_cap=recency_cap,
            recency_half_life_days=recency_half_life_days, now=now,
        )
        center = focus.vector if focus else None
        for h in hits:
            if center is not None and h.vector:
                h.ring = 1 if cosine(center, h.vector) >= self.focus_threshold else 2
            else:
                h.ring = 2
            if self.categories:
                h.category, _ = self.categories.attach(h.vector)
        return Recall(hits, focus_threshold=self.focus_threshold)
