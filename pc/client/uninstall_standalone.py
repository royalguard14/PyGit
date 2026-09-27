import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

APP_NAME = "PisoNetStandalone.exe"


def main():
    app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    app_path = os.path.join(app_dir, APP_NAME)
    uninstaller_path = os.path.abspath(sys.argv[0])

    try:
        if not messagebox.askyesno(
            "PisoNet Standalone",
            "Uninstall PisoNet Standalone?\n\nThis will remove the standalone EXE."
        ):
            return
    except Exception:
        pass

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", APP_NAME],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass

    delete_cmd = (
        'ping 127.0.0.1 -n 3 >nul & '
        f'del /f /q "{app_path}" >nul 2>&1 & '
        f'del /f /q "{uninstaller_path}" >nul 2>&1'
    )

    try:
        subprocess.Popen(
            ["cmd", "/c", delete_cmd],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
    except Exception as exc:
        try:
            messagebox.showerror("Uninstall failed", str(exc))
        except Exception:
            pass
        return

    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("PisoNet Standalone", "Uninstall started.")
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    main()
