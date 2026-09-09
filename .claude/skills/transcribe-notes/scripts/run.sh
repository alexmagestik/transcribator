#!/usr/bin/env bash
# Обёртка для шага Notes (raw → notes, ollama).
# Принимает все аргументы transcribe.py и прокидывает дальше.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ищем корень проекта по маркеру transcribe.py
find_project_root() {
  local dir="$1"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/transcribe.py" ]]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

PROJECT_ROOT="${PROJECT_ROOT:-$(find_project_root "$SCRIPT_DIR")}"

if [[ -z "$PROJECT_ROOT" ]]; then
  echo "Не найден transcribe.py. Укажите PROJECT_ROOT или запускайте из корня проекта." >&2
  exit 1
fi

PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Не найдено виртуальное окружение: ${PYTHON}" >&2
  echo "Создайте: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# Модель для notes-шага (с fallback на OLLAMA_MODEL)
export OLLAMA_NOTES_MODEL="${OLLAMA_NOTES_MODEL:-${OLLAMA_MODEL:-gemma4:e2b-32k}}"

cd "$PROJECT_ROOT"
exec "$PYTHON" transcribe.py "$@"
