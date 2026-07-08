"""Domu Hermes plugin.

Symlink: ~/.hermes/plugins/domu → ~/K1SS/domu/hermes-plugin/
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_CATEGORIES = {
    "la-tortue": "tortue",
    "l-atelier": "k1ss",
    "les-pertes": "perte",
    "tamashii": "tamashii",
    "la-musique": "musique",
    "les-petites-choses": "choses",
}


def _read_config() -> dict:
    try:
        from hermes_constants import get_hermes_home
        cfg_path = get_hermes_home() / "domu" / "config.json"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def register(ctx) -> None:
    from elasticsearch import AsyncElasticsearch
    from vectormind.space import HINDSIGHT_FIELDS
    from domu import DomuProvider

    cfg = _read_config()
    es_url = cfg.get("es_url") or os.getenv("DOMU_ES_URL") or "http://127.0.0.1:9200"
    bank_id = cfg.get("bank_id") or os.getenv("DOMU_BANK_ID") or "kage"
    index = cfg.get("index") or os.getenv("DOMU_INDEX") or "public-memory_units"

    ctx.register_memory_provider(DomuProvider(
        es_client_factory=lambda: AsyncElasticsearch(es_url),
        fields=HINDSIGHT_FIELDS,
        categories=_CATEGORIES,
        config={
            "index": index,
            "metrics_index": cfg.get("metrics_index", "domu-metrics"),
            "bank_id": bank_id,
            "dims": int(cfg.get("dims", 384)),
            "l1_size": int(cfg.get("l1_size", 3)),
            "l2_size": int(cfg.get("l2_size", 7)),
        },
    ))
