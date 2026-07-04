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

⸻

Phase 5: Embedding Pipeline

Add embeddings for every completed turn.

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
