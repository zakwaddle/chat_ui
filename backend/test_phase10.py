from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch


class ToolCallingChatLoopTest(unittest.TestCase):
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
            "MAX_TOOL_EXPANSION_PASSES",
        ):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_chat_loop_executes_one_context_expansion_pass(self) -> None:
        from backend.app import create_app
        from backend.database import create_conversation, create_embedding, create_message, list_messages
        from backend.embeddings import StubEmbeddingProvider, serialize_vector

        app = create_app()
        client = app.test_client()
        provider = StubEmbeddingProvider()
        conversation = create_conversation("tool calling")
        first = create_message(conversation["id"], "user", "before target")
        target = create_message(conversation["id"], "assistant", "target memory")
        third = create_message(conversation["id"], "user", "after target")

        for message in (first, target, third):
            create_embedding(
                message["id"],
                "stub",
                "deterministic-hash-v1",
                serialize_vector(provider.embed(message["content"]).vector),
            )

        captured_calls: list[dict] = []

        def fake_chat_message(_chat_client, messages, tools=None):
            captured_calls.append({"messages": messages, "tools": tools})
            if len(captured_calls) == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_context",
                            "type": "function",
                            "function": {
                                "name": "get_context_around_message",
                                "arguments": json.dumps({"message_id": target["id"]}),
                            },
                        }
                    ],
                }

            return {"role": "assistant", "content": "I expanded the memory and found the scene."}

        with patch("backend.app.LocalChatClient._create_chat_message", fake_chat_message):
            response = client.post(
                "/api/chat",
                json={"conversation_id": conversation["id"], "message": "what surrounded that memory?"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(captured_calls), 2)
        self.assertIsNotNone(captured_calls[0]["tools"])
        self.assertIsNone(captured_calls[1]["tools"])
        self.assertEqual(captured_calls[1]["messages"][-1]["role"], "tool")
        self.assertEqual(captured_calls[1]["messages"][-1]["name"], "get_context_around_message")

        tool_payload = json.loads(captured_calls[1]["messages"][-1]["content"])
        self.assertEqual(
            [message["content"] for message in tool_payload["messages"]],
            ["before target", "target memory", "after target"],
        )
        self.assertTrue(response.json["context_expansion"]["used"])
        self.assertEqual(response.json["context_expansion"]["tool_name"], "get_context_around_message")
        self.assertEqual(response.json["assistant_message"]["content"], "I expanded the memory and found the scene.")
        self.assertEqual(list_messages(conversation["id"])[-1]["content"], "I expanded the memory and found the scene.")

    def test_chat_loop_skips_tool_expansion_when_disabled(self) -> None:
        os.environ["MAX_TOOL_EXPANSION_PASSES"] = "0"

        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        with patch("backend.app.LocalChatClient.complete", return_value="no tool pass") as complete:
            response = client.post("/api/chat", json={"message": "skip tools"})

        self.assertEqual(response.status_code, 200)
        complete.assert_called_once()
        self.assertFalse(response.json["context_expansion"]["used"])
        self.assertEqual(response.json["assistant_message"]["content"], "no tool pass")


if __name__ == "__main__":
    unittest.main()
