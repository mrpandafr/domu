"""Domu Hermes plugin.

Thin ABC wrapper over DomuProvider.
The plugin knows nothing about ES, embeddings, or vectormind — it delegates
every ABC method to DomuProvider and stays out of the way.

Symlink: ~/.hermes/plugins/domu → ~/K1SS/domu/hermes-plugin/
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from agent.memory_provider import MemoryProvider
except ImportError:
    class MemoryProvider:  # type: ignore
        pass


class DomuPlugin(MemoryProvider):
    """Hermes-facing plugin. One attribute: _p (DomuProvider). One job: delegate."""

    def __init__(self, provider: Any) -> None:
        self._p = provider

    # -- required -----------------------------------------------------------

    @property
    def name(self) -> str:
        return self._p.name

    def is_available(self) -> bool:
        return self._p.is_available()

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self._p.initialize(session_id, **kwargs)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return self._p.get_tool_schemas()

    # -- optional -----------------------------------------------------------

    def system_prompt_block(self) -> str:
        return self._p.system_prompt_block()

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        return self._p.prefetch(query, session_id=session_id)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        self._p.queue_prefetch(query, session_id=session_id)

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: Optional[List[Dict[str, Any]]] = None) -> None:
        self._p.sync_turn(user_content, assistant_content,
                          session_id=session_id, messages=messages)

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs: Any) -> str:
        return self._p.handle_tool_call(tool_name, args, **kwargs)

    def shutdown(self) -> None:
        self._p.shutdown()

    def on_turn_start(self, turn_number: int, message: str, **kwargs: Any) -> None:
        self._p.on_turn_start(turn_number, message, **kwargs)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        self._p.on_session_end(messages)

    def on_session_switch(self, new_session_id: str, *,
                          parent_session_id: str = "", reset: bool = False,
                          rewound: bool = False, **kwargs: Any) -> None:
        self._p.on_session_switch(new_session_id, parent_session_id=parent_session_id,
                                  reset=reset, rewound=rewound, **kwargs)

    def on_pre_compress(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        return self._p.on_pre_compress(messages, **kwargs)

    def on_memory_write(self, action: str, target: str, content: str,
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        self._p.on_memory_write(action, target, content, metadata=metadata)

    def on_delegation(self, task: str, result: str, **kwargs: Any) -> None:
        self._p.on_delegation(task, result, **kwargs)

    def backup_paths(self) -> List[str]:
        return self._p.backup_paths()


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


_CATEGORIES = {
    "la-tortue": "tortue",
    "l-atelier": "k1ss",
    "les-pertes": "perte",
    "tamashii": "tamashii",
    "la-musique": "musique",
    "les-petites-choses": "choses",
}


def register(ctx) -> None:
    """Called by Hermes memory discovery."""
    from elasticsearch import AsyncElasticsearch
    from vectormind.space import HINDSIGHT_FIELDS
    from domu import DomuProvider

    cfg = _read_config()
    es_url = cfg.get("es_url") or os.getenv("DOMU_ES_URL") or "http://127.0.0.1:9200"
    bank_id = cfg.get("bank_id") or os.getenv("DOMU_BANK_ID") or "kage"
    index = cfg.get("index") or os.getenv("DOMU_INDEX") or "public-memory_units"

    provider = DomuProvider(
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
    )
    ctx.register_memory_provider(DomuPlugin(provider))
