# Справка: start-web-ui

## Что делает

Поднимает локальный Flask-сервер `app.py` (хост `127.0.0.1`, порт `8765`) —
веб-интерфейс пайплайна транскрибации. В UI можно:

- видеть дерево `source-mp3/` с бейджами `R / C / S` (raw / clean / summary);
- кликнуть файл и прочитать raw.txt / clean.txt / summary.md прямо в браузере;
- запустить pipeline на файл / папку / весь source-mp3/;
- запустить **любой отдельный шаг** (whisper / clean / summary);
- следить за прогрессом в реальном времени через SSE-стрим логов.

Сервер один процесс = один запущенный subprocess `transcribe.py`
(см. `_current` в `app.py:49`). Второй запуск через UI при активной
транскрибации даёт HTTP 409 на `/api/run`.

## CLI

```bash
.claude/skills/start-web-ui/scripts/run.sh start     # запустить в фоне
.claude/skills/start-web-ui/scripts/run.sh stop      # убить (SIGKILL)
.claude/skills/start-web-ui/scripts/run.sh status    # running | stopped
.claude/skills/start-web-ui/scripts/run.sh check     # проверить окружение
```

`start` выводит PID и URL, **сразу возвращает управление** — сервер крутится
в фоне. Для readiness-ожидания используйте `until curl -sf http://127.0.0.1:8765/api/status`.

## Поведение

- **PID-файл:** `${PROJECT_ROOT}/.web-ui.pid` — содержит PID Flask-процесса.
- **Лог:** `${PROJECT_ROOT}/web-ui.log` — stdout+stderr Flask. Там виден
  вывод `app.py:452` («Открой http://127.0.0.1:8765») и баннер werkzeug.
- **`use_reloader=False`** в `app.py` критично — иначе subprocess
  `transcribe.py` живёт в одном процессе, а reader-thread логов в другом,
  и логи теряются.
- **`debug=False`** — без интерактивного дебаггера и без автоперезапуска.
- **SIGKILL при `stop`** — Flask сам по себе не имеет обработчиков сигналов,
  поэтому SIGTERM ничем не лучше SIGKILL, а SIGKILL гарантированно
  освобождает порт. Subprocess `transcribe.py` (если был активен) переживёт
  смерть Flask — это нормально, при следующем `start` Flask подхватит его
  через `is_process_alive()` в `status.py`.
- **`lsof -i :8765`** — если порт занят другим процессом (не этим скиллом),
  `start` отказывается запускаться. Это страховка от дублей.

## Требования

- `.venv/bin/python` существует и исполняемый.
- `app.py` и `templates/` в корне проекта.
- В `.venv` установлены пакеты из `requirements.txt`: `flask`, `markdown`,
  `faster-whisper`, `python-dotenv`.
- Порт `8765` свободен (или старый PID убит через `stop`).

`check` проверяет все эти условия.

## Следующий шаг

UI готов — пользователь работает в браузере. Если он просит запустить
конкретный шаг пайплайна из терминала — это уже скиллы
`transcribe-whisper` / `transcribe-clean` / `transcribe-summary` /
`transcribe-pipeline`, не этот.
