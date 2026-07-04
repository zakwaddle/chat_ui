from __future__ import annotations

import os
import tempfile
import unittest


class ContextExpansionToolTest(unittest.TestCase):
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
            "DEFAULT_CONTEXT_BEFORE",
            "DEFAULT_CONTEXT_AFTER",
        ):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_get_context_around_message_returns_surrounding_scene(self) -> None:
        from backend.database import create_conversation, create_message, init_db
        from backend.tools import get_context_around_message

        init_db()
        conversation = create_conversation("scene")
        messages = [
            create_message(conversation["id"], "user", f"message {index}")
            for index in range(1, 7)
        ]

        context = get_context_around_message(messages[3]["id"], before=2, after=1)

        self.assertIsNotNone(context)
        self.assertEqual(context["target_message_id"], messages[3]["id"])
        self.assertEqual(context["conversation_id"], conversation["id"])
        self.assertEqual(
            [message["content"] for message in context["messages"]],
            ["message 2", "message 3", "message 4", "message 5"],
        )
        self.assertEqual(
            set(context["messages"][0].keys()),
            {"message_id", "role", "content", "created_at"},
        )

    def test_context_expansion_stays_inside_target_conversation(self) -> None:
        from backend.database import create_conversation, create_message, init_db
        from backend.tools import get_context_around_message

        init_db()
        first = create_conversation("first")
        second = create_conversation("second")
        create_message(first["id"], "user", "first conversation before")
        target = create_message(second["id"], "user", "second conversation target")
        create_message(first["id"], "assistant", "first conversation after")

        context = get_context_around_message(target["id"], before=3, after=3)

        self.assertIsNotNone(context)
        self.assertEqual([message["content"] for message in context["messages"]], ["second conversation target"])

    def test_context_route_uses_configurable_defaults(self) -> None:
        os.environ["DEFAULT_CONTEXT_BEFORE"] = "1"
        os.environ["DEFAULT_CONTEXT_AFTER"] = "2"

        from backend.app import create_app
        from backend.database import create_conversation, create_message

        app = create_app()
        client = app.test_client()
        conversation = create_conversation("route defaults")
        messages = [
            create_message(conversation["id"], "user", f"route message {index}")
            for index in range(1, 6)
        ]

        response = client.get(f"/api/tools/context-around-message/{messages[2]['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["context"]["before"], 1)
        self.assertEqual(response.json["context"]["after"], 2)
        self.assertEqual(
            [message["content"] for message in response.json["context"]["messages"]],
            ["route message 2", "route message 3", "route message 4", "route message 5"],
        )

    def test_context_route_returns_404_for_missing_message(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        response = client.get("/api/tools/context-around-message/999")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
