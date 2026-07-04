"""Chat orchestration home for future refactors.

Current chat routing still lives in `app.py` to keep the prototype small. This module
marks the boundary where multi-pass chat orchestration can move later.
"""

CHAT_PIPELINE_STAGES = (
    "save_user_message",
    "embed_user_message",
    "retrieve_memories",
    "assemble_prompt",
    "optional_context_expansion",
    "save_assistant_message",
)
