"""Flask-обёртка для локального UI пайплайна транскрибации.

Запуск: .venv/bin/python app.py
Открыть: http://127.0.0.1:8765

Эндпоинты:
  GET  /                       - UI (templates/index.html)
  GET  /api/config             - пути source/raw/clean/summary
  GET  /api/tree               - JSON-дерево source-mp3 с бейджами наличия
  GET  /api/view?path&kind     - текст raw/clean или HTML-рендер summary
  GET  /api/status             - running + .transcribe-status.json
  POST /api/run                - запустить transcribe.py как subprocess
  GET  /api/logs/stream        - SSE: stdout запущенного процесса
  GET  /api/logs?since=N       - буфер логов с позиции N

Без зависимостей сверх requirements.txt. Не модифицирует transcribe.py —
только дёргает его через subprocess и читает его status-файл.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import markdown as md_lib
from flask import Flask, Response, jsonify, request, send_from_directory

from config import load_settings
from status import is_process_alive, read_status

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
log = logging.getLogger("app")

# ---------------------------------------------------------------------------
# Состояние текущего запуска
# ---------------------------------------------------------------------------

# Один процесс Flask — один запущенный subprocess transcribe.py.
_current: dict[str, Any] = {
    "proc": None,
    "pid": 0,
    "started_at": 0.0,
    "command": "",
    "target": "",
    "log_buffer": deque(maxlen=1000),  # (ts, line) — для повторного получения
    "log_seq": 0,                       # монотонный счётчик строк
    "log_event": threading.Event(),     # сигнал "новая строка"
    "done_event": threading.Event(),    # сигнал "процесс завершился"
    "exit_code": None,
}

_state_lock = threading.Lock()  # защищает _current при запуске/завершении


# ---------------------------------------------------------------------------
# Загрузка настроек
# ---------------------------------------------------------------------------

_settings = load_settings()
log.info("Settings: source=%s raw=%s clean=%s summary=%s",
         _settings.source_dir, _settings.raw_dir,
         _settings.clean_dir, _settings.summary_dir)


def _abs(path: Path | str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


# ---------------------------------------------------------------------------
# Вспомогалки: дерево и пути артефактов
# ---------------------------------------------------------------------------

def _output_paths(mp3_abs: Path) -> dict[str, Path | None]:
    """Строит абсолютные пути raw/clean/summary для MP3, импортируя
    функции из transcribe.py. Если путь вне SOURCE_DIR — вернёт None."""
    try:
        from transcribe import output_path_for_mp3  # noqa: PLC0415

        rel = mp3_abs.resolve()
        src = _settings.source_dir.resolve()
        rel.relative_to(src)  # бросит ValueError, если вне
        return {
            "raw": output_path_for_mp3(mp3_abs, _settings.raw_dir, ".txt", _settings),
            "clean": output_path_for_mp3(mp3_abs, _settings.clean_dir, ".txt", _settings),
            "summary": output_path_for_mp3(mp3_abs, _settings.summary_dir, ".md", _settings),
        }
    except (ValueError, Exception):
        return {"raw": None, "clean": None, "summary": None}


def _build_tree() -> dict[str, Any]:
    """Рекурсивное JSON-дерево source_dir. Узлы: dir или file (mp3)."""
    src = _settings.source_dir
    if not src.exists():
        return {"name": src.name, "type": "dir", "missing": True, "children": []}

    def walk(d: Path, rel: Path) -> dict[str, Any]:
        node: dict[str, Any] = {
            "name": d.name,
            "rel": str(rel),
            "type": "dir",
            "children": [],
        }
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return node
        for entry in entries:
            if entry.name.startswith("."):
                continue
            entry_rel = rel / entry.name
            if entry.is_dir():
                node["children"].append(walk(entry, entry_rel))
            elif entry.is_file() and entry.suffix.lower() == ".mp3":
                outs = _output_paths(entry)
                node["children"].append({
                    "name": entry.name,
                    "rel": str(entry_rel),
                    "type": "file",
                    "size_mb": round(entry.stat().st_size / (1024 * 1024), 2),
                    "has_raw": bool(outs["raw"] and outs["raw"].exists()),
                    "has_clean": bool(outs["clean"] and outs["clean"].exists()),
                    "has_summary": bool(outs["summary"] and outs["summary"].exists()),
                })
        return node

    return walk(src, Path("."))


# ---------------------------------------------------------------------------
# /api/run — запуск subprocess
# ---------------------------------------------------------------------------

def _is_running() -> bool:
    with _state_lock:
        proc = _current["proc"]
    if proc is None:
        # На всякий случай: если status-файл указывает на живой PID,
        # а наш словарь пуст (например, после рестарта Flask).
        st = read_status(_settings.status_file)
        if st:
            pid = int(st.get("pid", 0))
            if pid and is_process_alive(pid):
                return True
        return False
    return proc.poll() is None


def _reader_thread(proc: subprocess.Popen) -> None:
    """Читает stdout построчно, кладёт в буфер, шлёт событие."""
    assert proc.stdout is not None
    try:
        for raw_line in proc.stdout:
            try:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            except Exception:
                continue
            with _state_lock:
                _current["log_seq"] += 1
                _current["log_buffer"].append((_current["log_seq"], line))
                _current["log_event"].set()
                _current["log_event"].clear()
    except Exception as exc:  # noqa: BLE001
        log.warning("reader thread error: %s", exc)
    finally:
        proc.wait()
        with _state_lock:
            _current["exit_code"] = proc.returncode
        _current["done_event"].set()


@app.post("/api/run")
def api_run() -> Response:
    body = request.get_json(silent=True) or {}
    command = body.get("command", "").strip()
    target = body.get("path", "").strip()
    match = (body.get("match") or "").strip()
    force = bool(body.get("force"))
    steps = (body.get("steps") or "").strip()

    if command not in {"pipeline", "whisper", "clean", "summary"}:
        return jsonify({"error": f"Неизвестная команда: {command!r}"}), 400
    if not target:
        return jsonify({"error": "Не указан path"}), 400

    # Страховка: если путь относительный и не нашёлся в cwd, попробуем
    # внутри source-mp3/ (фронтенд шлёт пути относительно source-mp3).
    target_path = Path(target)
    if not target_path.is_absolute() and not target_path.exists():
        candidate = _settings.source_dir / target
        if candidate.exists():
            target = str(candidate)

    if _is_running():
        st = read_status(_settings.status_file) or {}
        pid = int(st.get("pid", 0))
        return jsonify({
            "error": "Уже идёт транскрибация",
            "pid": pid,
            "command": st.get("command"),
            "step": st.get("step"),
            "current_file": st.get("current_file"),
        }), 409

    # Собираем argv: venv-python, transcribe.py, command, path, [flags]
    venv_py = BASE_DIR / ".venv" / "bin" / "python"
    if not venv_py.exists():
        venv_py = Path(sys.executable)

    argv: list[str] = [str(venv_py), str(BASE_DIR / "transcribe.py"), command, target]
    if match:
        argv += ["--match", match]
    if force:
        argv.append("--force")
    if command == "pipeline" and steps:
        argv += ["--steps", steps]

    # Сброс состояния
    with _state_lock:
        _current["log_buffer"].clear()
        _current["log_seq"] = 0
        _current["exit_code"] = None
        _current["done_event"].clear()
        _current["command"] = command
        _current["target"] = target
        _current["started_at"] = time.time()

    log.info("Запуск: %s", " ".join(argv))
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        return jsonify({"error": f"Не удалось запустить: {exc}"}), 500

    with _state_lock:
        _current["proc"] = proc
        _current["pid"] = proc.pid

    threading.Thread(target=_reader_thread, args=(proc,), daemon=True).start()

    return jsonify({
        "ok": True,
        "pid": proc.pid,
        "command": command,
        "target": target,
        "match": match,
        "force": force,
        "steps": steps,
    })


# ---------------------------------------------------------------------------
# /api/status — статус + status-файл
# ---------------------------------------------------------------------------

@app.get("/api/status")
def api_status() -> Response:
    st = read_status(_settings.status_file)
    running = _is_running()
    with _state_lock:
        return jsonify({
            "running": running,
            "pid": _current["pid"],
            "command": _current["command"],
            "target": _current["target"],
            "started_at": _current["started_at"] or None,
            "exit_code": _current["exit_code"],
            "log_lines": _current["log_seq"],
            "tracked": st,
            "status_file": str(_settings.status_file),
        })


# ---------------------------------------------------------------------------
# /api/logs/stream — SSE
# ---------------------------------------------------------------------------

def _sse_format(event: str, data: str) -> str:
    # SSE: каждая строка data префиксуется "data: ", event — отдельной строкой
    lines = data.splitlines() or [""]
    out = [f"event: {event}"]
    out += [f"data: {line}" for line in lines]
    out.append("")
    out.append("")
    return "\n".join(out)


@app.get("/api/logs/stream")
def api_logs_stream() -> Response:
    def gen():
        last_seq = 0
        # Сначала отдаём то, что уже накопилось
        with _state_lock:
            buf = list(_current["log_buffer"])
        for seq, line in buf:
            yield _sse_format("log", json.dumps({"seq": seq, "line": line}, ensure_ascii=False))
            last_seq = seq

        while True:
            with _state_lock:
                done = _current["done_event"].is_set()
                buf = list(_current["log_buffer"])
            for seq, line in buf:
                if seq > last_seq:
                    yield _sse_format("log", json.dumps({"seq": seq, "line": line}, ensure_ascii=False))
                    last_seq = seq
            if done:
                with _state_lock:
                    exit_code = _current["exit_code"]
                yield _sse_format("done", json.dumps({"exit_code": exit_code}))
                return
            # Ждём сигнал или таймаут для keep-alive
            _current["log_event"].wait(timeout=15.0)
            yield ": keep-alive\n\n"

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/logs")
def api_logs() -> Response:
    since = int(request.args.get("since", 0))
    with _state_lock:
        buf = [(s, l) for s, l in _current["log_buffer"] if s > since]
        exit_code = _current["exit_code"]
    return jsonify({"lines": [{"seq": s, "line": l} for s, l in buf],
                    "exit_code": exit_code,
                    "log_seq": _current["log_seq"]})


# ---------------------------------------------------------------------------
# /api/config и /api/tree
# ---------------------------------------------------------------------------

@app.get("/api/config")
def api_config() -> Response:
    return jsonify({
        "source_dir": str(_settings.source_dir),
        "raw_dir": str(_settings.raw_dir),
        "clean_dir": str(_settings.clean_dir),
        "summary_dir": str(_settings.summary_dir),
        "status_file": str(_settings.status_file),
        "ollama_host": _settings.ollama_host,
        "ollama_clean_model": _settings.ollama_clean_model,
        "ollama_summary_model": _settings.ollama_summary_model,
        "whisper_model": _settings.whisper_model,
    })


@app.get("/api/tree")
def api_tree() -> Response:
    return jsonify(_build_tree())


# ---------------------------------------------------------------------------
# /api/view — содержимое raw/clean/summary
# ---------------------------------------------------------------------------

@app.get("/api/view")
def api_view() -> Response:
    rel_path = request.args.get("path", "").strip()
    mp3_rel = request.args.get("mp3", "").strip()
    kind = request.args.get("kind", "").strip()
    if kind not in {"raw", "clean", "summary"}:
        return jsonify({"error": f"kind должен быть raw|clean|summary, не {kind!r}"}), 400
    if not rel_path and not mp3_rel:
        return jsonify({"error": "Не указан path или mp3"}), 400

    if mp3_rel:
        # Путь относительно source-mp3 (например, "Занятие 2. Apache Kafka/...part01.mp3")
        try:
            from transcribe import output_path_for_mp3  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"Не удалось импортировать transcribe: {exc}"}), 500
        mp3_abs = (_settings.source_dir / mp3_rel).resolve()
        # Безопасность: mp3 должен быть внутри source_dir
        if _settings.source_dir.resolve() not in mp3_abs.parents:
            return jsonify({"error": f"Путь должен быть внутри {_settings.source_dir}"}), 403
        if not mp3_abs.exists():
            return jsonify({"error": f"MP3 не найден: {mp3_rel}"}), 404
        target_dir = {
            "raw": _settings.raw_dir,
            "clean": _settings.clean_dir,
            "summary": _settings.summary_dir,
        }[kind]
        ext = ".md" if kind == "summary" else ".txt"
        abs_path = output_path_for_mp3(mp3_abs, target_dir, ext, _settings)
    else:
        # Старый путь: абсолютный или относительный к BASE_DIR
        abs_path = _abs(rel_path)

    if not abs_path.exists():
        return jsonify({"error": f"Файл не найден: {abs_path.name}"}), 404

    # Безопасность: только внутри raw/clean/summary
    allowed = {
        "raw": _settings.raw_dir.resolve(),
        "clean": _settings.clean_dir.resolve(),
        "summary": _settings.summary_dir.resolve(),
    }
    if allowed[kind] not in abs_path.resolve().parents:
        return jsonify({"error": f"Путь должен быть внутри {allowed[kind]}"}), 403

    text = abs_path.read_text(encoding="utf-8", errors="replace")
    if kind == "summary":
        try:
            html = md_lib.markdown(text, extensions=["fenced_code", "tables"])
        except Exception as exc:  # noqa: BLE001
            return jsonify({"text": text, "html": None, "error": str(exc)})
        return jsonify({"text": text, "html": html})
    return jsonify({"text": text})


# ---------------------------------------------------------------------------
# /
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> Response:
    resp = send_from_directory(str(BASE_DIR / "templates"), "index.html")
    # Не даём браузеру кешировать — частые правки index.html
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("Открой http://127.0.0.1:8765")
    # use_reloader=False — иначе subprocess-переменные живут в одном процессе,
    # а reader-thread — в другом, и логи теряются.
    app.run(host="127.0.0.1", port=8765, debug=False, use_reloader=False, threaded=True)
