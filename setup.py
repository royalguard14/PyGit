import json
import os
import tempfile
import urllib.request

GITHUB_RAW = "https://raw.githubusercontent.com/royalguard14/PyGit/main/"
LOCAL_CONTROL = "control.json"
LOCAL_CODE = "code.txt"


def get_remote(path):
    with urllib.request.urlopen(GITHUB_RAW + path, timeout=10) as response:
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


def main():
    print("Checking PyGit for updates...")

    remote_control = json.loads(get_remote("control.json"))
    remote_version = remote_control["version"]

    local_version = "0.0.0"
    if os.path.exists(LOCAL_CONTROL):
        try:
            with open(LOCAL_CONTROL, "r", encoding="utf-8") as f:
                local_control = json.load(f)
            local_version = local_control.get("version", "0.0.0")
        except (json.JSONDecodeError, OSError):
            pass

    print(f"Local version:  {local_version}")
    print(f"Remote version: {remote_version}")

    if parse_version(remote_version) > parse_version(local_version):
        print("Update available!")
        print("Updating...")

        code = get_remote(remote_control["code"])
        save_file(LOCAL_CODE, code)
        save_file(LOCAL_CONTROL, json.dumps(remote_control, indent=2) + "\n")

        print("Update complete.\n")
    else:
        print("Already up to date.\n")

    with open(LOCAL_CODE, "r", encoding="utf-8") as f:
        code = f.read()

    with open(LOCAL_CONTROL, "r", encoding="utf-8") as f:
        control = json.load(f)

    print(f"Running PyGit version: {control['version']}")
    print("Running local code...\n")

    exec(compile(code, control["code"], "exec"), {"__name__": "__main__"})


if __name__ == "__main__":
    main()
