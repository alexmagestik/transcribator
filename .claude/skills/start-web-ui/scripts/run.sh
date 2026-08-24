#!/usr/bin/env bash
# Запуск локального Flask-сервера app.py (веб-интерфейс пайплайна транскрибации).
# Сервер ДОЛГОЖИВУЩИЙ — start/stop/status/check.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_project_root() {
  local dir="$1"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/app.py" ]]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

PROJECT_ROOT="${PROJECT_ROOT:-$(find_project_root "$SCRIPT_DIR")}"

if [[ -z "$PROJECT_ROOT" ]]; then
  echo "Не найден app.py. Укажите PROJECT_ROOT=/path/to/transcribator" >&2
  exit 1
fi

PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Не найдено виртуальное окружение: ${PYTHON}" >&2
  echo "Создайте: ${PROJECT_ROOT}/.venv/bin/python (см. README проекта)" >&2
  exit 1
fi

PID_FILE="${PROJECT_ROOT}/.web-ui.pid"
LOG_FILE="${PROJECT_ROOT}/web-ui.log"
PORT=8765

cd "$PROJECT_ROOT"

case "${1:-}" in
  start)
    # Не даём запустить второй экземпляр через наш же PID-файл
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Уже запущен (PID $(cat "$PID_FILE")). Используйте 'stop'." >&2
      exit 1
    fi
    # Страховка от занятого порта чужим процессом
    if lsof -i ":${PORT}" >/dev/null 2>&1; then
      echo "Порт ${PORT} занят. Остановите процесс: lsof -ti:${PORT} | xargs kill -9" >&2
      exit 1
    fi
    # Уберём осиротевший PID-файл, если процесс уже умер
    rm -f "$PID_FILE"
    nohup "$PYTHON" app.py >"$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Запущен. PID=$(cat "$PID_FILE")"
    echo "URL: http://127.0.0.1:${PORT}/"
    echo "Лог: $LOG_FILE"
    ;;
  stop)
    if [[ -f "$PID_FILE" ]]; then
      local_pid="$(cat "$PID_FILE")"
      if kill -0 "$local_pid" 2>/dev/null; then
        kill -9 "$local_pid" 2>/dev/null || true
        echo "Остановлен (PID $local_pid)."
      else
        echo "PID $local_pid уже не существует."
      fi
      rm -f "$PID_FILE"
    else
      echo "Не запущен (нет ${PID_FILE})." >&2
      # На всякий случай — если порт всё-таки занят чужим процессом
      if lsof -i ":${PORT}" >/dev/null 2>&1; then
        echo "Но порт ${PORT} занят: lsof -ti:${PORT}" >&2
      fi
    fi
    ;;
  status)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "running (PID $(cat "$PID_FILE"), URL http://127.0.0.1:${PORT}/)"
    else
      echo "stopped"
    fi
    ;;
  check)
    [[ -x "$PYTHON" ]] || { echo "FAIL: нет ${PYTHON}"; exit 1; }
    [[ -f "${PROJECT_ROOT}/app.py" ]] || { echo "FAIL: нет ${PROJECT_ROOT}/app.py"; exit 1; }
    [[ -d "${PROJECT_ROOT}/templates" ]] || { echo "FAIL: нет ${PROJECT_ROOT}/templates/"; exit 1; }
    if ! "$PYTHON" -c "import flask, markdown" 2>/dev/null; then
      echo "FAIL: пакеты flask/markdown не импортируются. Запустите: ${PYTHON} -m pip install -r ${PROJECT_ROOT}/requirements.txt"
      exit 1
    fi
    echo "ok"
    ;;
  *)
    echo "Usage: $0 {start|stop|status|check}" >&2
    exit 1
    ;;
esac
