# Справка: transcribe-summary

## Что делает

Шаг 3 пайплайна: clean.txt → summary.md через локальную Ollama-модель
`gemma4:e2b-32k` (или `OLLAMA_SUMMARY_MODEL`, если переопределена).

## CLI

```bash
.claude/skills/transcribe-summary/scripts/run.sh summary <path> [--match PATTERN] [--force]
.claude/skills/transcribe-summary/scripts/run.sh list clean [--match PATTERN]
.claude/skills/transcribe-summary/scripts/run.sh status
```

`<path>` — `clean/.../*.txt`, `clean/`, `raw/`, `source-mp3/` или подкаталог.

## Поведение

- Если `summary/<path>.md` уже существует и `--force` не указан — пропуск.
- Temperature: 0.4 — небольшая вариативность.
- Структура выхода (по промпту): учебный конспект в Markdown, 8 секций.
- Технические термины сохраняются на английском.
- Модель не должна добавлять информацию, которой нет в clean.txt.

## Требования

- Ollama запущена (`OLLAMA_HOST`).
- Модель `gemma4:e2b-32k` доступна.
- Шаги whisper и clean уже выполнены.

## Конец пайплайна

После summary — это финальный шаг. `summary/<path>.md` готов к использованию.
