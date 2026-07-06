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

---

## Phase 6: Whisper.cpp Voice Input

Integrate local speech recognition.

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
