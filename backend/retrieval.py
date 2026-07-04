from __future__ import annotations

import json
import math
from typing import Any

try:
    from .database import list_embedding_candidates
except ImportError:
    from database import list_embedding_candidates


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot_product = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))

    if left_norm == 0 or right_norm == 0:
        return 0.0

    return dot_product / (left_norm * right_norm)


def retrieve_relevant_memories(
    conversation_id: int,
    query_vector: list[float],
    exclude_message_ids: set[int],
    limit: int,
    similarity_threshold: float | None,
) -> list[dict[str, Any]]:
    candidates = list_embedding_candidates(conversation_id, exclude_message_ids)
    scored_memories: list[dict[str, Any]] = []

    for candidate in candidates:
        try:
            candidate_vector = json.loads(candidate["vector"])
        except json.JSONDecodeError:
            continue

        similarity = cosine_similarity(query_vector, [float(value) for value in candidate_vector])
        if similarity_threshold is not None and similarity < similarity_threshold:
            continue

        scored_memories.append(
            {
                "message_id": candidate["message_id"],
                "role": candidate["role"],
                "content": candidate["content"],
                "created_at": candidate["created_at"],
                "similarity": round(similarity, 6),
            }
        )

    scored_memories.sort(key=lambda memory: memory["similarity"], reverse=True)
    return scored_memories[:limit]
