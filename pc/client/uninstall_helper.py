import os
import subprocess
import sys
import tempfile
import time

SERVICE_NAME = "SufyanPisoNetTimer"
INSTALL_DIR = r"C:\sufyan"


def run(cmd):
    return subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW
    )


def main():
    try:
        parent_pid = int(sys.argv[1])
    except Exception:
        parent_pid = 0

    run(["sc", "stop", SERVICE_NAME])
    time.sleep(2)
    run(["sc", "delete", SERVICE_NAME])

    run(["netsh", "advfirewall", "firewall", "delete", "rule",
         "name=Sufyan PisoNetTimer TCP 5000"])
    run(["netsh", "advfirewall", "firewall", "delete", "rule",
         "name=Sufyan PisoNetTimer UDP 5050"])

    script = os.path.join(tempfile.gettempdir(), "sufyan_pisonetimer_cleanup.cmd")
    this_pid = os.getpid()

    lines = [
        "@echo off",
        ":wait",
        f'tasklist /FI "PID eq {parent_pid}" 2>NUL | find "{parent_pid}" >NUL',
        "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto wait)",
        f'tasklist /FI "PID eq {this_pid}" 2>NUL | find "{this_pid}" >NUL',
        "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto wait)",
        f'rmdir /s /q "{INSTALL_DIR}"',
        f'del /f /q "%~f0"'
    ]

    with open(script, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    subprocess.Popen(
        ["cmd", "/c", script],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True
    )


if __name__ == "__main__":
    main()
