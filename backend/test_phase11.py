from __future__ import annotations

import os
import tempfile
import unittest


class ConversationManagementTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        os.environ["DATABASE_PATH"] = self.database_file.name
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "1"

    def tearDown(self) -> None:
        for key in ("DATABASE_PATH", "EMBEDDING_PROVIDER", "USE_PLACEHOLDER_CHAT"):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_conversations_can_be_created_listed_and_loaded(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        first = client.post("/api/conversations", json={"title": "First thread"})
        second = client.post("/api/conversations", json={"title": "Second thread"})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        first_id = first.json["conversation"]["id"]
        second_id = second.json["conversation"]["id"]

        message = client.post(
            f"/api/conversations/{first_id}/messages",
            json={"role": "user", "content": "message in first thread"},
        )
        self.assertEqual(message.status_code, 201)

        conversations = client.get("/api/conversations")
        self.assertEqual(conversations.status_code, 200)
        self.assertEqual(len(conversations.json["conversations"]), 2)

        counts = {
            conversation["id"]: conversation["message_count"]
            for conversation in conversations.json["conversations"]
        }
        self.assertEqual(counts[first_id], 1)
        self.assertEqual(counts[second_id], 0)

        first_messages = client.get(f"/api/conversations/{first_id}/messages")
        second_messages = client.get(f"/api/conversations/{second_id}/messages")

        self.assertEqual(first_messages.status_code, 200)
        self.assertEqual(second_messages.status_code, 200)
        self.assertEqual(first_messages.json["messages"][0]["content"], "message in first thread")
        self.assertEqual(second_messages.json["messages"], [])


if __name__ == "__main__":
    unittest.main()
