from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch


class RollingContextWindowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        os.environ["DATABASE_PATH"] = self.database_file.name
        os.environ["ROLLING_MESSAGE_COUNT"] = "3"
        os.environ["USE_PLACEHOLDER_CHAT"] = "1"
        os.environ["EMBEDDING_PROVIDER"] = "stub"

    def tearDown(self) -> None:
        for key in ("DATABASE_PATH", "ROLLING_MESSAGE_COUNT", "USE_PLACEHOLDER_CHAT", "EMBEDDING_PROVIDER"):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_chat_sends_only_recent_messages_to_model(self) -> None:
        from backend.app import create_app
        from backend.database import create_conversation, create_message

        app = create_app()
        client = app.test_client()
        conversation = create_conversation("bounded context test")

        for index in range(1, 6):
            create_message(conversation["id"], "user", f"older message {index}")

        sent_context: list[list[dict[str, str]]] = []

        def capture_context(_chat_client, messages: list[dict[str, str]]) -> str:
            sent_context.append(messages)
            return "bounded reply"

        with patch("backend.app.LocalChatClient.complete", capture_context):
            response = client.post(
                "/api/chat",
                json={"conversation_id": conversation["id"], "message": "current message"},
            )

        self.assertEqual(response.status_code, 200)
        recent_turns = [message for message in sent_context[0] if message["role"] != "system"]
        self.assertEqual(
            [message["content"].split("] ", 1)[1] for message in recent_turns],
            ["older message 4", "older message 5", "current message"],
        )
        self.assertEqual(response.json["context_window"]["configured_message_count"], 3)
        self.assertEqual(response.json["context_window"]["recent_message_count"], 3)

    def test_chat_defaults_to_twelve_recent_messages(self) -> None:
        os.environ.pop("ROLLING_MESSAGE_COUNT", None)

        from backend.app import create_app
        from backend.database import create_conversation, create_message

        app = create_app()
        client = app.test_client()
        conversation = create_conversation("default bounded context test")

        for index in range(1, 16):
            create_message(conversation["id"], "user", f"older message {index}")

        sent_context: list[list[dict[str, str]]] = []

        def capture_context(_chat_client, messages: list[dict[str, str]]) -> str:
            sent_context.append(messages)
            return "default bounded reply"

        with patch("backend.app.LocalChatClient.complete", capture_context):
            response = client.post(
                "/api/chat",
                json={"conversation_id": conversation["id"], "message": "current message"},
            )

        self.assertEqual(response.status_code, 200)
        recent_turns = [message for message in sent_context[0] if message["role"] != "system"]
        self.assertEqual(len(recent_turns), 12)
        self.assertIn("older message 5", recent_turns[0]["content"])
        self.assertIn("current message", recent_turns[-1]["content"])
        self.assertEqual(response.json["context_window"]["configured_message_count"], 12)


if __name__ == "__main__":
    unittest.main()
