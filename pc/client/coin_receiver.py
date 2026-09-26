import tkinter as tk
from tkinter import ttk

TIME_PER_PULSE = 500  # seconds


class CoinReceiver:
    def __init__(self, root):
        self.root = root
        self.root.title("PyGit Coin Receiver - Side A")
        self.root.geometry("420x300")
        self.root.resizable(False, False)

        self.receiving = False
        self.coins = 0
        self.total_time = 0

        frame = ttk.Frame(root, padding=25)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="PyGit Coin Receiver", font=("Segoe UI", 18, "bold")).pack(pady=(0, 20))

        self.status = ttk.Label(frame, text="Status: NOT RECEIVING", font=("Segoe UI", 11))
        self.status.pack(pady=5)

        self.coins_label = ttk.Label(frame, text="Received Coins: 0", font=("Segoe UI", 12))
        self.coins_label.pack(pady=5)

        self.time_label = ttk.Label(frame, text="Added Time: 0 seconds", font=("Segoe UI", 12))
        self.time_label.pack(pady=5)

        self.receive_button = ttk.Button(frame, text="RECEIVE COINS", command=self.toggle_receiving)
        self.receive_button.pack(pady=25, ipadx=20, ipady=8)

        ttk.Label(frame, text="1 pulse = 500 seconds", font=("Segoe UI", 9)).pack()

        # Test button: simulates one NodeMCU coin event.
        ttk.Button(frame, text="TEST COIN", command=self.receive_coin).pack(pady=8)

    def toggle_receiving(self):
        self.receiving = not self.receiving

        if self.receiving:
            self.status.config(text="Status: RECEIVING COINS")
            self.receive_button.config(text="STOP RECEIVING")
        else:
            self.status.config(text="Status: NOT RECEIVING")
            self.receive_button.config(text="RECEIVE COINS")

    def receive_coin(self):
        if not self.receiving:
            self.status.config(text="Status: NOT RECEIVING (coin ignored)")
            self.root.after(1500, lambda: self.status.config(text="Status: NOT RECEIVING"))
            return

        self.coins += 1
        self.total_time += TIME_PER_PULSE
        self.coins_label.config(text=f"Received Coins: {self.coins}")
        self.time_label.config(text=f"Added Time: {self.total_time} seconds")
        self.status.config(text="Status: COIN RECEIVED (+500 sec)")
        self.root.after(1500, lambda: self.status.config(text="Status: RECEIVING COINS"))


if __name__ == "__main__":
    root = tk.Tk()
    CoinReceiver(root)
    root.mainloop()
