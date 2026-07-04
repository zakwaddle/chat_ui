from __future__ import annotations

from typing import Any


DEFAULT_SYSTEM_PROMPT = (
    "You are a local-first chat assistant testing bounded conversational memory. "
    "Use the recent conversation as active working memory. Recalled memories are older, "
    "retrieved context and may be incomplete; use them only when relevant."
)


def assemble_prompt(
    system_prompt: str,
    recalled_memories: list[dict[str, Any]],
    recent_messages: list[dict[str, Any]],
    current_user_message_id: int,
) -> list[dict[str, str]]:
    prompt_messages = [{"role": "system", "content": system_prompt.strip() or DEFAULT_SYSTEM_PROMPT}]

    if recalled_memories:
        prompt_messages.append(
            {
                "role": "system",
                "content": _format_recalled_memories(recalled_memories),
            }
        )

    prompt_messages.append(
        {
            "role": "system",
            "content": (
                "Recent rolling conversation follows in chronological order. "
                f"The current user message is message_id={current_user_message_id}."
            ),
        }
    )

    for message in recent_messages:
        if message["role"] not in {"system", "user", "assistant"}:
            continue

        prompt_messages.append(
            {
                "role": message["role"],
                "content": f"[message_id={message['id']}] {message['content']}",
            }
        )

    return prompt_messages


def _format_recalled_memories(recalled_memories: list[dict[str, Any]]) -> str:
    lines = [
        "Older retrieved memories follow. These are not part of the recent conversation.",
        "Treat them as recalled context and do not assume they are chronologically adjacent.",
    ]

    for memory in recalled_memories:
        lines.extend(
            [
                "",
                (
                    f"[older_retrieved_memory message_id={memory['message_id']} "
                    f"role={memory['role']} created_at={memory['created_at']} "
                    f"similarity={memory['similarity']}]"
                ),
                str(memory["content"]),
            ]
        )

    return "\n".join(lines)
