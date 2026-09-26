import socket
import threading
import tkinter as tk
from tkinter import ttk

PC_NAME = "PC2"
PC_PORT = 5000
NODEMCU_IP = "192.168.1.23"
NODEMCU_PORT = 5001
TIME_PER_PULSE = 500  # seconds


def get_local_ip():
    """Get the PC's LAN IP address without opening a listening connection."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((NODEMCU_IP, NODEMCU_PORT))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class CoinReceiver:
    def __init__(self, root):
        self.root = root
        self.root.title("PyGit Coin Receiver - Side B")
        self.root.geometry("460x360")
        self.root.resizable(False, False)

        self.receiving = False
        self.requesting = False
        self.coins = 0
        self.total_time = 0
        self.local_ip = get_local_ip()

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", PC_PORT))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)

        self.server_thread = threading.Thread(
            target=self.listen_for_nodemcu,
            daemon=True
        )
        self.server_thread.start()

        self.node_socket = None
        self.node_lock = threading.Lock()

        frame = ttk.Frame(root, padding=25)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="PyGit Coin Receiver",
            font=("Segoe UI", 18, "bold")
        ).pack(pady=(0, 12))

        ttk.Label(
            frame,
            text=f"PC: {PC_NAME}    IP: {self.local_ip}:{PC_PORT}",
            font=("Segoe UI", 9)
        ).pack(pady=(0, 8))

        self.status = ttk.Label(
            frame,
            text="Status: NOT RECEIVING",
            font=("Segoe UI", 11)
        )
        self.status.pack(pady=5)

        self.coins_label = ttk.Label(
            frame,
            text="Received Coins: 0",
            font=("Segoe UI", 12)
        )
        self.coins_label.pack(pady=5)

        self.time_label = ttk.Label(
            frame,
            text="Added Time: 0 seconds",
            font=("Segoe UI", 12)
        )
        self.time_label.pack(pady=5)

        self.receive_button = ttk.Button(
            frame,
            text="RECEIVE COINS",
            command=self.toggle_receiving
        )
        self.receive_button.pack(pady=20, ipadx=20, ipady=8)

        ttk.Label(
            frame,
            text="1 pulse = 500 seconds",
            font=("Segoe UI", 9)
        ).pack()

        # Temporary local test. Remove later when hardware testing is complete.
        ttk.Button(
            frame,
            text="TEST COIN",
            command=self.receive_coin
        ).pack(pady=10)

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def set_status(self, message):
        self.root.after(0, lambda: self.status.config(text=message))

    def connect_to_nodemcu(self):
        """Open the control connection to NodeMCU on TCP port 5001."""
        try:
            sock = socket.create_connection(
                (NODEMCU_IP, NODEMCU_PORT),
                timeout=5
            )
            sock.settimeout(5)

            request = f"REQUEST|{PC_NAME}|{self.local_ip}|{PC_PORT}\n"
            sock.sendall(request.encode("utf-8"))

            response = sock.recv(256).decode("utf-8", errors="ignore").strip()

            if response.startswith("ACCEPT"):
                with self.node_lock:
                    if self.node_socket:
                        try:
                            self.node_socket.close()
                        except OSError:
                            pass
                    self.node_socket = sock
                return True, response

            sock.close()
            return False, response or "REJECT|UNKNOWN"

        except OSError as exc:
            return False, f"ERROR|{exc}"

    def release_from_nodemcu(self):
        """Tell NodeMCU that this PC no longer wants coin input."""
        with self.node_lock:
            sock = self.node_socket

        if not sock:
            return

        try:
            sock.sendall(f"RELEASE|{PC_NAME}\n".encode("utf-8"))
            sock.settimeout(2)
            sock.recv(128)
        except OSError:
            pass
        finally:
            with self.node_lock:
                if self.node_socket is sock:
                    self.node_socket = None
            try:
                sock.close()
            except OSError:
                pass

    def toggle_receiving(self):
        if self.receiving:
            self.receiving = False
            self.release_from_nodemcu()
            self.receive_button.config(text="RECEIVE COINS")
            self.set_status("Status: NOT RECEIVING")
            return

        self.requesting = True
        self.receive_button.config(state="disabled")
        self.set_status("Status: REQUESTING NODEMCU...")

        # Do the network request outside Tkinter's main thread.
        threading.Thread(
            target=self.request_receiving,
            daemon=True
        ).start()

    def request_receiving(self):
        accepted, response = self.connect_to_nodemcu()

        if accepted:
            self.receiving = True
            self.requesting = False
            self.root.after(0, lambda: self.receive_button.config(
                text="STOP RECEIVING", state="normal"
            ))
            self.set_status("Status: RECEIVING COINS")
            return

        self.receiving = False
        self.requesting = False

        if response.startswith("REJECTED|ACTIVE|"):
            parts = response.split("|")
            active_pc = parts[2] if len(parts) > 2 else "another PC"
            self.set_status(f"Status: {active_pc} IS RECEIVING")
        elif response.startswith("REJECT") or response.startswith("REJECTED|"):
            self.set_status("Status: ANOTHER PC IS RECEIVING")
        else:
            self.set_status("Status: NODEMCU CONNECTION FAILED")

        self.root.after(0, lambda: self.receive_button.config(
            text="RECEIVE COINS", state="normal"
        ))
        self.root.after(2500, self.restore_idle_status)

    def restore_idle_status(self):
        if not self.receiving:
            self.status.config(text="Status: NOT RECEIVING")

    def listen_for_nodemcu(self):
        """Listen on TCP 5000 for coin messages from NodeMCU."""
        while True:
            try:
                client, address = self.server_socket.accept()
            except socket.timeout:
                if self.server_socket.fileno() < 0:
                    return
                continue
            except OSError:
                return

            threading.Thread(
                target=self.handle_nodemcu_connection,
                args=(client, address),
                daemon=True
            ).start()

    def handle_nodemcu_connection(self, client, address):
        try:
            client.settimeout(None)
            buffer = ""

            while True:
                data = client.recv(1024)
                if not data:
                    break

                buffer += data.decode("utf-8", errors="ignore")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    if line == "PYGIT READY":
                        self.set_status("Status: NODEMCU CONNECTED")
                        continue

                    if line.startswith("COIN:"):
                        try:
                            seconds = int(line.split(":", 1)[1])
                        except ValueError:
                            continue

                        # A coin is only counted while this PC is active.
                        if self.receiving:
                            self.receive_coin(seconds)
                            try:
                                client.sendall(b"COIN_RECEIVED\\n")
                            except OSError:
                                pass

        except OSError:
            pass
        finally:
            try:
                client.close()
            except OSError:
                pass

    def receive_coin(self, seconds=None):
        if not self.receiving:
            self.set_status("Status: NOT RECEIVING (coin ignored)")
            self.root.after(
                1500,
                self.restore_idle_status
            )
            return

        if seconds is None:
            seconds = TIME_PER_PULSE

        self.coins += 1
        self.total_time += seconds

        self.root.after(
            0,
            lambda: self.coins_label.config(
                text=f"Received Coins: {self.coins}"
            )
        )
        self.root.after(
            0,
            lambda: self.time_label.config(
                text=f"Added Time: {self.total_time} seconds"
            )
        )
        self.set_status(f"Status: COIN RECEIVED (+{seconds} sec)")
        self.root.after(
            1500,
            lambda: self.status.config(text="Status: RECEIVING COINS")
            if self.receiving else None
        )

    def close(self):
        if self.receiving:
            self.release_from_nodemcu()

        try:
            self.server_socket.close()
        except OSError:
            pass

        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    CoinReceiver(root)
    root.mainloop()
