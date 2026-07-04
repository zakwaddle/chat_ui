# Associative Chat

Local-first chatbot prototype for testing bounded conversational memory.

The memory store can grow, but the active context window stays bounded. The app tests
whether indexed memory plus selective recall can create conversational continuity without
building an ever-growing prompt.

## What It Does

- Chats with an OpenAI-compatible local model server, such as `llama.cpp`
- Stores conversations, messages, and embeddings in SQLite
- Sends only the most recent `ROLLING_MESSAGE_COUNT` messages as active working memory
- Embeds older messages and retrieves semantically similar memories
- Labels recalled memories separately from recent chat in the model prompt
- Lets the model call `get_context_around_message` once to inspect surrounding context
- Shows retrieved memories, similarity scores, and expansion status in the UI

## Requirements

- Python 3.12+
- Node.js 24+
- A local OpenAI-compatible chat endpoint for real model chat
- Optional local GGUF embedding model at `/storage/gguf/nomic-embed-text-v2-moe.Q8_0.gguf`

## Run Backend

```bash
cd backend
python3 -m pip install -r requirements.txt
MODEL_ENDPOINT_URL=http://localhost:8080/v1 MODEL_NAME=your-chat-model python3 app.py
```

For UI testing without a model server:

```bash
cd backend
USE_PLACEHOLDER_CHAT=1 EMBEDDING_PROVIDER=stub python3 app.py
```

The backend listens on `http://localhost:5000` by default.

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api` to the Flask backend.

## Pointing At llama.cpp

Start a llama.cpp server with an OpenAI-compatible API. The exact command depends on your
build, but the shape is:

```bash
llama-server \
  --model /storage/gguf/your-chat-model.gguf \
  --host 0.0.0.0 \
  --port 8080
```

Then start the backend with:

```bash
MODEL_ENDPOINT_URL=http://localhost:8080/v1 MODEL_NAME=your-chat-model python3 backend/app.py
```

For embeddings, the default `EMBEDDING_PROVIDER=auto` uses `llama-cpp-python` with
`/storage/gguf/nomic-embed-text-v2-moe.Q8_0.gguf` when available. You can also point
embeddings at an OpenAI-compatible endpoint:

```bash
EMBEDDING_PROVIDER=openai-compatible \
EMBEDDING_ENDPOINT_URL=http://localhost:8081/v1 \
EMBEDDING_MODEL=nomic-embed-text-v2-moe
```

## How Rolling Memory Works

Every chat turn is saved to SQLite. For the next model request, the backend loads only the
latest `ROLLING_MESSAGE_COUNT` messages from the active conversation and includes those as
the recent conversation section.

Default:

```bash
ROLLING_MESSAGE_COUNT=12
```

Older messages are not silently appended to the prompt. They must be retrieved or expanded.

## How Retrieval Works

After the user message is saved, the backend creates an embedding for it. It searches older
embedded messages outside the rolling context window, scores them with cosine similarity,
and returns up to `RETRIEVED_MEMORY_COUNT` hits.

Relevant settings:

```bash
RETRIEVED_MEMORY_COUNT=6
RETRIEVAL_SIMILARITY_THRESHOLD=0.35
```

Leave `RETRIEVAL_SIMILARITY_THRESHOLD` unset to accept the top matches regardless of score.

## Prompt Assembly

The model prompt is assembled in separate sections:

1. Runtime/system instructions
2. Older retrieved memories, clearly labeled with `message_id`
3. Recent rolling conversation in chronological order
4. Current user message as part of the recent conversation

This keeps recalled memory distinct from active working memory.

## Context Expansion Tool

The backend exposes:

```text
get_context_around_message(message_id: int, before: int = 3, after: int = 3)
```

HTTP endpoint:

```text
GET /api/tools/context-around-message/:message_id?before=3&after=3
```

The chat loop also exposes this as an OpenAI-compatible tool. If the model calls it, the
backend executes one expansion pass, sends the tool result back to the model, and saves the
final assistant response.

Relevant settings:

```bash
DEFAULT_CONTEXT_BEFORE=3
DEFAULT_CONTEXT_AFTER=3
MAX_TOOL_EXPANSION_PASSES=1
```

## Settings

Settings live in [backend/config.py](backend/config.py) and are overridden with environment
variables.

| Setting | Default | Purpose |
| --- | --- | --- |
| `PORT` | `5000` | Flask port |
| `FRONTEND_ORIGIN` | `*` | CORS origin |
| `DATABASE_PATH` | `backend/data/associative_chat.sqlite3` | SQLite database path |
| `MODEL_ENDPOINT_URL` | `http://localhost:8080/v1` | Chat completions endpoint base |
| `MODEL_NAME` | `local-placeholder-model` | Chat model name sent to server |
| `MODEL_TIMEOUT_SECONDS` | `60` | Chat request timeout |
| `USE_PLACEHOLDER_CHAT` | `false` | Return deterministic placeholder replies |
| `EMBEDDING_PROVIDER` | `auto` | `auto`, `llama-cpp`, `openai-compatible`, or `stub` |
| `EMBEDDING_MODEL_PATH` | `/storage/gguf/nomic-embed-text-v2-moe.Q8_0.gguf` | Local GGUF embedding model |
| `EMBEDDING_ENDPOINT_URL` | `MODEL_ENDPOINT_URL` | Embedding endpoint base |
| `EMBEDDING_MODEL` | embedding filename | Embedding model name |
| `EMBEDDING_TIMEOUT_SECONDS` | `60` | Embedding request timeout |
| `EMBEDDING_CONTEXT_SIZE` | `512` | llama-cpp embedding context size |
| `ROLLING_MESSAGE_COUNT` | `12` | Recent messages sent as working memory |
| `RETRIEVED_MEMORY_COUNT` | `6` | Older memories retrieved per request |
| `RETRIEVAL_SIMILARITY_THRESHOLD` | unset | Optional minimum cosine similarity |
| `SYSTEM_PROMPT` | built-in | Runtime instruction override |
| `DEFAULT_CONTEXT_BEFORE` | `3` | Default expansion messages before target |
| `DEFAULT_CONTEXT_AFTER` | `3` | Default expansion messages after target |
| `MAX_TOOL_EXPANSION_PASSES` | `1` | Maximum expansion passes per chat request |

## API Summary

- `GET /api/health`
- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/:id/messages`
- `POST /api/conversations/:id/messages`
- `POST /api/chat`
- `GET /api/tools/context-around-message/:message_id`

## Known Limitations

- Retrieval currently searches within the active conversation only.
- Embeddings are stored as JSON text in SQLite, not a vector index.
- Similarity search is a simple linear scan.
- Only one context expansion pass is supported.
- Tool calling assumes OpenAI-compatible `tool_calls` responses.
- No authentication, multi-user isolation, or production deployment hardening.
- Thinking output is split in the UI when the model emits `<think>...</think>` or `</think>`,
  but the raw assistant message is still stored unchanged.

## Tests

```bash
python3 -m unittest \
  backend.test_phase4 \
  backend.test_phase5 \
  backend.test_phase6 \
  backend.test_phase7 \
  backend.test_phase9 \
  backend.test_phase10 \
  backend.test_phase11 \
  backend.test_phase12 \
  backend.test_phase13
```

Frontend build:

```bash
cd frontend
npm run build
```
