from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class KnowledgeSourceRegistrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.chat_database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.source_database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.sources_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.chat_database_file.close()
        self.source_database_file.close()
        self.sources_file.close()

        self.chat_path = Path(self.chat_database_file.name)
        self.source_path = Path(self.source_database_file.name)
        self.sources_path = Path(self.sources_file.name)
        self.sources_path.unlink()

        os.environ["DATABASE_PATH"] = str(self.chat_path)
        os.environ["KNOWLEDGE_SOURCES_PATH"] = str(self.sources_path)
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "0"

        with sqlite3.connect(self.source_path) as connection:
            connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, content TEXT NOT NULL)")
            connection.execute("INSERT INTO notes (content) VALUES ('registered source note')")

    def tearDown(self) -> None:
        for key in (
            "DATABASE_PATH",
            "KNOWLEDGE_SOURCES_PATH",
            "KNOWLEDGE_SOURCES_JSON",
            "EMBEDDING_PROVIDER",
            "USE_PLACEHOLDER_CHAT",
        ):
            os.environ.pop(key, None)

        for path in (self.chat_path, self.source_path, self.sources_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def test_registers_persists_and_exposes_sqlite_knowledge_source(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        response = client.post(
            "/api/knowledge-sources",
            json={
                "id": "archive",
                "name": "Archive",
                "path": str(self.source_path),
                "description": "Registered archive database",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["source"]["id"], "archive")
        self.assertEqual(response.json["source"]["path"], str(self.source_path.resolve()))
        self.assertTrue(self.sources_path.exists())

        saved_sources = json.loads(self.sources_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_sources[0]["id"], "archive")
        self.assertEqual(saved_sources[0]["name"], "Archive")

        databases_response = client.get("/api/sqlite/databases")
        sources_by_id = {source["id"]: source for source in databases_response.json["databases"]}
        self.assertEqual(sources_by_id["archive"]["description"], "Registered archive database")

        captured_calls: list[dict] = []

        def fake_chat_message(_chat_client, messages, tools=None, generation_params=None):
            captured_calls.append({"messages": messages, "tools": tools})
            if len(captured_calls) == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_sample_archive",
                            "type": "function",
                            "function": {
                                "name": "sample_rows",
                                "arguments": json.dumps({"source_id": "archive", "table_name": "notes"}),
                            },
                        }
                    ],
                }

            tool_payload = json.loads(messages[-1]["content"])
            return {"role": "assistant", "content": tool_payload["rows"][0]["content"]}

        with patch("backend.app.LocalChatClient._create_chat_message", fake_chat_message):
            chat_response = client.post("/api/chat", json={"message": "read the archive source"})

        self.assertEqual(chat_response.status_code, 200)
        self.assertEqual(chat_response.json["assistant_message"]["content"], "registered source note")
        self.assertEqual(captured_calls[1]["messages"][-1]["name"], "sample_rows")

        from backend.config import load_config
        from backend.tools import build_default_tool_registry

        reloaded_config = load_config()
        tool_registry = build_default_tool_registry(
            default_context_before=1,
            default_context_after=1,
            sqlite_database_path=reloaded_config.database_path,
            knowledge_sources=reloaded_config.knowledge_sources,
        )
        execution = tool_registry.execute_tool_call(
            {
                "id": "call_sample_rows",
                "type": "function",
                "function": {
                    "name": "sample_rows",
                    "arguments": json.dumps({"source_id": "archive", "table_name": "notes"}),
                },
            }
        )

        self.assertTrue(execution.result.ok)
        self.assertEqual(execution.result.content["rows"][0]["content"], "registered source note")

    def test_rejects_missing_or_unreadable_database_path(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        response = client.post(
            "/api/knowledge-sources",
            json={"id": "missing", "name": "Missing", "path": str(self.source_path.with_name("missing.sqlite3"))},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("database not found", response.json["error"])
        self.assertFalse(self.sources_path.exists())


if __name__ == "__main__":
    unittest.main()
