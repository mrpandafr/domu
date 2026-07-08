#!/usr/bin/env python3
"""Daily recap cron — writes a structured summary of today's Domu activity.

Usage:
    python3 cron/daily_recap.py [YYYY-MM-DD]

Reads today's new turns (field ``at``) and focus-drift metrics, formats a
compact recap, writes it back to the space tagged ``type:recap date:{today}``.
Runs as agent_context="cron" — uses DomuProvider.write_cron_recap(), the
dedicated path that bypasses the normal _writes_enabled gate.
"""

import sys
import os
from datetime import date as _date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch import AsyncElasticsearch
from sentence_transformers import SentenceTransformer
from vectormind.space import HINDSIGHT_FIELDS
from domu import DomuProvider

_CATEGORIES = {
    "la-tortue": "tortue",
    "l-atelier": "k1ss",
    "les-pertes": "perte",
    "tamashii": "tamashii",
    "la-musique": "musique",
    "les-petites-choses": "choses",
}

_model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")


async def _embed(texts):
    return [_model.encode(t, normalize_embeddings=True).tolist() for t in texts]


def _format_recap(summary: dict) -> str:
    today = summary["date"]
    turns = summary["turns"]
    metrics = summary["metrics"]

    lines = [f"# Recap Domu — {today}", ""]

    if not turns:
        lines.append("Aucune nouvelle mémoire écrite aujourd'hui.")
    else:
        roles: dict[str, int] = {}
        for t in turns:
            tags = t.get("tags") or []
            role = next((tag.split("role:")[-1] for tag in tags
                         if tag.startswith("role:")), "?")
            roles[role] = roles.get(role, 0) + 1

        lines.append(f"**{len(turns)} mémoire(s) écrite(s)** — "
                     + ", ".join(f"{n} {r}" for r, n in sorted(roles.items())))
        lines.append("")

        # Show up to 10 excerpts
        lines.append("## Extraits")
        for t in turns[:10]:
            text = (t.get("text") or "").replace("\n", " ")
            lines.append(f"- {text[:100]}")
        if len(turns) > 10:
            lines.append(f"  … et {len(turns) - 10} de plus.")

    if metrics:
        drifts = [m["value"] for m in metrics if m.get("type") == "focus_drift"]
        if drifts:
            lines.append("")
            lines.append("## Focus drift")
            avg = sum(drifts) / len(drifts)
            peak = max(drifts)
            lines.append(f"- {len(drifts)} mesures — moy {avg:.3f}, pic {peak:.3f}")
            # Flag topic changes (drift > 0.5)
            shifts = [m for m in metrics
                      if m.get("type") == "focus_drift" and m.get("value", 0) > 0.5]
            for s in shifts[:3]:
                ctx = (s.get("context") or "")[:60]
                lines.append(f"  → glissement ({s['value']:.2f}): {ctx}")

    return "\n".join(lines)


def main() -> None:
    import asyncio

    today = sys.argv[1] if len(sys.argv) > 1 else _date.today().isoformat()
    print(f"Recap Domu pour {today}...")

    provider = DomuProvider(
        es_client_factory=lambda: AsyncElasticsearch("http://127.0.0.1:9200"),
        fields=HINDSIGHT_FIELDS,
        categories=_CATEGORIES,
        config={
            "index": "public-memory_units",
            "metrics_index": "domu-metrics",
            "bank_id": "kage",
            "dims": 384,
        },
    )

    async def _run():
        provider.agent_context = "cron"
        provider.bank_id = "kage"
        provider._embed = _embed
        await provider._ainit()

        summary = await provider._adaily_summary(today)
        recap = _format_recap(summary)
        print(recap)
        print()

        doc_id = await provider._awrite_recap(recap, today)
        print(f"Recap écrit dans le space : {doc_id}")

        await provider._es_client.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
