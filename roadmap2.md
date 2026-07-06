# Roadmap 2 — Runtime Stability and Quality of Life

## Goal

The first roadmap proved the architecture.

This roadmap makes the application pleasant and reliable enough to become the primary interface for interacting with a local language model.

The objective is **not** to add major new AI capabilities.

The objective is to make the existing system robust, responsive, and enjoyable to use while preparing clean extension points for future tools.

The guiding principle:

> One implementation.
> One chat pipeline.
> One source of truth.

Streaming, tool usage, persistence, and future tools should all share the same orchestration layer instead of existing as parallel implementations.

---

## Phase 1: Unify Chat Orchestration

Current problem:

Streaming and tool usage have diverged.

Fixing one breaks the other because they are implemented through different execution paths.

Goal:

Create one chat orchestration layer responsible for:

- prompt assembly
- model requests
- tool execution
- follow-up model requests
- persistence
- streaming events

The Flask routes should simply expose this orchestration.

Deliverable:

- `/api/chat` and `/api/chat/stream` both use the same orchestration code
- no duplicated tool logic
- no duplicated prompt assembly
- one source of truth

Codex Result:
```
• Implemented Phase 1 from roadmap2.md.

  Centralized chat orchestration in backend/chat.py:275, including prompt assembly, retrieval, tool expansion, assistant persistence, response payloads, and stream event production. Both /api/chat and /api/chat/stream now delegate through the
  same ChatOrchestrator in backend/app.py:59.

  Kept Flask routes focused on HTTP handling and preserved existing backend.app.LocalChatClient imports so current tests and patches still work.

  Verification: python3 -m unittest discover backend passes, 23 tests.

```

---

## Phase 2: Streaming + Tool Usage

Streaming must continue working when tools are used.

Behavior:

Model begins generation.

If a tool call is emitted:

- pause streaming
- execute the tool
- continue through the orchestration layer
- stream the final assistant response

The user should never have to choose between streaming and tools.

Deliverable:

- streaming works without tools
- streaming works with tools
- tool responses remain persisted correctly
- no regression of existing retrieval behavior

Codex Result:
```
• Implemented Phase 2.

  /api/chat/stream now uses a real tool-aware streaming path in backend/chat.py:150. It streams normal deltas directly, accumulates streamed OpenAI-style tool_calls, executes the existing context tool, then streams the follow-up assistant
  response through the same orchestration layer before persisting it.

  I also added/updated tests in backend/test_phase10.py:132 for:

  - streaming without tool calls
  - streaming with a context tool call
  - final streamed assistant response persistence

  Verification passed:

  python3 -m py_compile backend/app.py backend/chat.py backend/test_phase10.py
  python3 -m unittest discover backend

  Result: 24 tests passing.
```

---

## Phase 3: Runtime Regression Tests

Protect the runtime from future regressions.

Add tests covering:

- normal chat
- streaming
- retrieval
- tool usage
- streaming plus tool usage
- conversation persistence

Codex should not be able to "fix" one path while silently breaking another.

Deliverable:

A single regression suite that validates the complete chat runtime.

Codex Result:
```
• Implemented Phase 3 by adding a single runtime regression suite: backend/test_runtime_regression.py:10.

  It covers:

  - normal /api/chat
  - /api/chat/stream
  - retrieval and recalled prompt context
  - context tool usage
  - streaming plus tool usage
  - conversation/message/embedding persistence

  Verification passed:

  python3 -m unittest backend.test_runtime_regression
  python3 -m unittest discover backend

  Result: 29 backend tests passing.
```

---

## Phase 4: Dark Mode

Add a dark theme.

Requirements:

- remember user preference
- pleasant contrast
- readable code blocks
- readable markdown
- readable memory panel

Keep styling simple.

Deliverable:

Application is comfortable for long conversations.

Codex Result:
```
• Implemented Phase 4 dark mode.

  Changes:

  - Added persisted light/dark theme state in frontend/src/main.jsx:2 using localStorage.
  - Added a header theme toggle.
  - Converted the UI colors in frontend/src/styles.css:1 to theme variables.
  - Covered dark styling for chat messages, markdown, code blocks, thinking panels, memory debug panels, forms, errors, and sidebar.

  Verification:

  npm run build

  Build passed.
```

---

## Phase 5: UI Quality of Life

Improve usability without changing architecture.

Possible improvements:

- better scrolling behavior
- improved streaming indicator
- copy assistant message
- improved markdown rendering
- keyboard shortcuts
- cleaner conversation switching
- better error presentation
- adjustable sidebar width
- remember UI state

The focus is polish rather than new capability.

Codex Result:
```
• Implemented Phase 5 UI polish in frontend/src/main.jsx:1 and frontend/src/styles.css:425.

  Added:

  - Smarter message auto-scroll that respects when the user has scrolled up
  - Animated streaming indicator
  - Copy button for assistant messages
  - Enter-to-send with Shift+Enter for newline
  - Dismissible error banner
  - Persisted temperature/repeat-penalty settings
  - Restores the last active conversation when available

  Verification passed:

  npm run build
  python3 -m unittest discover backend

  Result: frontend build passed and 29 backend tests passed.
```

---

## Phase 6: Whisper.cpp Voice Input

Integrate local speech recognition.

whisper.cpp can be found at:  /home/zak/engines/whisper.cpp


Behavior:

Microphone button

↓

Record audio

↓

Send audio to Flask

↓

Backend invokes Whisper.cpp

↓

Transcript returned

↓

Insert transcript into message box

↓

User edits if desired

↓

Send

Do not automatically send transcripts during this phase.

Deliverable:

Reliable local voice-to-text.

Codex Result:
```
• Implemented Phase 6 Whisper.cpp voice input.

  Added /api/voice/transcribe in backend/app.py, backed by backend/voice.py. The backend accepts uploaded microphone audio, converts browser formats such as webm to 16 kHz mono WAV through ffmpeg when needed, invokes local whisper.cpp at /home/zak/engines/whisper.cpp/build/bin/whisper-cli, and returns a cleaned transcript.

  Added configurable Whisper settings in backend/config.py:

  - WHISPER_EXECUTABLE_PATH
  - WHISPER_MODEL_PATH
  - WHISPER_FFMPEG_PATH
  - WHISPER_TIMEOUT_SECONDS
  - WHISPER_LANGUAGE

  Added a microphone control to the composer in frontend/src/main.jsx. It records audio, sends it to Flask, inserts the returned transcript into the message draft, and does not auto-send.

  Verification passed:

  python3 -m unittest backend.test_phase6_voice
  python3 -m unittest discover backend
  npm run build

  Result: 34 backend tests passing and frontend build passed.
```

---

## Phase 7: Llama Server Management

Reduce friction when experimenting with GGUF models.

Provide a lightweight interface for launching and managing llama.cpp.

Possible features:

- available GGUF list
- launch presets
- GPU layers
- context size
- batch size
- temperature defaults
- embedding model selection
- chat model selection
- start
- stop
- restart
- current server status

This should remain intentionally lightweight.

Its purpose is to make experimenting with local models easier.

Codex Result:
```
• Implemented Phase 7 llama.cpp server management.

  Added backend/llama_manager.py with a lightweight in-process manager for:

  - discovering GGUF models under /storage/gguf
  - exposing launch defaults
  - building llama-server commands
  - start, stop, and restart of a managed llama.cpp process
  - status reporting for managed process state and endpoint reachability

  Added Flask endpoints in backend/app.py:

  - GET /api/llama/models
  - GET /api/llama/status
  - POST /api/llama/start
  - POST /api/llama/stop
  - POST /api/llama/restart

  Added configurable launch defaults in backend/config.py, including LLAMA_SERVER_PATH, LLAMA_MODELS_DIR, LLAMA_DEFAULT_MODEL_PATH, LLAMA_HOST, LLAMA_PORT, LLAMA_CONTEXT_SIZE, LLAMA_BATCH_SIZE, LLAMA_GPU_LAYERS, and LLAMA_THREADS.

  Added a compact llama.cpp control panel to the frontend sidebar in frontend/src/main.jsx and frontend/src/styles.css. It supports chat model selection, embedding model selection, GPU layers, context size, batch size, threads, port, temperature, status refresh, start, stop, and restart.

  Verification passed:

  python3 -m unittest backend.test_phase7_llama_manager
  python3 -m unittest discover backend
  npm run build

  Result: 37 backend tests passing and frontend build passed.
```

---

## Phase 8: Prepare Tool Infrastructure

Do **not** add many new tools.

Instead:

Create the architecture future tools will use.

Examples:

- centralized tool registry
- tool metadata
- execution abstraction
- permission model
- consistent tool result format

Only migrate the existing context tool to the new infrastructure.

No additional tools are required during this roadmap.

Deliverable:

Future tools can be added without modifying the chat runtime.

Codex Result:
```
• Implemented Phase 8 tool infrastructure.

  Added a centralized registry in backend/tools.py with:

  - tool metadata
  - OpenAI-compatible tool definitions
  - execution context
  - consistent execution result wrapper
  - permission metadata

  Migrated the existing get_context_around_message tool into the registry while preserving the existing model-facing tool result JSON.

  Updated backend/chat.py so the chat runtime asks the registry for tool definitions and delegates tool-call execution through the registry instead of hardcoding context-tool logic. Future tools can now be registered in backend/tools.py without changing the model request, streaming, or persistence paths.

  Added GET /api/tools in backend/app.py to expose registered tool metadata.

  Added backend/test_phase8_tool_registry.py covering registry metadata, context tool execution, chat-runtime integration, and the tools metadata endpoint.

  Verification passed:

  python3 -m unittest backend.test_phase8_tool_registry
  python3 -m unittest discover backend
  npm run build

  Result: 41 backend tests passing and frontend build passed.
```

---

## Design Principles

Do not increase architectural complexity unless it removes future complexity.

Avoid duplicate execution paths.

Streaming is a transport concern.

Tool execution is a chat orchestration concern.

Persistence should happen once.

Prompt assembly should happen once.

Future tools should plug into the orchestration layer rather than bypassing it.

Favor readability over cleverness.

---

## Prototype Complete When

The application feels like a real daily driver for interacting with local models.

It should be possible to:

- hold long conversations
- stream responses
- use tools
- speak naturally through Whisper.cpp
- switch between GGUF models easily
- continue development without fear of breaking existing behavior

Major new memory systems, episodic memory, sleep/consolidation, semantic promotion, and additional tools belong in the next roadmap.

---
