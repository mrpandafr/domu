"""domu — the orchestrator of Wired: vectormind wired into Hermes."""

from .provider import DomuProvider
from .synapse import dedup, worth_remembering

__all__ = ["DomuProvider", "worth_remembering", "dedup"]
__version__ = "0.1.0"
