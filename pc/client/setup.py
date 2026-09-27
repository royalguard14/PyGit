import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

GITHUB_BASE = "https://raw.githubusercontent.com/royalguard14/PyGit/main/pc/client/"
CONTROL_URL = GITHUB_BASE + "control.json"

APP_DIR = os.path.join(
    os.environ.get("PROGRAMFILES", r"C:\Program Files"),
    "PisoNetClient",
)
APP_EXE = os.path.join(APP_DIR, "PisoNetClient.exe")
UPDATER_EXE = os.path.join(APP_DIR, "PisoNetSetup.exe")
LOCAL_CONTROL = os.path.join(APP_DIR, "control.json")
LOG_FILE = os.path.join(APP_DIR, "setup.log")

STARTUP_DIR = os.path.join(
    os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
    "Microsoft",
    "Windows",
    "Start Menu",
    "Programs",
    "Startup",
)
STARTUP_LINK = os.path.join(STARTUP_DIR, "PisoNetClient.lnk")
FIREWALL_RULE = "PisoNet Client TCP 5000"

APP_PROCESS = "PisoNetClient.exe"
STOP_WAIT_SECONDS = 15


def log(message):
    os.makedirs(APP_DIR, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    if is_admin():
        return False

    if getattr(sys, "frozen", False):
        executable = sys.executable
        parameters = " ".join(f'"{arg}"' for arg in sys.argv[1:])
    else:
        executable = sys.executable
        parameters = " ".join(
            f'"{arg}"' for arg in [os.path.abspath(sys.argv[0]), *sys.argv[1:]]
        )

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        parameters,
        os.path.dirname(os.path.abspath(sys.argv[0])),
        1,
    )

    if result <= 32:
        raise PermissionError("Administrator privileges are required.")

    return True


def fetch_bytes(url):
    request = urllib.request.Request(
        url + ("&" if "?" in url else "?") + "_=" + os.urandom(8).hex(),
        headers={
            "User-Agent": "PisoNetSetup",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def version_tuple(value):
    try:
        return tuple(int(x) for x in str(value).split("."))
    except Exception:
        return (0,)


def install_firewall():
    result = subprocess.run(
        [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            "name=" + FIREWALL_RULE,
            "dir=in",
            "action=allow",
            "protocol=TCP",
            "localport=5000",
            "profile=any",
            "enable=yes",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    log("[PisoNetSetup] Firewall rule configured (result=%s)." % result.returncode)


def install_startup():
    os.makedirs(STARTUP_DIR, exist_ok=True)

    script = (
        '$ws = New-Object -ComObject WScript.Shell; '
        f'$s = $ws.CreateShortcut("{STARTUP_LINK}"); '
        f'$s.TargetPath = "{UPDATER_EXE}"; '
        f'$s.WorkingDirectory = "{APP_DIR}"; '
        '$s.WindowStyle = 7; '
        '$s.Save()'
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    log("[PisoNetSetup] Startup configured (result=%s)." % result.returncode)


def stop_app():
    result = subprocess.run(
        ["taskkill", "/IM", APP_PROCESS, "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    if result.returncode != 0:
        return True

    deadline = time.time() + STOP_WAIT_SECONDS
    while time.time() < deadline:
        check = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {APP_PROCESS}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if APP_PROCESS.lower() not in check.stdout.lower():
            return True
        time.sleep(0.25)

    return False


def download_app(remote_control):
    app_name = remote_control.get("app", "PisoNetClient.exe")
    download_url = remote_control.get("download", GITHUB_BASE + app_name)

    log("[PisoNetSetup] Downloading " + app_name)

    data = fetch_bytes(download_url)

    os.makedirs(APP_DIR, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".PisoNetClient.",
        suffix=".exe",
        dir=APP_DIR,
    )
    os.close(fd)

    try:
        with open(temp_path, "wb") as f:
            f.write(data)

        if not stop_app():
            raise RuntimeError("PisoNetClient.exe did not stop in time.")

        os.replace(temp_path, APP_EXE)
        log("[PisoNetSetup] PisoNetClient.exe installed.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def load_local_control():
    try:
        with open(LOCAL_CONTROL, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_control(control):
    os.makedirs(APP_DIR, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=".control.",
        suffix=".json",
        dir=APP_DIR,
        text=True,
    )
    os.close(fd)

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(control, f, indent=2)
            f.write("\n")
        os.replace(temp_path, LOCAL_CONTROL)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def install_updater_copy():
    current = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else sys.argv[0])
    current = os.path.normcase(current)
    target = os.path.normcase(os.path.abspath(UPDATER_EXE))

    if current == target:
        return

    os.makedirs(APP_DIR, exist_ok=True)
    shutil.copy2(current, UPDATER_EXE)
    log("[PisoNetSetup] Installer/updater copied to Program Files.")


def launch_app():
    if not os.path.exists(APP_EXE):
        raise FileNotFoundError(APP_EXE)

    subprocess.Popen(
        [APP_EXE],
        cwd=APP_DIR,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log("[PisoNetSetup] PisoNetClient.exe started.")


def main():
    if relaunch_as_admin():
        return

    os.makedirs(APP_DIR, exist_ok=True)
    log("[PisoNetSetup] Starting.")

    remote = json.loads(fetch_bytes(CONTROL_URL).decode("utf-8"))
    if "version" not in remote:
        raise RuntimeError("control.json is missing version.")

    remote_version = version_tuple(remote["version"])
    local = load_local_control()
    local_version = version_tuple(local.get("version", "0.0.0")) if local else (0,)

    first_install = not os.path.exists(APP_EXE)
    needs_update = first_install or remote_version > local_version

    log(
        "[PisoNetSetup] GitHub version=%s local version=%s."
        % (remote.get("version"), local.get("version") if local else "none")
    )

    if needs_update:
        log(
            "[PisoNetSetup] %s version detected."
            % ("Installing" if first_install else "New")
        )
        download_app(remote)
    else:
        log("[PisoNetSetup] Client is already up to date.")

    install_updater_copy()
    save_control(remote)
    install_firewall()
    install_startup()
    launch_app()

    log("[PisoNetSetup] Completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            log("[PisoNetSetup] ERROR: " + str(exc))
        except Exception:
            pass
        raise
