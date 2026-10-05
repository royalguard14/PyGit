import os
import shutil
import subprocess
import sys

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

def run_netsh(args):
    subprocess.run(["netsh", "advfirewall", "firewall"] + args, check=True)

os.makedirs(INSTALL_DIR, exist_ok=True)

for name in (APP_EXE, SERVICE_EXE, UNINSTALLER_EXE, DETAIL_JSON, WALLPAPER):
    copy_file(name)

run_netsh(["delete", "rule", "name=Sufyan PisoNetTimer TCP 5000"])
run_netsh(["delete", "rule", "name=Sufyan PisoNetTimer UDP 5051"])

run_netsh(["add", "rule", "name=Sufyan PisoNetTimer TCP 5000", "dir=in", "action=allow", "protocol=TCP", "localport=5000"])
run_netsh(["add", "rule", "name=Sufyan PisoNetTimer UDP 5051", "dir=in", "action=allow", "protocol=UDP", "localport=5051"])

service_exe = os.path.join(INSTALL_DIR, SERVICE_EXE)
subprocess.run([service_exe, "install"], check=True)
subprocess.run([service_exe, "start"], check=True)

print(f"Sufyan PisoNetTimer installed successfully in {INSTALL_DIR}")
print("Firewall rules added for TCP 5000 and UDP 5051.")