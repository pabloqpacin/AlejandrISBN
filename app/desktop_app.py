"""
Desktop shell: no Docker, no system Python required when frozen with PyInstaller.

- Starts the FastAPI/Uvicorn server in a background thread (SQLite).
- Opens the browser.
- Shows a small control window; closing it stops the app.
- Optionally creates a Desktop shortcut on first run (Windows).
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


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
    # Writable folder next to the .exe (user can drop JSON backups here)
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


def _wait_until_up(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _ensure_desktop_shortcut() -> None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return

    marker = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AlejandrISBN" / ".desktop-shortcut-ok"
    if marker.exists():
        return

    exe = Path(sys.executable).resolve()
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    if not desktop.is_dir():
        desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        return

    import json
    import subprocess

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
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except Exception:
        pass


def _run_server() -> None:
    import uvicorn
    from app.main import app

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", access_log=False)


def _show_window() -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("AlejandrISBN")
    root.resizable(False, False)
    root.attributes("-topmost", False)

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

    def open_browser() -> None:
        webbrowser.open(URL)

    btn = tk.Button(frame, text="Abrir en el navegador", command=open_browser)
    btn.pack(anchor="w", pady=(14, 0))

    def on_close() -> None:
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    # Center roughly
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"+{x}+{y}")

    try:
        root.mainloop()
    except Exception as exc:
        messagebox.showerror("AlejandrISBN", str(exc))


def main() -> int:
    _configure_env()

    if not _port_free(PORT):
        # Already running — just open the UI
        webbrowser.open(URL)
        _ensure_desktop_shortcut()
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"AlejandrISBN ya estaba en marcha.\nSe abrió {URL}",
                "AlejandrISBN",
                0x40,
            )
        return 0

    server = threading.Thread(target=_run_server, name="uvicorn", daemon=True)
    server.start()

    if not _wait_until_up():
        msg = "No se pudo arrancar el servidor en el puerto 8000."
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, msg, "AlejandrISBN", 0x10)
        else:
            print(msg, file=sys.stderr)
        return 1

    _ensure_desktop_shortcut()
    webbrowser.open(URL)
    _show_window()
    # Window closed → process exit kills daemon thread
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        err = traceback.format_exc()
        if os.name == "nt":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(0, err[-1000:], "AlejandrISBN — error", 0x10)
            except Exception:
                print(err, file=sys.stderr)
        else:
            print(err, file=sys.stderr)
        raise SystemExit(1)
