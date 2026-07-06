from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


@dataclass(frozen=True)
class WhisperConfig:
    executable_path: Path
    model_path: Path
    ffmpeg_path: Path
    timeout_seconds: float
    language: str


class VoiceTranscriptionError(RuntimeError):
    pass


class WhisperCppTranscriber:
    def __init__(self, config: WhisperConfig) -> None:
        self.config = config

    def transcribe_upload(self, audio_file: BinaryIO, suffix: str = ".webm") -> str:
        suffix = normalize_audio_suffix(suffix)
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / f"voice{suffix}"
            audio_file.seek(0)
            audio_path.write_bytes(audio_file.read())
            whisper_audio_path = self._prepare_audio_for_whisper(audio_path)
            return self.transcribe_file(whisper_audio_path)

    def transcribe_file(self, audio_path: Path) -> str:
        if not self.config.executable_path.exists():
            raise VoiceTranscriptionError(f"Whisper executable not found: {self.config.executable_path}")
        if not self.config.model_path.exists():
            raise VoiceTranscriptionError(f"Whisper model not found: {self.config.model_path}")

        command = [
            str(self.config.executable_path),
            "-m",
            str(self.config.model_path),
            "-f",
            str(audio_path),
            "-np",
            "-nt",
        ]
        if self.config.language:
            command.extend(["-l", self.config.language])

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise VoiceTranscriptionError("Whisper transcription timed out") from error
        except OSError as error:
            raise VoiceTranscriptionError(f"Unable to run Whisper: {error}") from error

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            raise VoiceTranscriptionError(f"Whisper failed with exit code {result.returncode}: {detail}")

        transcript = parse_whisper_output(result.stdout)
        if not transcript:
            raise VoiceTranscriptionError("Whisper returned an empty transcript")

        return transcript

    def _prepare_audio_for_whisper(self, audio_path: Path) -> Path:
        if audio_path.suffix.lower() in WHISPER_SUPPORTED_AUDIO_SUFFIXES:
            return audio_path

        if not self.config.ffmpeg_path.exists():
            raise VoiceTranscriptionError(f"ffmpeg executable not found: {self.config.ffmpeg_path}")

        wav_path = audio_path.with_suffix(".wav")
        command = [
            str(self.config.ffmpeg_path),
            "-y",
            "-i",
            str(audio_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_path),
        ]

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise VoiceTranscriptionError("Audio conversion timed out") from error
        except OSError as error:
            raise VoiceTranscriptionError(f"Unable to run ffmpeg: {error}") from error

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            raise VoiceTranscriptionError(f"Audio conversion failed with exit code {result.returncode}: {detail}")

        return wav_path


def normalize_audio_suffix(filename_or_suffix: str) -> str:
    suffix = Path(filename_or_suffix or "").suffix.lower()
    if not suffix and filename_or_suffix.startswith("."):
        suffix = filename_or_suffix.lower()
    if suffix in {".aac", ".flac", ".mp3", ".ogg", ".wav", ".webm", ".m4a", ".mp4"}:
        return suffix

    return ".webm"


WHISPER_SUPPORTED_AUDIO_SUFFIXES = {".flac", ".mp3", ".ogg", ".wav"}


def parse_whisper_output(output: str) -> str:
    lines = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
        if line:
            lines.append(line)

    return " ".join(lines).strip()
