"""Domu Hermes plugin — thin HTTP client.

Delegates every ABC method to the Domu server (domu/server.py).
Zero heavy deps: stdlib urllib only.

Start the server first: python run_server.py
Config: DOMU_SERVER_URL env var (default http://127.0.0.1:7430)
        or server_url in ~/.hermes/domu/config.json

Install: ln -s /path/to/domu/hermes-plugin ~/.hermes/plugins/domu
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.request
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

logger = logging.getLogger(__name__)

_DEFAULT_URL = "http://127.0.0.1:7430"


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


class DomuClient(MemoryProvider):
    """Plugin Hermes — appelle le serveur Domu via HTTP."""

    def __init__(self, server_url: str, config: dict) -> None:
        self._url = server_url.rstrip("/")
        self._cfg = config
        self._session_id = ""

    # -- transport ----------------------------------------------------------

    def _post(self, path: str, body: dict, *, timeout: float = 5.0) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode()
        req = urllib.request.Request(
            f"{self._url}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            logger.debug("domu %s: %s", path, e)
            return {}

    def _get(self, path: str, *, timeout: float = 2.0) -> dict:
        try:
            with urllib.request.urlopen(f"{self._url}{path}", timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            logger.debug("domu GET %s: %s", path, e)
            return {}

    # -- ABC requis ---------------------------------------------------------

    @property
    def name(self) -> str:
        return "domu"

    def is_available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self._url}/health", timeout=2.0) as r:
                return r.status == 200
        except Exception:
            return False

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self._session_id = session_id
        result = self._post("/session/init", {
            "session_id": session_id,
            "bank_id": self._cfg.get("bank_id", "kage"),
            "index": self._cfg.get("index", "public-memory_units"),
            "dims": self._cfg.get("dims", 384),
            "l1_size": self._cfg.get("l1_size", 1),
            "l2_size": self._cfg.get("l2_size", 3),
            "l1_max_chars": self._cfg.get("l1_max_chars", 600),
            "l2_max_chars": self._cfg.get("l2_max_chars", 300),
            "agent_context": kwargs.get("agent_context", "primary"),
            "hermes_home": str(kwargs.get("hermes_home",
                                          os.path.expanduser("~/.hermes"))),
        }, timeout=35.0)
        if not result.get("ok"):
            raise RuntimeError(f"domu server: {result.get('error', 'init failed')}")
        logger.info("domu client ready: session=%s", session_id)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {"name": "domu_recall",
             "description": "Search memory. Returns L1/L2/L3 concentric context.",
             "parameters": {"type": "object",
                            "properties": {"query": {"type": "string"},
                                           "k": {"type": "integer", "default": 8}},
                            "required": ["query"]}},
            {"name": "domu_remember",
             "description": "Store a note in memory (goes through Synapse's gates).",
             "parameters": {"type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "scope": {"type": "string",
                                          "enum": ["private", "shared", "public"],
                                          "default": "shared"},
                            },
                            "required": ["text"]}},
            {"name": "domu_forget",
             "description": "Delete notes by id.",
             "parameters": {"type": "object",
                            "properties": {"ids": {"type": "array",
                                                   "items": {"type": "string"}}},
                            "required": ["ids"]}},
        ]

    # -- hooks optionnels ---------------------------------------------------

    def system_prompt_block(self) -> str:
        return (
            "Domu — vector memory active. A memory context block precedes each turn "
            "(L1 focus / L2 vault / L3 doors). Trust it. "
            "Use domu_recall only if the user asks for an explicit search "
            "or the prefetch is clearly insufficient. "
            "Absolute rule: never embroider reality. "
            "If memory returns nothing, say so."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        return self._post("/prefetch",
                          {"query": query,
                           "session_id": session_id or self._session_id},
                          timeout=3.0).get("context", "")

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        pass  # server handles its own warmth

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: Optional[List] = None) -> None:
        self._post("/sync_turn",
                   {"user": user_content, "assistant": assistant_content,
                    "session_id": session_id or self._session_id},
                   timeout=2.0)

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kw) -> str:
        path = {"domu_recall": "/recall",
                "domu_remember": "/remember",
                "domu_forget": "/forget"}.get(tool_name)
        if path is None:
            return json.dumps({"error": f"unknown tool {tool_name}"})
        return json.dumps(self._post(path, args, timeout=10.0), ensure_ascii=False)

    def shutdown(self) -> None:
        pass

    def on_turn_start(self, turn_number: int, message: str, **kw: Any) -> None:
        pass

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        self._post("/session/end", {"messages": messages}, timeout=90.0)

    def on_session_switch(self, new_session_id: str, **kw: Any) -> None:
        self._session_id = new_session_id

    def on_pre_compress(self, messages: List[Dict[str, Any]], **kw: Any) -> str:
        return ""

    def on_memory_write(self, action: str, target: str, content: str,
                        metadata: Optional[Dict] = None) -> None:
        if action in ("add", "replace"):
            self._post("/remember",
                       {"text": content, "role": "memory-tool", "scope": "shared"},
                       timeout=5.0)

    def on_delegation(self, task: str, result: str, **kw: Any) -> None:
        text = f"[delegation] {task}: {result}" if task else result
        self._post("/remember",
                   {"text": text, "role": "subagent", "scope": "shared"},
                   timeout=5.0)

    def backup_paths(self) -> List[str]:
        return []


def register(ctx) -> None:
    cfg = _read_config()
    url = cfg.get("server_url") or os.getenv("DOMU_SERVER_URL") or _DEFAULT_URL
    ctx.register_memory_provider(DomuClient(url, cfg))
