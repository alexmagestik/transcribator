---
name: transcribe-whisper
description: >-
  Субагент первого шага пайплайна — сырая транскрибация MP3 → raw.txt через
  локальную модель Whisper Large-v3 (faster-whisper, не ollama). Запускается
  агентом transcribe-whisper, не пользователем напрямую.
---

# Транскрибация — Whisper (raw)

## КРИТИЧНО: как выполнять

Этот skill вызывает `transcribe.py whisper` (Whisper Large-v3 через faster-whisper).
Ollama **не используется**.

| Запрещено | Обязательно |
|-----------|-------------|
| Использовать ollama для шага whisper | Использовать faster-whisper |
| Вызывать `transcribe.py clean` или `summary` | Только шаг `whisper` |
| Симулировать транскрипт в ответе | Запустить shell-команду и дождаться завершения |

## Алгоритм

1. Проверить статус:
   ```bash
   .claude/skills/transcribe-whisper/scripts/run.sh status
   ```
2. Найти файлы (если нужно):
   ```bash
   .claude/skills/transcribe-whisper/scripts/run.sh list mp3 --match "<фрагмент>"
   ```
3. Запустить:
   ```bash
   .claude/skills/transcribe-whisper/scripts/run.sh whisper source-mp3 --match "<фрагмент>"
   ```
   или для всех:
   ```bash
   .claude/skills/transcribe-whisper/scripts/run.sh whisper source-mp3
   ```
4. Дождаться exit code 0. Whisper на CPU — медленный, не прерывать.
5. Сообщить список созданных `raw/.../*.txt`.

## Контекст

- Рабочая директория: `transcribator/`.
- Модель: `large-v3`, device=cpu, compute_type=int8, beam=5, language=ru.
- Hotwords — в `prompts.toml`, секция `[hotwords]`.

## Параметры

- `whisper <path> [--match <pattern>] [--force]` — единственная команда.
- Поддерживает `--force` для перезаписи существующих raw.

Подробности: [reference.md](reference.md)
