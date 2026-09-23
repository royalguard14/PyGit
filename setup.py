import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

GITHUB_RAW = "https://raw.githubusercontent.com/royalguard14/PyGit/main/"
LOCAL_CONTROL = "control.json"
LOCAL_CODE = "code.txt"
CHECK_INTERVAL = 5


def get_remote(path):
    # Cache-buster prevents GitHub's raw CDN from serving an older copy.
    separator = "&" if "?" in path else "?"
    url = GITHUB_RAW + path + separator + "_=" + str(time.time_ns())

    request = urllib.request.Request(
        url,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"}
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8")


def parse_version(version):
    try:
        return tuple(int(x) for x in version.split("."))
    except (ValueError, AttributeError):
        return (0,)


def save_file(path, content):
    folder = os.path.dirname(os.path.abspath(path))
    fd, temp_path = tempfile.mkstemp(prefix=".pygit_", dir=folder, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def load_local_control():
    if not os.path.exists(LOCAL_CONTROL):
        return None

    try:
        with open(LOCAL_CONTROL, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def update_from_github():
    remote_control = json.loads(get_remote("control.json"))
    remote_version = remote_control["version"]

    local_control = load_local_control()
    local_version = local_control.get("version", "0.0.0") if local_control else "0.0.0"

    if parse_version(remote_version) > parse_version(local_version):
        print(f"\n[UPDATE] {local_version} -> {remote_version}")
        print("[UPDATE] Downloading new code...")

        code = get_remote(remote_control["code"])
        save_file(LOCAL_CODE, code)
        save_file(LOCAL_CONTROL, json.dumps(remote_control, indent=2) + "\n")

        print("[UPDATE] Update complete.")
        return remote_control, True

    return local_control or remote_control, False


def start_code(control):
    print(f"\n[PYGIT] Running version {control['version']}")
    print("[PYGIT] Press Q then ENTER to quit.\n")

    return subprocess.Popen(
        [sys.executable, LOCAL_CODE],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )


def stop_code(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()


def main():
    print("================================")
    print("          PyGit Live")
    print("================================")
    print(f"Checking GitHub every {CHECK_INTERVAL} seconds...")
    print("")

    try:
        control, updated = update_from_github()

        if not os.path.exists(LOCAL_CODE):
            code = get_remote(control["code"])
            save_file(LOCAL_CODE, code)

        if not os.path.exists(LOCAL_CONTROL):
            save_file(LOCAL_CONTROL, json.dumps(control, indent=2) + "\n")

        process = start_code(control)

        while True:
            time.sleep(CHECK_INTERVAL)

            if os.name == "nt":
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key.lower() == "q":
                        print("\n[PYGIT] Q received. Shutting down...")
                        stop_code(process)
                        break

            try:
                remote_control = json.loads(get_remote("control.json"))
                local_control = load_local_control() or {}
                local_version = local_control.get("version", "0.0.0")
                remote_version = remote_control["version"]

                if parse_version(remote_version) > parse_version(local_version):
                    print(f"\n[PYGIT] New version detected: {remote_version}")

                    code = get_remote(remote_control["code"])
                    save_file(LOCAL_CODE, code)
                    save_file(LOCAL_CONTROL, json.dumps(remote_control, indent=2) + "\n")

                    print("[PYGIT] New code downloaded.")
                    print("[PYGIT] Restarting application...")

                    stop_code(process)
                    control = remote_control
                    process = start_code(control)

                else:
                    print(".", end="", flush=True)

            except Exception as e:
                print(f"\n[PYGIT] Update check failed: {e}")

    except KeyboardInterrupt:
        print("\n[PYGIT] Stopping...")
        try:
            stop_code(process)
        except UnboundLocalError:
            pass


if __name__ == "__main__":
    main()
