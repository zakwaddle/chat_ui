from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch


class ChatRuntimeRegressionTest(unittest.TestCase):
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
            "ROLLING_MESSAGE_COUNT",
            "RETRIEVED_MEMORY_COUNT",
            "RETRIEVAL_SIMILARITY_THRESHOLD",
            "MAX_TOOL_EXPANSION_PASSES",
            "MODEL_TEMPERATURE",
            "MODEL_REPEAT_PENALTY",
        ):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_normal_chat_persists_conversation_messages_and_embeddings(self) -> None:
        from backend.app import create_app
        from backend.database import list_conversations, list_embeddings, list_messages

        app = create_app()
        client = app.test_client()

        def fake_chat_message(_chat_client, _messages, tools=None, generation_params=None):
            return {"role": "assistant", "content": "normal runtime response"}

        with patch("backend.app.LocalChatClient._create_chat_message", fake_chat_message):
            response = client.post("/api/chat", json={"message": "normal runtime request"})

        self.assertEqual(response.status_code, 200)
        conversation_id = response.json["conversation"]["id"]
        messages = list_messages(conversation_id)

        self.assertEqual([message["role"] for message in messages], ["user", "assistant"])
        self.assertEqual(messages[0]["content"], "normal runtime request")
        self.assertEqual(messages[1]["content"], "normal runtime response")
        self.assertIsNotNone(messages[0]["embedding_id"])
        self.assertIsNotNone(messages[1]["embedding_id"])
        self.assertEqual(len(list_embeddings()), 2)
        self.assertEqual(list_conversations()[0]["message_count"], 2)

    def test_streaming_chat_streams_deltas_and_persists_final_response(self) -> None:
        from backend.app import create_app
        from backend.database import list_messages

        app = create_app()
        client = app.test_client()

        def fake_stream_events(_chat_client, _messages, tools=None, generation_params=None):
            yield {"type": "delta", "content": "streamed "}
            yield {"type": "delta", "content": "runtime"}
            yield {"type": "message", "message": {"role": "assistant", "content": "streamed runtime"}}

        with patch("backend.app.LocalChatClient._create_chat_message_stream_events", fake_stream_events):
            response = client.post("/api/chat/stream", json={"message": "stream runtime"}, buffered=True)

        self.assertEqual(response.status_code, 200)
        events = self._decode_stream_events(response)
        assistant_event = next(event for event in events if event["event"] == "assistant_message")
        conversation_id = assistant_event["data"]["conversation"]["id"]

        self.assertEqual(
            [event["data"]["content"] for event in events if event["event"] == "delta"],
            ["streamed ", "runtime"],
        )
        self.assertFalse(assistant_event["data"]["context_expansion"]["used"])
        self.assertEqual(assistant_event["data"]["assistant_message"]["content"], "streamed runtime")
        self.assertEqual(list_messages(conversation_id)[-1]["content"], "streamed runtime")

    def test_retrieval_excludes_rolling_window_and_adds_recalled_prompt_context(self) -> None:
        os.environ["ROLLING_MESSAGE_COUNT"] = "2"
        os.environ["RETRIEVED_MEMORY_COUNT"] = "10"

        from backend.app import create_app
        from backend.database import create_conversation, create_embedding, create_message
        from backend.embeddings import StubEmbeddingProvider, serialize_vector

        app = create_app()
        client = app.test_client()
        provider = StubEmbeddingProvider()
        conversation = create_conversation("retrieval regression")

        for content in ("older apple memory", "recent banana turn", "recent cherry turn"):
            message = create_message(conversation["id"], "user", content)
            create_embedding(
                message["id"],
                "stub",
                "deterministic-hash-v1",
                serialize_vector(provider.embed(content).vector),
            )

        captured_prompts: list[list[dict[str, str]]] = []

        def fake_chat_message(_chat_client, messages, tools=None, generation_params=None):
            captured_prompts.append(messages)
            return {"role": "assistant", "content": "retrieval-aware response"}

        with patch("backend.app.LocalChatClient._create_chat_message", fake_chat_message):
            response = client.post(
                "/api/chat",
                json={"conversation_id": conversation["id"], "message": "apple"},
            )

        self.assertEqual(response.status_code, 200)
        retrieved_ids = {memory["message_id"] for memory in response.json["retrieved_memories"]}
        excluded_ids = set(response.json["retrieval"]["excluded_message_ids"])
        prompt_text = "\n".join(message["content"] for message in captured_prompts[0])

        self.assertTrue(retrieved_ids)
        self.assertTrue(retrieved_ids.isdisjoint(excluded_ids))
        self.assertTrue(response.json["prompt"]["used_recalled_memories"])
        self.assertIn("Older retrieved memories follow", prompt_text)
        self.assertIn("Recent rolling conversation follows", prompt_text)

    def test_tool_usage_executes_context_expansion_and_persists_final_response(self) -> None:
        from backend.app import create_app
        from backend.database import list_messages

        app = create_app()
        client = app.test_client()
        conversation, target = self._seed_context_messages()
        captured_calls: list[dict] = []

        def fake_chat_message(_chat_client, messages, tools=None, generation_params=None):
            captured_calls.append({"messages": messages, "tools": tools})
            if len(captured_calls) == 1:
                return self._tool_call_message("call_runtime_context", target["id"])

            return {"role": "assistant", "content": "expanded runtime response"}

        with patch("backend.app.LocalChatClient._create_chat_message", fake_chat_message):
            response = client.post(
                "/api/chat",
                json={"conversation_id": conversation["id"], "message": "expand runtime context"},
            )

        self.assertEqual(response.status_code, 200)
        tool_payload = json.loads(captured_calls[1]["messages"][-1]["content"])

        self.assertIsNotNone(captured_calls[0]["tools"])
        self.assertIsNone(captured_calls[1]["tools"])
        self.assertEqual(captured_calls[1]["messages"][-1]["role"], "tool")
        self.assertEqual(
            [message["content"] for message in tool_payload["messages"]],
            ["before target", "target memory", "after target"],
        )
        self.assertTrue(response.json["context_expansion"]["used"])
        self.assertEqual(response.json["assistant_message"]["content"], "expanded runtime response")
        self.assertEqual(list_messages(conversation["id"])[-1]["content"], "expanded runtime response")

    def test_streaming_plus_tool_usage_streams_followup_and_persists_final_response(self) -> None:
        from backend.app import create_app
        from backend.database import list_messages

        app = create_app()
        client = app.test_client()
        conversation, target = self._seed_context_messages()
        captured_calls: list[dict] = []

        def fake_stream_events(_chat_client, messages, tools=None, generation_params=None):
            captured_calls.append({"messages": messages, "tools": tools})
            if len(captured_calls) == 1:
                arguments = json.dumps({"message_id": target["id"]})
                yield {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_stream_runtime_context",
                                "type": "function",
                                "function": {
                                    "name": "get_context_around_message",
                                    "arguments": arguments,
                                },
                            }
                        ],
                    },
                }
                return

            yield {"type": "delta", "content": "stream tool "}
            yield {"type": "delta", "content": "response"}
            yield {"type": "message", "message": {"role": "assistant", "content": "stream tool response"}}

        with patch("backend.app.LocalChatClient._create_chat_message_stream_events", fake_stream_events):
            response = client.post(
                "/api/chat/stream",
                json={"conversation_id": conversation["id"], "message": "stream expand runtime context"},
                buffered=True,
            )

        self.assertEqual(response.status_code, 200)
        events = self._decode_stream_events(response)
        assistant_event = next(event for event in events if event["event"] == "assistant_message")

        self.assertEqual(len(captured_calls), 2)
        self.assertIsNotNone(captured_calls[0]["tools"])
        self.assertIsNone(captured_calls[1]["tools"])
        self.assertEqual(captured_calls[1]["messages"][-1]["role"], "tool")
        self.assertEqual(
            [event["data"]["content"] for event in events if event["event"] == "delta"],
            ["stream tool ", "response"],
        )
        self.assertTrue(assistant_event["data"]["context_expansion"]["used"])
        self.assertEqual(assistant_event["data"]["assistant_message"]["content"], "stream tool response")
        self.assertEqual(list_messages(conversation["id"])[-1]["content"], "stream tool response")

    def _seed_context_messages(self):
        from backend.database import create_conversation, create_embedding, create_message
        from backend.embeddings import StubEmbeddingProvider, serialize_vector

        provider = StubEmbeddingProvider()
        conversation = create_conversation("context regression")
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

        return conversation, target

    def _tool_call_message(self, tool_call_id: str, message_id: int) -> dict:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "get_context_around_message",
                        "arguments": json.dumps({"message_id": message_id}),
                    },
                }
            ],
        }

    def _decode_stream_events(self, response) -> list[dict]:
        return [json.loads(line) for line in response.data.decode("utf-8").splitlines() if line]


if __name__ == "__main__":
    unittest.main()
