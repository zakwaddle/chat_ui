from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SQLiteToolRegistryTest(unittest.TestCase):
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
                INSERT INTO notes (title, body) VALUES ('Embeddings', 'Messages about vector search');
                INSERT INTO notes (title, body) VALUES ('Birthday', 'Henry birthday notes');
                """
            )

    def tearDown(self) -> None:
        for key in ("DATABASE_PATH", "EMBEDDING_PROVIDER", "USE_PLACEHOLDER_CHAT"):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_path)
        except FileNotFoundError:
            pass

    def test_registry_exposes_sqlite_tools_as_read_only(self) -> None:
        from backend.tools import build_default_tool_registry

        registry = build_default_tool_registry(default_context_before=1, default_context_after=1)
        metadata = {tool["name"]: tool for tool in registry.metadata()}

        for tool_name in ("list_tables", "describe_table", "sample_rows", "search_table", "run_read_only_query"):
            self.assertIn(tool_name, metadata)
            self.assertEqual(metadata[tool_name]["permission"], "sqlite.read")
            self.assertFalse(metadata[tool_name]["destructive"])

    def test_sqlite_tools_list_describe_sample_and_search(self) -> None:
        from backend.tools import build_default_tool_registry

        registry = build_default_tool_registry(
            default_context_before=1,
            default_context_after=1,
            sqlite_database_path=self.database_path,
        )

        tables = self._execute(registry, "list_tables", {})
        description = self._execute(registry, "describe_table", {"table_name": "notes"})
        sample = self._execute(registry, "sample_rows", {"table_name": "notes", "limit": 1})
        search = self._execute(registry, "search_table", {"table_name": "notes", "query": "Henry"})

        self.assertTrue(tables.result.ok)
        self.assertIn("notes", [table["name"] for table in tables.result.content["tables"]])
        self.assertEqual([column["name"] for column in description.result.content["columns"]], ["id", "title", "body"])
        self.assertEqual(len(sample.result.content["rows"]), 1)
        self.assertEqual(search.result.content["rows"][0]["title"], "Birthday")

    def test_read_only_query_allows_select_and_rejects_mutation(self) -> None:
        from backend.tools import build_default_tool_registry

        registry = build_default_tool_registry(
            default_context_before=1,
            default_context_after=1,
            sqlite_database_path=self.database_path,
        )

        allowed = self._execute(
            registry,
            "run_read_only_query",
            {"sql": "SELECT title FROM notes WHERE body LIKE ?", "params": ["%vector%"]},
        )
        rejected_insert = self._execute(
            registry,
            "run_read_only_query",
            {"sql": "INSERT INTO notes (title, body) VALUES ('bad', 'write')"},
        )
        rejected_pragma = self._execute(registry, "run_read_only_query", {"sql": "PRAGMA writable_schema = ON"})
        rejected_attach = self._execute(registry, "run_read_only_query", {"sql": "ATTACH DATABASE '/tmp/x.db' AS x"})

        self.assertTrue(allowed.result.ok)
        self.assertEqual(allowed.result.content["rows"][0]["title"], "Embeddings")
        self.assertFalse(rejected_insert.result.ok)
        self.assertFalse(rejected_pragma.result.ok)
        self.assertFalse(rejected_attach.result.ok)

        with sqlite3.connect(self.database_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        self.assertEqual(count, 2)

    def test_chat_runtime_can_execute_sqlite_tool_call(self) -> None:
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
                            "id": "call_sqlite_tables",
                            "type": "function",
                            "function": {
                                "name": "list_tables",
                                "arguments": "{}",
                            },
                        }
                    ],
                }

            tool_payload = json.loads(messages[-1]["content"])
            table_names = [table["name"] for table in tool_payload["tables"]]
            return {"role": "assistant", "content": f"tables: {', '.join(table_names)}"}

        with patch("backend.app.LocalChatClient._create_chat_message", fake_chat_message):
            response = client.post("/api/chat", json={"message": "what tables are in the database?"})

        self.assertEqual(response.status_code, 200)
        tool_names = {tool["function"]["name"] for tool in captured_calls[0]["tools"]}
        self.assertIn("list_tables", tool_names)
        self.assertEqual(captured_calls[1]["messages"][-1]["name"], "list_tables")
        self.assertEqual(response.json["context_expansion"]["permission"], "sqlite.read")
        self.assertTrue(response.json["context_expansion"]["used"])
        self.assertIn("notes", response.json["assistant_message"]["content"])

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
