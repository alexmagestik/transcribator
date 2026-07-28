---
name: transcribe-summary
description: >-
  Субагент третьего шага пайплайна — саммаризация clean.txt → summary.md через
  локальную Ollama-модель gemma4:e2b-32k (или ту, на которой запущен основной
  пайплайн claude). Запускается агентом transcribe-summary, не пользователем
  напрямую.
---

# Транскрибация — Summary (саммаризация)

## КРИТИЧНО: как выполнять

Этот skill вызывает `transcribe.py summary` с моделью `gemma4:e2b-32k`.

| Запрещено | Обязательно |
|-----------|-------------|
| Использовать Whisper или шаг clean | Только шаг `summary` |
| Использовать модель clean | `gemma4:e2b-32k` (`OLLAMA_SUMMARY_MODEL`) |
| Симулировать саммари в ответе | Запустить shell-команду и дождаться ответа ollama |

## Алгоритм

1. Проверить статус:
   ```bash
   .claude/skills/transcribe-summary/scripts/run.sh status
   ```
2. Запустить:
   ```bash
   .claude/skills/transcribe-summary/scripts/run.sh summary clean --match "<фрагмент>"
   ```
   или для всех clean:
   ```bash
   .claude/skills/transcribe-summary/scripts/run.sh summary clean
   ```
   Также поддерживается `raw/` и `source-mp3/` (маппится в `clean/.../*.txt`).
3. Дождаться exit code 0.
4. Сообщить список созданных `summary/.../*.md`.

## Контекст

- Рабочая директория: `transcribator/`.
- Модель: `gemma4:e2b-32k` (env `OLLAMA_SUMMARY_MODEL`).
- Промпт: `prompts.toml`, секция `[summary]` (Markdown-структура конспекта).
- Temperature: `OLLAMA_TEMPERATURE_SUMMARY=0.4`.
- Ollama должна быть запущена на `OLLAMA_HOST`.

## Структура саммари (по промпту)

Основная идея / Ключевые понятия / Важные определения / Практические примеры /
Лучшие практики / Типичные ошибки / Что стоит запомнить / Чек-лист применения.

Подробности: [reference.md](reference.md)
