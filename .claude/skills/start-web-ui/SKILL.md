---
name: start-web-ui
description: >-
  Запускает локальный Flask-сервер app.py — веб-интерфейс пайплайна
  транскрибации (просмотр source-mp3/raw/clean/summary, запуск transcribe.py
  через /api/run, SSE-логи). Запускается пользователем через естественный язык.
---

# Транскрибация — Web UI (Flask)

## КРИТИЧНО: как выполнять

Этот skill запускает **долгоживущий** Flask-сервер `app.py` на `127.0.0.1:8765`
в фоне. Управление возвращается сразу, сервер продолжает работать до
явного `stop`.

| Запрещено | Обязательно |
|-----------|-------------|
| Запускать `transcribe.py whisper/clean/summary` напрямую из этого скилла | Запустить сервер; пользователь сам жмёт кнопки в UI |
| Использовать `flask run` или `python -m flask` | `.venv/bin/python app.py` через `scripts/run.sh start` |
| Запускать второй экземпляр Flask параллельно | Перед `start` проверить, что порт 8765 свободен (`lsof`) |
| Запускать Flask в foreground (висит в агенте) | `nohup … &` в `run.sh`, PID сохранить в `.web-ui.pid` |
| Трогать `app.py`, `templates/index.html` | Только запускать как есть |

## Алгоритм

1. Убедиться, что venv и зависимости есть:
   ```bash
   .claude/skills/start-web-ui/scripts/run.sh check
   ```
2. Проверить, что порт свободен (если занят — попробовать `status`, иначе
   сообщить пользователю, что нужно `stop` старого или вручную
   `lsof -ti:8765 | xargs kill -9`):
   ```bash
   lsof -i :8765 || echo "port free"
   ```
3. Запустить сервер в фоне:
   ```bash
   .claude/skills/start-web-ui/scripts/run.sh start
   ```
   Скрипт сам форкнет процесс, выведет PID и положит его в `.web-ui.pid`,
   лог — в `web-ui.log`.
4. Дождаться readiness (сервер поднимается ~1 сек):
   ```bash
   until curl -sf http://127.0.0.1:8765/api/status >/dev/null; do sleep 0.3; done
   ```
5. Сообщить пользователю URL: `http://127.0.0.1:8765/` + PID.

При запросе «останови веб-интерфейс» / «выключи UI»:
```bash
.claude/skills/start-web-ui/scripts/run.sh stop
```

При «UI ещё работает?» / «какой статус?»:
```bash
.claude/skills/start-web-ui/scripts/run.sh status
```

## Контекст

- Рабочая директория: `transcribator/` (корень проекта).
- Сервер: `app.py` (Flask), `host="127.0.0.1"`, `port=8765`,
  `debug=False`, `use_reloader=False`, `threaded=True`.
- UI: `templates/index.html`, статика из `templates/`.
- Зависимости (`requirements.txt`): `flask`, `markdown`, `faster-whisper`,
  `python-dotenv`. Все уже в `.venv`.
- Сервер не модифицирует `transcribe.py` — только дёргает его через
  subprocess (`app.py:241`) и читает `.transcribe-status.json`.
- Один процесс Flask = один запущенный subprocess `transcribe.py` (см.
  `_current` в `app.py:49`). UI это скрывает, но при активной транскрибации
  второй запуск через UI даст HTTP 409.
- Host/port **жёстко зашиты** в `app.py:455` — не параметризуются через env.
- `app.py` **не имеет** обработчиков сигналов (SIGTERM/SIGINT) — остановка
  через `kill -9` (как делает `run.sh stop`) безопасна, потому что
  subprocess `transcribe.py` отдельный процесс (если он шёл — переживёт
  смерть Flask, но это не проблема: при следующем старте Flask увидит его
  через `is_process_alive(pid)` из `status.py`).

## Параметры

`scripts/run.sh` принимает одну команду:

- `start` — запустить Flask в фоне, PID в `.web-ui.pid`, лог в `web-ui.log`.
- `stop` — убить Flask по PID (SIGKILL), удалить PID-файл.
- `status` — `running (PID …, URL http://127.0.0.1:8765/)` или `stopped`.
- `check` — есть ли venv, requirements, app.py, templates/; импортируются
  ли flask и markdown. Печатает `ok` либо первую ошибку.

`PROJECT_ROOT=/path/to/transcribator` env-переменная переопределяет
авто-определение корня (по умолчанию — поиск `app.py` вверх от
`scripts/run.sh`).

Подробности: [reference.md](reference.md)
