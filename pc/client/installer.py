import os
import shutil
import subprocess
import sys
import time
import winreg
import tkinter as tk
from tkinter import messagebox

INSTALL_DIR = r"C:\sufyan"
APP_EXE = "SufyanPisoNetTimer.exe"
SERVICE_EXE = "SufyanPisoNetTimerService.exe"
UNINSTALLER_EXE = "uninstall_helper.exe"
DETAIL_JSON = "detail.json"
WALLPAPER = "wallpapersden.com_valorant-hd-gaming_1920x1080.jpg"
SERVICE_NAME = "SufyanPisoNetTimer"


def source_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def copy_file(name):
    src = os.path.join(source_dir(), name)
    dst = os.path.join(INSTALL_DIR, name)
    if not os.path.isfile(src):
        raise FileNotFoundError(f"Installer payload is missing: {src}")
    shutil.copy2(src, dst)


def set_kiosk_policies():
    explorer_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, explorer_path) as key:
        values = {
            "NoClose": 1, "NoLogoff": 1, "NoSwitchUser": 1,
            "NoStartMenuMorePrograms": 1, "NoStartMenuMyGames": 1,
            "NoStartMenuMyMusic": 1, "NoStartMenuMyPictures": 1,
            "NoStartMenuMyVideos": 1, "NoRecentDocsMenu": 1,
            "NoRecentDocsHistory": 1, "NoWinKeys": 1,
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)

    system_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, system_path) as key:
        for name in ("DisableTaskMgr", "DisableLockWorkstation", "DisableChangePassword"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)


def run_netsh(args, check=True):
    return subprocess.run(["netsh", "advfirewall", "firewall"] + args, check=check, capture_output=True, text=True)


def run_sc(args, check=True):
    return subprocess.run(["sc.exe"] + args, check=check, capture_output=True, text=True)


def install_service():
    service_exe = os.path.join(INSTALL_DIR, SERVICE_EXE)
    run_sc(["stop", SERVICE_NAME], check=False)
    run_sc(["delete", SERVICE_NAME], check=False)
    # SCM deletion can be asynchronous; wait until the old registration is gone.
    for _ in range(10):
        query = run_sc(["query", SERVICE_NAME], check=False)
        if query.returncode != 0:
            break
        time.sleep(1)

    subprocess.run(
        [service_exe, "--startup", "auto", "install"],
        check=True, capture_output=True, text=True
    )

    # Windows restarts the service after unexpected process failures.
    run_sc(["failure", SERVICE_NAME, "reset=", "86400",
            "actions=", "restart/5000/restart/15000/restart/30000"])
    run_sc(["failureflag", SERVICE_NAME, "1"])
    run_sc(["config", SERVICE_NAME, "start=", "auto"])

    subprocess.run([service_exe, "start"], check=True, capture_output=True, text=True)


def install():
    os.makedirs(INSTALL_DIR, exist_ok=True)
    for name in (APP_EXE, SERVICE_EXE, UNINSTALLER_EXE, DETAIL_JSON, WALLPAPER):
        copy_file(name)

    run_netsh(["delete", "rule", "name=Sufyan PisoNetTimer TCP 5000"], check=False)
    run_netsh(["delete", "rule", "name=Sufyan PisoNetTimer UDP 5051"], check=False)
    run_netsh(["add", "rule", "name=Sufyan PisoNetTimer TCP 5000",
               "dir=in", "action=allow", "protocol=TCP", "localport=5000"])
    run_netsh(["add", "rule", "name=Sufyan PisoNetTimer UDP 5051",
               "dir=in", "action=allow", "protocol=UDP", "localport=5051"])

    install_service()
    set_kiosk_policies()


def main():
    try:
        install()
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "PisoNet Setup",
            "PisoNet client installation completed successfully.\n"
            "The Windows service is configured to start automatically "
            "and recover after unexpected failures."
        )
        root.destroy()
    except Exception as exc:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "PisoNet Setup - Installation Failed",
                f"{type(exc).__name__}: {exc}\n\n"
                "Check that you ran the installer as Administrator."
            )
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
