# Backend

Flask API for the associative chat prototype.

See the root [README](../README.md) for the full runbook, llama.cpp setup, memory behavior,
settings table, and known limitations.

## Run

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 app.py
```

Settings are centralized in `backend/config.py` and can be overridden with environment
variables:

- `PORT`, default `5000`
- `FRONTEND_ORIGIN`, default `*`
- `MODEL_ENDPOINT_URL`, default `http://localhost:8080/v1`
- `MODEL_NAME`, default `local-placeholder-model`
- `MODEL_TIMEOUT_SECONDS`, default `60`
- `MODEL_TEMPERATURE`, optional default sent to chat completions
- `MODEL_REPEAT_PENALTY`, optional default sent to chat completions
- `ROLLING_MESSAGE_COUNT`, default `12`
- `USE_PLACEHOLDER_CHAT`, default `false`. Set to `1` only when testing without a local model server.
- `DATABASE_PATH`, default `backend/data/associative_chat.sqlite3`
- `EMBEDDING_PROVIDER`, default `auto`. Supported values: `auto`, `llama-cpp`, `openai-compatible`, `stub`
- `EMBEDDING_MODEL_PATH`, default `/storage/gguf/nomic-embed-text-v2-moe.Q8_0.gguf`
- `EMBEDDING_ENDPOINT_URL`, default `MODEL_ENDPOINT_URL` when using `openai-compatible`
- `EMBEDDING_MODEL`, default embedding model filename when using `openai-compatible`
- `EMBEDDING_TIMEOUT_SECONDS`, default `60`
- `EMBEDDING_CONTEXT_SIZE`, default `512` for `llama-cpp`
- `RETRIEVED_MEMORY_COUNT`, default `6`
- `RETRIEVAL_SIMILARITY_THRESHOLD`, optional minimum cosine similarity
- `SYSTEM_PROMPT`, optional runtime instruction override
- `DEFAULT_CONTEXT_BEFORE`, default `3`
- `DEFAULT_CONTEXT_AFTER`, default `3`
- `MAX_TOOL_EXPANSION_PASSES`, default `1`

## API

- `GET /api/health`
- `GET /api/conversations`
- `POST /api/conversations` with `{ "title": "Optional title" }`
- `GET /api/conversations/:id/messages`
- `POST /api/conversations/:id/messages` with `{ "role": "user", "content": "..." }`
- `POST /api/chat` with `{ "message": "...", "conversation_id": 1 }`
- `POST /api/chat/stream` with `{ "message": "...", "conversation_id": 1 }`
- `GET /api/tools/context-around-message/:message_id?before=3&after=3`

`conversation_id` is optional. If omitted, the backend creates a new conversation.
Both chat routes also accept `generation.temperature` and `generation.repeat_penalty`
overrides, which are forwarded to the model server when provided.

`/api/chat` sends only the most recent `ROLLING_MESSAGE_COUNT` persisted messages to the
model prompt as recent conversation. The response includes `context_window` metadata with
the configured count, actual recent message count, and message ids.

Every successfully saved user or assistant message gets an embedding row. `auto` uses the
local GGUF embedding model when present and falls back to the deterministic stub otherwise.

`/api/chat` embeds the new user message, searches older embedded messages outside the
rolling context window, and returns `retrieved_memories` with `message_id`, `role`,
`content`, `created_at`, and `similarity`.

The model prompt is assembled as separate sections: runtime instructions, clearly labeled
older retrieved memories, and the recent rolling conversation in chronological order.

`/api/chat` and `/api/chat/stream` expose `get_context_around_message` as an
OpenAI-compatible tool. If the model calls it, the backend executes one expansion pass,
sends the tool result back to the model, saves the final assistant response, and returns
`context_expansion` metadata.

`GET /api/tools/context-around-message/:message_id` returns the target message plus nearby
messages from the same conversation in chronological order.
