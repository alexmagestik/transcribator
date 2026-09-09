from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent


def _env_path(name: str, default: str) -> Path:
    value = os.getenv(name, default)
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_optional_float(name: str, default: float | None) -> float | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    if not value or value.lower() == "none":
        return None
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    source_dir: Path
    raw_dir: Path
    clean_dir: Path
    summary_dir: Path
    notes_dir: Path
    prompts_file: Path
    status_file: Path

    ollama_host: str
    ollama_model: str
    ollama_clean_model: str
    ollama_summary_model: str
    ollama_notes_model: str
    ollama_chunk_chars: int
    ollama_temperature_clean: float
    ollama_temperature_summary: float
    ollama_temperature_notes: float

    whisper_model: str
    whisper_model_path: Path | None
    whisper_device: str
    whisper_compute_type: str
    whisper_beam_size: int
    whisper_language: str
    whisper_no_speech_threshold: float | None
    whisper_vad_filter: bool
    whisper_condition_on_previous_text: bool


@dataclass(frozen=True)
class Prompts:
    hotwords: str | None
    clear: str
    clear_user: str
    summary: str
    notes: str


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or BASE_DIR / ".env")
    return Settings(
        source_dir=_env_path("SOURCE_DIR", "source-mp3"),
        raw_dir=_env_path("RAW_DIR", "raw"),
        clean_dir=_env_path("CLEAN_DIR", "clean"),
        summary_dir=_env_path("SUMMARY_DIR", "summary"),
        notes_dir=_env_path("NOTES_DIR", "notes"),
        prompts_file=_env_path("PROMPTS_FILE", "prompts.toml"),
        status_file=_env_path("STATUS_FILE", ".transcribe-status.json"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:4b-summary-32k"),
        ollama_clean_model=os.getenv(
            "OLLAMA_CLEAN_MODEL",
            os.getenv("OLLAMA_MODEL", "llama3.1-clean-32k:latest"),
        ),
        ollama_summary_model=os.getenv(
            "OLLAMA_SUMMARY_MODEL",
            os.getenv("OLLAMA_MODEL", "gemma4:e2b-32k"),
        ),
        ollama_notes_model=os.getenv(
            "OLLAMA_NOTES_MODEL",
            os.getenv("OLLAMA_MODEL", "gemma4:e2b-32k"),
        ),
        ollama_chunk_chars=_env_int("OLLAMA_CHUNK_CHARS", 24_000),
        ollama_temperature_clean=_env_float("OLLAMA_TEMPERATURE_CLEAN", 0.1),
        ollama_temperature_summary=_env_float("OLLAMA_TEMPERATURE_SUMMARY", 0.4),
        ollama_temperature_notes=_env_float("OLLAMA_TEMPERATURE_NOTES", 0.4),
        whisper_model=os.getenv("WHISPER_MODEL", "large-v3"),
        whisper_model_path=_env_path("WHISPER_MODEL_PATH", "none") if os.getenv("WHISPER_MODEL_PATH") else None,
        whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        whisper_beam_size=_env_int("WHISPER_BEAM_SIZE", 9),
        whisper_language=os.getenv("WHISPER_LANGUAGE", "ru"),
        whisper_no_speech_threshold=_env_optional_float("WHISPER_NO_SPEECH_THRESHOLD", None),
        whisper_vad_filter=_env_bool("WHISPER_VAD_FILTER", False),
        whisper_condition_on_previous_text=_env_bool("WHISPER_CONDITION_ON_PREVIOUS_TEXT", True),
    )


def load_prompts(path: Path) -> Prompts:
    with path.open("rb") as file:
        data = tomllib.load(file)

    hotwords = None
    if "hotwords" in data:
        hotwords_text = data["hotwords"]["text"].strip()
        hotwords = hotwords_text or None
    elif "initial" in data:
        # initial_prompt устарел — ломает тайминги Whisper
        hotwords = None

    return Prompts(
        hotwords=hotwords,
        clear=data["clear"]["text"].strip(),
        clear_user=data["clear_user"]["text"].strip(),
        summary=data["summary"]["text"].strip(),
        notes=data["notes"]["text"].strip(),
    )
