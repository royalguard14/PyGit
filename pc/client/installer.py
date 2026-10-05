import os
import shutil
import subprocess
import sys
import winreg

INSTALL_DIR = r"C:\sufyan"
APP_EXE = "SufyanPisoNetTimer.exe"
SERVICE_EXE = "SufyanPisoNetTimerService.exe"
UNINSTALLER_EXE = "uninstall_helper.exe"
DETAIL_JSON = "detail.json"
WALLPAPER = "wallpapersden.com_valorant-hd-gaming_1920x1080.jpg"


def source_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def copy_file(name):
    src = os.path.join(source_dir(), name)
    dst = os.path.join(INSTALL_DIR, name)
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    shutil.copy2(src, dst)


def set_kiosk_policies():
    path = r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer"
    key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, path)
    for name, value in {
        "NoClose": 1,
        "NoLogoff": 1,
        "NoSwitchUser": 1,
        "NoStartMenuMorePrograms": 1,
        "NoStartMenuMyGames": 1,
        "NoStartMenuMyMusic": 1,
        "NoStartMenuMyPictures": 1,
        "NoStartMenuMyVideos": 1,
        "NoRecentDocsMenu": 1,
        "NoRecentDocsHistory": 1,
        "NoWinKeys": 1,
    }.items():
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
    winreg.CloseKey(key)

    path = r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System"
    key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, path)
    winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
    winreg.SetValueEx(key, "DisableLockWorkstation", 0, winreg.REG_DWORD, 1)
    winreg.SetValueEx(key, "DisableChangePassword", 0, winreg.REG_DWORD, 1)
    winreg.CloseKey(key)


def run_netsh(args, check=True):
    return subprocess.run(
        ["netsh", "advfirewall", "firewall"] + args,
        check=check
    )


os.makedirs(INSTALL_DIR, exist_ok=True)

for name in (APP_EXE, SERVICE_EXE, UNINSTALLER_EXE, DETAIL_JSON, WALLPAPER):
    copy_file(name)

# Removing an old rule is cleanup only. It is normal for the rule
# not to exist on a fresh PC, so a failed delete must not abort install.
run_netsh(["delete", "rule", "name=Sufyan PisoNetTimer TCP 5000"], check=False)
run_netsh(["delete", "rule", "name=Sufyan PisoNetTimer UDP 5051"], check=False)

run_netsh([
    "add", "rule",
    "name=Sufyan PisoNetTimer TCP 5000",
    "dir=in", "action=allow", "protocol=TCP", "localport=5000"
])

run_netsh([
    "add", "rule",
    "name=Sufyan PisoNetTimer UDP 5051",
    "dir=in", "action=allow", "protocol=UDP", "localport=5051"
])

service_exe = os.path.join(INSTALL_DIR, SERVICE_EXE)
subprocess.run([service_exe, "--startup", "auto", "install"], check=True)
subprocess.run([service_exe, "start"], check=True)
set_kiosk_policies()

print(f"Sufyan PisoNetTimer installed successfully in {INSTALL_DIR}")
print("Firewall rules added for TCP 5000 and UDP 5051.")
