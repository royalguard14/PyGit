import json
import msvcrt
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

GITHUB_RAW = "https://raw.githubusercontent.com/royalguard14/PyGit/main/"
CHECK_INTERVAL = 60

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.join(BASE_DIR, ".pygit_runtime")
RUNTIME_CODE = os.path.join(RUNTIME_DIR, "code.py")
RUNTIME_CONTROL = os.path.join(RUNTIME_DIR, "control.json")
BACKUP_CODE = os.path.join(RUNTIME_DIR, "code.previous.py")
LOG_FILE = os.path.join(RUNTIME_DIR, "pygit.log")


def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def get_remote(path):
    url = GITHUB_RAW + path.lstrip("/") + "?_=" + str(time.time_ns())

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PyGit-Live/3.1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8")


def parse_version(version):
    try:
        return tuple(int(x) for x in str(version).split("."))
    except (ValueError, AttributeError):
        return (0,)


def save_file(path, content):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=".pygit_",
        dir=folder,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def load_local_control():
    if not os.path.exists(RUNTIME_CONTROL):
        return None

    try:
        with open(RUNTIME_CONTROL, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def validate_code(code):
    compile(code, RUNTIME_CODE, "exec")


def install_remote(remote_control, remote_code):
    validate_code(remote_code)

    os.makedirs(RUNTIME_DIR, exist_ok=True)

    if os.path.exists(RUNTIME_CODE):
        shutil.copy2(RUNTIME_CODE, BACKUP_CODE)

    save_file(RUNTIME_CODE, remote_code)
    save_file(
        RUNTIME_CONTROL,
        json.dumps(remote_control, indent=2) + "\n",
    )


def fetch_remote_control():
    remote_control = json.loads(get_remote("control.json"))

    if "version" not in remote_control or "code" not in remote_control:
        raise ValueError("Invalid control.json: version and code are required.")

    return remote_control


def ensure_runtime():
    os.makedirs(RUNTIME_DIR, exist_ok=True)

    control = load_local_control()

    if control and os.path.exists(RUNTIME_CODE):
        return control

    log("[PYGIT] No local runtime found. Downloading current GitHub version...")

    remote_control = fetch_remote_control()
    remote_code = get_remote(remote_control["code"])

    install_remote(remote_control, remote_code)

    log(f"[PYGIT] Installed version {remote_control['version']}.")
    return remote_control


def start_code(control):
    log(f"[PYGIT] Running version {control['version']}")

    return subprocess.Popen(
        [sys.executable, RUNTIME_CODE],
        cwd=BASE_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def stop_code(process):
    if process and process.poll() is None:
        log("[PYGIT] Stopping application...")
        process.terminate()

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            log("[PYGIT] Application did not stop gracefully. Killing it...")
            process.kill()
            process.wait()


def check_for_update(current_control):
    remote_control = fetch_remote_control()

    remote_version = remote_control["version"]
    local_version = current_control.get("version", "0.0.0")

    if parse_version(remote_version) <= parse_version(local_version):
        return current_control, False

    log(f"[UPDATE] {local_version} -> {remote_version}")
    log("[UPDATE] Downloading new application code...")

    remote_code = get_remote(remote_control["code"])
    install_remote(remote_control, remote_code)

    log("[UPDATE] Code compiled and installed.")
    return remote_control, True


def main():
    print("================================")
    print("          PyGit Live")
    print("================================")
    print(f"Checking GitHub every {CHECK_INTERVAL} seconds...")
    print("")

    process = None

    try:
        control = ensure_runtime()
        process = start_code(control)

        while True:
            if os.name == "nt" and msvcrt.kbhit():
                key = msvcrt.getwch()
                if key.lower() == "q":
                    log("[PYGIT] Q received. Shutting down...")
                    stop_code(process)
                    break

            time.sleep(CHECK_INTERVAL)

            try:
                new_control, updated = check_for_update(control)

                if updated:
                    log("[PYGIT] Restarting application...")
                    stop_code(process)
                    control = new_control
                    process = start_code(control)

                elif process.poll() is not None:
                    log("[PYGIT] Application stopped; restarting local code.")
                    process = start_code(control)

            except (urllib.error.URLError, urllib.error.HTTPError) as e:
                log(f"[PYGIT] GitHub check failed: {e}")

            except Exception as e:
                log(f"[PYGIT] Update check failed: {e}")

    except KeyboardInterrupt:
        log("[PYGIT] Keyboard interrupt received. Stopping...")
        stop_code(process)

    except Exception as e:
        log(f"[PYGIT] Startup failed: {e}")
        stop_code(process)


if __name__ == "__main__":
    main()
