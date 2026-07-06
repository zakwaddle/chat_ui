from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class KnowledgeSourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.chat_database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.archive_database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.project_database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.chat_database_file.close()
        self.archive_database_file.close()
        self.project_database_file.close()
        self.chat_path = Path(self.chat_database_file.name)
        self.archive_path = Path(self.archive_database_file.name)
        self.project_path = Path(self.project_database_file.name)

        os.environ["DATABASE_PATH"] = str(self.chat_path)
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "0"
        os.environ["KNOWLEDGE_SOURCES_JSON"] = json.dumps(
            [
                {
                    "id": "archive",
                    "name": "Archive",
                    "path": str(self.archive_path),
                    "description": "Imported archive database",
                    "permission": "sqlite.read",
                },
                {
                    "id": "project",
                    "name": "Project",
                    "path": str(self.project_path),
                    "description": "Project knowledge database",
                    "permission": "sqlite.read",
                },
            ]
        )

        self._seed_database(self.archive_path, "archive_items", "archive only memory")
        self._seed_database(self.project_path, "project_items", "project only note")

    def tearDown(self) -> None:
        for key in ("DATABASE_PATH", "EMBEDDING_PROVIDER", "USE_PLACEHOLDER_CHAT", "KNOWLEDGE_SOURCES_JSON"):
            os.environ.pop(key, None)

        for path in (self.chat_path, self.archive_path, self.project_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def test_lists_multiple_knowledge_sources_with_metadata(self) -> None:
        from backend.config import load_config
        from backend.sqlite_explorer import list_available_databases

        config = load_config()
        sources = list_available_databases(config.database_path, config.knowledge_sources)
        sources_by_id = {source["id"]: source for source in sources}

        self.assertIn("chat", sources_by_id)
        self.assertIn("archive", sources_by_id)
        self.assertIn("project", sources_by_id)
        self.assertEqual(sources_by_id["archive"]["description"], "Imported archive database")
        self.assertEqual(sources_by_id["archive"]["permission"], "sqlite.read")
        self.assertTrue(sources_by_id["archive"]["read_only"])
        self.assertEqual(sources_by_id["archive"]["path"], str(self.archive_path.resolve()))

    def test_registry_can_list_sources_and_query_each_source_independently(self) -> None:
        from backend.config import load_config
        from backend.tools import build_default_tool_registry

        config = load_config()
        registry = build_default_tool_registry(
            default_context_before=1,
            default_context_after=1,
            sqlite_database_path=config.database_path,
            knowledge_sources=config.knowledge_sources,
        )

        sources = self._execute(registry, "list_knowledge_sources", {})
        archive_tables = self._execute(registry, "list_tables", {"source_id": "archive"})
        project_tables = self._execute(registry, "list_tables", {"source_id": "project"})
        archive_search = self._execute(registry, "search_database", {"source_id": "archive", "query": "archive only"})
        project_search = self._execute(registry, "search_database", {"source_id": "project", "query": "project only"})

        self.assertTrue(sources.result.ok)
        self.assertIn("archive", [source["id"] for source in sources.result.content["sources"]])
        self.assertEqual([table["name"] for table in archive_tables.result.content["tables"]], ["archive_items"])
        self.assertEqual([table["name"] for table in project_tables.result.content["tables"]], ["project_items"])
        self.assertEqual(archive_search.result.content["results"][0]["row"]["content"], "archive only memory")
        self.assertEqual(project_search.result.content["results"][0]["row"]["content"], "project only note")

    def test_api_lists_configured_sources(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        response = client.get("/api/sqlite/databases")

        self.assertEqual(response.status_code, 200)
        sources_by_id = {source["id"]: source for source in response.json["databases"]}
        self.assertEqual(sources_by_id["archive"]["name"], "Archive")
        self.assertEqual(sources_by_id["project"]["description"], "Project knowledge database")

    def test_chat_runtime_can_use_external_source_id(self) -> None:
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
                            "id": "call_archive_search",
                            "type": "function",
                            "function": {
                                "name": "search_database",
                                "arguments": json.dumps({"source_id": "archive", "query": "archive only"}),
                            },
                        }
                    ],
                }

            tool_payload = json.loads(messages[-1]["content"])
            return {"role": "assistant", "content": tool_payload["results"][0]["row"]["content"]}

        with patch("backend.app.LocalChatClient._create_chat_message", fake_chat_message):
            response = client.post("/api/chat", json={"message": "search the archive"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_calls[1]["messages"][-1]["name"], "search_database")
        self.assertEqual(response.json["assistant_message"]["content"], "archive only memory")

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

    def _seed_database(self, path: Path, table_name: str, content: str) -> None:
        with sqlite3.connect(path) as connection:
            connection.execute(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, content TEXT NOT NULL)")
            connection.execute(f"INSERT INTO {table_name} (content) VALUES (?)", (content,))


if __name__ == "__main__":
    unittest.main()
