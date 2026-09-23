import json
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
RUNTIME_REQUIREMENTS = os.path.join(RUNTIME_DIR, "requirements.txt")
BACKUP_CODE = os.path.join(RUNTIME_DIR, "code.previous.py")
LOG_FILE = os.path.join(RUNTIME_DIR, "pygit.log")


class GitHubFetchError(Exception):
    pass


def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def get_remote(path):
    path = path.lstrip("/")
    url = GITHUB_RAW + path

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PyGit-Live/4.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8")

    except urllib.error.HTTPError as e:
        raise GitHubFetchError(
            f"GitHub returned HTTP {e.code} while fetching {path}"
        ) from e

    except urllib.error.URLError as e:
        raise GitHubFetchError(
            f"GitHub connection failed while fetching {path}: {e.reason}"
        ) from e

    except UnicodeDecodeError as e:
        raise GitHubFetchError(
            f"Invalid text response while fetching {path}: {e}"
        ) from e


def parse_version(version):
    try:
        return tuple(int(x) for x in str(version).split("."))
    except (ValueError, AttributeError):
        return (0,)


def is_newer_version(remote_version, local_version):
    return parse_version(remote_version) > parse_version(local_version)


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
    if not getattr(sys, "frozen", False):
        return [sys.executable]

    python_exe = shutil.which("python")
    if python_exe:
        return [python_exe]

    py_launcher = shutil.which("py")
    if py_launcher:
        return [py_launcher, "-3"]

    raise RuntimeError(
        "Python is required to run downloaded code and install dependencies."
    )


def install_dependencies(requirements):
    requirements = requirements.strip()

    if not requirements:
        if load_local_requirements().strip():
            save_file(RUNTIME_REQUIREMENTS, "")
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
    compile(code, RUNTIME_CODE, "exec")


def install_remote(remote_control, remote_code, requirements):
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


def fetch_control():
    try:
        remote_control = json.loads(get_remote("control.json"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid control.json from GitHub: {e}") from e

    if "version" not in remote_control or "code" not in remote_control:
        raise RuntimeError(
            "Invalid control.json: version and code are required."
        )

    return remote_control


def ensure_runtime():
    os.makedirs(RUNTIME_DIR, exist_ok=True)

    control = load_local_control()

    if control and os.path.exists(RUNTIME_CODE):
        return control

    log("[PYGIT] No local runtime found. Downloading current GitHub version...")

    remote_control = fetch_control()
    remote_code = get_remote(remote_control["code"])

    try:
        remote_requirements = get_remote("requirements.txt")
    except GitHubFetchError as e:
        if "HTTP 404" in str(e):
            remote_requirements = ""
        else:
            raise

    install_remote(
        remote_control,
        remote_code,
        remote_requirements,
    )

    log(f"[PYGIT] Installed version {remote_control['version']}.")
    return remote_control


def start_code(control):
    log(f"[PYGIT] Running version {control['version']}")
    log("[PYGIT] Starting code.py...")

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
    remote_control = fetch_control()

    remote_version = remote_control["version"]
    local_version = current_control.get("version", "0.0.0")

    if not is_newer_version(remote_version, local_version):
        return current_control, False

    log(f"[PYGIT] New version detected: {remote_version}")
    log("[PYGIT] Downloading new code...")

    remote_code = get_remote(remote_control["code"])

    try:
        remote_requirements = get_remote("requirements.txt")
    except GitHubFetchError as e:
        if "HTTP 404" in str(e):
            remote_requirements = ""
        else:
            raise

    install_remote(
        remote_control,
        remote_code,
        remote_requirements,
    )

    log("[PYGIT] New code installed.")
    return remote_control, True


def main():
    process = None

    try:
        control = ensure_runtime()

        try:
            new_control, updated = check_for_update(control)

            if updated:
                control = new_control

        except GitHubFetchError as e:
            log(f"[PYGIT] Initial GitHub check failed: {e}")

        except Exception as e:
            log(f"[PYGIT] Initial update check failed: {e}")

        process = start_code(control)

        while True:
            time.sleep(CHECK_INTERVAL)

            try:
                new_control, updated = check_for_update(control)

                if updated:
                    log("[PYGIT] Restarting application...")
                    stop_code(process)

                    control = new_control
                    process = start_code(control)
                    continue

            except GitHubFetchError as e:
                log(f"[PYGIT] GitHub check failed: {e}")

            except Exception as e:
                log(f"[PYGIT] Update check failed: {e}")

            # Do not restart a naturally exited application here.
            # The supervisor only restarts code.py when a NEW GitHub
            # version is detected.

    except KeyboardInterrupt:
        log("[PYGIT] Keyboard interrupt received. Stopping...")
        stop_code(process)

    except Exception as e:
        log(f"[PYGIT] Startup failed: {e}")
        stop_code(process)


if __name__ == "__main__":
    main()
