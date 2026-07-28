# Справка: transcribe-whisper

## Что делает

Шаг 1 пайплайна: MP3 → raw.txt через локальную модель Whisper Large-v3
(faster-whisper, не ollama).

## CLI

```bash
.claude/skills/transcribe-whisper/scripts/run.sh whisper <path> [--match PATTERN] [--force]
.claude/skills/transcribe-whisper/scripts/run.sh list mp3 [--match PATTERN]
.claude/skills/transcribe-whisper/scripts/run.sh status
```

`<path>` — файл `.mp3`, папка или `source-mp3/` (по умолчанию).

## Поведение

- Whisper Large-v3 на CPU (`int8`) — медленно: ~10-20x от длительности аудио.
- Не прерывать процесс — прерывание = потеря прогресса.
- Если `raw/<path>.txt` уже существует и `--force` не указан — файл пропускается.
- `WHISPER_NO_SPEECH_THRESHOLD=none` — не пропускать «тихие» 30-секундные чанки
  (важно для лекций).
- Hotwords (список терминов через запятую) — в `prompts.toml`, секция `[hotwords]`.

## Статус

Файл `.transcribe-status.json` (`STATUS_FILE` в `.env`) показывает текущий шаг
и обрабатываемый файл.

## Следующий шаг

После whisper вызывается субагент `transcribe-clean` (модель `llama3.1-clean-32k:latest`).
