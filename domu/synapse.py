"""domu.synapse — the filter between raw turns and the space.

Synapse decides what deserves to become memory. Its rules are the ones
written in DOMU-HERMES.md, implemented literally:

1.  zero-result / empty payloads          -> discard
3.  tool-call noise without a human turn  -> discard
5.  fragments under 10 meaningful chars   -> discard
dedup: cosine > 0.95 between candidates   -> keep the fullest, alias the rest

Synapse never rewrites content. It only says yes, no, or "same as".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from vectormind import cosine

#: markers of technical noise (rule 3): a fragment that is *only* tool
#: machinery never becomes memory.
_NOISE_MARKERS = (
    "session_search", "write_file", "web_search", "tool_call",
    "tool_result", "[...", "<tool", "</tool",
)

_MEANINGFUL = re.compile(r"[\w]", re.UNICODE)


def worth_remembering(text: str | None) -> bool:
    """Rules 1, 3 and 5: is this fragment memory material at all?"""
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if len(_MEANINGFUL.findall(stripped)) < 10:          # rule 5
        return False
    lowered = stripped.lower()
    noise_hits = sum(1 for m in _NOISE_MARKERS if m in lowered)
    # rule 3: a fragment dominated by tool machinery is noise, not memory
    if noise_hits and len(stripped) < 200:
        return False
    return True


@dataclass
class Deduped:
    """The outcome of a dedup pass: survivors and who they absorbed."""

    kept: list[int] = field(default_factory=list)        # indexes into input
    aliases: dict[int, int] = field(default_factory=dict)  # loser -> winner


def dedup(texts: list[str], vectors: list[list[float]],
          threshold: float = 0.95) -> Deduped:
    """Cosine-dedup (DOMU-HERMES rule): above ``threshold`` two fragments
    are the same thought under different names. Keep the fullest (most
    characters), alias the shorter to it — nothing is lost, navigation
    survives."""
    out = Deduped()
    for i, vec in enumerate(vectors):
        winner = None
        for j in out.kept:
            if cosine(vec, vectors[j]) > threshold:
                winner = j
                break
        if winner is None:
            out.kept.append(i)
            continue
        # same thought: the fullest text wins, the other becomes its alias
        if len(texts[i]) > len(texts[winner]):
            out.kept[out.kept.index(winner)] = i
            out.aliases[winner] = i
            for loser, w in list(out.aliases.items()):
                if w == winner:
                    out.aliases[loser] = i
        else:
            out.aliases[i] = winner
    return out
