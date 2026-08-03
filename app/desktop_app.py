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


def _ensure_user_seed_dir() -> None:
    """Create seed/ next to the .exe with a short README (first run / missing folder)."""
    seed = _app_dir() / "seed"
    try:
        seed.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        _log(f"Could not create seed dir: {exc}")
        return

    readme = seed / "README.txt"
    if readme.exists():
        return

    bundled = None
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / "packaging" / "windows-seed-README.txt"
        if candidate.is_file():
            bundled = candidate
    repo_copy = _app_dir() / "packaging" / "windows-seed-README.txt"
    if bundled is None and repo_copy.is_file():
        bundled = repo_copy

    try:
        if bundled is not None:
            readme.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            readme.write_text(
                "Pon aquí un JSON exportado y reinicia AlejandrISBN para importarlo.\n",
                encoding="utf-8",
            )
        _log(f"Created {readme}")
    except Exception as exc:
        _log(f"Could not write seed README: {exc}")


def _configure_env() -> None:
    """Force SQLite desktop mode and sensible paths before importing the app."""
    os.environ.setdefault("ALEJANDRISBN_BACKEND", "sqlite")
    if os.environ.get("DATABASE_URL", "").lower().startswith("postgres"):
        os.environ.pop("DATABASE_URL", None)
    if not os.environ.get("DATABASE_URL"):
        os.environ["ALEJANDRISBN_BACKEND"] = "sqlite"

    if getattr(sys, "frozen", False):
        _ensure_user_seed_dir()

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


def _is_windows_desktop_build() -> bool:
    """True only for the packaged Windows .exe — never for Docker/Linux/dev."""
    return os.name == "nt" and bool(getattr(sys, "frozen", False))


def _ssl_context():
    """CA bundle that works inside the frozen Windows .exe (system store often missing)."""
    import ssl

    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _fetch_latest_release() -> dict:
    import json
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    from app.version import get_github_repo

    repo = get_github_repo()
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "AlejandrISBN-Updater",
        },
    )
    try:
        with urlopen(req, timeout=30, context=_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"GitHub API HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Sin red / GitHub: {exc.reason}") from exc


def _find_setup_asset(release: dict) -> tuple[str, str]:
    for asset in release.get("assets") or []:
        name = asset.get("name") or ""
        if name.lower() == "alejandrisbn-setup.exe":
            url = asset.get("browser_download_url")
            if url:
                return url, name
    for asset in release.get("assets") or []:
        name = (asset.get("name") or "").lower()
        if name.endswith("setup.exe"):
            url = asset.get("browser_download_url")
            if url:
                return url, asset.get("name") or "AlejandrISBN-Setup.exe"
    raise RuntimeError(
        "El release no incluye AlejandrISBN-Setup.exe.\n"
        "Publica un tag para que build-windows lo adjunte."
    )


def _download_file(url: str, dest: Path) -> None:
    from urllib.request import Request, urlopen

    req = Request(url, headers={"User-Agent": "AlejandrISBN-Updater"})
    with urlopen(req, timeout=120, context=_ssl_context()) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)


def _write_and_launch_updater(setup_path: Path) -> None:
    exe = Path(sys.executable).resolve()
    script = _data_dir() / "apply-update.ps1"
    ps = f"""
$ErrorActionPreference = 'Stop'
$setup = {setup_path.as_posix()!r}
$exe = {exe.as_posix()!r}
$pidToWait = {os.getpid()}
try {{
  Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue
}} catch {{}}
Start-Sleep -Seconds 2
$setupArgs = @('/VERYSILENT','/NORESTART','/SUPPRESSMSGBOXES','/CLOSEAPPLICATIONS=yes')
Start-Process -FilePath $setup -ArgumentList $setupArgs -Wait
Start-Sleep -Seconds 1
if (Test-Path -LiteralPath $exe) {{
  Start-Process -FilePath $exe
}}
"""
    script.write_text(ps, encoding="utf-8")
    _log(f"launching updater script {script}")
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script),
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _show_window(on_close) -> None:
    import threading
    import tkinter as tk
    from tkinter import messagebox

    from app.version import get_version, is_newer, normalize_version

    root = tk.Tk()
    root.title("AlejandrISBN")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=20, pady=16)
    frame.pack()

    version = get_version()
    tk.Label(frame, text="AlejandrISBN", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    tk.Label(
        frame,
        text="La biblioteca está en marcha.\nCierra esta ventana para salir.",
        justify="left",
        font=("Segoe UI", 10),
    ).pack(anchor="w", pady=(8, 8))
    tk.Label(frame, text=URL, fg="#1f4a36", font=("Segoe UI", 10)).pack(anchor="w")
    tk.Label(frame, text=f"Versión {version}", fg="#666666", font=("Segoe UI", 9)).pack(
        anchor="w", pady=(6, 0)
    )

    status = tk.Label(frame, text="", justify="left", font=("Segoe UI", 9), wraplength=320)
    status.pack(anchor="w", pady=(8, 0))

    btn_row = tk.Frame(frame)
    btn_row.pack(anchor="w", pady=(14, 0))

    tk.Button(btn_row, text="Abrir en el navegador", command=lambda: webbrowser.open(URL)).pack(
        side="left"
    )

    update_btn: object | None = None

    def handle_close() -> None:
        on_close()
        root.destroy()

    def run_update_flow() -> None:
        btn = update_btn
        assert btn is not None
        btn.configure(state="disabled")
        status.configure(text="Comprobando en GitHub…")

        def work() -> None:
            try:
                release = _fetch_latest_release()
                remote = normalize_version(release.get("tag_name") or release.get("name") or "")
                if not remote:
                    raise RuntimeError("Release sin tag")
                local = normalize_version(get_version())
                if not is_newer(remote, local):

                    def up_to_date() -> None:
                        status.configure(text=f"Ya estás al día ({local}).")
                        btn.configure(state="normal")
                        messagebox.showinfo(
                            "AlejandrISBN",
                            f"No hay actualizaciones.\nVersión actual: {local}",
                        )

                    root.after(0, up_to_date)
                    return

                url, asset_name = _find_setup_asset(release)

                def ask() -> None:
                    ok = messagebox.askyesno(
                        "AlejandrISBN",
                        f"Hay una versión nueva: {remote}\n"
                        f"(tú tienes {local})\n\n"
                        "Se descargará el instalador y se aplicará solo.\n"
                        "Tus libros no se borran.\n\n¿Actualizar ahora?",
                    )
                    if not ok:
                        status.configure(text="")
                        btn.configure(state="normal")
                        return
                    status.configure(text=f"Descargando {asset_name}…")

                    def download_and_apply() -> None:
                        try:
                            dest = _data_dir() / asset_name
                            _download_file(url, dest)
                            _log(f"downloaded update to {dest}")
                            _write_and_launch_updater(dest)

                            def finish() -> None:
                                status.configure(text="Instalando… la app se cerrará.")
                                on_close()
                                root.destroy()

                            root.after(0, finish)
                        except Exception as exc:
                            err = str(exc)
                            _log(f"update failed: {err}")

                            def fail() -> None:
                                status.configure(text="Error al actualizar.")
                                btn.configure(state="normal")
                                messagebox.showerror("AlejandrISBN", err)

                            root.after(0, fail)

                    threading.Thread(target=download_and_apply, daemon=True).start()

                root.after(0, ask)
            except Exception as exc:
                err = str(exc)
                _log(f"update check failed: {err}")

                def fail_check() -> None:
                    status.configure(text="No se pudo comprobar la actualización.")
                    btn.configure(state="normal")
                    messagebox.showerror("AlejandrISBN", err)

                root.after(0, fail_check)

        threading.Thread(target=work, daemon=True).start()

    if _is_windows_desktop_build():
        update_btn = tk.Button(btn_row, text="Buscar actualizaciones", command=run_update_flow)
        update_btn.pack(side="left", padx=(8, 0))

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
