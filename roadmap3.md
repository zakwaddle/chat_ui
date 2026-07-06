# Roadmap 3 — Knowledge, Databases, and External Memory

## Goal

The first roadmap proved bounded working memory and associative recall.

The second roadmap made the runtime stable and pleasant to use.

This roadmap begins turning the application into a general local knowledge environment.

The objective is not to build an autonomous agent.

The objective is to allow the chat runtime to safely explore and use structured knowledge sources through well-defined tools.

The chat application should become the central interface.

Other applications (archive ingestion, importers, future agents) should become producers of knowledge rather than independent chat systems.

---

## Guiding Principles

The chat runtime remains the primary user interface.

Knowledge is modular.

Every external data source should be usable without changing the chat runtime.

Tools expose capabilities.

Applications produce data.

The model decides when to use tools.

---

# Phase 1: Mobile Voice Compatibility

Improve voice recording compatibility.

Goals:

- Safari support
- Chrome on iPad support
- better microphone capability detection
- better error reporting
- graceful fallback messages

Do not redesign voice input.

Simply make it reliable across supported browsers.

Deliverable:

Voice input works consistently on desktop and mobile.

Codex Result:
```
• Implemented Phase 1 from roadmap3.md.

  Changed:

  - Improved voice support detection for HTTPS/localhost, microphone API, and MediaRecorder.
  - Added Safari/iPad-compatible recorder MIME choices: audio/mp4, audio/mp4;codecs=mp4a.40.2, and audio/aac.
  - Added clearer microphone permission/device/recording error messages.
  - Made recorder stop more reliable by flushing data before stop and handling empty recordings gracefully.
  - Preserved .aac uploads on the backend so mobile recordings are passed correctly to ffmpeg.
  - Added a regression test for mobile audio suffix handling.

  Verified:

  - python3 -m unittest backend.test_phase6_voice passes.
  - npm run build passes.
  - Backend health check returns {"status":"ok"}.

  Running locally:

  - Frontend: http://localhost:5173/
  - Network/mobile URL: http://192.168.6.138:5173/
  - Backend: http://localhost:5000/

  Note: real transcription still depends on the local Whisper/ffmpeg paths being configured and available.
```

---

# Phase 2: SQLite Explorer

Create the first general-purpose knowledge tool.

Initially support read-only exploration.

Capabilities:

- list available databases
- connect to a database
- inspect schema
- list tables
- describe columns
- preview rows
- row counts

The user should be able to inspect any SQLite database from the UI.

Deliverable:

A complete read-only SQLite explorer.

Codex Result:
```
• Completed Phase 2 from roadmap3.md.

  Implemented:

  - Read-only SQLite explorer backend in backend/sqlite_explorer.py.
  - New API routes:
      - GET /api/sqlite/databases
      - GET /api/sqlite/schema?path=...
      - GET /api/sqlite/tables/:table
      - GET /api/sqlite/tables/:table/rows

  - Safe read-only database access using SQLite mode=ro plus PRAGMA query_only = ON.
  - UI explorer in the main app:
      - Lists available databases.
      - Allows entering any local SQLite path.
      - Opens/inspects schema.
      - Lists tables/views.
      - Shows row counts, columns, schema SQL, and preview rows.
      - Keeps chat available via the header/sidebar toggle.

  - Regression tests in backend/test_phase2_sqlite_explorer.py.

  Verified:

  - python3 -m unittest backend.test_phase2_sqlite_explorer passes.
  - python3 -m unittest discover backend passes: 48 tests.
  - npm run build passes.
  - Live backend checks passed for health, database listing, schema inspection, and row preview.

```

---

# Phase 3: SQLite Tool Registry

Expose SQLite functionality to the model.

Create tools such as:

list_tables()

describe_table()

sample_rows()

search_table()

run_read_only_query()

Every query must be read-only.

Reject:

INSERT

UPDATE

DELETE

DROP

ALTER

ATTACH

PRAGMA modifications

Only safe exploration is allowed.

Deliverable:

The model can inspect databases without risking corruption.

Codex Result:
```
• Completed Phase 3 from roadmap3.md.

  Implemented:

  - Registered SQLite model tools:
      - list_tables
      - describe_table
      - sample_rows
      - search_table
      - run_read_only_query

  - Added read-only SQL execution guardrails:
      - SQLite mode=ro connections
      - PRAGMA query_only
      - SQLite authorizer denial for write, schema, ATTACH/DETACH, and PRAGMA actions
      - preflight rejection for INSERT, UPDATE, DELETE, DROP, ALTER, ATTACH, DETACH, CREATE, REPLACE, VACUUM, REINDEX, ANALYZE, and PRAGMA
      - single-statement SELECT/WITH-only validation

  - Added registry tests in backend/test_phase3_sqlite_tool_registry.py.

  Verified:

  - python3 -m unittest backend.test_phase3_sqlite_tool_registry passes.
  - python3 -m unittest discover backend passes: 52 tests.
  - npm run build passes.
  - Live /api/tools check shows all SQLite tools with sqlite.read permission and destructive=false.
```

---

# Phase 4: Database Search

Searching should not require SQL.

Provide higher-level tools.

Examples:

search_database("Henry birthday")

search_database("messages about embeddings")

search_database("Mark essay")

The implementation may internally use SQL.

The model should not have to generate SQL for common searches.

Deliverable:

Natural-language search over SQLite databases.

Codex Result:
```
• Completed Phase 4 from roadmap3.md.

  Implemented:

  - Added search_database() support in backend/sqlite_explorer.py.
  - Registered a model-facing search_database tool with sqlite.read permission.
  - Search now accepts natural-language text and scans text-like columns across tables.
  - Added optional table restriction, safe result limits, tokenized matching, matched column metadata, and per-result scores.
  - Kept search read-only through the same SQLite mode=ro and query_only connection path used by the explorer.
  - Added regression tests in backend/test_phase4_database_search.py.

  Verified:

  - python3 -m unittest backend.test_phase4_database_search passes.
  - python3 -m unittest discover backend passes: 56 tests.
  - npm run build passes.
```

---

# Phase 5: External Knowledge Sources

Allow multiple databases to be attached.

Examples:

chat.db

archive.db

future memory databases

future project databases

The runtime should know:

- available databases
- descriptions
- permissions

Databases should remain independent.

Deliverable:

Multiple knowledge sources available simultaneously.

Codex Result:
```
• Completed Phase 5 from roadmap3.md.

  Implemented:

  - Added KNOWLEDGE_SOURCES_JSON configuration for external SQLite knowledge sources.
  - Every source now has stable metadata: id, name, path, description, permission, type, read_only, exists, and size_bytes.
  - The active chat database is always exposed as the chat source.
  - Configured sources such as archive and project databases are listed alongside discovered databases without merging files.
  - Added a list_knowledge_sources model tool.
  - SQLite model tools now accept source_id as well as database_path, so the model can target chat, archive, project, or future memory databases independently.
  - The UI database selector now shows source ids, descriptions, and permissions.
  - Added regression tests in backend/test_phase5_knowledge_sources.py.

  Verified:

  - python3 -m unittest backend.test_phase5_knowledge_sources passes.
  - python3 -m unittest discover backend passes: 60 tests.
  - npm run build passes.
```

---

# Phase 6: Manual Knowledge Source Registration

Make external SQLite databases easy to add as knowledge sources.

Behavior:

- user provides a database path
- user provides a source id, name, and optional description
- backend validates that the database exists
- backend validates that it can be opened read-only
- source is saved as a configured knowledge source
- source appears in the database explorer
- source appears in `list_knowledge_sources`
- SQLite tools can target it by `source_id`

Deliverable:

Any readable SQLite database can become a model-visible knowledge source by adding its path.

Codex Result:
```
• Completed Phase 6 from roadmap3.md.

  Implemented:

  - Added persistent knowledge source storage via KNOWLEDGE_SOURCES_PATH.
  - Added POST /api/knowledge-sources for manual SQLite source registration.
  - Validates source id, name, path existence, and read-only SQLite access before saving.
  - Registered sources immediately appear in the SQLite explorer source list.
  - The chat tool registry refreshes after registration, so list_knowledge_sources and SQLite source_id targeting work without restarting.
  - Added a compact UI form in the SQLite sidebar for saving a database as a source.
  - Added regression tests in backend/test_phase6_knowledge_source_registration.py.

  Verified:

  - python3 -m unittest backend.test_phase6_knowledge_source_registration passes.
  - python3 -m unittest discover backend passes: 62 tests.
  - npm run build passes.
```

---

# Phase 7: Unified Knowledge Browser

Create a simple browser inside the UI.

Allow browsing:

- conversations
- memories
- SQLite databases
- imported archives
- tool results

The browser should feel like a local knowledge explorer.

Not an IDE.

Not phpMyAdmin.

Just enough to inspect information.

Deliverable:

Knowledge can be explored visually.

---

# Phase 8: Knowledge Tool Framework

Expand the tool registry.

Prepare for future tools.

Possible future tools:

Filesystem

SQLite

Vector search

Document search

Importers

Future memory systems

The runtime should not care where information originates.

Every capability should look like:

Tool

↓

Result

↓

Model

Deliverable:

Future tools can be added by registration only.

---

## Design Notes

Avoid creating multiple chat applications.

There should be one conversational runtime.

Supporting applications should perform specialized work.

Examples:

Archive importer

Document importer

Future email importer

Future calendar importer

Future Git repository importer

All of these produce knowledge.

The chat runtime consumes knowledge.

---

## Prototype Complete When

The application becomes the central interface for interacting with local knowledge.

It should be possible to:

- explore SQLite databases
- search imported archives
- ask questions about external knowledge
- browse conversations
- inspect schemas
- use safe database tools
- add new knowledge sources without changing the runtime

Future work—including episodic memory, sleep/consolidation, semantic promotion, autonomous workers, and long-term memory synthesis—belongs in the next roadmap.
