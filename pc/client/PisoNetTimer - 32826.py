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
def probe_nodemcu(local_ip):
    """Live non-claiming STATUS probe. Returns (node_ip, active_pc) or None."""
    parts = local_ip.split(".")
    if len(parts) != 4 or any(not p.isdigit() for p in parts):
        return None

    prefix = ".".join(parts[:3])
    local_last = int(parts[3])
    candidates = [f"{prefix}.{i}" for i in range(1, 255) if i != local_last]

    def probe(ip):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(NODEMCU_DISCOVERY_TIMEOUT)
        try:
            sock.connect((ip, NODEMCU_PORT))
            sock.sendall(b"STATUS\\n")
            sock.settimeout(1.0)
            response = sock.recv(256).decode("utf-8", errors="ignore").strip()
            sock.close()

            if response.startswith("NODEMCU|"):
                parts = response.split("|", 2)
                active_pc = parts[2].strip() if len(parts) >= 3 else "NONE"
                return ip, active_pc or "NONE"
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
                return result
    except TimeoutError:
        pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return None


def get_nodemcu_status():
    """Return (node_ip, active_pc) without claiming the NodeMCU."""
    try:
        return probe_nodemcu(get_local_ip()) or (None, None)
    except Exception:
        return None, None


def request_nodemcu():
    """Claim the NodeMCU and keep this TCP connection for heartbeat/release."""
    global nodemcu_ip, node_socket

    try:
        local_ip = get_local_ip()
        found, active_pc = probe_nodemcu(local_ip)

        if not found:
            return False

        # Someone else became active between STATUS and REQUEST.
        if active_pc not in (None, "", "NONE", PC_NAME):
            return False

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(COIN_REQUEST_TIMEOUT)
        sock.connect((found, NODEMCU_PORT))

        request = f"REQUEST|{PC_NAME}|{local_ip}|{PORT}\\n"
        sock.sendall(request.encode("utf-8"))

        response = sock.recv(256).decode("utf-8", errors="ignore").strip()

        if response.startswith("ACCEPTED|"):
            sock.settimeout(None)
            with node_lock:
                old = node_socket
                node_socket = sock
                nodemcu_ip = found

            if old:
                try:
                    old.close()
                except OSError:
                    pass

            return True

        sock.close()
        return False

    except OSError:
        try:
            sock.close()
        except Exception:
            pass
        return False


def release_from_nodemcu():
    global node_socket, coin_receiving, coin_window_running, coin_window_remaining

    with node_lock:
        sock = node_socket
        node_socket = None

    if sock:
        try:
            sock.settimeout(2)
            sock.sendall(f"RELEASE|{PC_NAME}\\n".encode("utf-8"))
            sock.recv(128)
        except OSError:
            pass
        finally:
            try:
                sock.close()
            except OSError:
                pass

    coin_receiving = False
    coin_window_running = False
    coin_window_remaining = 0


def live_nodemcu_loop():
    global nodemcu_ip

    while True:
        time.sleep(2)

        try:
            found, active_pc = get_nodemcu_status()
            nodemcu_ip = found

            if found:
                # Keep our own control connection if we are the active PC.
                if active_pc == PC_NAME:
                    with node_lock:
                        owns_node = node_socket is not None
                    if not owns_node:
                        # Our claim connection was lost; do not steal/reclaim automatically.
                        coin_receiving = False

        except Exception:
            nodemcu_ip = None
            active_pc = None

        def refresh_button(active_pc=active_pc if 'active_pc' in locals() else None):
            if "insert_coin_button" not in globals():
                return

            if coin_receiving:
                insert_coin_button.config(text="STOP RECEIVING", state="normal")
            elif coin_requesting:
                insert_coin_button.config(text="Connecting...", state="disabled")
            elif not nodemcu_ip:
                insert_coin_button.config(text="NodeMCU Offline", state="disabled")
            elif active_pc and active_pc not in ("NONE", "", PC_NAME):
                insert_coin_button.config(text=f"{active_pc} RECEIVING", state="disabled")
            else:
                insert_coin_button.config(text="Insert Coin", state="normal")

        try:
            root.after(0, refresh_button)
        except Exception:
            pass


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
            text="Insert Coin" if nodemcu_ip else "NodeMCU Offline",
            state="normal" if nodemcu_ip else "disabled"
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
    """Receive direct PisoNetTimer messages such as PC1:+10."""
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

                if not line:
                    continue

                # Direct NodeMCU coin protocol: PC_NAME:+minutes
                m = re.match(rf"^{re.escape(PC_NAME)}:(\\+|\\-)(\\d+)$", line, re.I)
                if m:
                    sign, minutes = m.groups()
                    minutes = int(minutes)

                    if sign == "+":
                        receive_coin_from_nodemcu(minutes)

                    try:
                        conn.sendall(b"OK\\n")
                    except OSError:
                        pass
                    continue

                # Ignore unrelated data on the same timer port.
                try:
                    conn.sendall(b"ERROR\\n")
                except OSError:
                    pass

    except OSError:
        pass


def request_receiving():
    global coin_requesting, coin_receiving

    accepted = request_nodemcu()

    if accepted:
        coin_receiving = True
        coin_requesting = False
        start_coin_window()

        root.after(0, lambda: insert_coin_button.config(
            text="STOP RECEIVING",
            state="normal"
        ))

        threading.Thread(target=coin_heartbeat, daemon=True).start()
        return

    coin_receiving = False
    coin_requesting = False

    root.after(0, lambda: insert_coin_button.config(
        text="Insert Coin" if nodemcu_ip else "NodeMCU Offline",
        state="normal" if nodemcu_ip else "disabled"
    ))


def toggle_coin_receiving():
    global coin_requesting, coin_receiving

    if coin_receiving:
        coin_receiving = False
        stop_coin_window()
        threading.Thread(target=release_from_nodemcu, daemon=True).start()

        insert_coin_button.config(
            text="Insert Coin" if nodemcu_ip else "NodeMCU Offline",
            state="normal" if nodemcu_ip else "disabled"
        )
        return

    if coin_requesting or not nodemcu_ip:
        return

    coin_requesting = True
    insert_coin_button.config(text="Connecting...", state="disabled")
    threading.Thread(target=request_receiving, daemon=True).start()


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
        cursor="hand2",
        state="disabled"
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

        m = re.match(rf"^{re.escape(PC_NAME)}:(\+|\-)?(\d+)(:admin:(.+))?$", data, re.I)

        if m:
            sign, minutes, _, key = m.groups()
            minutes = int(minutes)
            if sign is None:
                sign = "+"

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

threading.Thread(target=live_nodemcu_loop, daemon=True).start()


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