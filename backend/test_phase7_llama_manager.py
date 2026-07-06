from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch


class LlamaServerManagementTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        self.models_dir = tempfile.TemporaryDirectory()
        self.server_file = tempfile.NamedTemporaryFile(delete=False)
        self.server_file.close()
        self.chat_model = Path(self.models_dir.name) / "chat-model.Q4_K_M.gguf"
        self.embedding_model = Path(self.models_dir.name) / "nomic-embed.Q8_0.gguf"
        self.chat_model.write_bytes(b"chat")
        self.embedding_model.write_bytes(b"embed")

        os.environ["DATABASE_PATH"] = self.database_file.name
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "1"
        os.environ["LLAMA_SERVER_PATH"] = self.server_file.name
        os.environ["LLAMA_MODELS_DIR"] = self.models_dir.name
        os.environ["LLAMA_DEFAULT_MODEL_PATH"] = str(self.chat_model)
        os.environ["EMBEDDING_MODEL_PATH"] = str(self.embedding_model)
        os.environ["MODEL_NAME"] = "managed-local"
        os.environ["LLAMA_CONTEXT_SIZE"] = "4096"
        os.environ["LLAMA_BATCH_SIZE"] = "512"
        os.environ["LLAMA_GPU_LAYERS"] = "4"
        os.environ["LLAMA_THREADS"] = "8"
        os.environ["MODEL_TEMPERATURE"] = "0.65"
        os.environ["MODEL_REPEAT_PENALTY"] = "1.05"

    def tearDown(self) -> None:
        for key in (
            "DATABASE_PATH",
            "EMBEDDING_PROVIDER",
            "USE_PLACEHOLDER_CHAT",
            "LLAMA_SERVER_PATH",
            "LLAMA_MODELS_DIR",
            "LLAMA_DEFAULT_MODEL_PATH",
            "EMBEDDING_MODEL_PATH",
            "MODEL_NAME",
            "LLAMA_CONTEXT_SIZE",
            "LLAMA_BATCH_SIZE",
            "LLAMA_GPU_LAYERS",
            "LLAMA_THREADS",
            "MODEL_TEMPERATURE",
            "MODEL_REPEAT_PENALTY",
        ):
            os.environ.pop(key, None)

        self.models_dir.cleanup()
        for path in (self.database_file.name, self.server_file.name):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def test_models_endpoint_lists_ggufs_and_defaults(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        with patch("backend.llama_manager.is_endpoint_reachable", return_value=False):
            response = client.get("/api/llama/models")

        self.assertEqual(response.status_code, 200)
        model_names = {model["name"] for model in response.json["models"]}
        self.assertEqual(model_names, {"chat-model.Q4_K_M.gguf", "nomic-embed.Q8_0.gguf"})
        self.assertEqual(response.json["defaults"]["model_path"], str(self.chat_model))
        self.assertEqual(response.json["defaults"]["embedding_model_path"], str(self.embedding_model))
        self.assertEqual(response.json["defaults"]["context_size"], 4096)

    def test_start_endpoint_launches_llama_server_command(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()
        process = Mock()
        process.pid = 12345
        process.poll.return_value = None

        with (
            patch("backend.llama_manager.subprocess.Popen", return_value=process) as fake_popen,
            patch("backend.llama_manager.is_endpoint_reachable", return_value=True),
        ):
            response = client.post(
                "/api/llama/start",
                json={
                    "model_path": str(self.chat_model),
                    "embedding_model_path": str(self.embedding_model),
                    "host": "127.0.0.1",
                    "port": 8088,
                    "context_size": 8192,
                    "batch_size": 1024,
                    "gpu_layers": 12,
                    "threads": 16,
                    "temperature": 0.7,
                    "repeat_penalty": 1.1,
                    "model_name": "phase7-test",
                },
            )

        self.assertEqual(response.status_code, 200)
        command = fake_popen.call_args.args[0]
        self.assertEqual(command[0], self.server_file.name)
        self.assertIn(str(self.chat_model), command)
        self.assertIn("--ctx-size", command)
        self.assertIn("8192", command)
        self.assertIn("--gpu-layers", command)
        self.assertIn("12", command)
        self.assertEqual(response.json["process_state"], "running")
        self.assertEqual(response.json["pid"], 12345)
        self.assertTrue(response.json["endpoint_reachable"])

    def test_stop_endpoint_terminates_managed_process(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()
        process = Mock()
        process.pid = 12345
        process.poll.return_value = None

        with (
            patch("backend.llama_manager.subprocess.Popen", return_value=process),
            patch("backend.llama_manager.is_endpoint_reachable", return_value=False),
        ):
            start_response = client.post("/api/llama/start", json={"model_path": str(self.chat_model)})
            stop_response = client.post("/api/llama/stop")

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(stop_response.status_code, 200)
        process.terminate.assert_called_once()
        process.wait.assert_called()
        self.assertEqual(stop_response.json["process_state"], "stopped")


if __name__ == "__main__":
    unittest.main()
