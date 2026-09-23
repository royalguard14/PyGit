import json
import urllib.request

GITHUB_RAW = "https://raw.githubusercontent.com/royalguard14/PyGit/main/"


def get_remote(path):
    with urllib.request.urlopen(GITHUB_RAW + path, timeout=10) as response:
        return response.read().decode("utf-8")


def main():
    control = json.loads(get_remote("control.json"))
    code = get_remote(control["code"])

    print(f"PyGit version: {control['version']}")
    print("Running remote code...\n")
    exec(compile(code, control["code"], "exec"), {"__name__": "__main__"})


if __name__ == "__main__":
    main()
