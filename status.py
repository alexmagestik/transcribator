from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_status(status_file: Path) -> dict[str, Any] | None:
    if not status_file.exists():
        return None
    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def write_status(status_file: Path, data: dict[str, Any]) -> None:
    status_file.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utc_now()
    status_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clear_status(status_file: Path) -> None:
    if status_file.exists():
        status_file.unlink()


def find_transcribe_processes() -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            ["pgrep", "-fl", "transcribe.py"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []

    processes: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        processes.append({"pid": parts[0], "command": parts[1] if len(parts) > 1 else ""})
    return processes


def fetch_ollama_ps(host: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(f"{host.rstrip('/')}/api/ps", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []
    models = body.get("models", [])
    return models if isinstance(models, list) else []


_active_status_file: Path | None = None
_active_data: dict[str, Any] | None = None


def set_current_file(path: Path | str | None) -> None:
    if _active_status_file is None or _active_data is None:
        return
    _active_data["current_file"] = str(path) if path is not None else None
    write_status(_active_status_file, _active_data)


def set_step(step: str) -> None:
    if _active_status_file is None or _active_data is None:
        return
    _active_data["step"] = step
    write_status(_active_status_file, _active_data)


@contextmanager
def track_job(
    status_file: Path,
    *,
    command: str,
    target: str,
    allow_parallel: bool = False,
) -> Iterator[None]:
    global _active_status_file, _active_data

    existing = read_status(status_file)
    if existing and not allow_parallel:
        existing_pid = int(existing.get("pid", 0))
        if is_process_alive(existing_pid) and existing_pid != os.getpid():
            raise RuntimeError(
                f"Уже выполняется транскрибация (PID {existing_pid}, "
                f"шаг {existing.get('step')}, файл {existing.get('current_file')}). "
                f"Проверьте: transcribe.py status"
            )

    _active_status_file = status_file
    _active_data = {
        "pid": os.getpid(),
        "command": command,
        "step": command,
        "target": target,
        "current_file": None,
        "started_at": _utc_now(),
    }
    write_status(status_file, _active_data)
    try:
        yield
    finally:
        clear_status(status_file)
        _active_status_file = None
        _active_data = None


def build_status_report(settings_status_file: Path, ollama_host: str) -> dict[str, Any]:
    status_data = read_status(settings_status_file)
    running = bool(status_data and is_process_alive(int(status_data.get("pid", 0))))
    stale_file = bool(status_data and not running)

    if stale_file:
        clear_status(settings_status_file)
        status_data = None

    processes = find_transcribe_processes()
    ollama_models = fetch_ollama_ps(ollama_host)

    return {
        "running": running or bool(processes),
        "tracked": status_data,
        "processes": processes,
        "ollama": ollama_models,
        "status_file": str(settings_status_file),
    }


def print_status_report(report: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    if report["running"]:
        print("Статус: работает")
    else:
        print("Статус: простаивает")

    tracked = report.get("tracked")
    if tracked:
        print(f"PID: {tracked.get('pid')}")
        print(f"Команда: {tracked.get('command')}")
        print(f"Шаг: {tracked.get('step')}")
        print(f"Цель: {tracked.get('target')}")
        if tracked.get("current_file"):
            print(f"Текущий файл: {tracked.get('current_file')}")
        print(f"Запущено: {tracked.get('started_at')}")
        print(f"Обновлено: {tracked.get('updated_at')}")
    elif report["processes"]:
        print("Найдены процессы transcribe.py:")
        for proc in report["processes"]:
            print(f"  PID {proc['pid']}: {proc['command']}")
    else:
        print("Активных процессов transcribe.py не найдено")

    if report["ollama"]:
        print("Ollama (активные модели):")
        for model in report["ollama"]:
            name = model.get("name", model.get("model", "unknown"))
            print(f"  - {name}")
    else:
        print("Ollama: нет активных генераций или сервер недоступен")

    print(f"Файл статуса: {report['status_file']}")
