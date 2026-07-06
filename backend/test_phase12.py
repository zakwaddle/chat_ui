from __future__ import annotations

import os
import unittest
from pathlib import Path


class ConfigurationFileTest(unittest.TestCase):
    CONFIG_KEYS = (
        "MODEL_ENDPOINT_URL",
        "MODEL_NAME",
        "MODEL_TIMEOUT_SECONDS",
        "MODEL_TEMPERATURE",
        "MODEL_REPEAT_PENALTY",
        "USE_PLACEHOLDER_CHAT",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL_PATH",
        "EMBEDDING_ENDPOINT_URL",
        "EMBEDDING_MODEL",
        "EMBEDDING_TIMEOUT_SECONDS",
        "EMBEDDING_CONTEXT_SIZE",
        "ROLLING_MESSAGE_COUNT",
        "RETRIEVED_MEMORY_COUNT",
        "RETRIEVAL_SIMILARITY_THRESHOLD",
        "DEFAULT_CONTEXT_BEFORE",
        "DEFAULT_CONTEXT_AFTER",
        "MAX_TOOL_EXPANSION_PASSES",
        "SYSTEM_PROMPT",
        "KNOWLEDGE_SOURCES_JSON",
        "KNOWLEDGE_SOURCES_PATH",
    )

    def tearDown(self) -> None:
        for key in self.CONFIG_KEYS:
            os.environ.pop(key, None)

    def test_config_loads_defaults(self) -> None:
        from backend.config import load_config

        config = load_config()

        self.assertEqual(config.model_endpoint_url, "http://localhost:8080/v1")
        self.assertEqual(config.model_name, "local-placeholder-model")
        self.assertIsNone(config.model_temperature)
        self.assertIsNone(config.model_repeat_penalty)
        self.assertEqual(config.embedding_provider, "auto")
        self.assertEqual(config.embedding_model_path, Path("/storage/gguf/nomic-embed-text-v2-moe.Q8_0.gguf"))
        self.assertEqual(config.rolling_message_count, 12)
        self.assertEqual(config.retrieved_memory_count, 6)
        self.assertIsNone(config.retrieval_similarity_threshold)
        self.assertEqual(config.default_context_before, 3)
        self.assertEqual(config.default_context_after, 3)
        self.assertEqual(config.max_tool_expansion_passes, 1)
        self.assertEqual(config.knowledge_sources, ())

    def test_config_loads_environment_overrides(self) -> None:
        from backend.config import load_config

        os.environ["MODEL_ENDPOINT_URL"] = "http://localhost:9999/v1"
        os.environ["MODEL_NAME"] = "chat-model"
        os.environ["MODEL_TEMPERATURE"] = "0.4"
        os.environ["MODEL_REPEAT_PENALTY"] = "1.15"
        os.environ["USE_PLACEHOLDER_CHAT"] = "true"
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["EMBEDDING_MODEL"] = "embed-model"
        os.environ["ROLLING_MESSAGE_COUNT"] = "4"
        os.environ["RETRIEVED_MEMORY_COUNT"] = "2"
        os.environ["RETRIEVAL_SIMILARITY_THRESHOLD"] = "0.75"
        os.environ["DEFAULT_CONTEXT_BEFORE"] = "1"
        os.environ["DEFAULT_CONTEXT_AFTER"] = "5"
        os.environ["MAX_TOOL_EXPANSION_PASSES"] = "0"
        os.environ["KNOWLEDGE_SOURCES_JSON"] = (
            '[{"id":"archive","path":"/tmp/archive.sqlite3",'
            '"description":"Imported archive","permission":"sqlite.read"}]'
        )

        config = load_config()

        self.assertEqual(config.model_endpoint_url, "http://localhost:9999/v1")
        self.assertEqual(config.model_name, "chat-model")
        self.assertEqual(config.model_temperature, 0.4)
        self.assertEqual(config.model_repeat_penalty, 1.15)
        self.assertTrue(config.use_placeholder_chat)
        self.assertEqual(config.embedding_provider, "stub")
        self.assertEqual(config.embedding_model, "embed-model")
        self.assertEqual(config.rolling_message_count, 4)
        self.assertEqual(config.retrieved_memory_count, 2)
        self.assertEqual(config.retrieval_similarity_threshold, 0.75)
        self.assertEqual(config.default_context_before, 1)
        self.assertEqual(config.default_context_after, 5)
        self.assertEqual(config.max_tool_expansion_passes, 0)
        self.assertEqual(config.knowledge_sources[0]["id"], "archive")
        self.assertEqual(config.knowledge_sources[0]["path"], "/tmp/archive.sqlite3")
        self.assertEqual(config.knowledge_sources[0]["description"], "Imported archive")

    def test_config_clamps_memory_counts(self) -> None:
        from backend.config import load_config

        os.environ["ROLLING_MESSAGE_COUNT"] = "0"
        os.environ["RETRIEVED_MEMORY_COUNT"] = "-1"
        os.environ["DEFAULT_CONTEXT_BEFORE"] = "-3"
        os.environ["DEFAULT_CONTEXT_AFTER"] = "-4"
        os.environ["MAX_TOOL_EXPANSION_PASSES"] = "-2"
        os.environ["EMBEDDING_CONTEXT_SIZE"] = "8"
        os.environ["MODEL_TEMPERATURE"] = "-0.5"
        os.environ["MODEL_REPEAT_PENALTY"] = "-1"

        config = load_config()

        self.assertEqual(config.rolling_message_count, 1)
        self.assertEqual(config.retrieved_memory_count, 0)
        self.assertEqual(config.default_context_before, 0)
        self.assertEqual(config.default_context_after, 0)
        self.assertEqual(config.max_tool_expansion_passes, 0)
        self.assertEqual(config.embedding_context_size, 128)
        self.assertEqual(config.model_temperature, 0.0)
        self.assertEqual(config.model_repeat_penalty, 0.0)


if __name__ == "__main__":
    unittest.main()
