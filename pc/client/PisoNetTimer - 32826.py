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
NODEMCU_IP = "192.168.1.23"
NODEMCU_PORT = 5001
NODEMCU_DISCOVERY_TIMEOUT = 0.50
NODEMCU_DISCOVERY_WORKERS = 16
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
nodemcu_ip = NODEMCU_IP
nodemcu_active_pc = None
node_socket = None
node_lock = threading.Lock()
coin_window_seconds = 10
coin_window_remaining = 0
coin_window_running = False
coin_window_label = None
status_label = None
STATUS_FLASH_MS = 2500

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
def get_nodemcu_status():
    global nodemcu_ip

    last_error = None

    # Fixed NodeMCU address. Log the actual TCP/response result so we can
    # see why a STATUS check fails instead of hiding the error.
    for attempt in range(1, 4):
        sock = None
        try:
            print(
                f"[PYGIT] STATUS check {attempt}/3 -> "
                f"{NODEMCU_IP}:{NODEMCU_PORT}",
                flush=True
            )

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.connect((NODEMCU_IP, NODEMCU_PORT))

            print("[PYGIT] STATUS TCP connected", flush=True)

            sock.sendall(b"STATUS\n")

            # TCP is a stream. One recv() is NOT guaranteed to contain the
            # complete NodeMCU response, so keep reading until the newline.
            response_buffer = b""
            while b"\n" not in response_buffer:
                chunk = sock.recv(256)
                if not chunk:
                    break
                response_buffer += chunk

            response = response_buffer.decode("utf-8", errors="ignore").strip()

            print(
                f"[PYGIT] STATUS response: {response!r}",
                flush=True
            )

            if response.startswith("NODEMCU|"):
                # Accept the normal response:
                #   NODEMCU|192.168.1.23|NONE
                # and also tolerate ESP8266 TCP framing where the final
                # separator/line ending is missing:
                #   NODEMCU|192.168.1.23
                #   NODEMCU|192.168.1.23NONE
                payload = response[len("NODEMCU|"):].strip()

                if payload == NODEMCU_IP:
                    active_pc = "NONE"
                elif payload.startswith(NODEMCU_IP):
                    suffix = payload[len(NODEMCU_IP):].strip()
                    if suffix.startswith("|"):
                        suffix = suffix[1:].strip()
                    active_pc = suffix or "NONE"
                else:
                    parts = response.split("|", 2)
                    if len(parts) >= 2 and parts[1].strip() == NODEMCU_IP:
                        active_pc = parts[2].strip() if len(parts) >= 3 else "NONE"
                        active_pc = active_pc or "NONE"
                    else:
                        last_error = "Invalid NodeMCU STATUS response format"
                        continue

                nodemcu_ip = NODEMCU_IP
                return NODEMCU_IP, active_pc
            else:
                last_error = "Unexpected NodeMCU STATUS response"

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            print(f"[PYGIT] STATUS ERROR: {last_error}", flush=True)

        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

        time.sleep(0.2)

    print(
        f"[PYGIT] NodeMCU STATUS FAILED: {last_error}",
        flush=True
    )
    return None, None
def request_nodemcu():
    """Claim the NodeMCU and keep this TCP connection for heartbeat/release."""
    global nodemcu_ip, nodemcu_active_pc, node_socket

    sock = None

    try:
        local_ip = get_local_ip()
        found = NODEMCU_IP

        # Do NOT perform a STATUS probe before claiming. STATUS is only for
        # display/discovery. The NodeMCU itself is the authority and will
        # ACCEPT or REJECT this REQUEST atomically.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(COIN_REQUEST_TIMEOUT)
        sock.connect((found, NODEMCU_PORT))

        request = f"REQUEST|{PC_NAME}|{local_ip}|{PORT}\n"
        sock.sendall(request.encode("utf-8"))

        # NodeMCU may deliver the ACCEPTED response in fragments, so read
        # the TCP stream until the complete line is received.
        response_buffer = b""
        response_deadline = time.time() + COIN_REQUEST_TIMEOUT

        while b"\n" not in response_buffer and time.time() < response_deadline:
            try:
                chunk = sock.recv(256)
            except socket.timeout:
                continue

            if not chunk:
                # Give the ESP8266 a moment if the connection is still being
                # finalized on its side.
                time.sleep(0.05)
                continue

            response_buffer += chunk

        response = response_buffer.decode("utf-8", errors="ignore").strip()

        print(f"[PYGIT] REQUEST response: {response!r}", flush=True)

        if response.startswith("ACCEPTED|"):
            sock.settimeout(None)
            with node_lock:
                old = node_socket
                node_socket = sock
                nodemcu_ip = found
                nodemcu_active_pc = PC_NAME

            if old:
                try:
                    old.close()
                except OSError:
                    pass

            return True

        if response.startswith("REJECTED|"):
            print(f"[PYGIT] NodeMCU rejected REQUEST: {response}", flush=True)
            parts = response.split("|")
            if len(parts) >= 3 and parts[1] == "ACTIVE":
                nodemcu_active_pc = parts[2].strip() or None

        sock.close()
        return False

    except OSError as e:
        print(f"[PYGIT] REQUEST ERROR: {type(e).__name__}: {e}", flush=True)
        if sock:
            try:
                sock.close()
            except OSError:
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
            sock.sendall(f"RELEASE|{PC_NAME}\n".encode("utf-8"))
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
    global nodemcu_ip, nodemcu_active_pc, coin_receiving
    missed_status = 0
    MAX_MISSED_STATUS = 3

    while True:
        time.sleep(2)

        # IMPORTANT:
        # Do not open STATUS connections while this PC is claiming or
        # receiving. The REQUEST connection is the live control channel,
        # and STATUS probes were competing with it and causing the ESP8266
        # TCP server to become unstable/time out.
        if not coin_receiving and not coin_requesting:
            try:
                found, active_pc = get_nodemcu_status()
                if found:
                    missed_status = 0
                    nodemcu_ip = found
                    nodemcu_active_pc = active_pc
                else:
                    missed_status += 1
                    with node_lock:
                        owns_node = node_socket is not None
                    if missed_status >= MAX_MISSED_STATUS and not owns_node:
                        # STATUS failure does NOT mean the fixed-IP NodeMCU
                        # is offline. STATUS responses can be dropped by the
                        # ESP8266 while it is handling another TCP connection.
                        # Keep the configured IP and let REQUEST be the real
                        # connectivity/claim test.
                        nodemcu_ip = NODEMCU_IP
            except Exception:
                missed_status += 1
                with node_lock:
                    owns_node = node_socket is not None
                if missed_status >= MAX_MISSED_STATUS and not owns_node:
                    # Keep fixed NodeMCU IP visible; do not falsely report
                    # "offline" just because STATUS timed out.
                    nodemcu_ip = NODEMCU_IP

        def refresh_button():
            active_pc = nodemcu_active_pc
            if "insert_coin_button" not in globals():
                return

            # If another PC owns the NodeMCU, this PC must not be able to
            # start a competing claim. Otherwise keep the button available.
            another_pc_active = (
                active_pc
                and active_pc not in ("NONE", "", PC_NAME)
            )

            if coin_receiving:
                button_state = "normal"
                button_text = "STOP RECEIVING"
            elif another_pc_active:
                button_state = "disabled"
                button_text = "Insert Coin"
            else:
                button_state = "normal"
                button_text = "Insert Coin"

            insert_coin_button.config(
                text=button_text,
                state=button_state
            )

            if coin_receiving:
                set_nodemcu_status("RECEIVING - " + PC_NAME)
            elif coin_requesting:
                set_nodemcu_status("Connecting to NodeMCU...")
            elif not nodemcu_ip:
                set_nodemcu_status("NodeMCU offline")
            elif another_pc_active:
                set_nodemcu_status(f"{active_pc} is connected")
            else:
                set_nodemcu_status("NodeMCU ready")

        try:
            root.after(0, refresh_button)
        except Exception:
            pass

def set_nodemcu_status(message):
    print(f"[PYGIT] {message}", flush=True)
    if status_label is None:
        return
    try:
        root.after(0, lambda: status_label.config(text=message))
    except Exception:
        pass

def flash_nodemcu_status(message):
    print(f"[PYGIT] {message}", flush=True)
    if status_label is None:
        return
    try:
        def show():
            status_label.config(text=message)
            status_label.place(relx=0.02, rely=0.96, anchor="sw")
            root.after(STATUS_FLASH_MS, lambda: status_label.config(text=""))
        root.after(0, show)
    except Exception:
        pass


def update_coin_window_display():
    if coin_window_label is None:
        return

    value = max(0, coin_window_remaining)

    def refresh():
        if value > 0:
            coin_window_label.config(text=f"INSERT COIN WINDOW: {value}s")
            coin_window_label.place(relx=0.5, rely=0.84, anchor="center")
        else:
            coin_window_label.config(text="")
            coin_window_label.place_forget()

    try:
        root.after(0, refresh)
    except Exception:
        pass


def start_coin_window():
    global coin_window_running, coin_window_remaining

    coin_window_running = True
    coin_window_remaining = coin_window_seconds
    update_coin_window_display()


def reset_coin_window():
    global coin_window_running, coin_window_remaining

    if coin_receiving:
        coin_window_running = True
        coin_window_remaining = coin_window_seconds
        update_coin_window_display()


def stop_coin_window():
    global coin_window_running, coin_window_remaining

    coin_window_running = False
    coin_window_remaining = 0
    if coin_window_label is not None:
        try: root.after(0, lambda: coin_window_label.config(text=""))
        except Exception: pass


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
        update_coin_window_display()

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
            sock.sendall(b"PING\n")
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

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()

                if not line:
                    continue

                # Direct NodeMCU coin protocol: PC_NAME:+minutes
                m = re.match(rf"^{re.escape(PC_NAME)}:(\+|\-)(\d+)$", line, re.I)
                if m:
                    sign, minutes = m.groups()
                    minutes = int(minutes)

                    if sign == "+":
                        receive_coin_from_nodemcu(minutes)

                    try:
                        conn.sendall(b"OK\n")
                    except OSError:
                        pass
                    continue

                # Ignore unrelated data on the same timer port.
                try:
                    conn.sendall(b"ERROR\n")
                except OSError:
                    pass

    except OSError:
        pass


def request_receiving():
    global coin_requesting, coin_receiving

    print(f"[PYGIT] Insert Coin clicked by {PC_NAME}", flush=True)

    try:
        accepted = request_nodemcu()
    except Exception as e:
        print(f"[PYGIT] Insert Coin ERROR: {type(e).__name__}: {e}", flush=True)
        flash_nodemcu_status(f"ERROR: {type(e).__name__}: {e}")
        accepted = False

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

    if not nodemcu_ip:
        flash_nodemcu_status(f"NodeMCU offline - cannot connect to {NODEMCU_IP}:{NODEMCU_PORT}")
    elif nodemcu_active_pc and nodemcu_active_pc not in ("NONE", "", PC_NAME):
        flash_nodemcu_status(f"{nodemcu_active_pc} is connected")
    else:
        flash_nodemcu_status(f"Cannot connect/claim NodeMCU at {NODEMCU_IP}:{NODEMCU_PORT}")

    root.after(0, lambda: insert_coin_button.config(
        text="Insert Coin",
        state="normal"
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

    if coin_requesting:
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

    status_label = tk.Label(
        overlay,
        text="",
        font=("Arial", 14, "bold"),
        bg="black",
        fg="white",
        padx=12,
        pady=5
    )
    status_label.place(relx=0.02, rely=0.96, anchor="sw")

    coin_window_label = tk.Label(
        overlay,
        text="",
        font=("Arial", 18, "bold"),
        bg="black",
        fg="white",
        padx=18,
        pady=8
    )
    coin_window_label.place_forget()

    # Keep a reference for the coin receiver functions.
    globals()["insert_coin_button"] = insert_coin_button
    globals()["coin_window_label"] = coin_window_label
    globals()["status_label"] = status_label

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

        m = re.match(rf"^{re.escape(PC_NAME)}:(\+|\-)(\d+)(:admin:(.+))?$", data, re.I)

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