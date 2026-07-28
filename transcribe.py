#!/usr/bin/env python3
"""
Пайплайн транскрибации:

  source-mp3/*.mp3  →  raw/*.txt  →  clean/*.txt  →  summary/*.md
       Whisper           Qwen clean        Qwen summary

Запуск:
  .venv/bin/python transcribe.py pipeline source-mp3/
  .venv/bin/python transcribe.py pipeline source-mp3/lesson.mp3
  .venv/bin/python transcribe.py whisper source-mp3/lesson.mp3
  .venv/bin/python transcribe.py clean raw/lesson.txt
  .venv/bin/python transcribe.py summary clean/lesson.txt
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

from config import Prompts, Settings, load_prompts, load_settings
from status import build_status_report, print_status_report, set_current_file, set_step, track_job

log = logging.getLogger("transcribe")


def filter_paths(files: list[Path], match: str | None) -> list[Path]:
    if not match:
        return files

    filtered: list[Path] = []
    for file_path in files:
        relative = str(file_path)
        if (
            match.lower() in relative.lower()
            or fnmatch.fnmatch(file_path.name, match)
            or fnmatch.fnmatch(relative, match)
        ):
            filtered.append(file_path)

    if not filtered:
        raise ValueError(f"Нет файлов по фильтру --match {match!r}")
    return filtered


def resolve_source_root(path: Path, settings: Settings) -> Path:
    path = path.resolve()
    source_root = settings.source_dir.resolve()
    if path == source_root or source_root in path.parents:
        return source_root
    raise ValueError(f"Путь должен находиться внутри {settings.source_dir}: {path}")


def collect_mp3_files(path: Path) -> list[Path]:
    path = path.resolve()
    if path.is_file():
        if path.suffix.lower() != ".mp3":
            raise ValueError(f"Ожидается MP3-файл: {path}")
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"Путь не найден: {path}")

    files = sorted(path.rglob("*.mp3"))
    if not files:
        raise ValueError(f"MP3-файлы не найдены в {path}")
    return files


def collect_txt_files(path: Path, suffix: str) -> list[Path]:
    path = path.resolve()
    if path.is_file():
        if path.suffix.lower() != suffix:
            raise ValueError(f"Ожидается файл *{suffix}: {path}")
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"Путь не найден: {path}")

    files = sorted(path.rglob(f"*{suffix}"))
    if not files:
        raise ValueError(f"Файлы *{suffix} не найдены в {path}")
    return files


def output_path_for_mp3(mp3_path: Path, output_root: Path, extension: str, settings: Settings) -> Path:
    source_root = resolve_source_root(mp3_path, settings)
    rel = mp3_path.resolve().relative_to(source_root)
    return output_root / rel.with_suffix(extension)


def output_path_for_txt(txt_path: Path, output_root: Path, extension: str, settings: Settings) -> Path:
    txt_path = txt_path.resolve()
    for input_root, out_root in (
        (settings.raw_dir.resolve(), output_root),
        (settings.clean_dir.resolve(), output_root),
        (settings.source_dir.resolve(), output_root),
    ):
        if txt_path == input_root or input_root in txt_path.parents:
            rel = txt_path.relative_to(input_root)
            return out_root / rel.with_suffix(extension)
    raise ValueError(
        f"Не удалось определить выходной путь для {txt_path}. "
        f"Файл должен быть внутри {settings.raw_dir}, {settings.clean_dir} "
        f"или {settings.source_dir}."
    )


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_parent(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def split_text_chunks(text: str, chunk_size: int) -> list[str]:
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if paragraph_len > chunk_size:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            for i in range(0, paragraph_len, chunk_size):
                chunks.append(paragraph[i : i + chunk_size])
            continue

        extra = paragraph_len + (2 if current else 0)
        if current_len + extra > chunk_size:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_len = paragraph_len
        else:
            current.append(paragraph)
            current_len += extra

    if current:
        chunks.append("\n\n".join(current))
    return chunks


class WhisperTranscriber:
    def __init__(self, settings: Settings, prompts: Prompts) -> None:
        self._model = None
        self.settings = settings
        self.prompts = prompts

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            log.info(
                "Загрузка Whisper %s (%s, %s)...",
                self.settings.whisper_model,
                self.settings.whisper_device,
                self.settings.whisper_compute_type,
            )
            self._model = WhisperModel(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
            )
        return self._model

    def transcribe(self, mp3_path: Path) -> str:
        model = self._load()
        log.info("Транскрибация: %s", mp3_path)

        transcribe_kwargs: dict = {
            "language": self.settings.whisper_language,
            "beam_size": self.settings.whisper_beam_size,
            "no_speech_threshold": self.settings.whisper_no_speech_threshold,
            "vad_filter": self.settings.whisper_vad_filter,
            "condition_on_previous_text": self.settings.whisper_condition_on_previous_text,
            "log_progress": log.isEnabledFor(logging.DEBUG),
        }
        if self.prompts.hotwords:
            transcribe_kwargs["hotwords"] = self.prompts.hotwords
            log.info("Whisper hotwords: %d символов", len(self.prompts.hotwords))

        segments, info = model.transcribe(str(mp3_path), **transcribe_kwargs)
        log.info("Язык: %s, длительность: %.1f с", info.language, info.duration)

        segment_list = list(segments)
        if segment_list and segment_list[0].start > 1.0:
            log.warning(
                "Первый сегмент начинается с %.1f с — возможно, пропущено начало записи. "
                "Проверьте WHISPER_NO_SPEECH_THRESHOLD (рекомендуется none) и WHISPER_VAD_FILTER=false",
                segment_list[0].start,
            )

        return "\n".join(
            segment.text.strip() for segment in segment_list if segment.text.strip()
        )


def format_user_prompt(template: str, text: str) -> str:
    return template.replace("{{TEXT}}", text)


class OllamaClient:
    def __init__(self, settings: Settings, model: str | None = None) -> None:
        self.settings = settings
        self.host = settings.ollama_host.rstrip("/")
        # Если модель не передана — fallback на основную OLLAMA_MODEL (обратная совместимость)
        self.model = model or settings.ollama_model

    def chat(self, system_prompt: str, user_content: str, *, temperature: float) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": temperature},
        }
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=3600) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Не удалось обратиться к Ollama ({self.host}). "
                f"Убедитесь, что Ollama запущена и модель {self.model} доступна."
            ) from exc

        message = body.get("message", {})
        content = message.get("content", "").strip()
        if not content:
            raise RuntimeError(f"Пустой ответ Ollama для модели {self.model}")
        return content

    def process_long_text(
        self,
        system_prompt: str,
        text: str,
        task_name: str,
        *,
        temperature: float,
        user_template: str | None = None,
    ) -> str:
        chunks = split_text_chunks(text, self.settings.ollama_chunk_chars)

        def user_content(chunk: str) -> str:
            if user_template is not None:
                return format_user_prompt(user_template, chunk)
            return chunk

        if len(chunks) == 1:
            return self.chat(system_prompt, user_content(chunks[0]), temperature=temperature)

        log.info("%s: текст разбит на %d частей", task_name, len(chunks))
        results: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            log.info("%s: часть %d/%d", task_name, index, len(chunks))
            results.append(self.chat(system_prompt, user_content(chunk), temperature=temperature))
        return "\n\n".join(results)


def should_skip(output_path: Path, force: bool) -> bool:
    return output_path.exists() and not force


def run_whisper(
    paths: Iterable[Path],
    *,
    force: bool,
    settings: Settings,
    prompts: Prompts,
) -> list[Path]:
    transcriber = WhisperTranscriber(settings, prompts)
    written: list[Path] = []

    for mp3_path in paths:
        output_path = output_path_for_mp3(mp3_path, settings.raw_dir, ".txt", settings)
        if should_skip(output_path, force):
            log.info("Пропуск (уже есть): %s", output_path)
            continue

        set_step("whisper")
        set_current_file(mp3_path)
        text = transcriber.transcribe(mp3_path)
        write_text(output_path, text)
        log.info("Сохранено: %s", output_path)
        written.append(output_path)

    return written


def run_clean(
    paths: Iterable[Path],
    *,
    force: bool,
    ollama: OllamaClient,
    prompts: Prompts,
    settings: Settings,
) -> list[Path]:
    written: list[Path] = []

    for txt_path in paths:
        output_path = output_path_for_txt(txt_path, settings.clean_dir, ".txt", settings)
        if should_skip(output_path, force):
            log.info("Пропуск (уже есть): %s", output_path)
            continue

        set_step("clean")
        set_current_file(txt_path)
        text = read_text(txt_path)
        log.info("Clean-модель: %s", ollama.model)
        cleaned = ollama.process_long_text(
            prompts.clear,
            text,
            "Очистка",
            temperature=settings.ollama_temperature_clean,
            user_template=prompts.clear_user,
        )
        write_text(output_path, cleaned)
        log.info("Сохранено: %s", output_path)
        written.append(output_path)

    return written


def run_summary(
    paths: Iterable[Path],
    *,
    force: bool,
    ollama: OllamaClient,
    prompts: Prompts,
    settings: Settings,
) -> list[Path]:
    written: list[Path] = []

    for txt_path in paths:
        output_path = output_path_for_txt(txt_path, settings.summary_dir, ".md", settings)
        if should_skip(output_path, force):
            log.info("Пропуск (уже есть): %s", output_path)
            continue

        set_step("summary")
        set_current_file(txt_path)
        text = read_text(txt_path)
        log.info("Summary-модель: %s", ollama.model)
        summary = ollama.process_long_text(
            prompts.summary,
            text,
            "Саммаризация",
            temperature=settings.ollama_temperature_summary,
        )
        write_text(output_path, summary)
        log.info("Сохранено: %s", output_path)
        written.append(output_path)

    return written


def mp3_targets(path: Path, settings: Settings) -> list[Path]:
    path = path.resolve()
    if path.suffix.lower() == ".mp3":
        resolve_source_root(path, settings)
        return [path]
    if path.is_dir():
        return collect_mp3_files(path)
    raise ValueError(f"Для шага Whisper нужен MP3-файл или папка: {path}")


def raw_targets(path: Path, settings: Settings) -> list[Path]:
    path = path.resolve()
    if path.suffix.lower() == ".mp3":
        return [output_path_for_mp3(path, settings.raw_dir, ".txt", settings)]
    if path.suffix.lower() == ".txt":
        return [path]
    if path.is_dir():
        if path.resolve() == settings.source_dir.resolve() or settings.source_dir.resolve() in path.parents:
            return [
                output_path_for_mp3(mp3, settings.raw_dir, ".txt", settings)
                for mp3 in collect_mp3_files(path)
            ]
        return collect_txt_files(path, ".txt")
    raise ValueError(f"Для шага clean нужен raw.txt, MP3 или папка: {path}")


def inputs_for_summary(path: Path, settings: Settings) -> list[Path]:
    path = path.resolve()
    if path.suffix.lower() == ".mp3":
        return [output_path_for_mp3(path, settings.clean_dir, ".txt", settings)]
    if path.suffix.lower() == ".txt":
        if settings.raw_dir.resolve() in path.parents:
            return [output_path_for_txt(path, settings.clean_dir, ".txt", settings)]
        return [path]
    if path.is_dir():
        if path.resolve() == settings.source_dir.resolve() or settings.source_dir.resolve() in path.parents:
            return [
                output_path_for_mp3(mp3, settings.clean_dir, ".txt", settings)
                for mp3 in collect_mp3_files(path)
            ]
        if path.resolve() == settings.raw_dir.resolve() or settings.raw_dir.resolve() in path.parents:
            return [
                output_path_for_txt(raw, settings.clean_dir, ".txt", settings)
                for raw in collect_txt_files(path, ".txt")
            ]
        return collect_txt_files(path, ".txt")
    raise ValueError(f"Для шага summary нужен clean.txt, raw.txt, MP3 или папка: {path}")


def list_targets(command: str, path: Path, settings: Settings) -> list[Path]:
    if command == "mp3":
        if path.is_file():
            return mp3_targets(path, settings)
        return collect_mp3_files(path)
    if command == "raw":
        return raw_targets(path, settings)
    if command == "clean":
        return inputs_for_summary(path, settings)
    raise ValueError(f"Неизвестный тип list: {command}")


def run_list(command: str, path: Path, settings: Settings, *, match: str | None) -> None:
    files = filter_paths(list_targets(command, path, settings), match)
    print(json.dumps([str(file_path) for file_path in files], ensure_ascii=False, indent=2))


def run_pipeline(
    path: Path,
    *,
    force: bool,
    ollama: OllamaClient,
    prompts: Prompts,
    settings: Settings,
    steps: set[str] | None = None,
    mp3_files: list[Path] | None = None,
) -> None:
    selected = steps or {"whisper", "clean", "summary"}
    mp3_files = mp3_files or mp3_targets(path, settings)

    if "whisper" in selected:
        set_step("whisper")
        run_whisper(mp3_files, force=force, settings=settings, prompts=prompts)

    raw_files = [
        output_path_for_mp3(mp3, settings.raw_dir, ".txt", settings) for mp3 in mp3_files
    ]
    missing_raw = [p for p in raw_files if not p.exists()]
    if "clean" in selected and missing_raw:
        raise FileNotFoundError(f"Нет raw-файлов для очистки: {missing_raw[0]}")

    if "clean" in selected:
        set_step("clean")
        clean_ollama = OllamaClient(settings, model=settings.ollama_clean_model)
        run_clean(raw_files, force=force, ollama=clean_ollama, prompts=prompts, settings=settings)

    clean_files = [
        output_path_for_mp3(mp3, settings.clean_dir, ".txt", settings) for mp3 in mp3_files
    ]
    missing_clean = [p for p in clean_files if not p.exists()]
    if "summary" in selected and missing_clean:
        raise FileNotFoundError(f"Нет clean-файлов для саммаризации: {missing_clean[0]}")

    if "summary" in selected:
        set_step("summary")
        summary_ollama = OllamaClient(settings, model=settings.ollama_summary_model)
        run_summary(clean_files, force=force, ollama=summary_ollama, prompts=prompts, settings=settings)


def build_parser(settings: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Транскрибация MP3: Whisper → raw → Qwen clean → summary",
    )
    parser.add_argument(
        "command",
        choices=["pipeline", "whisper", "clean", "summary", "list", "status"],
        help="pipeline — все шаги; whisper/clean/summary — отдельный шаг; list — список файлов; status — проверка процесса",
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help=f"MP3-файл, txt-файл, папка или тип для list: mp3/raw/clean",
    )
    parser.add_argument(
        "--match",
        metavar="PATTERN",
        help="Фильтр по имени или пути (подстрока или glob). Удобно для путей с пробелами",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Перезаписать уже существующие результаты",
    )
    parser.add_argument(
        "--steps",
        help="Для pipeline: шаги через запятую (whisper,clean,summary)",
    )
    parser.add_argument(
        "--ollama-host",
        default=settings.ollama_host,
        help=f"URL Ollama API (по умолчанию из .env: {settings.ollama_host})",
    )
    parser.add_argument(
        "--ollama-model",
        default=settings.ollama_model,
        help=f"Модель Ollama (по умолчанию из .env: {settings.ollama_model})",
    )
    parser.add_argument(
        "--ollama-clean-model",
        default=settings.ollama_clean_model,
        help=f"Модель Ollama для шага clean (по умолчанию из .env: {settings.ollama_clean_model})",
    )
    parser.add_argument(
        "--ollama-summary-model",
        default=settings.ollama_summary_model,
        help=f"Модель Ollama для шага summary (по умолчанию из .env: {settings.ollama_summary_model})",
    )
    parser.add_argument(
        "--whisper-device",
        default=settings.whisper_device,
        help=f"Устройство Whisper (по умолчанию из .env: {settings.whisper_device})",
    )
    parser.add_argument(
        "--whisper-compute-type",
        default=settings.whisper_compute_type,
        help=f"Тип вычислений Whisper (по умолчанию из .env: {settings.whisper_compute_type})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Для status: вывести JSON",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Подробный вывод",
    )
    return parser


def apply_cli_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    return Settings(
        source_dir=settings.source_dir,
        raw_dir=settings.raw_dir,
        clean_dir=settings.clean_dir,
        summary_dir=settings.summary_dir,
        prompts_file=settings.prompts_file,
        status_file=settings.status_file,
        ollama_host=args.ollama_host,
        ollama_model=args.ollama_model,
        ollama_clean_model=args.ollama_clean_model,
        ollama_summary_model=args.ollama_summary_model,
        ollama_chunk_chars=settings.ollama_chunk_chars,
        ollama_temperature_clean=settings.ollama_temperature_clean,
        ollama_temperature_summary=settings.ollama_temperature_summary,
        whisper_model=settings.whisper_model,
        whisper_device=args.whisper_device,
        whisper_compute_type=args.whisper_compute_type,
        whisper_beam_size=settings.whisper_beam_size,
        whisper_language=settings.whisper_language,
        whisper_no_speech_threshold=settings.whisper_no_speech_threshold,
        whisper_vad_filter=settings.whisper_vad_filter,
        whisper_condition_on_previous_text=settings.whisper_condition_on_previous_text,
    )


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    prompts = load_prompts(settings.prompts_file)

    parser = build_parser(settings)
    args = parser.parse_args(argv)
    settings = apply_cli_overrides(settings, args)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    path = args.path
    if args.command == "status":
        report = build_status_report(settings.status_file, settings.ollama_host)
        print_status_report(report, as_json=args.json)
        return 0

    if args.command == "list":
        list_kind = (str(path) if path else "mp3").lower()
        if list_kind not in {"mp3", "raw", "clean"}:
            parser.error("Для list укажите тип: mp3, raw или clean")
        list_root = {
            "mp3": settings.source_dir,
            "raw": settings.raw_dir,
            "clean": settings.clean_dir,
        }[list_kind]
        if not list_root.exists():
            parser.error(f"Путь не найден: {list_root}")
        try:
            run_list(list_kind, list_root, settings, match=args.match)
        except (ValueError, FileNotFoundError) as exc:
            log.error("%s", exc)
            return 1
        return 0

    path = path or settings.source_dir
    if not path.exists():
        parser.error(f"Путь не найден: {path}")

    # OllamaClient для разных шагов использует разные модели.
    # В pipeline они пересоздаются внутри run_pipeline, здесь — для отдельных шагов.
    clean_ollama = OllamaClient(settings, model=settings.ollama_clean_model)
    summary_ollama = OllamaClient(settings, model=settings.ollama_summary_model)
    steps = None
    if args.steps:
        steps = {part.strip() for part in args.steps.split(",") if part.strip()}
        unknown = steps - {"whisper", "clean", "summary"}
        if unknown:
            parser.error(f"Неизвестные шаги: {', '.join(sorted(unknown))}")

    target = str(path)
    if args.match:
        target = f"{target} --match {args.match}"

    try:
        with track_job(
            settings.status_file,
            command=args.command,
            target=target,
            allow_parallel=args.force,
        ):
            if args.command == "pipeline":
                mp3_files = filter_paths(mp3_targets(path, settings), args.match)
                if not mp3_files:
                    raise ValueError("Нет MP3-файлов для обработки")
                run_pipeline(
                    path,
                    force=args.force,
                    ollama=clean_ollama,  # fallback; run_pipeline создаёт свои
                    prompts=prompts,
                    settings=settings,
                    steps=steps,
                    mp3_files=mp3_files,
                )
            elif args.command == "whisper":
                run_whisper(
                    filter_paths(mp3_targets(path, settings), args.match),
                    force=args.force,
                    settings=settings,
                    prompts=prompts,
                )
            elif args.command == "clean":
                run_clean(
                    filter_paths(raw_targets(path, settings), args.match),
                    force=args.force,
                    ollama=clean_ollama,
                    prompts=prompts,
                    settings=settings,
                )
            elif args.command == "summary":
                run_summary(
                    filter_paths(inputs_for_summary(path, settings), args.match),
                    force=args.force,
                    ollama=summary_ollama,
                    prompts=prompts,
                    settings=settings,
                )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        log.error("%s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
