import ctypes
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

GITHUB_BASE = "https://raw.githubusercontent.com/royalguard14/PyGit/main/pc/client/"
CONTROL_URL = GITHUB_BASE + "control.json"

APP_DIR = os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "PisoNetClient")
APP_EXE = os.path.join(APP_DIR, "PisoNetClient.exe")
LOCAL_CONTROL = os.path.join(APP_DIR, "control.json")
LOG_FILE = os.path.join(APP_DIR, "setup.log")
STARTUP_DIR = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
FIREWALL_RULE = "PisoNet Client TCP 5000"


def log(message):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def require_admin():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Administrator privileges are required.")


def fetch_text(url):
    request = urllib.request.Request(
        url + ("&" if "?" in url else "?") + "_=" + str(os.urandom(8).hex()),
        headers={"User-Agent": "PisoNetSetup", "Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def version_tuple(value):
    try:
        return tuple(int(x) for x in str(value).split("."))
    except Exception:
        return (0,)


def install_firewall():
    subprocess.run(
        ["netsh", "advfirewall", "firewall", "add", "rule",
         "name=" + FIREWALL_RULE, "dir=in", "action=allow",
         "protocol=TCP", "localport=5000", "profile=any", "enable=yes"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def install_startup():
    os.makedirs(STARTUP_DIR, exist_ok=True)
    shortcut = os.path.join(STARTUP_DIR, "PisoNetClient.lnk")
    script = (
        '$ws = New-Object -ComObject WScript.Shell; '
        '$s = $ws.CreateShortcut([Environment]::GetFolderPath("CommonStartup") + "\\PisoNetClient.lnk"); '
        f'$s.TargetPath = "{APP_EXE}"; $s.WorkingDirectory = "{APP_DIR}"; '
        '$s.WindowStyle = 7; $s.Save()'
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def stop_app():
    subprocess.run(["taskkill", "/IM", "PisoNetClient.exe", "/F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def update_app(remote_control):
    app_name = remote_control.get("app", "PisoNetClient.exe")
    download_url = remote_control.get("download", GITHUB_BASE + app_name)
    data = fetch_text(download_url)

    os.makedirs(APP_DIR, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".PisoNetClient.", suffix=".exe", dir=APP_DIR)
    os.close(fd)

    try:
        with open(temp_path, "wb") as f:
            f.write(data)
        stop_app()
        os.replace(temp_path, APP_EXE)
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
    fd, temp_path = tempfile.mkstemp(prefix=".control.", suffix=".json", dir=APP_DIR, text=True)
    os.close(fd)
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(control, f, indent=2)
            f.write("\n")
        os.replace(temp_path, LOCAL_CONTROL)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def launch():
    subprocess.Popen([APP_EXE], cwd=APP_DIR, creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    require_admin()
    os.makedirs(APP_DIR, exist_ok=True)

    try:
        remote = json.loads(fetch_text(CONTROL_URL).decode("utf-8"))
        if "version" not in remote:
            raise RuntimeError("control.json is missing version.")

        local = load_local_control()
        needs_update = not os.path.exists(APP_EXE)

        if local and not needs_update:
            needs_update = version_tuple(remote["version"]) > version_tuple(local.get("version", "0.0.0"))

        if needs_update:
            log("[PisoNetSetup] Installing/updating PisoNetClient " + str(remote["version"]))
            update_app(remote)

        save_control(remote)
        install_firewall()
        install_startup()
        launch()
        log("[PisoNetSetup] Installation/update completed.")

    except Exception as exc:
        log("[PisoNetSetup] ERROR: " + str(exc))
        raise


if __name__ == "__main__":
    main()
