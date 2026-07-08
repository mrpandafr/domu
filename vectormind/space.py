"""vectormind.space — the substrate.

One index. One document shape. No tables, no layers, no junction indexes:
the L1/L2/L3 hierarchy is *queries over this space*, never schema.

    space = Space(client, embed)
    await space.ensure()
    await space.remember(["…"], tags=[["tortue"]])

Design rules
------------
* The document is deliberately minimal: text, vector, tags, timestamp,
  free-form meta. Anything richer belongs to query time.
* Ids are deterministic when the caller provides them, generated otherwise;
  ``op_type=index`` makes remember() idempotent on caller-provided ids.
* Elasticsearch owns durability and similarity; this module owns nothing
  but the mapping and the bulk plumbing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Sequence

Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldMap:
    """The lens: how a foreign index spells this space's five fields.

    vectormind never requires its own storage — any index holding a text,
    a dense_vector, tags and a timestamp *is* a space. The FieldMap names
    them; ``extra`` lists foreign fields folded into ``hit.meta`` in
    passing (fact_type, context, ...).
    """

    id: str = "id"
    text: str = "text"
    vector: str = "vector"
    tags: str = "tags"
    at: str = "at"
    meta: str | None = "meta"
    extra: tuple[str, ...] = ()

    def source(self, with_vectors: bool = True) -> list[str]:
        out = [self.id, self.text, self.tags, self.at]
        if self.meta:
            out.append(self.meta)
        out.extend(self.extra)
        if with_vectors:
            out.append(self.vector)
        return out


#: the lens over a Hindsight-driver space ({schema}-memory_units)
HINDSIGHT_FIELDS = FieldMap(
    id="id", text="text", vector="embedding", tags="tags",
    at="created_at", meta=None,
    extra=("fact_type", "context", "document_id", "event_date"),
)

MAPPINGS: dict[str, Any] = {
    "properties": {
        "id": {"type": "keyword"},
        "text": {"type": "text"},
        "vector": {"type": "dense_vector", "index": True, "similarity": "cosine"},
        "tags": {"type": "keyword"},
        "at": {"type": "date"},
        "meta": {"type": "object", "enabled": True},
    }
}


def _iso(dt: datetime | None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class Space:
    """The single vector space every circle reads from.

    ``fields`` is the lens (defaults to vectormind's own spelling);
    ``scope`` is a list of ES filter clauses stamped on every read (e.g.
    ``[{"term": {"bank_id": ...}}]`` when reading a Hindsight space);
    ``read_only=True`` guards attached mode: writes must go through the
    owner of the space (Hindsight's retain pipeline), never around it.
    """

    def __init__(self, client: Any, embed: Embedder, *, index: str = "vm-space",
                 dims: int | None = None, fields: FieldMap | None = None,
                 scope: list[dict] | None = None, read_only: bool = False) -> None:
        self.client = client
        self.embed = embed
        self.index = index
        self.dims = dims
        self.fields = fields or FieldMap()
        self.scope = list(scope or [])
        self.read_only = read_only

    def _guard_write(self, verb: str) -> None:
        if self.read_only:
            raise RuntimeError(
                f"{verb}() is disabled: this Space is a read-only lens over "
                f"{self.index!r}. Write through the owner of the space "
                "(Hindsight retain), so entities, links and consolidation "
                "stay consistent."
            )

    # -- lifecycle ---------------------------------------------------------

    async def ensure(self) -> None:
        """Create the index if missing (idempotent; races tolerated).
        No-op in attached/read-only mode: the owner manages the mapping."""
        if self.read_only:
            return
        if await self.client.indices.exists(index=self.index):
            return
        body = {k: dict(v) for k, v in MAPPINGS["properties"].items()}
        if self.dims:
            body["vector"] = dict(body["vector"], dims=self.dims)
        try:
            await self.client.indices.create(index=self.index,
                                             mappings={"properties": body})
        except Exception as exc:  # resource_already_exists race
            if getattr(exc, "status_code", getattr(exc, "status", None)) != 400:
                raise

    # -- writes --------------------------------------------------------------

    async def remember(
        self,
        texts: Sequence[str],
        *,
        ids: Sequence[str] | None = None,
        tags: Sequence[Sequence[str]] | None = None,
        at: Sequence[datetime | None] | None = None,
        meta: Sequence[dict | None] | None = None,
        refresh: str | bool = "wait_for",
    ) -> list[str]:
        """Embed and index a batch; returns the ids (RETURNING, client-side).

        Caller-provided ids make the write idempotent (re-remembering the
        same id replaces the note); omitted ids are generated.
        """
        self._guard_write("remember")
        if not texts:
            return []
        vectors = await self.embed(list(texts))
        out_ids = [str(ids[i]) if ids else str(uuid.uuid4()) for i in range(len(texts))]
        ops: list[dict] = []
        for i, text in enumerate(texts):
            ops.append({"index": {"_index": self.index, "_id": out_ids[i]}})
            ops.append({
                "id": out_ids[i],
                "text": text,
                "vector": vectors[i],
                "tags": list(tags[i]) if tags and tags[i] else [],
                "at": _iso(at[i] if at else None),
                "meta": (meta[i] if meta else None) or {},
            })
        resp = await self.client.bulk(operations=ops, refresh=refresh)
        if resp.get("errors"):
            failed = [i for i in resp.get("items", [])
                      if i.get("index", {}).get("error")]
            raise RuntimeError(f"remember(): {len(failed)} bulk failures "
                               f"(first: {failed[:1]})")
        return out_ids

    async def forget(self, ids: Sequence[str], *, refresh: str | bool = "wait_for") -> int:
        """Delete by ids; returns the number actually removed."""
        self._guard_write("forget")
        if not ids:
            return 0
        ops: list[dict] = [op for i in ids
                           for op in ({"delete": {"_index": self.index, "_id": str(i)}},)]
        resp = await self.client.bulk(operations=ops, refresh=refresh)
        return sum(1 for item in resp.get("items", [])
                   if item.get("delete", {}).get("result") == "deleted")

    # -- reads ----------------------------------------------------------------

    async def fetch(self, ids: Sequence[str], *, with_vectors: bool = False) -> list[dict]:
        """Hydrate documents by id (order preserved, missing dropped)."""
        if not ids:
            return []
        f = self.fields
        query: dict = {"terms": {f.id: [str(i) for i in ids]}}
        if self.scope:
            query = {"bool": {"filter": [query] + self.scope}}
        resp = await self.client.search(
            index=self.index,
            body={"query": query, "size": len(ids),
                  "_source": f.source(with_vectors), "track_total_hits": False},
        )
        by_id = {str(h["_source"].get(f.id)): h["_source"] for h in resp["hits"]["hits"]}
        return [by_id[str(i)] for i in ids if str(i) in by_id]
