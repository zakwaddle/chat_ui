from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class KnowledgeBrowserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.chat_database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.archive_database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.chat_database_file.close()
        self.archive_database_file.close()
        self.chat_path = Path(self.chat_database_file.name)
        self.archive_path = Path(self.archive_database_file.name)

        os.environ["DATABASE_PATH"] = str(self.chat_path)
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "1"
        os.environ["KNOWLEDGE_SOURCES_JSON"] = json.dumps(
            [
                {
                    "id": "archive",
                    "name": "Archive",
                    "path": str(self.archive_path),
                    "description": "Imported archive database",
                    "permission": "sqlite.read",
                }
            ]
        )

        with sqlite3.connect(self.archive_path) as connection:
            connection.execute("CREATE TABLE archive_items (id INTEGER PRIMARY KEY, content TEXT NOT NULL)")
            connection.execute("INSERT INTO archive_items (content) VALUES ('archive note')")

    def tearDown(self) -> None:
        for key in ("DATABASE_PATH", "EMBEDDING_PROVIDER", "USE_PLACEHOLDER_CHAT", "KNOWLEDGE_SOURCES_JSON"):
            os.environ.pop(key, None)

        for path in (self.chat_path, self.archive_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def test_browser_exposes_conversations_memories_databases_archives_and_tools(self) -> None:
        from backend.app import create_app
        from backend.database import connect, create_conversation, create_message

        app = create_app()
        conversation = create_conversation("Browser thread")
        create_message(conversation["id"], "user", "conversation browser message")
        create_message(
            conversation["id"],
            "tool",
            json.dumps({"tool_name": "search_database", "result": {"rows": [{"content": "tool result"}]}}),
        )
        with connect() as connection:
            connection.execute(
                "INSERT INTO semantic_memory (content, created_at, metadata) VALUES (?, ?, '{}')",
                ("durable browser memory", "2026-07-06T00:00:00+00:00"),
            )

        response = app.test_client().get("/api/knowledge/browser")

        self.assertEqual(response.status_code, 200)
        sections = {section["id"]: section for section in response.json["sections"]}
        self.assertEqual(set(sections), {"conversations", "memories", "sqlite_databases", "archives", "tool_results"})

        self.assertIn("Browser thread", [item["title"] for item in sections["conversations"]["items"]])
        self.assertIn("semantic memory", [item["title"] for item in sections["memories"]["items"]])
        self.assertIn("archive", [item["source_id"] for item in sections["sqlite_databases"]["items"]])
        self.assertEqual(sections["archives"]["items"][0]["source_id"], "archive")
        self.assertIn("search_database", [item["title"] for item in sections["tool_results"]["items"]])

    def test_browser_handles_empty_database(self) -> None:
        from backend.app import create_app

        app = create_app()
        response = app.test_client().get("/api/knowledge/browser")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json["total_items"], 1)
        sections = {section["id"]: section for section in response.json["sections"]}
        self.assertEqual(sections["conversations"]["items"], [])
        self.assertTrue(sections["memories"]["items"])


if __name__ == "__main__":
    unittest.main()
