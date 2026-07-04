from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FutureMemoryLayer:
    name: str
    table_name: str
    purpose: str


FUTURE_MEMORY_LAYERS = (
    FutureMemoryLayer("episodes", "episodes", "Future episodic boundaries over the message timeline."),
    FutureMemoryLayer("episode summaries", "episode_summaries", "Future compressed summaries of episodes."),
    FutureMemoryLayer("semantic memory", "semantic_memory", "Future extracted facts or durable knowledge."),
    FutureMemoryLayer("memory index", "memory_index", "Future unified index over memory layers."),
    FutureMemoryLayer("crystallization seeds", "crystallization_seeds", "Future compact semantic handles."),
)
