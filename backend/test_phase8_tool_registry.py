from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch


class ToolRegistryInfrastructureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        os.environ["DATABASE_PATH"] = self.database_file.name
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "0"
        os.environ["DEFAULT_CONTEXT_BEFORE"] = "1"
        os.environ["DEFAULT_CONTEXT_AFTER"] = "1"

    def tearDown(self) -> None:
        for key in (
            "DATABASE_PATH",
            "EMBEDDING_PROVIDER",
            "USE_PLACEHOLDER_CHAT",
            "DEFAULT_CONTEXT_BEFORE",
            "DEFAULT_CONTEXT_AFTER",
        ):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_default_registry_exposes_context_tool_metadata_and_definition(self) -> None:
        from backend.tools import build_default_tool_registry

        registry = build_default_tool_registry(default_context_before=2, default_context_after=4)
        definitions = registry.definitions()
        metadata = registry.metadata()

        definition_names = {definition["function"]["name"] for definition in definitions}
        metadata_by_name = {tool["name"]: tool for tool in metadata}

        self.assertIn("get_context_around_message", definition_names)
        self.assertIn("list_tables", definition_names)
        self.assertIn("describe_table", definition_names)
        self.assertIn("sample_rows", definition_names)
        self.assertIn("search_table", definition_names)
        self.assertIn("run_read_only_query", definition_names)
        self.assertEqual(metadata_by_name["get_context_around_message"]["permission"], "conversation.read")
        self.assertEqual(metadata_by_name["run_read_only_query"]["permission"], "sqlite.read")
        self.assertFalse(any(tool["destructive"] for tool in metadata))

    def test_registry_executes_context_tool_with_consistent_result_wrapper(self) -> None:
        from backend.database import create_conversation, create_message, init_db
        from backend.tools import build_default_tool_registry

        init_db()
        conversation = create_conversation("registry")
        before = create_message(conversation["id"], "user", "before")
        target = create_message(conversation["id"], "assistant", "target")
        after = create_message(conversation["id"], "user", "after")
        registry = build_default_tool_registry(default_context_before=1, default_context_after=1)

        execution = registry.execute_tool_call(
            {
                "id": "call_registry_context",
                "type": "function",
                "function": {
                    "name": "get_context_around_message",
                    "arguments": json.dumps({"message_id": target["id"]}),
                },
            }
        )

        self.assertEqual(execution.tool_call_id, "call_registry_context")
        self.assertTrue(execution.result.ok)
        self.assertEqual(execution.result.permission, "conversation.read")
        self.assertEqual(
            [message["message_id"] for message in execution.result.content["messages"]],
            [before["id"], target["id"], after["id"]],
        )
        self.assertEqual(json.loads(execution.result.model_content())["target_message_id"], target["id"])

    def test_chat_runtime_uses_registry_definitions_for_tool_expansion(self) -> None:
        from backend.app import create_app
        from backend.database import create_conversation, create_embedding, create_message
        from backend.embeddings import StubEmbeddingProvider, serialize_vector

        app = create_app()
        client = app.test_client()
        provider = StubEmbeddingProvider()
        conversation = create_conversation("registry chat")
        target = create_message(conversation["id"], "assistant", "target memory")
        create_embedding(
            target["id"],
            "stub",
            "deterministic-hash-v1",
            serialize_vector(provider.embed(target["content"]).vector),
        )
        captured_calls: list[dict] = []

        def fake_chat_message(_chat_client, messages, tools=None, generation_params=None):
            captured_calls.append({"messages": messages, "tools": tools})
            if len(captured_calls) == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_registered_context",
                            "type": "function",
                            "function": {
                                "name": "get_context_around_message",
                                "arguments": json.dumps({"message_id": target["id"]}),
                            },
                        }
                    ],
                }

            return {"role": "assistant", "content": "registry response"}

        with patch("backend.app.LocalChatClient._create_chat_message", fake_chat_message):
            response = client.post(
                "/api/chat",
                json={"conversation_id": conversation["id"], "message": "use registry"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_calls[0]["tools"][0]["function"]["name"], "get_context_around_message")
        self.assertEqual(captured_calls[1]["messages"][-1]["name"], "get_context_around_message")
        self.assertEqual(response.json["context_expansion"]["permission"], "conversation.read")
        self.assertTrue(response.json["context_expansion"]["used"])

    def test_tools_endpoint_exposes_registry_metadata(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        response = client.get("/api/tools")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["tools"][0]["name"], "get_context_around_message")
        self.assertEqual(response.json["tools"][0]["permission"], "conversation.read")
        self.assertFalse(response.json["tools"][0]["destructive"])


if __name__ == "__main__":
    unittest.main()
