---
name: transcribe-clean
description: >-
  Субагент второго шага пайплайна — очистка raw.txt → clean.txt через локальную
  Ollama-модель llama3.1-clean-32k:latest. Запускается агентом transcribe-clean,
  не пользователем напрямую.
---

# Транскрибация — Clean (очистка)

## КРИТИЧНО: как выполнять

Этот skill вызывает `transcribe.py clean` с моделью `llama3.1-clean-32k:latest`.

| Запрещено | Обязательно |
|-----------|-------------|
| Использовать Whisper или саммаризацию | Только шаг `clean` |
| Использовать другую ollama-модель | `llama3.1-clean-32k:latest` (`OLLAMA_CLEAN_MODEL`) |
| Симулировать очистку в ответе | Запустить shell-команду и дождаться ответа ollama |

## Алгоритм

1. Проверить статус:
   ```bash
   .claude/skills/transcribe-clean/scripts/run.sh status
   ```
2. Запустить:
   ```bash
   .claude/skills/transcribe-clean/scripts/run.sh clean raw --match "<фрагмент>"
   ```
   или для всех raw:
   ```bash
   .claude/skills/transcribe-clean/scripts/run.sh clean raw
   ```
   Также поддерживается `source-mp3/...` (тогда raw маппится автоматически).
3. Дождаться exit code 0. Модель 32k — может обрабатывать большие raw одним проходом.
4. Сообщить список созданных `clean/.../*.txt`.

## Контекст

- Рабочая директория: `transcribator/`.
- Модель: `llama3.1-clean-32k:latest` (env `OLLAMA_CLEAN_MODEL`).
- Промпт: `prompts.toml`, секция `[clear]` (system) и `[clear_user]` (user template).
- Temperature: `OLLAMA_TEMPERATURE_CLEAN=0.1`.
- Ollama должна быть запущена на `OLLAMA_HOST` (по умолчанию `http://127.0.0.1:11434`).

## Параметры

- `clean <path> [--match PATTERN] [--force]`
  - `<path>` — `raw/.../*.txt`, `raw/`, `source-mp3/` (или подкаталог).
- `list raw` / `list clean` — посмотреть файлы.

Подробности: [reference.md](reference.md)
