VERSION = "1.4.6"

# ================= IMPORTS =================
import socket, sys, threading, re, tkinter as tk, time, os, json, requests
from PIL import Image, ImageTk, ImageOps
import keyboard
import ctypes
from ctypes import POINTER, cast
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from datetime import datetime
import pytz
import ntplib

# ================= CONFIG =================
HOST = "0.0.0.0"
PORT = 5000
IMAGE_FOLDER = "C:/sufyan"
DETAIL_JSON = os.path.join(IMAGE_FOLDER, "detail.json")
SLIDE_INTERVAL = 5
IP_BASE = 100
MAX_PC = 10
GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzxrlmAv0Sr7KWMIgLVi4RoA8CnLv7WxHUfgzfoF0IYVmzacJaIe7OBPrxn0zCXtYCp/exec"
TIMEZONE = pytz.timezone("Asia/Manila")
INSERT_COIN_MINUTES = 1

# ================= SINGLE INSTANCE =================
_instance_lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _instance_lock.bind(("127.0.0.1", 45678))
except:
    sys.exit(0)

# ================= GLOBALS =================
remaining_seconds = 0
lock = threading.Lock()
root = None
canvas = None
timer_text = None
status_text = None
background_photo = None
current_image_index = 0
shop_name = "PisoNet"
operation_text = "SHOP OPERATION: 8:00 AM - 10:30 PM"
dev_btn = True
open_minutes = 8 * 60
close_minutes = 22 * 60 + 30

# ================= DETAIL CONFIG =================
def load_detail_config():
    global PC_NAME, shop_name, operation_text, dev_btn, open_minutes, close_minutes

    data = {}
    try:
        if os.path.isfile(DETAIL_JSON):
            with open(DETAIL_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception:
        data = {}

    PC_NAME = data.get("PcName", PC_NAME)

    shop_name = str(data.get("pisonetName", "PisoNet")).strip() or "PisoNet"

    def parse_hhmm(value, fallback):
        try:
            text = str(value).strip()
            hour, minute = map(int, text.split(":"))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour * 60 + minute
        except Exception:
            pass
        return fallback

    open_minutes = parse_hhmm(data.get("time_open", "08:00"), 8 * 60)
    close_minutes = parse_hhmm(data.get("time_close", "22:30"), 22 * 60 + 30)
    dev_btn = bool(data.get("dev_btn", True))

    def display_time(total):
        hour = (total // 60) % 24
        minute = total % 60
        suffix = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        return f"{display_hour}:{minute:02d} {suffix}"

    operation_text = f"SHOP OPERATION: {display_time(open_minutes)} - {display_time(close_minutes)}"

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

    # 00:00 -> 12:00 is handled normally.
    # If open == close, treat it as a 24-hour schedule.
    if open_minutes == close_minutes:
        return "OPEN", now

    # Supports schedules that cross midnight, e.g. 20:00 -> 04:00.
    if open_minutes < close_minutes:
        is_open = open_minutes <= current < close_minutes
    else:
        is_open = current >= open_minutes or current < close_minutes

    return ("OPEN" if is_open else "CLOSED"), now

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
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def get_pc_name():
    try:
        ip = get_local_ip()
        last = int(ip.split(".")[-1])
        return f"PC{last - IP_BASE}" if 1 <= (last - IP_BASE) <= MAX_PC else "PC1"
    except:
        return "PC1"

PC_NAME = get_pc_name()
load_detail_config()

# ================= LOAD IMAGES =================
IMAGE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"
)

def load_images():
    global images
    images = []

    try:
        if not os.path.isdir(IMAGE_FOLDER):
            return

        for filename in sorted(os.listdir(IMAGE_FOLDER)):
            path = os.path.join(IMAGE_FOLDER, filename)
            if os.path.isfile(path) and filename.lower().endswith(IMAGE_EXTENSIONS):
                images.append(path)
    except Exception:
        images = []

images = []
load_images()

# ================= AUDIO =================
def mute():
    try:
        dev = AudioUtilities.GetSpeakers()
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMute(1, None)
    except Exception:
        pass

def unmute():
    try:
        dev = AudioUtilities.GetSpeakers()
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMute(0, None)
    except Exception:
        pass

# ================= INPUT =================
BLOCK_KEYS = ["tab", "esc", "windows", "alt"]

def lock_input():
    for key in BLOCK_KEYS:
        try:
            keyboard.block_key(key)
        except Exception:
            pass

def unlock_input():
    for key in BLOCK_KEYS:
        try:
            keyboard.unblock_key(key)
        except Exception:
            pass

# ================= LOGGING =================
def log_to_google(minutes):
    try:
        requests.post(
            GOOGLE_SCRIPT_URL,
            json={"pc": PC_NAME, "minutes": minutes},
            timeout=5
        )
    except Exception:
        pass

# ================= TIMER / INSERT COIN =================
def add_minutes(minutes):
    global remaining_seconds

    if minutes <= 0:
        return

    status, _ = get_shop_status()
    if status != "OPEN":
        return

    with lock:
        remaining_seconds += minutes * 60

    threading.Thread(
        target=log_to_google,
        args=(minutes,),
        daemon=True
    ).start()

    if root:
        root.after(0, refresh_ui)

def insert_coin():
    add_minutes(INSERT_COIN_MINUTES)

def countdown():
    global remaining_seconds

    while True:
        time.sleep(1)

        with lock:
            if remaining_seconds > 0:
                remaining_seconds -= 1

        if root:
            root.after(0, refresh_ui)

# ================= NETWORK SERVER =================
def handle_client(conn, addr):
    try:
        data = conn.recv(1024).decode(errors="ignore").strip()
        match = re.fullmatch(
            rf"{re.escape(PC_NAME)}:(\+|\-)(\d+)",
            data,
            re.I
        )

        if not match:
            conn.sendall(b"ERROR")
            return

        sign, minutes_text = match.groups()
        minutes = int(minutes_text)
        status, _ = get_shop_status()

        if status == "TAMPERED":
            conn.sendall(b"BLOCKED")
            return

        if status != "OPEN":
            conn.sendall(b"SHOP CLOSED")
            return

        with lock:
            if sign == "+":
                remaining_seconds += minutes * 60
            else:
                remaining_seconds = max(
                    0,
                    remaining_seconds - minutes * 60
                )

        if sign == "+":
            threading.Thread(
                target=log_to_google,
                args=(minutes,),
                daemon=True
            ).start()

        conn.sendall(b"OK")

        if root:
            root.after(0, refresh_ui)

    except Exception:
        pass
    finally:
        conn.close()

def server():
    server_socket = socket.socket()
    server_socket.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)

    while True:
        conn, addr = server_socket.accept()
        threading.Thread(
            target=handle_client,
            args=(conn, addr),
            daemon=True
        ).start()

# ================= KIOSK UI =================
def format_time(seconds):
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def update_background():
    global background_photo, current_image_index

    if not root or not canvas:
        return

    width = max(1, root.winfo_width())
    height = max(1, root.winfo_height())

    if images:
        try:
            path = images[current_image_index % len(images)]
            with Image.open(path) as source:
                image = source.convert("RGB")
                image = ImageOps.fit(
                    image,
                    (width, height),
                    method=Image.Resampling.LANCZOS
                )

            background_photo = ImageTk.PhotoImage(image)
            canvas.itemconfig("background", image=background_photo)
        except Exception:
            canvas.itemconfig("background", image="")
            canvas.tag_lower("background")
    else:
        canvas.itemconfig("background", image="")
        canvas.tag_lower("background")

def next_background():
    global current_image_index

    if not root or not canvas:
        return

    if images:
        current_image_index = (
            current_image_index + 1
        ) % len(images)
        update_background()

    root.after(SLIDE_INTERVAL * 1000, next_background)

def build_main_ui():
    global root, canvas, timer_text, status_text

    root = tk.Tk()
    root.title("PisoNet Client")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg="black", cursor="arrow")
    root.protocol("WM_DELETE_WINDOW", lambda: None)

    canvas = tk.Canvas(
        root,
        bg="black",
        highlightthickness=0,
        cursor="arrow"
    )
    canvas.pack(fill="both", expand=True)

    canvas.create_rectangle(
        0, 0,
        root.winfo_screenwidth(),
        root.winfo_screenheight(),
        fill="black",
        outline="",
        tags="background"
    )

    update_background()

    canvas.create_text(
        root.winfo_screenwidth() // 2,
        75,
        text=shop_name.upper(),
        fill="white",
        font=("Arial", 42, "bold"),
        tags="ui"
    )

    canvas.create_text(
        root.winfo_screenwidth() // 2,
        125,
        text=PC_NAME,
        fill="white",
        font=("Arial", 22),
        tags="ui"
    )

    canvas.create_text(
        root.winfo_screenwidth() // 2,
        175,
        text=operation_text,
        fill="white",
        font=("Arial", 20, "bold"),
        tags="ui"
    )

    timer_text = canvas.create_text(
        root.winfo_screenwidth() // 2,
        root.winfo_screenheight() // 2 - 40,
        text="00:00:00",
        fill="white",
        font=("Arial", 90, "bold"),
        tags="ui"
    )

    status_text = canvas.create_text(
        root.winfo_screenwidth() // 2,
        root.winfo_screenheight() // 2 + 70,
        text="",
        fill="white",
        font=("Arial", 24),
        tags="ui"
    )

    if dev_btn:
        insert_button = tk.Button(
            root,
            text="INSERT COIN",
            command=insert_coin,
            font=("Arial", 30, "bold"),
            padx=50,
            pady=25,
            bg="white",
            fg="black",
            activebackground="lightgray",
            relief="raised",
            bd=4,
            cursor="hand2"
        )

        canvas.create_window(
            root.winfo_screenwidth() // 2,
            root.winfo_screenheight() // 2 + 180,
            window=insert_button,
            tags="ui"
        )

    root.config(cursor="arrow")
    root.bind("<Alt-F4>", lambda event: "break")
    root.bind("<Escape>", lambda event: "break")
    root.bind("<Configure>", lambda event: update_background())

def refresh_ui():
    if not root or not canvas:
        return

    status, _ = get_shop_status()

    with lock:
        seconds = remaining_seconds

    if timer_text:
        canvas.itemconfig(
            timer_text,
            text=format_time(seconds)
        )

    if status == "TAMPERED":
        message = "TIME VERIFICATION ERROR"
    elif status != "OPEN":
        message = "SHOP CLOSED"
    elif seconds <= 0:
        message = "INSERT COIN TO START"
    else:
        message = "TIME REMAINING"

    if status_text:
        canvas.itemconfig(status_text, text=message)

    root.after(1000, refresh_ui)

# ================= START =================
threading.Thread(target=server, daemon=True).start()
threading.Thread(target=countdown, daemon=True).start()

build_main_ui()
refresh_ui()

if root:
    root.after(SLIDE_INTERVAL * 1000, next_background)

root.mainloop()
