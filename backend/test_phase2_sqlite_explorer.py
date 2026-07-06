from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class SQLiteExplorerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        self.database_path = Path(self.database_file.name)
        os.environ["DATABASE_PATH"] = str(self.database_path)
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "1"

        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE people (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    note TEXT
                );
                INSERT INTO people (name, note) VALUES ('Ada', 'math');
                INSERT INTO people (name, note) VALUES ('Grace', 'compiler');
                """
            )

    def tearDown(self) -> None:
        for key in ("DATABASE_PATH", "EMBEDDING_PROVIDER", "USE_PLACEHOLDER_CHAT"):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_path)
        except FileNotFoundError:
            pass

    def test_lists_available_active_database(self) -> None:
        from backend.sqlite_explorer import list_available_databases

        databases = list_available_databases(self.database_path)

        self.assertTrue(any(database["path"] == str(self.database_path.resolve()) for database in databases))

    def test_inspects_schema_and_row_counts_read_only(self) -> None:
        from backend.sqlite_explorer import inspect_database

        schema = inspect_database(self.database_path)

        people = next(table for table in schema["tables"] if table["name"] == "people")
        self.assertEqual(people["type"], "table")
        self.assertEqual(people["row_count"], 2)

    def test_describes_columns(self) -> None:
        from backend.sqlite_explorer import describe_table

        description = describe_table(self.database_path, "people")

        self.assertEqual(description["row_count"], 2)
        self.assertEqual([column["name"] for column in description["columns"]], ["id", "name", "note"])
        self.assertTrue(description["columns"][1]["not_null"])

    def test_previews_rows_with_limit(self) -> None:
        from backend.sqlite_explorer import preview_rows

        preview = preview_rows(self.database_path, "people", limit=1)

        self.assertEqual(preview["columns"], ["id", "name", "note"])
        self.assertEqual(preview["row_count"], 2)
        self.assertEqual(len(preview["rows"]), 1)
        self.assertEqual(preview["rows"][0]["name"], "Ada")

    def test_api_exposes_database_table_and_preview(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        databases_response = client.get("/api/sqlite/databases")
        schema_response = client.get("/api/sqlite/schema", query_string={"path": str(self.database_path)})
        table_response = client.get("/api/sqlite/tables/people", query_string={"path": str(self.database_path)})
        rows_response = client.get("/api/sqlite/tables/people/rows", query_string={"path": str(self.database_path), "limit": 2})

        self.assertEqual(databases_response.status_code, 200)
        self.assertEqual(schema_response.status_code, 200)
        self.assertEqual(table_response.status_code, 200)
        self.assertEqual(rows_response.status_code, 200)
        self.assertEqual(rows_response.json["row_count"], 2)
        self.assertEqual([row["name"] for row in rows_response.json["rows"]], ["Ada", "Grace"])

    def test_api_rejects_missing_database(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        response = client.get("/api/sqlite/schema", query_string={"path": "/tmp/does-not-exist.sqlite3"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("database not found", response.json["error"])


if __name__ == "__main__":
    unittest.main()
