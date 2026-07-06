from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class DatabaseSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        self.database_path = Path(self.database_file.name)
        os.environ["DATABASE_PATH"] = str(self.database_path)
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "0"

        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE notes (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL
                );
                CREATE TABLE message_archive (
                    id INTEGER PRIMARY KEY,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL
                );
                CREATE TABLE binary_items (
                    id INTEGER PRIMARY KEY,
                    payload BLOB NOT NULL
                );

                INSERT INTO notes (title, body) VALUES ('Henry birthday', 'Gift notes and dinner time');
                INSERT INTO notes (title, body) VALUES ('Mark essay', 'Archive notes about an essay draft');
                INSERT INTO message_archive (role, content) VALUES ('user', 'messages about embeddings and vector search');
                INSERT INTO binary_items (payload) VALUES (x'00FF');
                """
            )

    def tearDown(self) -> None:
        for key in ("DATABASE_PATH", "EMBEDDING_PROVIDER", "USE_PLACEHOLDER_CHAT"):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_path)
        except FileNotFoundError:
            pass

    def test_search_database_finds_matches_across_tables(self) -> None:
        from backend.sqlite_explorer import search_database

        result = search_database(self.database_path, "messages about embeddings")

        self.assertEqual(result["query"], "messages about embeddings")
        self.assertIn("message_archive", [match["table"] for match in result["results"]])
        message_match = next(match for match in result["results"] if match["table"] == "message_archive")
        self.assertIn("content", message_match["matched_columns"]["messages"])
        self.assertEqual(message_match["row"]["content"], "messages about embeddings and vector search")

    def test_search_database_supports_table_restriction_and_limit(self) -> None:
        from backend.sqlite_explorer import search_database

        result = search_database(self.database_path, "Henry birthday", tables=["notes"], limit=1)

        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["table"], "notes")
        self.assertEqual(result["results"][0]["row"]["title"], "Henry birthday")
        self.assertTrue(result["truncated"])

    def test_registry_exposes_search_database_tool(self) -> None:
        from backend.tools import build_default_tool_registry

        registry = build_default_tool_registry(
            default_context_before=1,
            default_context_after=1,
            sqlite_database_path=self.database_path,
        )
        metadata = {tool["name"]: tool for tool in registry.metadata()}
        execution = self._execute(registry, "search_database", {"query": "Mark essay"})

        self.assertIn("search_database", metadata)
        self.assertEqual(metadata["search_database"]["permission"], "sqlite.read")
        self.assertFalse(metadata["search_database"]["destructive"])
        self.assertTrue(execution.result.ok)
        self.assertEqual(execution.result.content["results"][0]["row"]["title"], "Mark essay")

    def test_chat_runtime_can_search_database_without_sql(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()
        captured_calls: list[dict] = []

        def fake_chat_message(_chat_client, messages, tools=None, generation_params=None):
            captured_calls.append({"messages": messages, "tools": tools})
            if len(captured_calls) == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_search_database",
                            "type": "function",
                            "function": {
                                "name": "search_database",
                                "arguments": json.dumps({"query": "Henry birthday"}),
                            },
                        }
                    ],
                }

            tool_payload = json.loads(messages[-1]["content"])
            return {"role": "assistant", "content": tool_payload["results"][0]["row"]["title"]}

        with patch("backend.app.LocalChatClient._create_chat_message", fake_chat_message):
            response = client.post("/api/chat", json={"message": "Find Henry birthday"})

        self.assertEqual(response.status_code, 200)
        tool_names = {tool["function"]["name"] for tool in captured_calls[0]["tools"]}
        self.assertIn("search_database", tool_names)
        self.assertEqual(captured_calls[1]["messages"][-1]["name"], "search_database")
        self.assertEqual(response.json["context_expansion"]["permission"], "sqlite.read")
        self.assertIn("Henry birthday", response.json["assistant_message"]["content"])

    def _execute(self, registry, tool_name: str, arguments: dict):
        return registry.execute_tool_call(
            {
                "id": f"call_{tool_name}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(arguments),
                },
            }
        )


if __name__ == "__main__":
    unittest.main()
