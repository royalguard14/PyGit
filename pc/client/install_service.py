import ctypes
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_DIR = Path(r"C:\sufyan")
DETAIL_FILE = INSTALL_DIR / "detail.json"
SERVICE_NAME = "SufyanPisoNetTimer"
APP_FILE = INSTALL_DIR / "PisoNetTimer - 32826.py"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
PYTHON = Path(sys.executable)


def admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_admin(cmd):
    subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)


def firewall():
    # Keep these rules scoped to this application and required listener ports.
    rules = [
        ("Sufyan PisoNetTimer TCP 5000", "TCP", "5000"),
        ("Sufyan PisoNetTimer UDP 5050", "UDP", "5050"),
    ]
    for name, proto, port in rules:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        run_admin([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={name}", "dir=in", "action=allow",
            f"protocol={proto}", f"localport={port}", "profile=any"
        ])


def service():
    # Windows Service starts Python without a console/taskbar window.
    pyw = str(PYTHONW if PYTHONW.exists() else PYTHON)
    cmd = f'"{pyw}" "{APP_FILE}"'
    subprocess.run(["sc", "stop", SERVICE_NAME], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    subprocess.run(["sc", "delete", SERVICE_NAME], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    run_admin(["sc", "create", SERVICE_NAME, "binPath=", cmd,
               "start=", "auto", "DisplayName=", "Sufyan PisoNetTimer"])
    run_admin(["sc", "description", SERVICE_NAME,
               "Sufyan PisoNetTimer background client"])
    run_admin(["sc", "failure", SERVICE_NAME, "reset=", "86400",
               "actions=", "restart/5000/restart/5000/restart/10000"])
    run_admin(["sc", "start", SERVICE_NAME])


def main():
    if os.name != "nt":
        raise SystemExit("Windows only")
    if not admin():
        params = " ".join(f'"{x}"' for x in sys.argv)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", str(PYTHON), params, None, 1)
        return

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    source_app = Path(__file__).with_name("PisoNetTimer - 32826.py")
    if source_app.exists() and source_app.resolve() != APP_FILE.resolve():
        shutil.copy2(source_app, APP_FILE)

    if not DETAIL_FILE.exists():
        DETAIL_FILE.write_text(json.dumps({
            "pisonetName": "Sufyan Pisonet",
            "PcName": "PC1",
            "time_open": "06:00",
            "time_close": "24:00",
            "dev_btn": True,
            "RECOVERY_FILE": r"C:/sufyan/recovery.json"
        }, indent=2), encoding="utf-8")

    firewall()
    service()


if __name__ == "__main__":
    main()
