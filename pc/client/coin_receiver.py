import socket
import threading
import tkinter as tk
from tkinter import ttk
from concurrent.futures import ThreadPoolExecutor, as_completed

PC_NAME = "PC1"
PC_PORT = 5000
NODEMCU_PORT = 5001
TIME_PER_PULSE = 10  # minutes
DISCOVERY_TIMEOUT = 0.35
DISCOVERY_WORKERS = 32


def get_local_ip():
    """Get this PC's LAN IP without requiring a connection to the NodeMCU."""
    for target in ("8.8.8.8", "1.1.1.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((target, 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            pass
        finally:
            sock.close()

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass

    return "127.0.0.1"


def discover_nodemcu(local_ip):
    """Find a PyGit NodeMCU by scanning this PC's local /24 subnet."""
    parts = local_ip.split(".")
    if len(parts) != 4 or any(not p.isdigit() for p in parts):
        return None, "INVALID LOCAL IP"

    prefix = ".".join(parts[:3])
    candidates = [f"{prefix}.{i}" for i in range(1, 255) if i != int(parts[3])]

    def probe(ip):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(DISCOVERY_TIMEOUT)
        try:
            sock.connect((ip, NODEMCU_PORT))
            sock.settimeout(1.5)
            request = f"REQUEST|{PC_NAME}|{local_ip}|{PC_PORT}\n"
            sock.sendall(request.encode("utf-8"))
            response = sock.recv(256).decode("utf-8", errors="ignore").strip()

            if response.startswith("ACCEPTED|") or response.startswith("REJECTED|ACTIVE|"):
                return ip, sock, response

            sock.close()
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
        return None

    with ThreadPoolExecutor(max_workers=DISCOVERY_WORKERS) as executor:
        futures = [executor.submit(probe, ip) for ip in candidates]
        for future in as_completed(futures):
            result = future.result()
            if result:
                ip, sock, response = result
                return ip, (sock, response)

    return None, None


class CoinReceiver:
    def __init__(self, root):
        self.root = root
        self.root.title("PyGit Coin Receiver - Side A")
        self.root.geometry("460x360")
        self.root.resizable(False, False)

        self.receiving = False
        self.requesting = False
        self.coins = 0
        self.total_time = 0
        self.local_ip = get_local_ip()
        self.nodemcu_ip = None

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", PC_PORT))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)

        self.server_thread = threading.Thread(target=self.listen_for_nodemcu, daemon=True)
        self.server_thread.start()

        self.node_socket = None
        self.node_lock = threading.Lock()

        frame = ttk.Frame(root, padding=25)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="PyGit Coin Receiver", font=("Segoe UI", 18, "bold")).pack(pady=(0, 12))
        ttk.Label(frame, text=f"PC: {PC_NAME}    IP: {self.local_ip}:{PC_PORT}", font=("Segoe UI", 9)).pack(pady=(0, 8))

        self.status = ttk.Label(frame, text="Status: NOT RECEIVING", font=("Segoe UI", 11))
        self.status.pack(pady=5)

        self.coins_label = ttk.Label(frame, text="Received Coins: 0", font=("Segoe UI", 12))
        self.coins_label.pack(pady=5)

        self.time_label = ttk.Label(frame, text="Added Time: 0 minutes", font=("Segoe UI", 12))
        self.time_label.pack(pady=5)

        self.receive_button = ttk.Button(frame, text="RECEIVE COINS", command=self.toggle_receiving)
        self.receive_button.pack(pady=20, ipadx=20, ipady=8)

        ttk.Label(frame, text="1 pulse = 10 minutes", font=("Segoe UI", 9)).pack()

        ttk.Button(frame, text="TEST COIN", command=self.receive_coin).pack(pady=10)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def set_status(self, message):
        self.root.after(0, lambda: self.status.config(text=message))

    def connect_to_nodemcu(self):
        node_ip, discovery = discover_nodemcu(self.local_ip)

        if not node_ip or not discovery:
            return False, "ERROR|NODEMCU NOT FOUND"

        sock, response = discovery
        self.nodemcu_ip = node_ip

        if response.startswith("ACCEPTED|"):
            with self.node_lock:
                if self.node_socket:
                    try: self.node_socket.close()
                    except OSError: pass
                self.node_socket = sock
            return True, response

        sock.close()
        return False, response or "REJECT|UNKNOWN"

    def release_from_nodemcu(self):
        with self.node_lock:
            sock = self.node_socket
        if not sock: return
        try:
            sock.sendall(f"RELEASE|{PC_NAME}\n".encode("utf-8"))
            sock.settimeout(2)
            sock.recv(128)
        except OSError:
            pass
        finally:
            with self.node_lock:
                if self.node_socket is sock: self.node_socket = None
            try: sock.close()
            except OSError: pass

    def toggle_receiving(self):
        if self.receiving:
            self.receiving = False
            self.release_from_nodemcu()
            self.receive_button.config(text="RECEIVE COINS")
            self.set_status("Status: NOT RECEIVING")
            return

        self.requesting = True
        self.receive_button.config(state="disabled")
        self.set_status("Status: SEARCHING FOR NODEMCU...")
        threading.Thread(target=self.request_receiving, daemon=True).start()

    def request_receiving(self):
        accepted, response = self.connect_to_nodemcu()
        if accepted:
            self.receiving = True
            self.requesting = False
            self.root.after(0, lambda: self.receive_button.config(text="STOP RECEIVING", state="normal"))
            self.set_status(f"Status: RECEIVING COINS ({self.nodemcu_ip})")
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
            self.set_status("Status: NODEMCU NOT FOUND")

        self.root.after(0, lambda: self.receive_button.config(text="RECEIVE COINS", state="normal"))
        self.root.after(2500, self.restore_idle_status)

    def restore_idle_status(self):
        if not self.receiving: self.status.config(text="Status: NOT RECEIVING")

    def listen_for_nodemcu(self):
        while True:
            try:
                client, address = self.server_socket.accept()
            except socket.timeout:
                if self.server_socket.fileno() < 0: return
                continue
            except OSError:
                return
            threading.Thread(target=self.handle_nodemcu_connection, args=(client, address), daemon=True).start()

    def handle_nodemcu_connection(self, client, address):
        try:
            client.settimeout(None)
            buffer = ""
            while True:
                data = client.recv(1024)
                if not data: break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line: continue
                    if line == "PYGIT READY":
                        self.set_status("Status: NODEMCU CONNECTED")
                        continue
                    if line.startswith("COIN:"):
                        try: minutes = int(line.split(":", 1)[1])
                        except ValueError: continue
                        if self.receiving:
                            self.receive_coin(minutes)
                            try: client.sendall(b"COIN_RECEIVED\\n")
                            except OSError: pass
        except OSError:
            pass
        finally:
            try: client.close()
            except OSError: pass

    def receive_coin(self, minutes=None):
        if not self.receiving:
            self.set_status("Status: NOT RECEIVING (coin ignored)")
            self.root.after(1500, self.restore_idle_status)
            return
        if minutes is None: minutes = TIME_PER_PULSE

        self.coins += 1
        self.total_time += minutes
        self.root.after(0, lambda: self.coins_label.config(text=f"Received Coins: {self.coins}"))
        self.root.after(0, lambda: self.time_label.config(text=f"Added Time: {self.total_time} minutes"))
        self.set_status(f"Status: COIN RECEIVED (+{minutes} min)")
        self.root.after(1500, lambda: self.status.config(text="Status: RECEIVING COINS") if self.receiving else None)

    def close(self):
        if self.receiving: self.release_from_nodemcu()
        try: self.server_socket.close()
        except OSError: pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    CoinReceiver(root)
    root.mainloop()
