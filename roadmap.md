Associative Chat Roadmap

Goal

Build a small local-first chatbot that tests bounded conversational memory.

The core idea is simple:

The active context window must stay bounded. The app should keep only the most recent N messages in the prompt, while older messages become searchable memory.

This is not trying to create an infinite context window. It is trying to test whether conversation can feel continuous when attention is bounded but memory is indexed.

Long-term direction:

* rolling working memory
* semantic retrieval
* context expansion around retrieved memories
* later: episodic summaries
* later: sleep/consolidation/indexing
* later: crystallization seeds as compressed semantic handles

Version one should only build the simple working system while keeping those future directions easy to add.

⸻

Phase 1: Project Skeleton

Create the basic app structure.

Backend:

* Python
* Flask
* SQLite
* OpenAI-compatible chat client for llama.cpp or another local GGUF server

Frontend:

* React
* Vite
* simple chat UI

Deliverable:

* Backend starts successfully
* Frontend starts successfully
* Frontend can send a message to backend and receive a placeholder response

Codex Result:
```
• Implemented Phase 1 from roadmap.md.

  Added:

  - Flask backend in backend/app.py with /api/health and /api/chat
  - OpenAI-compatible local model config placeholders via MODEL_ENDPOINT_URL and MODEL_NAME
  - Vite React frontend in frontend/src/main.jsx
  - Chat UI styling in frontend/src/styles.css
  - Vite proxy from /api to Flask
  - Root/backend/frontend READMEs and .gitignore

  Verified:

  - python3 -m flask --app backend.app routes
  - Backend HTTP /api/health
  - Backend HTTP /api/chat
  - Frontend npm install
  - Frontend npm run build
  - Vite dev server starts
  - Vite /api/chat proxy reaches Flask and returns the placeholder response

  Run locally with:

  cd backend && python3 app.py

  cd frontend && npm run dev

  Then open http://localhost:5173.
```

⸻

Phase 2: Database Layer

Create SQLite tables.

Tables:

* conversations
* messages
* embeddings

Messages should store:

* id
* conversation_id
* role
* content
* created_at
* token_estimate
* embedding_id

Embeddings should store:

* id
* message_id
* provider
* model
* vector
* created_at

Design note:
Do not assume conversations are the final memory boundary. They are useful for UI, but the long-term system may treat memory as one continuous timeline.

Deliverable:

* messages can be saved and loaded
* conversations can be created and listed

Codex Result:
```
• Implemented Phase 2 database layer.

  Added:

  - SQLite schema initialization for conversations, messages, and embeddings
  - backend/database.py repository helpers for creating/listing conversations
  - message save/load helpers with token_estimate and embedding_id fields
  - Flask API routes for conversation and message persistence
  - DATABASE_PATH configuration with backend/data ignored by git

  Verified:

  - python3 -m flask --app backend.app routes
  - Flask test client creates and lists conversations
  - Flask test client saves and loads messages
  - Message rows include id, conversation_id, role, content, created_at, token_estimate, and embedding_id
```

⸻

Phase 3: Basic Chat Loop

Connect the frontend to the backend chat route.

Behavior:

1. User sends a message.
2. Backend saves the user message.
3. Backend sends recent messages to the local model.
4. Backend saves the assistant response.
5. Frontend displays the exchange.

Use only recent messages for now.

Config:

* model endpoint URL
* model name
* rolling_message_count

Deliverable:

* real local model chat works through the UI

Codex Result:
```
• Implemented Phase 3 basic chat loop.

  Added:

  - OpenAI-compatible chat completions client for local GGUF servers
  - MODEL_ENDPOINT_URL, MODEL_NAME, MODEL_TIMEOUT_SECONDS, and ROLLING_MESSAGE_COUNT config
  - /api/chat now creates or reuses a conversation, saves the user message, sends recent messages to the model, saves the assistant response, and returns both persisted rows
  - frontend conversation_id tracking so follow-up messages continue in the same conversation
  - USE_PLACEHOLDER_CHAT=1 test mode for environments without a running local model

  Verified:

  - python3 -m py_compile backend/app.py backend/database.py
  - Flask test client saves both user and assistant messages through /api/chat
  - mocked OpenAI-compatible client posts to /chat/completions and parses assistant content
  - python3 -m flask --app backend.app routes
  - frontend npm run build
  - Vite proxy POST /api/chat returns persisted user_message and assistant_message
```

⸻

Phase 4: Rolling Context Window

Implement bounded working memory.

Behavior:

* For each request, load only the most recent N messages.
* N should be configurable.
* Default N: 12.
* The model should never receive the full conversation by default.

Deliverable:

* active context stays bounded
* recent continuity still works

Codex Result:
```
• Implemented Phase 4 rolling context window.

  Added:

  - explicit context_window metadata on /api/chat responses
  - configured_message_count, recent_message_count, and message_ids for bounded-context verification
  - backend regression tests proving older messages are excluded from the model request
  - default-window regression test proving the app sends only 12 recent messages when ROLLING_MESSAGE_COUNT is unset
  - frontend phase label updated to Phase 4

  Verified:

  - python3 -m unittest backend.test_phase4
  - python3 -m flask --app backend.app routes
  - frontend npm run build
```

⸻

Phase 5: Embedding Pipeline

Add embeddings for every completed turn.

there is an embedding model available at:
/storage/gguf/nomic-embed-text-v2-moe.Q8_0.gguf

with more models available for chat test (if necessary) at:
/storage/gguf/


Behavior:

* After saving a user or assistant message, create an embedding.
* Store the embedding linked to the message.
* Keep the embedding provider swappable.

Start simple:

* Use a local embedding model if available.
* Otherwise stub the provider cleanly so it can be replaced.

Deliverable:

* every new message gets an embedding
* embeddings are stored in SQLite

Codex Result:
```
• Implemented Phase 5 embedding pipeline.

  Added:

  - swappable embedding providers in backend/embeddings.py
  - auto local provider for /storage/gguf/nomic-embed-text-v2-moe.Q8_0.gguf through llama-cpp-python
  - OpenAI-compatible embeddings endpoint provider
  - deterministic stub provider for tests and fallback
  - embedding creation after every successful user or assistant message save
  - SQLite embedding rows linked back through messages.embedding_id
  - Phase 5 regression tests for standalone message saves and chat turns

  Verified:

  - python3 -m unittest backend.test_phase4 backend.test_phase5
  - python3 -m py_compile backend/app.py backend/database.py backend/embeddings.py backend/test_phase4.py backend/test_phase5.py
  - python3 -m flask --app backend.app routes
  - frontend npm run build
  - local GGUF embedding smoke test returns a 768-dimensional vector
```

⸻

Phase 6: Memory Retrieval

Add semantic search over older messages.

Behavior:

1. Embed the new user message.
2. Search older messages outside the rolling context window.
3. Return top K similar messages.
4. Exclude messages already in the rolling window.
5. Apply an optional similarity threshold.

Config:

* retrieved_memory_count, default 6
* retrieval_similarity_threshold

Deliverable:

* backend retrieves relevant older messages
* retrieved messages include message_id, role, content, created_at, and similarity score

Design note:
This is the first form of associative recall. Retrieval is not expected to return the entire memory. It only needs to find a useful scent trail.

Codex Result:
```
• Implemented Phase 6 memory retrieval.

  Added:

  - cosine similarity retrieval over stored SQLite embeddings
  - database candidate query that excludes active rolling-window message ids
  - RETRIEVED_MEMORY_COUNT config with default 6
  - RETRIEVAL_SIMILARITY_THRESHOLD optional config
  - /api/chat retrieved_memories response including message_id, role, content, created_at, and similarity
  - retrieval metadata showing excluded rolling-window ids
  - Phase 6 regression tests for ranking, thresholding, and rolling-window exclusion

  Verified:

  - python3 -m unittest backend.test_phase4 backend.test_phase5 backend.test_phase6
  - python3 -m py_compile backend/app.py backend/database.py backend/embeddings.py backend/retrieval.py backend/test_phase4.py backend/test_phase5.py backend/test_phase6.py
  - python3 -m flask --app backend.app routes
  - frontend npm run build
```

⸻

Phase 7: Prompt Assembly

Build the complete model prompt.

Prompt sections:

1. system/runtime instructions
2. relevant recalled context
3. recent rolling conversation
4. current user message

Rules:

* recalled context must be clearly labeled as older retrieved memory
* each recalled memory must include its message_id
* recent conversation should remain chronological
* do not silently mix recalled memories with recent chat

Deliverable:

* model receives bounded working memory plus retrieved older memories

Codex Result:
```
• Implemented Phase 7 prompt assembly.

  Added:

  - backend/prompt.py prompt assembler
  - runtime/system instruction section with SYSTEM_PROMPT override
  - clearly labeled older retrieved memory section with message_id, role, created_at, and similarity
  - recent rolling conversation section preserved in chronological order
  - message_id labels on recent turns
  - /api/chat prompt metadata showing recalled memory usage
  - Phase 7 tests for prompt shape and chat-loop prompt delivery

  Verified:

  - python3 -m unittest backend.test_phase4 backend.test_phase5 backend.test_phase6 backend.test_phase7
  - python3 -m py_compile backend/app.py backend/database.py backend/embeddings.py backend/retrieval.py backend/prompt.py backend/test_phase4.py backend/test_phase5.py backend/test_phase6.py backend/test_phase7.py
  - python3 -m flask --app backend.app routes
  - frontend npm run build
```

⸻

Phase 8: Memory Debug Panel

Expose memory behavior in the UI.

Frontend:
Add a collapsible memory/debug panel near each assistant response.

Show:

* retrieved memory hits
* similarity scores
* message_id
* whether expanded context was used

Deliverable:

* user can inspect what the system remembered and why

Codex Result:
```
• Implemented Phase 8 memory debug panel.

  Added:

  - collapsible memory/debug panel on assistant responses
  - retrieved memory hits with message_id, role, content, and similarity score
  - recalled-context usage status from prompt metadata
  - expanded-context usage status from /api/chat context_expansion.used
  - explicit context_expansion.used=false response field until Phase 9/10 implements expansion
  - frontend phase label updated to Phase 8

  Verified:

  - frontend npm run build
  - python3 -m unittest backend.test_phase4 backend.test_phase5 backend.test_phase6 backend.test_phase7
  - python3 -m py_compile backend/app.py backend/database.py backend/embeddings.py backend/retrieval.py backend/prompt.py
  - python3 -m flask --app backend.app routes
```

⸻

Phase 9: Context Expansion Tool

Add a tool that lets the model expand around a retrieved memory.

Tool:
get_context_around_message(message_id: int, before: int = 3, after: int = 3)

Behavior:

* find the target message
* return surrounding messages from the same timeline/conversation
* include up to before messages before it
* include up to after messages after it
* preserve chronological order
* include role, content, created_at, and message_id

Config:

* default_context_before, default 3
* default_context_after, default 3

Deliverable:

* backend can expand a retrieved memory into its surrounding scene

Design note:
Retrieval is recognition. Context expansion is recollection.

Codex Result:
```
• Implemented Phase 9 context expansion tool.

  Added:

  - backend/tools.py with get_context_around_message(message_id, before, after)
  - database helpers for messages before and after a target message
  - GET /api/tools/context-around-message/:message_id endpoint
  - DEFAULT_CONTEXT_BEFORE and DEFAULT_CONTEXT_AFTER config
  - chronological context output with message_id, role, content, and created_at
  - Phase 9 tests for surrounding scene expansion, same-conversation boundaries, route defaults, and missing messages
  - frontend phase label updated to Phase 9

  Verified:

  - python3 -m unittest backend.test_phase4 backend.test_phase5 backend.test_phase6 backend.test_phase7 backend.test_phase9
  - python3 -m py_compile backend/app.py backend/database.py backend/embeddings.py backend/retrieval.py backend/prompt.py backend/tools.py backend/test_phase4.py backend/test_phase5.py backend/test_phase6.py backend/test_phase7.py backend/test_phase9.py
  - frontend npm run build
  - python3 -m flask --app backend.app routes
```

⸻

Phase 10: Tool-Calling Chat Loop

Update the chat loop to support one memory expansion pass.

Behavior:

1. Retrieve top-K older memory hits.
2. Send prompt to model with available tool definition.
3. If the model calls get_context_around_message, execute it.
4. Send tool result back to model.
5. Save final assistant response.

Keep it simple:

* allow one expansion pass at first
* later this can become multiple passes

Deliverable:

* model can inspect surrounding context when a retrieved memory is relevant but incomplete

Codex Result:
```
• Implemented Phase 10 tool-calling chat loop.

  Added:

  - OpenAI-compatible get_context_around_message tool definition
  - one-pass tool-call handling in LocalChatClient
  - execution of get_context_around_message with DEFAULT_CONTEXT_BEFORE and DEFAULT_CONTEXT_AFTER
  - second model call with the tool result before saving the final assistant response
  - MAX_TOOL_EXPANSION_PASSES config, default 1
  - /api/chat context_expansion metadata with tool result details
  - Phase 10 tests for expansion execution and disabled expansion behavior
  - frontend phase label updated to Phase 10

  Verified:

  - python3 -m unittest backend.test_phase4 backend.test_phase5 backend.test_phase6 backend.test_phase7 backend.test_phase9 backend.test_phase10
  - python3 -m py_compile backend/app.py backend/database.py backend/embeddings.py backend/retrieval.py backend/prompt.py backend/tools.py backend/test_phase10.py
  - python3 -m flask --app backend.app routes
  - frontend npm run build
```

⸻

Phase 11: Conversation Management

Add basic conversation controls.

Frontend:

* new conversation
* conversation list
* open existing conversation
* optional conversation title

Backend:

* list conversations
* create conversation
* load messages for conversation

Deliverable:

* multiple conversations are supported

Design note:
Keep the database flexible enough that future retrieval can search across all conversations, not only the currently open one.

Codex Result:
```
• Implemented Phase 11 conversation management.

  Added:

  - frontend conversation sidebar
  - new conversation control with optional title
  - conversation list with message counts
  - open existing conversation flow that loads persisted messages
  - active conversation title in the chat header
  - Phase 11 backend tests for create, list, and load conversation APIs
  - frontend phase label updated to Phase 11

  Verified:

  - python3 -m unittest backend.test_phase4 backend.test_phase5 backend.test_phase6 backend.test_phase7 backend.test_phase9 backend.test_phase10 backend.test_phase11
  - python3 -m py_compile backend/app.py backend/database.py backend/embeddings.py backend/retrieval.py backend/prompt.py backend/tools.py backend/test_phase11.py
  - frontend npm run build
```

⸻

Phase 12: Configuration File

Centralize settings.

Create a config file for:

* model endpoint URL
* model name
* embedding provider
* embedding model
* rolling_message_count
* retrieved_memory_count
* retrieval_similarity_threshold
* default_context_before
* default_context_after
* max_tool_expansion_passes

Deliverable:

* memory behavior can be tuned without editing core logic

Codex Result:
```
• Implemented Phase 12 configuration file.

  Added:

  - backend/config.py with typed AppConfig
  - centralized settings for model endpoint URL, model name, embedding provider/model, rolling_message_count, retrieved_memory_count, retrieval_similarity_threshold, default_context_before, default_context_after, and max_tool_expansion_passes
  - app.py now loads one config object and passes it to chat, retrieval, context expansion, and embedding setup
  - embeddings.py now receives config instead of reading environment variables directly
  - database path resolution now goes through config
  - Phase 12 tests for defaults, environment overrides, and minimum value clamping

  Verified:

  - python3 -m unittest backend.test_phase4 backend.test_phase5 backend.test_phase6 backend.test_phase7 backend.test_phase9 backend.test_phase10 backend.test_phase11 backend.test_phase12
  - python3 -m py_compile backend/app.py backend/config.py backend/database.py backend/embeddings.py backend/retrieval.py backend/prompt.py backend/tools.py backend/test_phase12.py
  - python3 -m flask --app backend.app routes
  - frontend npm run build
```

⸻

Phase 13: Extensibility Hooks

Add empty or minimal structures for future memory layers without implementing them yet.

Future tables or modules may include:

* episodes
* episode_summaries
* semantic_memory
* memory_index
* crystallization_seeds

Do not fully build these yet.

Just keep the code organized so they can be added later.

Suggested backend modules:

* app.py
* db.py
* models.py
* chat.py
* embeddings.py
* retrieval.py
* prompt_builder.py
* tools.py
* config.py

Deliverable:

* working prototype remains simple
* future episodic memory and indexing will not require a rewrite

Codex Result:
```
• Implemented Phase 13 extensibility hooks.

  Added:

  - minimal future-memory tables for episodes, episode_summaries, semantic_memory, memory_index, and crystallization_seeds
  - backend/models.py with a lightweight future memory layer registry
  - backend/memory_layers.py registry reader
  - backend/chat.py placeholder boundary for future chat orchestration refactors
  - backend/db.py and backend/prompt_builder.py compatibility module entry points
  - Phase 13 tests for schema hooks, registry availability, and module imports

  Verified:

  - python3 -m unittest backend.test_phase4 backend.test_phase5 backend.test_phase6 backend.test_phase7 backend.test_phase9 backend.test_phase10 backend.test_phase11 backend.test_phase12 backend.test_phase13
  - python3 -m py_compile backend/app.py backend/config.py backend/database.py backend/db.py backend/models.py backend/chat.py backend/embeddings.py backend/retrieval.py backend/prompt.py backend/prompt_builder.py backend/tools.py backend/memory_layers.py backend/test_phase13.py
  - frontend npm run build
```

⸻

Phase 14: README and Usage Notes

Write clear documentation.

README should explain:

* how to run the backend
* how to run the frontend
* how to point the app at llama.cpp
* how rolling memory works
* how retrieval works
* how the expansion tool works
* where settings live
* known limitations

Also explain the design philosophy:

The memory store may grow, but the active context window should stay bounded.

This app is testing whether good indexing plus selective recall can create conversational continuity without an ever-growing prompt.

⸻

Done Definition

The prototype is complete when:

* a user can chat with a local GGUF model
* only the last N messages are included directly
* older messages are embedded and searchable
* relevant older messages are retrieved automatically
* the model can expand around a retrieved message
* the UI shows what memories were retrieved
* settings are configurable
* the README explains how to run and tune the system

Do not overbuild this.

The first version should prove the feel of bounded working memory plus associative recall.

Codex Result:
```
• Implemented Phase 14 README and usage notes.

  Added:

  - root README runbook for backend and frontend startup
  - llama.cpp OpenAI-compatible server setup notes
  - rolling memory explanation
  - retrieval explanation
  - prompt assembly and context expansion tool explanation
  - centralized settings table pointing to backend/config.py
  - API summary
  - known limitations
  - design philosophy emphasizing bounded working memory plus indexed recall
  - backend README pointer to the root runbook

  Verified:

  - python3 -m unittest backend.test_phase4 backend.test_phase5 backend.test_phase6 backend.test_phase7 backend.test_phase9 backend.test_phase10 backend.test_phase11 backend.test_phase12 backend.test_phase13
  - python3 -m py_compile backend/app.py backend/config.py backend/database.py backend/db.py backend/models.py backend/chat.py backend/embeddings.py backend/retrieval.py backend/prompt.py backend/prompt_builder.py backend/tools.py backend/memory_layers.py
  - frontend npm run build
  - README contains required Phase 14 topics
```
