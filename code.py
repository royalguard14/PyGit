import tkinter as tk

def main():
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)

    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()
    root.geometry(f"{width}x{height}+0+0")

    root.configure(bg="black")
    root.attributes("-alpha", 0.3)
    root.focus_force()
    root.grab_set()

    label = tk.Label(
        root,
        text="Hello world",
        font=("Consolas", 48, "bold"),
        fg="#00FF00",
        bg="black",
    )
    label.place(relx=0.5, rely=0.5, anchor="center")

    root.after(50000, root.destroy)
    root.mainloop()

if __name__ == "__main__":
    main()
