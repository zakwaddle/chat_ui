from __future__ import annotations

import os
import tempfile
import unittest


class MemoryRetrievalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        os.environ["DATABASE_PATH"] = self.database_file.name
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "1"

    def tearDown(self) -> None:
        for key in (
            "DATABASE_PATH",
            "EMBEDDING_PROVIDER",
            "USE_PLACEHOLDER_CHAT",
            "ROLLING_MESSAGE_COUNT",
            "RETRIEVED_MEMORY_COUNT",
            "RETRIEVAL_SIMILARITY_THRESHOLD",
        ):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_retrieval_ranks_older_embedded_messages(self) -> None:
        from backend.database import create_conversation, create_embedding, create_message, init_db
        from backend.embeddings import serialize_vector
        from backend.retrieval import retrieve_relevant_memories

        init_db()
        conversation = create_conversation("retrieval ranking")
        weak = create_message(conversation["id"], "user", "weak memory")
        strong = create_message(conversation["id"], "assistant", "strong memory")
        excluded = create_message(conversation["id"], "user", "active window memory")

        create_embedding(weak["id"], "test", "manual", serialize_vector([0.0, 1.0, 0.0]))
        create_embedding(strong["id"], "test", "manual", serialize_vector([1.0, 0.0, 0.0]))
        create_embedding(excluded["id"], "test", "manual", serialize_vector([1.0, 0.0, 0.0]))

        memories = retrieve_relevant_memories(
            conversation_id=conversation["id"],
            query_vector=[1.0, 0.0, 0.0],
            exclude_message_ids={excluded["id"]},
            limit=2,
            similarity_threshold=0.5,
        )

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["message_id"], strong["id"])
        self.assertEqual(memories[0]["role"], "assistant")
        self.assertEqual(memories[0]["content"], "strong memory")
        self.assertEqual(memories[0]["similarity"], 1.0)

    def test_chat_retrieval_excludes_messages_in_rolling_window(self) -> None:
        os.environ["ROLLING_MESSAGE_COUNT"] = "2"
        os.environ["RETRIEVED_MEMORY_COUNT"] = "10"

        from backend.app import create_app
        from backend.database import create_conversation, create_embedding, create_message
        from backend.embeddings import StubEmbeddingProvider, serialize_vector

        app = create_app()
        client = app.test_client()
        provider = StubEmbeddingProvider()
        conversation = create_conversation("chat retrieval")

        for content in ("older apple memory", "recent banana memory", "recent cherry memory"):
            message = create_message(conversation["id"], "user", content)
            vector = provider.embed(content).vector
            create_embedding(message["id"], "stub", "deterministic-hash-v1", serialize_vector(vector))

        response = client.post(
            "/api/chat",
            json={"conversation_id": conversation["id"], "message": "apple"},
        )

        self.assertEqual(response.status_code, 200)
        excluded_ids = set(response.json["retrieval"]["excluded_message_ids"])
        retrieved_ids = {memory["message_id"] for memory in response.json["retrieved_memories"]}

        self.assertEqual(response.json["context_window"]["recent_message_count"], 2)
        self.assertTrue(retrieved_ids)
        self.assertTrue(retrieved_ids.isdisjoint(excluded_ids))

        for memory in response.json["retrieved_memories"]:
            self.assertIn("message_id", memory)
            self.assertIn("role", memory)
            self.assertIn("content", memory)
            self.assertIn("created_at", memory)
            self.assertIsInstance(memory["similarity"], float)


if __name__ == "__main__":
    unittest.main()
