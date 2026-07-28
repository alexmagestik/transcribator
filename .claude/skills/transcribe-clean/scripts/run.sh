#!/usr/bin/env bash
# Обёртка для шага Clean (raw → clean, ollama llama3.1-clean-32k:latest).
# Принимает все аргументы transcribe.py и прокидывает дальше.
# Модель берётся из OLLAMA_CLEAN_MODEL (с fallback на OLLAMA_MODEL).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ищем корень проекта по маркеру transcribe.py — поднимаемся вверх от SCRIPT_DIR.
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

# Модель для clean-шага (если не задана — fallback на OLLAMA_MODEL, default llama3.1-clean-32k:latest)
export OLLAMA_CLEAN_MODEL="${OLLAMA_CLEAN_MODEL:-llama3.1-clean-32k:latest}"

cd "$PROJECT_ROOT"
exec "$PYTHON" transcribe.py "$@"
