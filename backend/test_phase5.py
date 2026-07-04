from __future__ import annotations

import json
import os
import tempfile
import unittest


class EmbeddingPipelineTest(unittest.TestCase):
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

    def test_message_route_creates_embedding_and_links_message(self) -> None:
        from backend.app import create_app
        from backend.database import create_conversation, list_embeddings

        app = create_app()
        client = app.test_client()
        conversation = create_conversation("embedding test")

        response = client.post(
            f"/api/conversations/{conversation['id']}/messages",
            json={"role": "user", "content": "remember this"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.json["message"]["embedding_id"])
        self.assertEqual(response.json["embedding"]["message_id"], response.json["message"]["id"])
        self.assertEqual(response.json["embedding"]["provider"], "stub")

        embeddings = list_embeddings()
        self.assertEqual(len(embeddings), 1)
        self.assertEqual(len(json.loads(embeddings[0]["vector"])), 32)

    def test_chat_route_embeds_user_and_assistant_messages(self) -> None:
        from backend.app import create_app
        from backend.database import list_embeddings

        app = create_app()
        client = app.test_client()

        response = client.post("/api/chat", json={"message": "embed both sides"})

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json["user_message"]["embedding_id"])
        self.assertIsNotNone(response.json["assistant_message"]["embedding_id"])
        self.assertEqual(response.json["embeddings"]["user"]["provider"], "stub")
        self.assertEqual(response.json["embeddings"]["assistant"]["provider"], "stub")
        self.assertEqual(len(list_embeddings()), 2)


if __name__ == "__main__":
    unittest.main()
