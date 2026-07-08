"""vectormind.search — fusion in the engine, shaping at the edge.

The one design rule of this module:

    **Fusion belongs to Elasticsearch. Shaping belongs to the client.**

* *Fusion* — combining the lexical and semantic views of the space — runs
  inside ES through the native ``rrf`` retriever (8.14+), one request, zero
  Python merging. Because the native retriever has historically sat behind
  a licensed tier, a faithful Python RRF (same k=60 constant, same window)
  stands as an automatic fallback: the first 4xx flips a per-instance
  switch and every later call takes the two-search path. Same results
  contract either way.
* *Shaping* — the small, opinionated score adjustments — happens once,
  client-side, after fusion, identically for both paths:
  - **apax bonus**: additive and capped as a *fraction of the leader's
    fused score*, never multiplicative and never absolute. Rarity is
    measured honestly from the retrieved neighborhood itself (how isolated
    a hit is from the other hits), not from a corpus statistic we don't
    have. A rare-but-off-topic document can gain at most ``apax_cap`` ×
    the top fused score; it can never displace an on-topic leader.
  - **recency**: exponential half-life decay, additive and relative too.

Every hit carries its audit trail: raw rrf score, per-view ranks, bonuses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

RRF_K = 60  # the canonical reciprocal-rank constant, native and fallback alike


@dataclass
class Hit:
    id: str
    text: str
    tags: list[str]
    at: datetime | None
    meta: dict
    vector: list[float] | None
    score: float                 # final shaped score (rrf + bonuses)
    rrf: float                   # fusion score before shaping
    ranks: dict[str, int] = field(default_factory=dict)   # view -> rank (1-based)
    bonuses: dict[str, float] = field(default_factory=dict)
    category: str | None = None  # attached by circles.Categories
    ring: int | None = None      # 1 = focus, 2 = vault (annotated by circles)


def _parse_at(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class HybridSearch:
    """One space, two views (BM25 + kNN), one fused ranking."""

    def __init__(self, client: Any, index: str, *, fields: Any = None,
                 scope: list[dict] | None = None) -> None:
        from .space import FieldMap

        self.client = client
        self.index = index
        self.fields = fields or FieldMap()
        self.scope = list(scope or [])
        self._native_rrf_available: bool | None = None  # unknown until first call

    # -- public -----------------------------------------------------------

    async def search(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        k: int = 10,
        filters: list[dict] | None = None,
        num_candidates: int | None = None,
        apax_cap: float = 0.0,
        recency_cap: float = 0.0,
        recency_half_life_days: float = 30.0,
        now: datetime | None = None,
    ) -> list[Hit]:
        """Fused retrieval over the space, shaped, sorted by final score.

        ``apax_cap`` / ``recency_cap`` are the *maximum additive* bonuses
        (0 disables). Shaping never multiplies.
        """
        filters = filters or []
        num_candidates = num_candidates or max(k * 5, 100)
        window = max(k * 3, 50)

        if self._native_rrf_available is not False:
            try:
                hits = await self._native(query_text, query_vector, k, filters,
                                          num_candidates, window)
                self._native_rrf_available = True
            except Exception as exc:
                status = getattr(exc, "status_code", getattr(exc, "status", None))
                if self._native_rrf_available is None and (status is None or 400 <= int(status) < 500):
                    # native retriever unsupported (version/licence): remember,
                    # fall back forever on this instance — never retry-spam.
                    self._native_rrf_available = False
                    hits = await self._fallback(query_text, query_vector, k,
                                                filters, num_candidates, window)
                else:
                    raise
        else:
            hits = await self._fallback(query_text, query_vector, k,
                                        filters, num_candidates, window)

        self._shape(hits, query_vector, apax_cap, recency_cap,
                    recency_half_life_days, now)
        hits.sort(key=lambda h: -h.score)
        return hits[:k]

    # -- fusion: native rrf retriever (the showcase) ------------------------

    def _views(self, query_text: str, query_vector: list[float],
               filters: list[dict], k: int, num_candidates: int) -> tuple[dict, dict]:
        f = self.fields
        all_filters = self.scope + filters
        lexical = {"standard": {"query": {"bool": {
            "must": [{"match": {f.text: query_text}}],
            "filter": all_filters,
        }}}}
        semantic = {"knn": {
            "field": f.vector, "query_vector": query_vector,
            "k": max(k, 10), "num_candidates": num_candidates,
            "filter": all_filters,
        }}
        return lexical, semantic

    async def _native(self, query_text, query_vector, k, filters,
                      num_candidates, window) -> list[Hit]:
        lexical, semantic = self._views(query_text, query_vector, filters, k, num_candidates)
        resp = await self.client.search(
            index=self.index,
            body={
                "retriever": {"rrf": {
                    "retrievers": [lexical, semantic],
                    "rank_window_size": window,
                    "rank_constant": RRF_K,
                }},
                "size": window,
                "_source": self.fields.source(),
                "track_total_hits": False,
            },
        )
        hits: list[Hit] = []
        for rank, h in enumerate(resp["hits"]["hits"], start=1):
            hit = self._hit(h)
            hit.score = hit.rrf = float(h.get("_score") or 0.0)
            hit.ranks["fused"] = rank
            hits.append(hit)
        return hits

    def _hit(self, h: dict) -> Hit:
        f, src = self.fields, h["_source"]
        meta = dict((src.get(f.meta) or {})) if f.meta else {}
        for name in f.extra:
            if src.get(name) is not None:
                meta[name] = src[name]
        return Hit(
            id=str(src.get(f.id, h.get("_id"))), text=src.get(f.text, ""),
            tags=src.get(f.tags) or [], at=_parse_at(src.get(f.at)),
            meta=meta, vector=src.get(f.vector),
            score=0.0, rrf=0.0,
        )

    # -- fusion fallback: the same RRF, spelled out ---------------------------

    async def _fallback(self, query_text, query_vector, k, filters,
                        num_candidates, window) -> list[Hit]:
        lexical, semantic = self._views(query_text, query_vector, filters, k, num_candidates)
        source = self.fields.source()
        resp = await self.client.msearch(searches=[
            {"index": self.index},
            {"query": lexical["standard"]["query"], "size": window,
             "_source": source, "track_total_hits": False},
            {"index": self.index},
            {"knn": dict(semantic["knn"], k=window), "size": window,
             "_source": source, "track_total_hits": False},
        ])
        views = dict(zip(("lexical", "semantic"), resp["responses"]))
        by_id: dict[str, Hit] = {}
        for view, sub in views.items():
            if sub.get("error"):
                raise RuntimeError(f"fallback view {view}: {sub['error']}")
            for rank, h in enumerate(sub["hits"]["hits"], start=1):
                src = h["_source"]
                hid = str(src.get(self.fields.id, h.get("_id")))
                hit = by_id.get(hid)
                if hit is None:
                    hit = by_id[hid] = self._hit(h)
                hit.ranks[view] = rank
                hit.rrf += 1.0 / (RRF_K + rank)   # the exact native formula
        hits = list(by_id.values())
        for h in hits:
            h.score = h.rrf
        hits.sort(key=lambda h: -h.rrf)
        return hits[:window]

    # -- shaping: additive, capped, auditable ---------------------------------
    #
    # Caps are *fractions of the leader's fused score*: RRF scores live on a
    # tiny scale (the winner of two views is 2/(k+1) ≈ 0.033), so absolute
    # bonuses would drown the fusion. Relative caps make shaping subordinate
    # to fusion by construction: apax_cap=0.15 reads "an isolated hit may
    # gain at most 15% of the top fused score" — never enough to displace an
    # on-topic leader, always enough to surface within its ring.

    @staticmethod
    def _shape(hits: list[Hit], query_vector: list[float],
               apax_cap: float, recency_cap: float,
               half_life_days: float, now: datetime | None) -> None:
        if not hits:
            return
        scale = max(h.rrf for h in hits)
        if scale <= 0:
            return
        if apax_cap > 0 and len(hits) > 1:
            with_vec = [h for h in hits if h.vector]
            for h in with_vec:
                nearest = max(
                    (cosine(h.vector, o.vector) for o in with_vec
                     if o is not h and o.vector),
                    default=1.0,
                )
                isolation = max(0.0, 1.0 - nearest)   # alone in the neighborhood
                bonus = apax_cap * scale * isolation
                if bonus > 0:
                    h.bonuses["apax"] = bonus
                    h.score += bonus
        if recency_cap > 0:
            ref = now or datetime.now(timezone.utc)
            for h in hits:
                if not h.at:
                    continue
                age_days = max(0.0, (ref - h.at).total_seconds() / 86400)
                bonus = recency_cap * scale * math.exp(-age_days / half_life_days * math.log(2))
                if bonus > 1e-12:
                    h.bonuses["recency"] = bonus
                    h.score += bonus
