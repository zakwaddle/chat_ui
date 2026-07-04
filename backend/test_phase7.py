from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch


class PromptAssemblyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        os.environ["DATABASE_PATH"] = self.database_file.name
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "1"
        os.environ["ROLLING_MESSAGE_COUNT"] = "2"
        os.environ["RETRIEVED_MEMORY_COUNT"] = "6"

    def tearDown(self) -> None:
        for key in (
            "DATABASE_PATH",
            "EMBEDDING_PROVIDER",
            "USE_PLACEHOLDER_CHAT",
            "ROLLING_MESSAGE_COUNT",
            "RETRIEVED_MEMORY_COUNT",
            "RETRIEVAL_SIMILARITY_THRESHOLD",
            "SYSTEM_PROMPT",
        ):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_assemble_prompt_labels_recalled_memory_and_keeps_recent_chronological(self) -> None:
        from backend.prompt import assemble_prompt

        prompt = assemble_prompt(
            system_prompt="Runtime instructions",
            recalled_memories=[
                {
                    "message_id": 10,
                    "role": "user",
                    "content": "older recalled fact",
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "similarity": 0.91,
                }
            ],
            recent_messages=[
                {"id": 20, "role": "assistant", "content": "recent answer"},
                {"id": 21, "role": "user", "content": "current question"},
            ],
            current_user_message_id=21,
        )

        self.assertEqual(prompt[0], {"role": "system", "content": "Runtime instructions"})
        self.assertEqual(prompt[1]["role"], "system")
        self.assertIn("Older retrieved memories follow", prompt[1]["content"])
        self.assertIn("message_id=10", prompt[1]["content"])
        self.assertIn("older recalled fact", prompt[1]["content"])
        self.assertEqual(prompt[3]["role"], "assistant")
        self.assertIn("[message_id=20] recent answer", prompt[3]["content"])
        self.assertEqual(prompt[4]["role"], "user")
        self.assertIn("[message_id=21] current question", prompt[4]["content"])

    def test_chat_sends_bounded_prompt_with_recalled_context_to_model(self) -> None:
        from backend.app import create_app
        from backend.database import create_conversation, create_embedding, create_message
        from backend.embeddings import StubEmbeddingProvider, serialize_vector

        app = create_app()
        client = app.test_client()
        provider = StubEmbeddingProvider()
        conversation = create_conversation("prompt assembly")

        for content in ("older memory about apples", "recent assistant turn", "recent user turn"):
            role = "assistant" if "assistant" in content else "user"
            message = create_message(conversation["id"], role, content)
            create_embedding(
                message["id"],
                "stub",
                "deterministic-hash-v1",
                serialize_vector(provider.embed(content).vector),
            )

        captured_prompts: list[list[dict[str, str]]] = []

        def capture_prompt(_chat_client, messages: list[dict[str, str]]) -> str:
            captured_prompts.append(messages)
            return "assembled prompt reply"

        with patch("backend.app.LocalChatClient.complete", capture_prompt):
            response = client.post(
                "/api/chat",
                json={"conversation_id": conversation["id"], "message": "ask about apples"},
            )

        self.assertEqual(response.status_code, 200)
        prompt = captured_prompts[0]
        prompt_text = "\n".join(message["content"] for message in prompt)

        self.assertEqual(prompt[0]["role"], "system")
        self.assertIn("Older retrieved memories follow", prompt_text)
        self.assertIn("older_retrieved_memory message_id=", prompt_text)
        self.assertIn("Recent rolling conversation follows", prompt_text)
        self.assertNotIn("older memory about apples", prompt[-2]["content"])
        self.assertEqual(prompt[-2]["role"], "user")
        self.assertIn("recent user turn", prompt[-2]["content"])
        self.assertEqual(prompt[-1]["role"], "user")
        self.assertIn("ask about apples", prompt[-1]["content"])
        self.assertTrue(response.json["prompt"]["used_recalled_memories"])


if __name__ == "__main__":
    unittest.main()
