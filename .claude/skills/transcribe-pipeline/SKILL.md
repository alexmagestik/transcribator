---
name: transcribe-pipeline
description: >-
  Главный субагент пайплайна. Координирует запуск whisper/clean/summary
  субагентов, обрабатывая файлы, папки или весь source-mp3/. Запускается
  пользователем через естественный язык.
---

# Транскрибация — главный субагент пайплайна

Этот skill описывает, как главный субагент `transcribe-pipeline` запускает
субагентов шагов. Ты — главный субагент; субагентов шагов запускай через
Agent tool по их именам (`transcribe-whisper`, `transcribe-clean`, `transcribe-summary`).

## Алгоритм

1. **Понять запрос пользователя.** Что именно нужно обработать и какой шаг:
   - файл, папка, весь `source-mp3`?
   - полный pipeline / только whisper / только clean / только summary / комбинация?

2. **Сформулировать `--match`.** Всегда используй `--match "<фрагмент имени>"`
   — так надёжнее для путей с пробелами.

3. **Запустить субагентов последовательно** через Agent tool:
   - Полный pipeline: сначала `transcribe-whisper`, затем `transcribe-clean`, затем `transcribe-summary`.
   - Только whisper → только `transcribe-whisper`.
   - Только clean → только `transcribe-clean` (но вход — `raw/`).
   - Только summary → только `transcribe-summary` (но вход — `clean/`).
   - Комбинация clean+summary → запустить по очереди.

4. **Сообщить результат** — пути к созданным файлам. Не выдумывать содержимое.

## Примеры запросов и реакций

| Запрос | Действия |
|--------|----------|
| "запусти полный пайплайн для part12" | `transcribe-whisper` → `transcribe-clean` → `transcribe-summary` с `--match "part12"` |
| "обработай только clean для Apache Kafka" | только `transcribe-clean` с `--match "Apache Kafka"` |
| "пройди все mp3 в source-mp3" | 3 субагента, без `--match` |
| "перезапусти summary для всего" | только `transcribe-summary` с `--force` |

## Команды для проверки

```bash
.claude/skills/transcribe-whisper/scripts/run.sh status
```

Подробности: [reference.md](reference.md)
