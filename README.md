# transcribator

Пайплайн транскрибации MP3 через локальные модели (Whisper + Ollama) с архитектурой
**главный субагент → субагенты шагов** в Claude Code.

## Архитектура

```
source-mp3/*.mp3  →  raw/*.txt  →  clean/*.txt  →  summary/*.md
       ↓                  ↓                 ↓
transcribe-whisper   transcribe-clean   transcribe-summary
(faster-whisper)    (ollama clean)     (ollama summary)
       │                  │                 │
       └──── субагент шага ─────────────────┘
                       │
                       ▼
              transcribe-pipeline
            (главный субагент пайплайна)
```

Главный субагент `transcribe-pipeline` запускает субагентов шагов
**последовательно** через Agent tool. Сейчас — последовательно; в будущем
clean и summary будут параллельными.

## Структура

```
transcribator/
├── transcribe.py              # CLI (pipeline/whisper/clean/summary/list/status)
├── config.py                  # Settings (env, в т.ч. OLLAMA_CLEAN_MODEL, OLLAMA_SUMMARY_MODEL)
├── status.py                  # Статус и track_job
├── prompts.toml               # Hotwords + промпты clean и summary
├── requirements.txt           # faster-whisper, python-dotenv
├── env.example                # Шаблон .env
├── source-mp3/                # Исходные MP3
├── raw/                       # Whisper-транскрипт
├── clean/                     # Очищенный текст
├── summary/                   # Саммари в Markdown
└── .claude/
    ├── agents/
    │   ├── transcribe-pipeline.md   # Главный субагент пайплайна
    │   ├── transcribe-whisper.md    # Субагент whisper
    │   ├── transcribe-clean.md      # Субагент clean
    │   └── transcribe-summary.md    # Субагент summary
    └── skills/
        ├── transcribe-pipeline/     # Skill главного субагента
        ├── transcribe-whisper/      # Skill whisper (raw-транскрипт)
        ├── transcribe-clean/        # Skill clean (ollama llama3.1-clean-32k)
        └── transcribe-summary/      # Skill summary (ollama gemma4:e2b-32k)
```

## Подготовка (один раз)

```bash
cd transcribator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp env.example .env
# Отредактируйте .env если нужно (модели ollama, устройство whisper и т.п.)
```

Убедитесь, что ollama запущена и модели доступны:
```bash
ollama list   # должны быть llama3.1-clean-32k:latest и gemma4:e2b-32k
ollama ps     # что-то из них может быть активно
```

## Использование через Claude Code

### Полный пайплайн (через главного субагента)

Запустите главного субагента пайплайна. Примеры запросов:

> "Запусти полный пайплайн для part12"

> "Обработай все mp3 в source-mp3"

> "Сделай clean и summary для `Занятие 2. Apache Kafka`"

Главный субагент `transcribe-pipeline` разберёт запрос и последовательно
запустит субагентов шагов (`transcribe-whisper` → `transcribe-clean` →
`transcribe-summary`).

### Запуск только шага (напрямую через субагента)

Можно сразу вызвать нужного субагента шага:

> "Запусти только whisper для part05"
> "Только clean для всех raw"
> "Перезапусти summary с --force для всего"

### Прямой запуск через CLI (без агента)

```bash
# Полный pipeline
.venv/bin/python transcribe.py pipeline source-mp3 --match "part12"

# Только whisper
.venv/bin/python transcribe.py whisper source-mp3 --match "part12"

# Только clean (вход — raw)
.venv/bin/python transcribe.py clean raw --match "part12"

# Только summary (вход — clean)
.venv/bin/python transcribe.py summary clean --match "part12"

# С указанием моделей
.venv/bin/python transcribe.py clean raw --ollama-clean-model other-model:latest
.venv/bin/python transcribe.py summary clean --ollama-summary-model other-model
```

## Модели

| Шг    | Модель                       | Как запускается                     |
|-------|------------------------------|--------------------------------------|
| whisper | `large-v3` (faster-whisper) | локально, CPU, через faster-whisper |
| clean | `llama3.1-clean-32k:latest` | через Ollama (`OLLAMA_CLEAN_MODEL`) |
| summary | `gemma4:e2b-32k`           | через Ollama (`OLLAMA_SUMMARY_MODEL`) |

Можно переопределить:
- через `.env`: `OLLAMA_CLEAN_MODEL=...`, `OLLAMA_SUMMARY_MODEL=...`;
- через CLI: `--ollama-clean-model ...`, `--ollama-summary-model ...`;
- через ENV: `OLLAMA_CLEAN_MODEL=...` при вызове.

Если `OLLAMA_CLEAN_MODEL` / `OLLAMA_SUMMARY_MODEL` не заданы — fallback на
`OLLAMA_MODEL` (а если и она не задана — на встроенные дефолты).

## Структура файлов

Сохраняется полностью. Пример:
```
source-mp3/Занятие 2. Apache Kafka/Занятие 2. Apache Kafka part12.mp3
raw/Занятие 2. Apache Kafka/Занятие 2. Apache Kafka part12.txt
clean/Занятие 2. Apache Kafka/Занятие 2. Apache Kafka part12.txt
summary/Занятие 2. Apache Kafka/Занятие 2. Apache Kafka part12.md
```

## Что дальше

- Параллелизация clean и summary (запускать в одном сообщении Agent tool).
- Возможно: параллелизация по файлам внутри whisper (если faster-whisper
  не блокирует GPU/CPU).
