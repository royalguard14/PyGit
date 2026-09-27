import ctypes
import os
import subprocess
import sys
import tempfile

APP_DIR = os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "PisoNetClient")
STARTUP_DIR = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
FIREWALL_RULES = ["PisoNet TCP 5000", "PisoNet Client TCP 5000"]

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def relaunch_admin():
    if is_admin():
        return False
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable,
        " ".join(f'"{a}"' for a in sys.argv[1:]),
        os.path.dirname(os.path.abspath(sys.argv[0])), 1
    )
    if result <= 32:
        raise PermissionError("Administrator privileges are required.")
    return True

def stop_old_apps():
    for name in ["PisoNet.exe", "PisoNetClient.exe", "PisoNetSetup.exe"]:
        subprocess.run(
            ["taskkill", "/IM", name, "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )

def remove_firewall():
    for rule in FIREWALL_RULES:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule", "name=" + rule],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )

def remove_startup():
    for name in ["PisoNet.lnk", "PisoNetClient.lnk"]:
        path = os.path.join(STARTUP_DIR, name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

def main():
    if relaunch_admin():
        return

    stop_old_apps()
    remove_firewall()
    remove_startup()

    script_fd, script_path = tempfile.mkstemp(prefix="PisoNetUninstall.", suffix=".cmd", text=True)
    os.close(script_fd)

    current = os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("@echo off\n")
        f.write("timeout /t 2 /nobreak >nul\n")
        f.write(f'rmdir /s /q "{APP_DIR}" >nul 2>&1\n')
        f.write(f'del /q "{current}" >nul 2>&1\n')
        f.write('del /q "%~f0" >nul 2>&1\n')

    subprocess.Popen(
        ["cmd", "/c", script_path],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )

if __name__ == "__main__":
    main()
