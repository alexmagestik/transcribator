#!/usr/bin/env bash
# Заглушка для главного субагента пайплайна.
# Главный субагент не вызывает transcribe.py напрямую — он запускает субагентов
# шагов через Agent tool. Этот скрипт оставлен для совместимости (status / list).
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
  exit 1
fi

cd "$PROJECT_ROOT"
# Только status / list — для остального используйте субагентов шагов.
case "${1:-}" in
  status|list)
    exec "$PYTHON" transcribe.py "$@"
    ;;
  *)
    echo "Главный субагент пайплайна не вызывает transcribe.py напрямую." >&2
    echo "Запускайте субагентов шагов:" >&2
    echo "  .claude/skills/transcribe-whisper/scripts/run.sh whisper source-mp3 [--match ...]" >&2
    echo "  .claude/skills/transcribe-clean/scripts/run.sh clean raw [--match ...]" >&2
    echo "  .claude/skills/transcribe-summary/scripts/run.sh summary clean [--match ...]" >&2
    echo "Или вызовите 'status' / 'list <type>' для справки." >&2
    exit 1
    ;;
esac
