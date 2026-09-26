VERSION = "1.4.3"

# ================= IMPORTS =================
import socket, sys, threading, re, tkinter as tk, time, os, json, requests
from PIL import Image, ImageTk
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
OPEN_HOUR = 8
OPEN_MINUTE = 0
CLOSE_HOUR = 22
CLOSE_MINUTE = 30

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
root = None
timer_label = None
status_label = None

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
    if current >= close_time:
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

# ================= LOAD CONFIG =================
if os.path.exists(DETAIL_JSON):
    try:
        with open(DETAIL_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
else:
    data = {}

PC_NAME = data.get("PcName", PC_NAME)

# ================= LOAD IMAGES =================
if os.path.exists(IMAGE_FOLDER):
    for filename in os.listdir(IMAGE_FOLDER):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            images.append(os.path.join(IMAGE_FOLDER, filename))

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
        requests.post(GOOGLE_SCRIPT_URL, json={"pc": PC_NAME, "minutes": minutes}, timeout=5)
    except Exception:
        pass

# ================= TIMER =================
def add_minutes(minutes):
    global remaining_seconds
    if minutes <= 0:
        return

    status, _ = get_shop_status()
    if status == "TAMPERED" or status != "OPEN":
        return

    with lock:
        remaining_seconds += minutes * 60

    threading.Thread(target=log_to_google, args=(minutes,), daemon=True).start()
    root.after(0, refresh_ui)


def insert_coin():
    # Manual/test coin button. One test coin currently adds 1 minute.
    add_minutes(1)


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
        match = re.fullmatch(rf"{re.escape(PC_NAME)}:(\+|\-)(\d+)", data, re.I)

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
                remaining_seconds = max(0, remaining_seconds - minutes * 60)

        if sign == "+":
            threading.Thread(target=log_to_google, args=(minutes,), daemon=True).start()

        conn.sendall(b"OK")
        if root:
            root.after(0, refresh_ui)
    except Exception:
        pass
    finally:
        conn.close()


def server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)
    while True:
        conn, addr = server_socket.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

# ================= KIOSK UI =================
def format_time(seconds):
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_main_ui():
    global root, timer_label, status_label

    root = tk.Tk()
    root.title("PisoNet Client")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg="black")
    root.protocol("WM_DELETE_WINDOW", lambda: None)

    frame = tk.Frame(root, bg="black")
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="PISONET CLIENT", bg="black", fg="white",
             font=("Arial", 42, "bold")).pack(pady=(70, 10))

    tk.Label(frame, text=PC_NAME, bg="black", fg="gray",
             font=("Arial", 22)).pack(pady=(0, 35))

    timer_label = tk.Label(frame, text="00:00:00", bg="black", fg="white",
                           font=("Arial", 90, "bold"))
    timer_label.pack(pady=20)

    status_label = tk.Label(frame, text="", bg="black", fg="white",
                            font=("Arial", 24))
    status_label.pack(pady=15)

    insert_button = tk.Button(
        frame,
        text="INSERT COIN",
        command=insert_coin,
        font=("Arial", 30, "bold"),
        padx=50,
        pady=25,
        bg="white",
        fg="black",
        activebackground="lightgray",
        relief="raised",
        bd=4
    )
    insert_button.pack(pady=35)

    root.bind("<Alt-F4>", lambda event: "break")
    root.bind("<Escape>", lambda event: "break")


def refresh_ui():
    if not root:
        return

    status, _ = get_shop_status()
    with lock:
        seconds = remaining_seconds

    if timer_label:
        timer_label.config(text=format_time(seconds))

    if status == "TAMPERED":
        status_label.config(text="TIME VERIFICATION ERROR")
    elif status != "OPEN":
        status_label.config(text="SHOP CLOSED")
    elif seconds <= 0:
        status_label.config(text="INSERT COIN TO START")
    else:
        status_label.config(text="TIME REMAINING")

    root.after(1000, refresh_ui)

# ================= START =================
threading.Thread(target=server, daemon=True).start()
threading.Thread(target=countdown, daemon=True).start()

build_main_ui()
refresh_ui()
root.mainloop()
