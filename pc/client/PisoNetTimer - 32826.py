VERSION = "1.4.1"

# ================= IMPORTS =================
import socket, sys, threading, re, tkinter as tk, time, os, json, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageTk
import keyboard
import winreg, ctypes
from ctypes import POINTER, cast
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from datetime import datetime, timedelta
import pytz
import ntplib
import traceback



# ================= CONFIG =================
HOST = "0.0.0.0"
PORT = 5000
DISCOVERY_PORT = 5050

IMAGE_FOLDER = "C:/sufyan"
DETAIL_JSON = os.path.join(IMAGE_FOLDER, "detail.json")

SLIDE_INTERVAL = 5
NODEMCU_PORT = 5001
NODEMCU_DISCOVERY_TIMEOUT = 0.35
NODEMCU_DISCOVERY_WORKERS = 32
COIN_TIME_PER_PULSE = 10
COIN_REQUEST_TIMEOUT = 3.0
IP_BASE = 100
MAX_PC = 10

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzxrlmAv0Sr7KWMIgLVi4RoA8CnLv7WxHUfgzfoF0IYVmzacJaIe7OBPrxn0zCXtYCp/exec"
ADMIN_KEY = "7148"
TIMEZONE = pytz.timezone("Asia/Manila")

OPEN_HOUR = 8
OPEN_MINUTE = 0
CLOSE_HOUR = 22
CLOSE_MINUTE = 30

# ================= CRASH RECOVERY =================
RECOVERY_FILE = "D:/recovery.json"
os.makedirs(os.path.dirname(RECOVERY_FILE), exist_ok=True)

def save_state():
    try:
        with open(RECOVERY_FILE, "w") as f:
            json.dump({"remaining": remaining_seconds}, f)
    except:
        pass

def load_state():
    global remaining_seconds
    if os.path.exists(RECOVERY_FILE):
        try:
            with open(RECOVERY_FILE) as f:
                data = json.load(f)
                remaining_seconds = data.get("remaining", 0)
        except:
            remaining_seconds = 0

# ================= SINGLE INSTANCE =================
_instance_lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _instance_lock.bind(("127.0.0.1", 45678))
except:
    sys.exit(0)

# ================= GLOBALS =================
remaining_seconds = 0
lock = threading.Lock()
overlay = None
overlay_active = False
slide_index = 0
images = []
coin_receiving = False
coin_requesting = False
nodemcu_ip = None
node_socket = None
node_lock = threading.Lock()
coin_window_seconds = 10
coin_window_remaining = 0
coin_window_running = False

# ================= TIME =================
def get_ntp_time():
    try:
        client = ntplib.NTPClient()
        res = client.request("pool.ntp.org", version=3)
        return datetime.fromtimestamp(res.tx_time, TIMEZONE)
    except:
        return datetime.now(TIMEZONE)


def is_time_tampered():
    try:
        ntp = get_ntp_time()
        sys_time = datetime.now(TIMEZONE)
        return abs((ntp - sys_time).total_seconds()) > 120
    except:
        return False


def get_shop_status():
    now = get_ntp_time()

    if is_time_tampered():
        return "TAMPERED", now

    current = now.hour * 60 + now.minute
    open_time = OPEN_HOUR * 60 + OPEN_MINUTE
    close_time = CLOSE_HOUR * 60 + CLOSE_MINUTE

    if current < open_time:
        return "CLOSED_BEFORE", now
    elif current >= close_time:
        return "CLOSED_AFTER", now
    return "OPEN", now

# ================= ADMIN =================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    sys.exit()

# ================= PC NAME =================
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip


def get_pc_name():
    ip = get_local_ip()
    last = int(ip.split(".")[-1])
    return f"PC{last - IP_BASE}" if 1 <= (last - IP_BASE) <= MAX_PC else "PC1"

PC_NAME = get_pc_name()

# ================= LOAD CONFIG =================
if os.path.exists(DETAIL_JSON):
    with open(DETAIL_JSON) as f:
        data = json.load(f)
else:
    data = {}

PC_NAME = data.get("PcName", PC_NAME)

# ================= LOAD IMAGES =================
if os.path.exists(IMAGE_FOLDER):
    for f in os.listdir(IMAGE_FOLDER):
        if f.lower().endswith((".png", ".jpg", ".jpeg")):
            images.append(os.path.join(IMAGE_FOLDER, f))

# ================= AUDIO =================
def mute():
    try:
        dev = AudioUtilities.GetSpeakers()
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMute(1, None)
    except:
        pass

def unmute():
    try:
        dev = AudioUtilities.GetSpeakers()
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMute(0, None)
    except:
        pass

# ================= INPUT =================
BLOCK_KEYS = ["tab", "esc", "windows"]

def lock_input():
    for k in BLOCK_KEYS:
        try:
            keyboard.block_key(k)
        except:
            pass

def unlock_input():
    for k in BLOCK_KEYS:
        try:
            keyboard.unblock_key(k)
        except:
            pass

# ================= COIN RECEIVER =================
def discover_nodemcu(local_ip):
    """Find the PyGit NodeMCU on the local /24 subnet."""
    parts = local_ip.split(".")
    if len(parts) != 4 or any(not p.isdigit() for p in parts):
        return None, None

    prefix = ".".join(parts[:3])
    local_last = int(parts[3])
    candidates = [f"{prefix}.{i}" for i in range(1, 255) if i != local_last]

    def probe(ip):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(NODEMCU_DISCOVERY_TIMEOUT)
        try:
            sock.connect((ip, NODEMCU_PORT))
            sock.settimeout(1.5)
            request = f"REQUEST|{PC_NAME}|{local_ip}|{PORT}\\n"
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

    executor = ThreadPoolExecutor(max_workers=NODEMCU_DISCOVERY_WORKERS)
    futures = [executor.submit(probe, ip) for ip in candidates]

    try:
        for future in as_completed(futures, timeout=COIN_REQUEST_TIMEOUT):
            result = future.result()
            if result:
                for other in futures:
                    if other is not future:
                        other.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                return result[0], (result[1], result[2])
    except TimeoutError:
        pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return None, None


def connect_to_nodemcu():
    global nodemcu_ip, node_socket

    local_ip = get_local_ip()
    found = discover_nodemcu(local_ip)

    if not found or not found[0]:
        return False, "NODEMCU NOT FOUND"

    node_ip, discovery = found
    sock, response = discovery
    nodemcu_ip = node_ip

    if response.startswith("ACCEPTED|"):
        with node_lock:
            if node_socket:
                try:
                    node_socket.close()
                except OSError:
                    pass
            node_socket = sock
        return True, response

    try:
        sock.close()
    except OSError:
        pass

    return False, response or "REJECTED"


def release_from_nodemcu():
    global node_socket, coin_receiving, coin_window_running, coin_window_remaining

    with node_lock:
        sock = node_socket

    if not sock:
        return

    try:
        sock.sendall(f"RELEASE|{PC_NAME}\\n".encode("utf-8"))
        sock.settimeout(2)
        sock.recv(128)
    except OSError:
        pass
    finally:
        with node_lock:
            if node_socket is sock:
                node_socket = None
        try:
            sock.close()
        except OSError:
            pass

    coin_receiving = False
    coin_window_running = False
    coin_window_remaining = 0


def start_coin_window():
    global coin_window_running, coin_window_remaining

    coin_window_running = True
    coin_window_remaining = coin_window_seconds


def reset_coin_window():
    global coin_window_running, coin_window_remaining

    if coin_receiving:
        coin_window_running = True
        coin_window_remaining = coin_window_seconds


def stop_coin_window():
    global coin_window_running, coin_window_remaining

    coin_window_running = False
    coin_window_remaining = 0


def coin_window_loop():
    global coin_receiving, coin_window_running, coin_window_remaining

    while True:
        time.sleep(1)

        if not coin_window_running:
            continue

        if not coin_receiving:
            stop_coin_window()
            continue

        coin_window_remaining -= 1

        if coin_window_remaining <= 0:
            coin_window_running = False
            coin_receiving = False

            root.after(0, lambda: insert_coin_button.config(
                text="Insert Coin",
                state="normal"
            ))

            threading.Thread(
                target=release_from_nodemcu,
                daemon=True
            ).start()


def coin_heartbeat():
    global coin_receiving

    while coin_receiving:
        with node_lock:
            sock = node_socket

        if not sock:
            break

        try:
            sock.sendall(b"PING\\n")
        except OSError:
            break

        time.sleep(3)

    if coin_receiving:
        coin_receiving = False
        stop_coin_window()
        root.after(0, lambda: insert_coin_button.config(
            text="Insert Coin",
            state="normal"
        ))


def receive_coin_from_nodemcu(minutes):
    global remaining_seconds

    if not coin_receiving:
        return

    with lock:
        remaining_seconds += minutes * 60
        save_state()

    threading.Thread(
        target=log_to_google,
        args=(minutes,),
        daemon=True
    ).start()

    reset_coin_window()


def handle_coin_receiver_connection(conn):
    global coin_receiving

    try:
        conn.settimeout(None)
        buffer = ""

        while True:
            data = conn.recv(1024)
            if not data:
                break

            buffer += data.decode("utf-8", errors="ignore")

            while "\\n" in buffer:
                line, buffer = buffer.split("\\n", 1)
                line = line.strip()

                if line == "PYGIT READY":
                    coin_receiving = True
                    start_coin_window()

                    root.after(0, lambda: insert_coin_button.config(
                        text="STOP RECEIVING",
                        state="normal"
                    ))
                    continue

                if line.startswith("COIN:") and coin_receiving:
                    try:
                        minutes = int(line.split(":", 1)[1])
                    except ValueError:
                        continue

                    receive_coin_from_nodemcu(minutes)

                    try:
                        conn.sendall(b"COIN_RECEIVED\\n")
                    except OSError:
                        pass

    except OSError:
        pass


def request_receiving():
    global coin_requesting, coin_receiving

    accepted, response = connect_to_nodemcu()

    if accepted:
        coin_receiving = True
        coin_requesting = False

        root.after(0, lambda: insert_coin_button.config(
            text="STOP RECEIVING",
            state="normal"
        ))

        threading.Thread(target=coin_heartbeat, daemon=True).start()
        return

    coin_receiving = False
    coin_requesting = False

    root.after(0, lambda: insert_coin_button.config(
        text="Insert Coin",
        state="normal"
    ))


def toggle_coin_receiving():
    global coin_requesting, coin_receiving

    if coin_receiving:
        coin_receiving = False
        stop_coin_window()

        threading.Thread(
            target=release_from_nodemcu,
            daemon=True
        ).start()

        insert_coin_button.config(
            text="Insert Coin",
            state="normal"
        )
        return

    if coin_requesting:
        return

    coin_requesting = True
    insert_coin_button.config(
        state="disabled"
    )

    threading.Thread(
        target=request_receiving,
        daemon=True
    ).start()


def handle_coin_socket(conn):
    handle_coin_receiver_connection(conn)


# ================= LOGGING =================
def log_to_google(minutes):
    try:
        requests.post(GOOGLE_SCRIPT_URL, json={"pc": PC_NAME, "minutes": minutes}, timeout=5)
    except:
        pass

# ================= OVERLAY =================
def show_overlay():
    global overlay, overlay_active, slide_index

    if overlay_active:
        return

    overlay_active = True

    overlay = tk.Toplevel()
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-topmost", True)

    canvas = tk.Canvas(overlay)
    canvas.pack(fill="both", expand=True)

    overlay.configure(cursor="arrow")

    def insert_coin():
        toggle_coin_receiving()

    insert_coin_button = tk.Button(
        overlay,
        text="Insert Coin",
        command=insert_coin,
        font=("Arial", 24, "bold"),
        padx=35,
        pady=12,
        cursor="hand2"
    )
    insert_coin_button.place(relx=0.5, rely=0.90, anchor="center")

    # Keep a reference for the coin receiver functions.
    globals()["insert_coin_button"] = insert_coin_button

    def slide():
        global slide_index
        canvas.delete("all")

        if images:
            try:
                img = Image.open(images[slide_index]).resize((overlay.winfo_screenwidth(), overlay.winfo_screenheight()))
                photo = ImageTk.PhotoImage(img)
                canvas.image = photo
                canvas.create_image(0, 0, image=photo, anchor="nw")
                slide_index = (slide_index + 1) % len(images)
            except:
                pass

        # PC name badge at the top-left, with PC name centered inside
        font = ("Arial", 64, "bold")
        x = 35
        y = 30

        text_width = max(260, len(PC_NAME) * 43)
        text_height = 78
        pad_x = 30
        pad_y = 18
        badge_w = text_width + (pad_x * 2) + 45
        badge_h = text_height + (pad_y * 2)
        badge_x1 = x
        badge_y1 = y
        badge_x2 = x + badge_w
        badge_y2 = y + badge_h
        r = 28

        # Use a single rounded rectangle shape built from a polygon.
        # This avoids the separate visible circles caused by overlapping ovals.
        points = [
            badge_x1 + r, badge_y1,
            badge_x2 - r, badge_y1,
            badge_x2, badge_y1 + r,
            badge_x2, badge_y2 - r,
            badge_x2 - r, badge_y2,
            badge_x1 + r, badge_y2,
            badge_x1, badge_y2 - r,
            badge_x1, badge_y1 + r
        ]

        canvas.create_polygon(
            points,
            fill="white",
            outline="black",
            width=3,
            stipple="gray25"
        )

        # Subtle decorative accent on the left
        canvas.create_line(
            badge_x1 + 18, badge_y1 + 20,
            badge_x1 + 18, badge_y2 - 20,
            fill="black",
            width=5
        )

        # PC name centered inside the badge
        center_x = (badge_x1 + badge_x2) // 2 + 10
        center_y = (badge_y1 + badge_y2) // 2

        stroke = 3
        for dx, dy in [(-stroke, -stroke), (0, -stroke), (stroke, -stroke),
                       (-stroke, 0),                    (stroke, 0),
                       (-stroke, stroke),  (0, stroke),  (stroke, stroke)]:
            canvas.create_text(
                center_x + dx, center_y + dy,
                text=PC_NAME, fill="black", font=font, anchor="center"
            )

        canvas.create_text(
            center_x, center_y,
            text=PC_NAME, fill="white", font=font, anchor="center"
        )

        overlay.after(SLIDE_INTERVAL * 1000, slide)

    slide()
    lock_input()
    mute()


def hide_overlay():
    global overlay, overlay_active

    if overlay:
        overlay.destroy()

    overlay_active = False
    unlock_input()
    unmute()

# ================= TIMER =================
def countdown():
    global remaining_seconds
    while True:
        time.sleep(1)
        with lock:
            if remaining_seconds > 0:
                remaining_seconds -= 1
                save_state()

# ================= SERVER =================
def handle_client(conn, addr):
    global remaining_seconds

    try:
        data = conn.recv(1024).decode().strip()

        # NodeMCU coin-receiver protocol uses the same PC port.
        if data == "PYGIT READY" or data.startswith("COIN:"):
            handle_coin_receiver_connection(conn)
            return

        m = re.match(rf"{PC_NAME}:(\+|\-)(\d+)(:admin:(.+))?", data, re.I)

        if m:
            sign, minutes, _, key = m.groups()
            minutes = int(minutes)

            is_admin_cmd = key == ADMIN_KEY

            status, _ = get_shop_status()

            if status == "TAMPERED":
                conn.sendall(b"BLOCKED")
                return

            if status != "OPEN" and not is_admin_cmd:
                conn.sendall(b"SHOP CLOSED")
                return

            with lock:
                if sign == "+":
                    remaining_seconds += minutes * 60
                else:
                    remaining_seconds = max(0, remaining_seconds - minutes * 60)

                save_state()

            threading.Thread(target=log_to_google, args=(minutes,), daemon=True).start()

            conn.sendall(b"OK")
            return

        if data.lower() == f"{PC_NAME.lower()}:shutdown":
            conn.sendall(b"SHUTDOWN")
            os.system("shutdown /s /t 1")
            return

        if data.lower() == f"{PC_NAME.lower()}:restart":
            conn.sendall(b"RESTART")
            os.system("shutdown /r /t 1")
            return

        conn.sendall(b"ERROR")

    except Exception:
        traceback.print_exc()
    finally:
        conn.close()

# ================= SERVER =================
def server():
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(5)

    while True:
        c, a = s.accept()
        threading.Thread(target=handle_client, args=(c, a), daemon=True).start()

# ================= RECOVERY LOAD =================
load_state()

# ================= START =================
threading.Thread(target=server, daemon=True).start()
threading.Thread(target=countdown, daemon=True).start()
threading.Thread(target=coin_window_loop, daemon=True).start()


root = tk.Tk()
root.withdraw()


def update():
    status, _ = get_shop_status()

    with lock:
        zero = remaining_seconds <= 0

    if status != "OPEN" or zero:
        show_overlay()
    else:
        hide_overlay()

    root.after(1000, update)

update()
root.mainloop()