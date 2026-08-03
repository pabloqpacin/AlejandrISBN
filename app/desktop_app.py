"""
Desktop shell: no Docker, no system Python required when frozen with PyInstaller.

Architecture (Windows-safe):
- Parent process: Tk control window + browser + Desktop shortcut
- Child process (``--serve``): Uvicorn in the *main* thread (required on Windows;
  running Uvicorn in a background thread often dies silently)

Closing the window stops the child server.
"""

from __future__ import annotations

import multiprocessing
import os
import socket
import subprocess
import sys
import time
import traceback
import webbrowser
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def _data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    path = base / "AlejandrISBN"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _log_path() -> Path:
    return _data_dir() / "desktop.log"


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _configure_env() -> None:
    """Force SQLite desktop mode and sensible paths before importing the app."""
    os.environ.setdefault("ALEJANDRISBN_BACKEND", "sqlite")
    if os.environ.get("DATABASE_URL", "").lower().startswith("postgres"):
        os.environ.pop("DATABASE_URL", None)
    if not os.environ.get("DATABASE_URL"):
        os.environ["ALEJANDRISBN_BACKEND"] = "sqlite"

    app_dir = _app_dir()
    user_seed = app_dir / "seed"
    bundled_seed = None
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled_seed = Path(sys._MEIPASS) / "seed"

    if user_seed.is_dir():
        os.environ.setdefault("SEED_DIR", str(user_seed))
    elif bundled_seed and bundled_seed.is_dir():
        os.environ.setdefault("SEED_DIR", str(bundled_seed))
    elif (app_dir / "seed").is_dir():
        os.environ.setdefault("SEED_DIR", str(app_dir / "seed"))


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((HOST, port))
            return True
        except OSError:
            return False


def _wait_until_up(timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def _show_error(msg: str) -> None:
    _log(f"ERROR: {msg}")
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, msg[:1500], "AlejandrISBN", 0x10)
            return
        except Exception:
            pass
    print(msg, file=sys.stderr)


def _ensure_desktop_shortcut() -> None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return

    marker = _data_dir() / ".desktop-shortcut-ok"
    if marker.exists():
        return

    exe = Path(sys.executable).resolve()
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    if not desktop.is_dir():
        desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        return

    import json

    lnk = desktop / "AlejandrISBN.lnk"
    target = json.dumps(str(exe))
    workdir = json.dumps(str(exe.parent))
    shortcut = json.dumps(str(lnk))
    ps = (
        "$s = New-Object -ComObject WScript.Shell; "
        f"$l = $s.CreateShortcut({shortcut}); "
        f"$l.TargetPath = {target}; "
        f"$l.WorkingDirectory = {workdir}; "
        "$l.Description = 'AlejandrISBN'; "
        "$l.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            check=False,
            capture_output=True,
            text=True,
        )
        marker.write_text("1", encoding="utf-8")
        _log(f"Desktop shortcut created: {lnk}")
    except Exception as exc:
        _log(f"Shortcut failed: {exc}")


def _serve_forever() -> int:
    """Run Uvicorn in this process (must be main thread — used by ``--serve`` child)."""
    _configure_env()
    _log(f"serve start backend={os.environ.get('ALEJANDRISBN_BACKEND')} cwd={os.getcwd()}")
    try:
        import asyncio

        import uvicorn
        from app.main import app

        # Explicit asyncio loop: avoid Windows Proactor quirks with defaults in threads.
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        config = uvicorn.Config(
            app,
            host=HOST,
            port=PORT,
            log_level="info",
            access_log=True,
            loop="asyncio",
            http="h11",
            lifespan="on",
        )
        server = uvicorn.Server(config)
        asyncio.run(server.serve())
        return 0
    except Exception:
        err = traceback.format_exc()
        _log(err)
        raise


def _serve_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(sys.executable), "--serve"]
    return [sys.executable, "-m", "app.desktop_app", "--serve"]


def _stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    if os.name == "nt" and proc.pid:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass


def _show_window(on_close) -> None:
    import tkinter as tk

    root = tk.Tk()
    root.title("AlejandrISBN")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=20, pady=16)
    frame.pack()

    tk.Label(frame, text="AlejandrISBN", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    tk.Label(
        frame,
        text="La biblioteca está en marcha.\nCierra esta ventana para salir.",
        justify="left",
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=(8, 12))
    tk.Label(frame, text=URL, fg="#1f4a36", font=("Segoe UI", 10)).pack(anchor="w")

    tk.Button(frame, text="Abrir en el navegador", command=lambda: webbrowser.open(URL)).pack(
        anchor="w", pady=(14, 0)
    )

    def handle_close() -> None:
        on_close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", handle_close)
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"+{x}+{y}")
    root.mainloop()


def _tail_log(max_chars: int = 1200) -> str:
    path = _log_path()
    if not path.exists():
        return "(sin log)"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:] if text else "(log vacío)"
    except Exception as exc:
        return f"(no se pudo leer el log: {exc})"


def main() -> int:
    multiprocessing.freeze_support()

    if "--serve" in sys.argv:
        try:
            return _serve_forever()
        except Exception:
            return 1

    _configure_env()
    _log("launcher start")

    if not _port_free(PORT):
        webbrowser.open(URL)
        _ensure_desktop_shortcut()
        _show_error(f"AlejandrISBN ya estaba en marcha (o el puerto {PORT} está ocupado).\nSe abrió {URL}")
        return 0

    log_file = _log_path()
    # Truncate previous run log for easier debugging
    try:
        log_file.write_text("", encoding="utf-8")
    except Exception:
        pass
    _log("spawning --serve child")

    creationflags = 0
    if os.name == "nt":
        # Detach from GUI console; keep stdout/stderr redirected to log
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    child_log = log_file.open("a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            _serve_command(),
            cwd=str(_app_dir()),
            stdout=child_log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            env=os.environ.copy(),
        )
    except Exception as exc:
        child_log.close()
        _show_error(f"No se pudo lanzar el servidor:\n{exc}")
        return 1

    try:
        if not _wait_until_up(timeout=60.0):
            _stop_process(proc)
            detail = _tail_log()
            _show_error(
                "No se pudo arrancar el servidor en el puerto 8000.\n\n"
                f"Log: {log_file}\n\n"
                f"{detail}"
            )
            return 1

        if proc.poll() is not None:
            _show_error(
                f"El servidor se cerró solo (código {proc.returncode}).\n\n"
                f"Log: {log_file}\n\n{_tail_log()}"
            )
            return 1

        _ensure_desktop_shortcut()
        webbrowser.open(URL)
        _show_window(on_close=lambda: _stop_process(proc))
        _stop_process(proc)
        _log("launcher exit ok")
        return 0
    finally:
        try:
            child_log.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        err = traceback.format_exc()
        _log(err)
        _show_error(err[-1500:])
        raise SystemExit(1)
