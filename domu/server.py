"""Domu memory server.

Expose DomuProvider via HTTP. Le plugin Hermes appelle ce serveur.

Lancement : python -m domu.server [--port 7430] [--host 127.0.0.1]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from elasticsearch import AsyncElasticsearch
from vectormind.space import HINDSIGHT_FIELDS
from domu import DomuProvider

logger = logging.getLogger(__name__)

_CATEGORIES = {
    "la-tortue": "tortue",
    "l-atelier": "k1ss",
    "les-pertes": "perte",
    "tamashii": "tamashii",
    "la-musique": "musique",
    "les-petites-choses": "choses",
}

_provider: DomuProvider | None = None


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def _ok(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            self._ok({"error": "not found"}, 404)
            return
        p = _provider
        self._ok({"ok": p is not None and p.mind is not None,
                  "bank": p.bank_id if p else None})

    def do_POST(self):
        try:
            body = self._body()
        except Exception:
            self._ok({"error": "invalid json"}, 400)
            return
        routes = {
            "/session/init": self._init,
            "/session/end":  self._end,
            "/prefetch":     self._prefetch,
            "/sync_turn":    self._sync_turn,
            "/recall":       self._recall,
            "/remember":     self._remember,
            "/forget":       self._forget,
        }
        handler = routes.get(self.path)
        if handler is None:
            self._ok({"error": "not found"}, 404)
        else:
            handler(body)

    # ------------------------------------------------------------------

    def _init(self, body: dict) -> None:
        global _provider
        es_url = body.get("es_url") or os.getenv("DOMU_ES_URL") or "http://127.0.0.1:9200"
        bank_id = body.get("bank_id") or os.getenv("DOMU_BANK_ID") or "kage"
        index = body.get("index") or os.getenv("DOMU_INDEX") or "public-memory_units"
        if _provider is not None:
            try:
                _provider.shutdown()
            except Exception:
                pass
        _provider = DomuProvider(
            es_client_factory=lambda: AsyncElasticsearch(es_url),
            fields=HINDSIGHT_FIELDS,
            categories=_CATEGORIES,
            config={
                "index": index,
                "bank_id": bank_id,
                "dims": int(body.get("dims", 384)),
                "l1_size": int(body.get("l1_size", 3)),
                "l2_size": int(body.get("l2_size", 7)),
            },
        )
        try:
            _provider.initialize(
                session_id=body.get("session_id", ""),
                agent_context=body.get("agent_context", "primary"),
                hermes_home=body.get("hermes_home", os.path.expanduser("~/.hermes")),
                agent_identity=bank_id,
            )
            self._ok({"ok": True})
        except Exception as e:
            logger.exception("session/init failed")
            self._ok({"ok": False, "error": str(e)}, 500)

    def _end(self, body: dict) -> None:
        if _provider:
            _provider.on_session_end(body.get("messages", []))
        self._ok({"ok": True})

    def _prefetch(self, body: dict) -> None:
        if _provider is None:
            self._ok({"context": ""})
            return
        ctx = _provider.prefetch(body.get("query", ""),
                                 session_id=body.get("session_id", ""))
        self._ok({"context": ctx})

    def _sync_turn(self, body: dict) -> None:
        if _provider:
            _provider.sync_turn(body.get("user", ""), body.get("assistant", ""),
                                session_id=body.get("session_id", ""))
        self._ok({"ok": True})

    def _recall(self, body: dict) -> None:
        if _provider is None:
            self._ok({"error": "not initialized"}, 503)
            return
        self._ok(json.loads(_provider.handle_tool_call("domu_recall", body)))

    def _remember(self, body: dict) -> None:
        if _provider is None:
            self._ok({"error": "not initialized"}, 503)
            return
        self._ok(json.loads(_provider.handle_tool_call("domu_remember", body)))

    def _forget(self, body: dict) -> None:
        if _provider is None:
            self._ok({"error": "not initialized"}, 503)
            return
        self._ok(json.loads(_provider.handle_tool_call("domu_forget", body)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7430)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    logger.info("domu server on %s:%d", args.host, args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if _provider is not None:
            _provider.shutdown()
        srv.server_close()


if __name__ == "__main__":
    main()
