VERSION = "1.4.1"

# ================= IMPORTS =================
import socket, sys, threading, re, tkinter as tk, time, os, json, requests
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
        print("Hello World!")

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

        # PC name badge centered at the top
        font = ("Arial", 64, "bold")
        screen_w = overlay.winfo_screenwidth()
        x_center = screen_w // 2
        y = 35

        # Centered rounded badge
        text_width = max(260, len(PC_NAME) * 43)
        text_height = 78
        pad_x = 30
        pad_y = 18
        badge_w = text_width + (pad_x * 2) + 45
        badge_h = text_height + (pad_y * 2)
        badge_x1 = x_center - badge_w // 2
        badge_y1 = y
        badge_x2 = x_center + badge_w // 2
        badge_y2 = y + badge_h
        r = 28

        # Tkinter canvas items cannot have independent alpha.
        # Use a semi-transparent overlay window effect instead.
        badge = tk.Frame(overlay, bg="white", bd=0, highlightthickness=0)
        badge.place(x=badge_x1, y=badge_y1, width=badge_w, height=badge_h)

        # Rounded visual treatment using nested frames
        inner = tk.Frame(badge, bg="white", bd=0, highlightthickness=0)
        inner.place(x=8, y=8, relwidth=1, relheight=1, width=-16, height=-16)

        label = tk.Label(
            inner,
            text=PC_NAME,
            font=font,
            fg="white",
            bg="white"
        )
        label.pack(expand=True, padx=20, pady=4)

        # Give the badge a polished outline and rounded-looking corners
        badge.configure(highlightbackground="black", highlightcolor="black", highlightthickness=3)

        # Fade the whole badge window area to approximately 80% opacity
        # while keeping the slideshow visible around it.
        try:
            badge.attributes("-alpha", 0.80)
        except:
            pass


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