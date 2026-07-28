# Справка: transcribe-clean

## Что делает

Шаг 2 пайплайна: raw.txt → clean.txt через локальную Ollama-модель
`llama3.1-clean-32k:latest`.

## CLI

```bash
.claude/skills/transcribe-clean/scripts/run.sh clean <path> [--match PATTERN] [--force]
.claude/skills/transcribe-clean/scripts/run.sh list raw|clean [--match PATTERN]
.claude/skills/transcribe-clean/scripts/run.sh status
```

`<path>` — `raw/.../*.txt`, `raw/`, `source-mp3/` или подкаталог в нём.

## Поведение

- Если `clean/<path>.txt` уже существует и `--force` не указан — пропуск.
- Если raw > `OLLAMA_CHUNK_CHARS` (по умолчанию 24000), текст разбивается
  на чанки по абзацам, обрабатывается последовательно и склеивается.
- Temperature: 0.1 — детерминированная очистка.
- System prompt: редактор транскриптов (см. `prompts.toml`, `[clear]`).
- User prompt: `[clear_user]` с `{{TEXT}}` placeholder.

## Требования

- Ollama запущена (`OLLAMA_HOST`, по умолчанию `http://127.0.0.1:11434`).
- Модель `llama3.1-clean-32k:latest` доступна (`ollama list`).
- Whisper-шаг уже выполнен — иначе `raw/*.txt` ещё нет.

## Следующий шаг

После clean вызывается субагент `transcribe-summary` (модель `gemma4:e2b-32k`).
