import json
import msvcrt
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
import urllib.error
import urllib.request

GITHUB_RAW = "https://raw.githubusercontent.com/royalguard14/PyGit/main/"
CHECK_INTERVAL = 60

# PyGit keeps its own private Python runtime. Clients do not need to
# install Python system-wide.
PYTHON_VERSION = "3.12.10"
PYTHON_RUNTIME_URL = (
    "https://www.python.org/ftp/python/3.12.10/"
    "python-3.12.10-embed-amd64.zip"
)
PYTHON_RUNTIME_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".pygit_python"
)
PYTHON_EXE = os.path.join(PYTHON_RUNTIME_DIR, "python.exe")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.join(BASE_DIR, ".pygit_runtime")
RUNTIME_CODE = os.path.join(RUNTIME_DIR, "code.py")
RUNTIME_CONTROL = os.path.join(RUNTIME_DIR, "control.json")
RUNTIME_REQUIREMENTS = os.path.join(RUNTIME_DIR, "requirements.txt")
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
    # GitHub Raw is used instead of the GitHub Contents API.
    # A cache-busting query keeps live-update testing responsive.
    url = GITHUB_RAW + path.lstrip("/") + "?_=" + str(time.time_ns())

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PyGit-Live/2.5",
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


def load_local_requirements():
    if not os.path.exists(RUNTIME_REQUIREMENTS):
        return ""

    try:
        with open(RUNTIME_REQUIREMENTS, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def get_python_command():
    # Once the private runtime exists, always use it.
    if os.path.exists(PYTHON_EXE):
        return [PYTHON_EXE]

    # During first bootstrap, use the interpreter that launched setup.py.
    return [sys.executable]


def bootstrap_private_python():
    if os.path.exists(PYTHON_EXE):
        return

    log(f"[PYGIT] Private Python {PYTHON_VERSION} not found. Installing...")
    os.makedirs(PYTHON_RUNTIME_DIR, exist_ok=True)

    fd, archive_path = tempfile.mkstemp(
        prefix=".pygit_python_", suffix=".zip", dir=BASE_DIR
    )
    os.close(fd)

    try:
        request = urllib.request.Request(
            PYTHON_RUNTIME_URL,
            headers={"User-Agent": "PyGit-Live/2.6"},
        )
        with urllib.request.urlopen(request, timeout=60) as response, open(
            archive_path, "wb"
        ) as out:
            shutil.copyfileobj(response, out)

        with zipfile.ZipFile(archive_path, "r") as archive:
            archive.extractall(PYTHON_RUNTIME_DIR)

        if not os.path.exists(PYTHON_EXE):
            raise RuntimeError(
                "Private Python installation completed without python.exe."
            )

        # Enable site-packages for the Windows embeddable distribution.
        pth_files = [
            name for name in os.listdir(PYTHON_RUNTIME_DIR)
            if name.endswith("._pth")
        ]
        if not pth_files:
            raise RuntimeError(
                "Python embeddable configuration file was not found."
            )

        pth_path = os.path.join(PYTHON_RUNTIME_DIR, pth_files[0])
        with open(pth_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        if "Lib\\site-packages" not in lines:
            lines.insert(0, "Lib\\site-packages")
        if "import site" not in lines:
            lines.append("import site")
        save_file(pth_path, "\n".join(lines) + "\n")

        # The embeddable package does not include pip.
        get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
        get_pip_path = os.path.join(PYTHON_RUNTIME_DIR, "get-pip.py")
        request = urllib.request.Request(
            get_pip_url,
            headers={"User-Agent": "PyGit-Live/2.6"},
        )
        with urllib.request.urlopen(request, timeout=60) as response, open(
            get_pip_path, "wb"
        ) as out:
            shutil.copyfileobj(response, out)

        result = subprocess.run(
            [PYTHON_EXE, get_pip_path, "--no-warn-script-location"],
            cwd=BASE_DIR,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Private pip installation failed with exit code "
                f"{result.returncode}."
            )

        os.remove(get_pip_path)
        log("[PYGIT] Private Python is ready.")

    except Exception:
        shutil.rmtree(PYTHON_RUNTIME_DIR, ignore_errors=True)
        raise
    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)


def install_dependencies(requirements):
    requirements = requirements.strip()

    # No third-party dependencies are required.
    if not requirements:
        if load_local_requirements().strip():
            save_file(RUNTIME_REQUIREMENTS, "")
        log("[PYGIT] No external dependencies required.")
        return

    if requirements == load_local_requirements().strip():
        return

    log("[PYGIT] Installing/updating application dependencies...")

    os.makedirs(RUNTIME_DIR, exist_ok=True)

    fd, temp_requirements = tempfile.mkstemp(
        prefix=".pygit_requirements_",
        dir=RUNTIME_DIR,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(requirements + "\n")

        command = get_python_command() + [
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            temp_requirements,
        ]

        result = subprocess.run(
            command,
            cwd=BASE_DIR,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Dependency installation failed with exit code "
                f"{result.returncode}."
            )

        save_file(RUNTIME_REQUIREMENTS, requirements + "\n")
        log("[PYGIT] Dependencies ready.")

    finally:
        if os.path.exists(temp_requirements):
            os.remove(temp_requirements)


def validate_code(code):
    # Compile first so a broken Python file is never installed.
    compile(code, RUNTIME_CODE, "exec")


def install_remote(remote_control, remote_code, requirements):
    # Dependencies must be ready before the new application is installed.
    install_dependencies(requirements)
    validate_code(remote_code)

    os.makedirs(RUNTIME_DIR, exist_ok=True)

    if os.path.exists(RUNTIME_CODE):
        shutil.copy2(RUNTIME_CODE, BACKUP_CODE)

    save_file(RUNTIME_CODE, remote_code)
    save_file(
        RUNTIME_CONTROL,
        json.dumps(remote_control, indent=2) + "\n",
    )


def update_from_github():
    remote_control = json.loads(get_remote("control.json"))

    if "version" not in remote_control or "code" not in remote_control:
        raise ValueError("Invalid control.json: version and code are required.")

    remote_version = remote_control["version"]
    local_control = load_local_control()
    local_version = (
        local_control.get("version", "0.0.0")
        if local_control
        else "0.0.0"
    )

    if parse_version(remote_version) <= parse_version(local_version):
        return local_control, False

    log(f"[UPDATE] {local_version} -> {remote_version}")
    log("[UPDATE] Downloading new application code...")

    remote_code = get_remote(remote_control["code"])
    remote_requirements = get_remote("requirements.txt")

    install_remote(
        remote_control,
        remote_code,
        remote_requirements,
    )

    log("[UPDATE] Code compiled and installed.")
    return remote_control, True


def ensure_runtime():
    os.makedirs(RUNTIME_DIR, exist_ok=True)

    control = load_local_control()

    if control and os.path.exists(RUNTIME_CODE):
        # Existing installations also get dependency updates if GitHub
        # publishes a changed requirements.txt.
        try:
            remote_requirements = get_remote("requirements.txt")
            install_dependencies(remote_requirements)
        except Exception as e:
            log(f"[PYGIT] Dependency check failed: {e}")

        return control

    log("[PYGIT] No local runtime found. Downloading current GitHub version...")

    remote_control = json.loads(get_remote("control.json"))
    remote_code = get_remote(remote_control["code"])
    remote_requirements = get_remote("requirements.txt")

    install_remote(
        remote_control,
        remote_code,
        remote_requirements,
    )
    return remote_control


def start_code(control):
    log(f"[PYGIT] Running version {control['version']}")
    log("[PYGIT] Press Q to quit.")

    return subprocess.Popen(
        get_python_command() + [RUNTIME_CODE],
        cwd=BASE_DIR,
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
    remote_control = json.loads(get_remote("control.json"))

    remote_version = remote_control["version"]
    local_version = current_control.get("version", "0.0.0")

    if parse_version(remote_version) <= parse_version(local_version):
        return current_control, False

    log(f"[PYGIT] New version detected: {remote_version}")
    log("[PYGIT] Downloading new code...")

    remote_code = get_remote(remote_control["code"])
    remote_requirements = get_remote("requirements.txt")

    install_remote(
        remote_control,
        remote_code,
        remote_requirements,
    )

    log("[PYGIT] New code compiled and installed.")
    return remote_control, True


def main():
    bootstrap_private_python()

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
            # Check keyboard without blocking the application.
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
                    # The application ended normally. Keep PyGit silent.
                    pass

            except (urllib.error.URLError, urllib.error.HTTPError) as e:
                log(f"[PYGIT] GitHub check failed: {e}")
            except Exception as e:
                log(f"[PYGIT] Update check failed: {e}")

    except KeyboardInterrupt:
        log("[PYGIT] Keyboard interrupt received. Stopping...")
        stop_code(process)

    except Exception as e:
        log(f"[PYGIT] Startup failed: {e}")
        if process:
            stop_code(process)


if __name__ == "__main__":
    main()
