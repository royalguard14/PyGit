VERSION = "1.4.2"

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
coin_window_deadline = 0.0
coin_window_label = None
coin_progress_canvas = None
coin_window_frame = None
coin_window_visible = False
status_label = None
remaining_time_label = None
remaining_time_window = None
remaining_insert_coin_button = None
remaining_timer_blink_state = False
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
    try:
        s.connect((NODEMCU_IP, NODEMCU_PORT))
        return s.getsockname()[0]
    finally:
        s.close()


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
PISONET_NAME = data.get("pisonetName", "PisoNet")
SHOP_TIME_OPEN = data.get("time_open", "00:00")
SHOP_TIME_CLOSE = data.get("time_close", "24:00")

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
    """Claim the NodeMCU with a short-lived control connection."""
    global nodemcu_ip, nodemcu_active_pc

    sock = None

    try:
        local_ip = get_local_ip()
        found = NODEMCU_IP

        print(
            f"[PYGIT] Connecting to NodeMCU {found}:{NODEMCU_PORT} "
            f"from {local_ip}:{PORT}",
            flush=True
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(COIN_REQUEST_TIMEOUT)
        sock.connect((found, NODEMCU_PORT))

        request = f"REQUEST|{PC_NAME}|{local_ip}|{PORT}\n"
        sock.sendall(request.encode("utf-8"))

        response_buffer = b""
        response_deadline = time.time() + COIN_REQUEST_TIMEOUT

        while b"\n" not in response_buffer and time.time() < response_deadline:
            try:
                chunk = sock.recv(256)
            except socket.timeout:
                continue

            if not chunk:
                break

            response_buffer += chunk

        response = response_buffer.decode("utf-8", errors="ignore").strip()
        print(f"[PYGIT] REQUEST response: {response!r}", flush=True)

        if response.startswith("ACCEPTED|"):
            nodemcu_ip = found
            nodemcu_active_pc = PC_NAME
            return True

        if response.startswith("REJECTED|"):
            print(f"[PYGIT] NodeMCU rejected REQUEST: {response}", flush=True)
            parts = response.split("|")
            if len(parts) >= 3 and parts[1] == "ACTIVE":
                nodemcu_active_pc = parts[2].strip() or None

        return False

    except OSError as e:
        print(f"[PYGIT] REQUEST ERROR: {type(e).__name__}: {e}", flush=True)
        return False

    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass

def _widget_alive(widget):
    try:
        return widget is not None and bool(widget.winfo_exists())
    except tk.TclError:
        return False
    except Exception:
        return False


def release_from_nodemcu():
    global coin_receiving, coin_window_running, coin_window_remaining, nodemcu_active_pc

    sock = None

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(COIN_REQUEST_TIMEOUT)
        sock.connect((NODEMCU_IP, NODEMCU_PORT))

        sock.sendall(f"RELEASE|{PC_NAME}\n".encode("utf-8"))

        response_buffer = b""
        deadline = time.time() + COIN_REQUEST_TIMEOUT

        while b"\n" not in response_buffer and time.time() < deadline:
            try:
                chunk = sock.recv(128)
            except socket.timeout:
                break
            if not chunk:
                break
            response_buffer += chunk

        response = response_buffer.decode("utf-8", errors="ignore").strip()
        print(f"[PYGIT] RELEASE response: {response!r}", flush=True)

    except OSError as e:
        print(f"[PYGIT] RELEASE ERROR: {type(e).__name__}: {e}", flush=True)

    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass

    coin_receiving = False
    coin_window_running = False
    coin_window_remaining = 0
    nodemcu_active_pc = None

    try:
        root.after(0, lambda: insert_coin_button.config(
            text="Insert Coin",
            state="normal"
        ) if _widget_alive(insert_coin_button) else None)
        root.after(0, lambda: status_label.config(text="") if _widget_alive(status_label) else None)
    except Exception:
        pass

def live_nodemcu_loop():
    """No background NodeMCU polling.

    NodeMCU communication starts only when the user presses Insert Coin.
    The REQUEST connection becomes the live control channel while receiving.
    """
    return

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
    if not coin_window_visible:
        return
    if coin_window_label is None or coin_progress_canvas is None:
        return
    try:
        if not coin_window_label.winfo_exists() or not coin_progress_canvas.winfo_exists():
            return
    except tk.TclError:
        return

    remaining = max(0.0, coin_window_deadline - time.monotonic())
    ratio = min(1.0, remaining / float(coin_window_seconds))

    if remaining > 0 and coin_receiving:
        coin_window_label.config(text=f"INSERT COIN • {remaining:.1f}s")
        coin_window_label.place(relx=0.5, rely=0.50, anchor="center")

        coin_progress_canvas.place(relx=0.5, rely=0.57, anchor="center")
        coin_progress_canvas.delete("all")

        width = 600
        height = 30
        fill_width = int(width * ratio)

        coin_progress_canvas.create_rectangle(
            0, 0, width, height,
            fill="white",
            outline="white",
            width=2
        )
        if fill_width > 0:
            coin_progress_canvas.create_rectangle(
                0, 0, fill_width, height,
                fill="#22c55e",
                outline="#22c55e"
            )
    else:
        coin_window_label.place_forget()
        coin_progress_canvas.place_forget()


def start_coin_window():
    global coin_window_running, coin_window_remaining, coin_window_deadline, coin_window_visible

    coin_window_running = True
    coin_window_remaining = coin_window_seconds
    coin_window_deadline = time.monotonic() + coin_window_seconds
    coin_window_visible = True


def reset_coin_window():
    global coin_window_running, coin_window_remaining, coin_window_deadline, coin_window_visible

    if coin_receiving:
        coin_window_running = True
        coin_window_remaining = coin_window_seconds
        coin_window_deadline = time.monotonic() + coin_window_seconds
        # Keep the timer active, but do not force the UI visible while
        # receiving if it was intentionally hidden.
        if coin_window_visible:
            update_coin_window_display()


def stop_coin_window():
    global coin_window_running, coin_window_remaining, coin_window_deadline, coin_window_visible

    coin_window_running = False
    coin_window_remaining = 0
    coin_window_deadline = 0.0
    coin_window_visible = False

    # Hide both immediately on STOP.
    try:
        if coin_window_label is not None:
            coin_window_label.place_forget()
        if coin_progress_canvas is not None:
            coin_progress_canvas.place_forget()
    except Exception:
        pass


def coin_window_loop():
    global coin_receiving, coin_window_running, coin_window_remaining

    while True:
        time.sleep(0.05)

        if not coin_window_running or not coin_receiving:
            continue

        remaining = max(0.0, coin_window_deadline - time.monotonic())
        coin_window_remaining = int(remaining + 0.999)

        if remaining <= 0:
            coin_window_remaining = 0
            coin_window_running = False
            coin_receiving = False

            root.after(0, lambda: insert_coin_button.config(
                text="Releasing...",
                state="disabled"
            ) if _widget_alive(insert_coin_button) else None)

            root.after(0, lambda: coin_window_label.place_forget() if _widget_alive(coin_window_label) else None)
            root.after(0, lambda: coin_progress_canvas.place_forget() if _widget_alive(coin_progress_canvas) else None)

            threading.Thread(
                target=release_from_nodemcu,
                daemon=True
            ).start()
        else:
            # Only schedule one UI update at a time. The old version queued
            # hundreds of root.after() callbacks and caused lag/freezing.
            root.after(0, update_coin_window_display)


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

    # Show the 10-second countdown/progress bar after a coin is received.
    # It stays hidden while waiting for the first coin.
    global coin_window_visible
    coin_window_visible = True
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
                    print(f"[PYGIT] COIN RECEIVED FROM COINSLOT: {line!r}", flush=True)
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
    global coin_requesting, coin_receiving, coin_window_running, coin_window_remaining, coin_window_deadline, coin_window_visible

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

        # Start the 10-second timeout in the background,
        # but keep the countdown/progress bar hidden while receiving.
        coin_window_running = True
        coin_window_remaining = coin_window_seconds
        coin_window_deadline = time.monotonic() + coin_window_seconds
        coin_window_visible = False

        try:
            root.after(0, lambda: coin_window_label.place_forget() if _widget_alive(coin_window_label) else None)
            root.after(0, lambda: coin_progress_canvas.place_forget() if _widget_alive(coin_progress_canvas) else None)
        except Exception:
            pass

        root.after(0, lambda: insert_coin_button.config(
            text="STOP RECEIVING",
            state="normal"
        ))

        print(
            f"[PYGIT] NodeMCU claimed successfully by {PC_NAME}. "
            f"Waiting for coin on GPIO12.",
            flush=True
        )
        return

    coin_receiving = False
    coin_requesting = False

    if nodemcu_active_pc and nodemcu_active_pc not in ("NONE", "", PC_NAME):
        flash_nodemcu_status(f"{nodemcu_active_pc} is connected")
    else:
        flash_nodemcu_status(f"Cannot connect/claim NodeMCU at {NODEMCU_IP}:{NODEMCU_PORT}")

    root.after(0, lambda: insert_coin_button.config(
        text="Insert Coin",
        state="normal"
    ) if _widget_alive(insert_coin_button) else None)


def toggle_coin_receiving():
    global coin_requesting, coin_receiving

    if coin_receiving:
        coin_receiving = False
        stop_coin_window()
        threading.Thread(target=release_from_nodemcu, daemon=True).start()

        insert_coin_button.config(
            text="Insert Coin",
            state="normal"
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
    global overlay, overlay_active, slide_index, insert_coin_button, status_label, coin_window_label, coin_progress_canvas, coin_window_frame

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
        state="normal"
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
        pady=6
    )
    coin_window_label.place_forget()

    coin_progress_canvas = tk.Canvas(
        overlay,
        width=600,
        height=30,
        bg="black",
        highlightthickness=2,
        highlightbackground="white"
    )
    coin_progress_canvas.place_forget()

    # Keep references for the coin receiver functions.
    globals()["insert_coin_button"] = insert_coin_button
    globals()["coin_window_label"] = coin_window_label
    globals()["coin_progress_canvas"] = coin_progress_canvas
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

        # Match the shop-info badge size.
        badge_w = 430
        badge_h = 150
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

        # Shop information badge at the top-right.
        def format_shop_time(value):
            try:
                hour, minute = map(int, value.split(":"))
                suffix = "AM" if hour < 12 else "PM"
                hour12 = hour % 12 or 12
                return f"{hour12}:{minute:02d} {suffix}"
            except:
                return value

        shop_open = format_shop_time(SHOP_TIME_OPEN)
        shop_close = format_shop_time(SHOP_TIME_CLOSE)

        shop_x2 = overlay.winfo_screenwidth() - 35
        shop_x1 = shop_x2 - 430
        shop_y1 = 30
        shop_y2 = 180
        shop_r = 24

        shop_points = [
            shop_x1 + shop_r, shop_y1,
            shop_x2 - shop_r, shop_y1,
            shop_x2, shop_y1 + shop_r,
            shop_x2, shop_y2 - shop_r,
            shop_x2 - shop_r, shop_y2,
            shop_x1 + shop_r, shop_y2,
            shop_x1, shop_y2 - shop_r,
            shop_x1, shop_y1 + shop_r
        ]

        canvas.create_polygon(
            shop_points,
            fill="white",
            outline="black",
            width=3,
            stipple="gray25"
        )

        canvas.create_line(
            shop_x1 + 18, shop_y1 + 18,
            shop_x1 + 18, shop_y2 - 18,
            fill="black",
            width=5
        )

        shop_center_x = (shop_x1 + shop_x2) // 2 + 8

        def stroked_text(x, y, text, font, fill="white", stroke="black", width=3):
            for dx, dy in [
                (-width, -width), (0, -width), (width, -width),
                (-width, 0),                 (width, 0),
                (-width, width),  (0, width),  (width, width)
            ]:
                canvas.create_text(
                    x + dx, y + dy,
                    text=text,
                    fill=stroke,
                    font=font,
                    anchor="center"
                )
            canvas.create_text(
                x, y,
                text=text,
                fill=fill,
                font=font,
                anchor="center"
            )

        stroked_text(
            shop_center_x, shop_y1 + 48,
            PISONET_NAME,
            ("Arial", 34, "bold"),
            width=3
        )
        stroked_text(
            shop_center_x, shop_y1 + 92,
            f"{shop_open} - {shop_close}",
            ("Arial", 24, "bold"),
            width=2
        )
        stroked_text(
            shop_center_x, shop_y1 + 126,
            "SHOP TIME",
            ("Arial", 15, "bold"),
            width=2
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


def update_remaining_time_display():
    """Show remaining PC usage time outside the overlay, at the top-right."""
    global remaining_time_window, remaining_time_label, remaining_insert_coin_button, insert_coin_button

    with lock:
        total = max(0, int(remaining_seconds))

    if total <= 0:
        if remaining_time_window is not None:
            try:
                remaining_time_window.destroy()
            except tk.TclError:
                pass
            remaining_time_window = None
            remaining_time_label = None
        return

    if remaining_time_window is None or not _widget_alive(remaining_time_window):
        remaining_time_window = tk.Toplevel(root)
        remaining_time_window.overrideredirect(True)
        remaining_time_window.attributes("-topmost", True)
        remaining_time_window.configure(bg="black")

        remaining_time_label = tk.Label(
            remaining_time_window,
            text="00:00:00",
            font=("Arial", 16, "bold"),
            bg="black",
            fg="green",
            padx=8,
            pady=4
        )
        remaining_time_label.pack()

        # Allow the player to move the timer anywhere by dragging it.
        def start_timer_drag(event):
            remaining_time_window._drag_x = event.x
            remaining_time_window._drag_y = event.y

        def move_timer_drag(event):
            x = remaining_time_window.winfo_x() + event.x - remaining_time_window._drag_x
            y = remaining_time_window.winfo_y() + event.y - remaining_time_window._drag_y
            remaining_time_window.geometry(f"+{x}+{y}")
            remaining_time_window._user_moved = True

        remaining_time_label.bind("<ButtonPress-1>", start_timer_drag)
        remaining_time_label.bind("<B1-Motion>", move_timer_drag)

        remaining_insert_coin_button = tk.Button(
            remaining_time_window,
            text="Insert Coin",
            command=toggle_coin_receiving,
            font=("Arial", 13, "bold"),
            padx=12,
            pady=4,
            cursor="hand2"
        )
        remaining_insert_coin_button.pack(pady=(0, 6))
        insert_coin_button = remaining_insert_coin_button

    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    remaining_time_label.config(
        text=f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    )

    global remaining_timer_blink_state
    if total <= 60:
        remaining_timer_blink_state = not remaining_timer_blink_state
        remaining_time_label.config(
            fg="red" if remaining_timer_blink_state else "black"
        )
    else:
        remaining_timer_blink_state = False
        remaining_time_label.config(fg="green")

    # Keep the player's chosen timer position instead of resetting it every update.
    if not hasattr(remaining_time_window, "_user_moved"):
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        remaining_time_window.update_idletasks()
        window_width = remaining_time_window.winfo_width()
        window_height = remaining_time_window.winfo_height()

        # Initial position: bottom-right, just above the Windows taskbar.
        taskbar_offset = 55
        remaining_time_window.geometry(
            f"+{screen_width - window_width - 20}+{screen_height - window_height - taskbar_offset}"
        )

# ================= TIMER =================
# Cache shop status so the Tkinter main thread is never blocked by an NTP
# network request while the coin countdown/progress bar is animating.
_cached_shop_status = "OPEN"

def refresh_shop_status():
    global _cached_shop_status
    try:
        status, _ = get_shop_status()
        _cached_shop_status = status
    except Exception:
        pass
    root.after(30000, refresh_shop_status)

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
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)
        print(f"[PYGIT] COIN SERVER listening on {HOST}:{PORT}", flush=True)
    except OSError as e:
        print(f"[PYGIT] COIN SERVER ERROR on {HOST}:{PORT}: {type(e).__name__}: {e}", flush=True)
        return

    while True:
        try:
            c, a = s.accept()
            print(f"[PYGIT] COIN SERVER connection from {a[0]}:{a[1]}", flush=True)
            threading.Thread(target=handle_coin_receiver_connection, args=(c,), daemon=True).start()
        except OSError as e:
            print(f"[PYGIT] COIN SERVER accept ERROR: {type(e).__name__}: {e}", flush=True)
            break

# ================= RECOVERY LOAD =================
load_state()

# ================= START =================
threading.Thread(target=server, daemon=True).start()
threading.Thread(target=countdown, daemon=True).start()
threading.Thread(target=coin_window_loop, daemon=True).start()


root = tk.Tk()
root.withdraw()

def update():
    status = _cached_shop_status

    with lock:
        zero = remaining_seconds <= 0

    if status != "OPEN" or zero:
        # Overlay has no remaining-time display.
        update_remaining_time_display()
        show_overlay()
        # Hide the external timer while the overlay is active.
        if remaining_time_window is not None:
            try:
                remaining_time_window.withdraw()
            except tk.TclError:
                pass
    else:
        hide_overlay()
        if remaining_time_window is not None:
            try:
                remaining_time_window.deiconify()
            except tk.TclError:
                pass
        update_remaining_time_display()

    root.after(1000, update)

refresh_shop_status()
update()
root.mainloop()