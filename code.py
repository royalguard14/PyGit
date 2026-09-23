import tkinter as tk

# ============================================================
# PISONET KIOSK BASIC TEST
# ============================================================
# SAFE TEST MODE: True = top half only, auto-closes after 50 sec.
# Future kiosk mode: set False to use full screen.
USABLE = True
VERSION = "3.0.4"


def main():
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)

    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()

    if USABLE:
        app_height = height // 2
        root.geometry(f"{width}x{app_height}+0+0")
    else:
        root.geometry(f"{width}x{height}+0+0")

    root.configure(bg="black")
    root.attributes("-alpha", 0.3)
    root.focus_force()

    label = tk.Label(
        root,
        text=f"PISONET KIOSK\\n\\nPyGit Auto-Update TEST\\n\\nVERSION {VERSION}",
        font=("Consolas", 32, "bold"),
        fg="#00FF00",
        bg="black",
        justify="center",
    )
    label.place(relx=0.5, rely=0.5, anchor="center")

    root.after(50000, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
