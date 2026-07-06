from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class VoiceInputTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database_file.close()
        os.environ["DATABASE_PATH"] = self.database_file.name
        os.environ["EMBEDDING_PROVIDER"] = "stub"
        os.environ["USE_PLACEHOLDER_CHAT"] = "1"
        os.environ["WHISPER_EXECUTABLE_PATH"] = "/tmp/test-whisper-cli"
        os.environ["WHISPER_MODEL_PATH"] = "/tmp/test-whisper-model.bin"
        os.environ["WHISPER_FFMPEG_PATH"] = "/tmp/test-ffmpeg"

    def tearDown(self) -> None:
        for key in (
            "DATABASE_PATH",
            "EMBEDDING_PROVIDER",
            "USE_PLACEHOLDER_CHAT",
            "WHISPER_EXECUTABLE_PATH",
            "WHISPER_MODEL_PATH",
            "WHISPER_FFMPEG_PATH",
            "WHISPER_TIMEOUT_SECONDS",
            "WHISPER_LANGUAGE",
        ):
            os.environ.pop(key, None)

        try:
            os.unlink(self.database_file.name)
        except FileNotFoundError:
            pass

    def test_transcribe_endpoint_returns_transcript(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        def fake_transcribe_upload(_transcriber, audio_file, suffix=".webm"):
            self.assertEqual(suffix, ".webm")
            self.assertEqual(audio_file.read(), b"audio bytes")
            return "spoken draft"

        with patch("backend.app.WhisperCppTranscriber.transcribe_upload", fake_transcribe_upload):
            response = client.post(
                "/api/voice/transcribe",
                data={"audio": (io.BytesIO(b"audio bytes"), "voice.webm")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"transcript": "spoken draft"})

    def test_transcribe_endpoint_requires_audio_file(self) -> None:
        from backend.app import create_app

        app = create_app()
        client = app.test_client()

        response = client.post("/api/voice/transcribe", data={}, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "audio file is required")

    def test_parse_whisper_output_removes_timestamps(self) -> None:
        from backend.voice import parse_whisper_output

        transcript = parse_whisper_output(
            "[00:00:00.000 --> 00:00:01.000] Hello there\n"
            "[00:00:01.000 --> 00:00:02.000] continue please\n"
        )

        self.assertEqual(transcript, "Hello there continue please")

    def test_mobile_audio_suffixes_are_preserved(self) -> None:
        from backend.voice import normalize_audio_suffix

        self.assertEqual(normalize_audio_suffix("voice.mp4"), ".mp4")
        self.assertEqual(normalize_audio_suffix("voice.m4a"), ".m4a")
        self.assertEqual(normalize_audio_suffix("voice.aac"), ".aac")

    def test_whisper_runner_builds_cli_command_and_cleans_text(self) -> None:
        from backend.voice import WhisperConfig, WhisperCppTranscriber

        transcriber = WhisperCppTranscriber(
            WhisperConfig(
                executable_path=Path("/tmp/test-whisper-cli"),
                model_path=Path("/tmp/test-whisper-model.bin"),
                ffmpeg_path=Path("/tmp/test-ffmpeg"),
                timeout_seconds=3.0,
                language="auto",
            )
        )

        with (
            patch("backend.voice.Path.exists", return_value=True),
            patch("backend.voice.subprocess.run") as fake_run,
        ):
            fake_run.return_value.returncode = 0
            fake_run.return_value.stdout = "[00:00:00.000 --> 00:00:01.000] command transcript\n"
            fake_run.return_value.stderr = ""

            transcript = transcriber.transcribe_file(Path("/tmp/input.webm"))

        command = fake_run.call_args.args[0]
        self.assertEqual(transcript, "command transcript")
        self.assertEqual(command[:5], ["/tmp/test-whisper-cli", "-m", "/tmp/test-whisper-model.bin", "-f", "/tmp/input.webm"])
        self.assertIn("-np", command)
        self.assertIn("-nt", command)
        self.assertEqual(command[-2:], ["-l", "auto"])

    def test_browser_audio_is_converted_before_whisper(self) -> None:
        from backend.voice import WhisperConfig, WhisperCppTranscriber

        transcriber = WhisperCppTranscriber(
            WhisperConfig(
                executable_path=Path("/tmp/test-whisper-cli"),
                model_path=Path("/tmp/test-whisper-model.bin"),
                ffmpeg_path=Path("/tmp/test-ffmpeg"),
                timeout_seconds=3.0,
                language="en",
            )
        )

        with (
            patch("backend.voice.Path.exists", return_value=True),
            patch("backend.voice.subprocess.run") as fake_run,
        ):
            fake_run.return_value.returncode = 0
            fake_run.return_value.stdout = "converted transcript"
            fake_run.return_value.stderr = ""

            transcript = transcriber.transcribe_upload(io.BytesIO(b"browser audio"), suffix=".webm")

        ffmpeg_command = fake_run.call_args_list[0].args[0]
        whisper_command = fake_run.call_args_list[1].args[0]
        self.assertEqual(transcript, "converted transcript")
        self.assertEqual(ffmpeg_command[0], "/tmp/test-ffmpeg")
        self.assertEqual(ffmpeg_command[-1].split("/")[-1], "voice.wav")
        self.assertIn("/voice.wav", whisper_command[4])


if __name__ == "__main__":
    unittest.main()
