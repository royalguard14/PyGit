import tkinter as tk

# ============================================================
# PISONET KIOSK BASIC TEST
# ============================================================
# True  = normal/client-usable mode (TOP HALF only for testing)
# False = kiosk mode (FULL SCREEN)
USABLE = True


def main():
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)

    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()

    if USABLE:
        # SAFE TEST MODE: use only the top half of the screen.
        app_height = height // 2
        root.geometry(f"{width}x{app_height}+0+0")
    else:
        # FUTURE KIOSK MODE: occupy the entire screen.
        root.geometry(f"{width}x{height}+0+0")

    root.configure(bg="black")
    root.attributes("-alpha", 0.3)
    root.focus_force()

    label = tk.Label(
        root,
        text="PISONET KIOSK\n\nBasic Test\n\nUSABLE = " + str(USABLE),
        font=("Consolas", 32, "bold"),
        fg="#00FF00",
        bg="black",
        justify="center",
    )
    label.place(relx=0.5, rely=0.5, anchor="center")

    # Temporary test timeout so the PC is never locked indefinitely.
    root.after(50000, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
