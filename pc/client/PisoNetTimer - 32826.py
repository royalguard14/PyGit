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
# Loaded dynamically from detail.json after configuration is read.
RECOVERY_FILE = None

def save_state():
    try:
        if not RECOVERY_FILE:
            return
        folder = os.path.dirname(RECOVERY_FILE)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(RECOVERY_FILE, "w") as f:
            json.dump({"remaining": remaining_seconds}, f)
    except:
        pass

def load_state():
    global remaining_seconds
    if not RECOVERY_FILE:
        return
    if not os.path.exists(RECOVERY_FILE):
        try:
            folder = os.path.dirname(RECOVERY_FILE)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(RECOVERY_FILE, "w") as f:
                json.dump({"remaining": 0}, f)
        except:
            pass
        return
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
    close_time = CLOSE_HOUR * 60 + CLOSE_MINUTE

    # Opening time is intentionally not enforced.
    # The PC may be started at any time. Only closing time matters.
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
RECOVERY_FILE = data.get("RECOVERY_FILE", os.path.join(IMAGE_FOLDER, "recovery.json"))

# Create the configured recovery file automatically when missing.
try:
    recovery_dir = os.path.dirname(RECOVERY_FILE)
    if recovery_dir:
        os.makedirs(recovery_dir, exist_ok=True)
    if not os.path.exists(RECOVERY_FILE):
        with open(RECOVERY_FILE, "w") as f:
            json.dump({"remaining": 0}, f)
except:
    pass

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
