---
name: transcribe-notes
description: >-
  Субагент шага конспектирования — создание подробных технических заметок из raw.txt → notes.md через локальную
  Ollama-модель. Запускается агентом transcribe-notes, не пользователем напрямую.
---

# Транскрибация — Notes (конспектирование)

## КРИТИЧНО: как выполнять

Этот skill вызывает `transcribe.py notes` с моделью из `OLLAMA_NOTES_MODEL`.

| Запрещено | Обязательно |
|-----------|-------------|
| Использовать Whisper или очистку | Только шаг `notes` |
| Использовать другую ollama-модель | `OLLAMA_NOTES_MODEL` |
| Симулировать конспект в ответе | Запустить shell-команду и дождаться ответа ollama |

## Алгоритм

1. Проверить статус:
   ```bash
   .claude/skills/transcribe-notes/scripts/run.sh status
   ```
2. Запустить:
   ```bash
   .claude/skills/transcribe-notes/scripts/run.sh notes raw --match "<фрагмент>"
   ```
   или для всех raw:
   ```bash
   .claude/skills/transcribe-notes/scripts/run.sh notes raw
   ```
   Также поддерживается `source-mp3/...` (тогда raw маппится автоматически).
3. Дождаться exit code 0. Текст обрабатывается чанками (с учётом промпта) для лимита 32k.
4. Сообщить список созданных `notes/.../*.md`.

## Контекст

- Рабочая директория: `transcribator/`.
- Модель: `OLLAMA_NOTES_MODEL`.
- Промпт: `prompts.toml`, секция `[notes]`.
- Temperature: `OLLAMA_TEMPERATURE_NOTES`.
- Ollama должна быть запущена на `OLLAMA_HOST`.

## Параметры

- `notes <path> [--match PATTERN] [--force]`
  - `<path>` — `raw/.../*.txt`, `raw/`, `source-mp3/` (или подкаталог).
- `list raw` / `list notes` — посмотреть файлы.
