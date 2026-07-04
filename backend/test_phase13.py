from __future__ import annotations

import os
import tempfile
import unittest


class ExtensibilityHooksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        os.environ["DATABASE_PATH"] = self.database_file.name

    def tearDown(self) -> None:
        os.environ.pop("DATABASE_PATH", None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_future_memory_tables_are_initialized(self) -> None:
        from backend.database import FUTURE_MEMORY_TABLES, connect, init_db

        init_db()
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name IN (
                    'episodes',
                    'episode_summaries',
                    'semantic_memory',
                    'memory_index',
                    'crystallization_seeds'
                  )
                ORDER BY name
                """
            ).fetchall()

        self.assertEqual(
            {row["name"] for row in rows},
            set(FUTURE_MEMORY_TABLES),
        )

    def test_future_memory_layer_registry_is_available(self) -> None:
        from backend.memory_layers import list_future_memory_layers

        layers = list_future_memory_layers()

        self.assertEqual(
            {layer["table_name"] for layer in layers},
            {
                "episodes",
                "episode_summaries",
                "semantic_memory",
                "memory_index",
                "crystallization_seeds",
            },
        )

    def test_compatibility_modules_import(self) -> None:
        from backend import chat, db, prompt_builder

        self.assertTrue(hasattr(db, "init_db"))
        self.assertTrue(hasattr(prompt_builder, "assemble_prompt"))
        self.assertIn("retrieve_memories", chat.CHAT_PIPELINE_STAGES)


if __name__ == "__main__":
    unittest.main()
