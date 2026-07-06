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

---

# Phase 6: Archive Integration

The Archive application should become an importer rather than a chat application.

Responsibilities:

Archive application:

- import ChatGPT exports
- clean data
- normalize data
- generate embeddings
- write archive database

Chat application:

- search archive
- retrieve memories
- answer questions
- use archive tools

Remove duplicated chat functionality.

There should be one primary chat interface.

Deliverable:

Archive becomes a knowledge producer.

Chat becomes the knowledge consumer.

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