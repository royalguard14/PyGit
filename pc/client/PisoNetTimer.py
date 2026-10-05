def show_overlay():
    global overlay, overlay_active, slide_index, insert_coin_button, status_label, coin_window_label, coin_progress_canvas, coin_window_frame

    if overlay_active:
        return

    overlay_active = True

    overlay = tk.Toplevel()
    overlay.attributes("-fullscreen", True)
    overlay.overrideredirect(True)
    overlay.attributes("-topmost", True)

    canvas = tk.Canvas(overlay)
    canvas.pack(fill="both", expand=True)

    overlay.configure(cursor="arrow")

    def insert_coin():
        toggle_coin_receiving()

    insert_coin_button = tk.Button(
        overlay,
        text="INSERT COIN",
        command=insert_coin,
        font=("Arial", 24, "bold"),
        padx=48,
        pady=16,
        cursor="hand2",
        state="normal",
        bg="#22c55e",
        fg="white",
        activebackground="#16a34a",
        activeforeground="white",
        relief="raised",
        bd=4,
        highlightthickness=2,
        highlightbackground="white"
    )
    insert_coin_button.place(relx=0.5, rely=0.90, anchor="center")
