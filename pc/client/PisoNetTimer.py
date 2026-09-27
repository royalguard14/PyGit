VERSION = "1.4.8"

# ================= IMPORTS =================
import socket, sys, threading, re, tkinter as tk, time, os, json, requests, shutil, subprocess, tempfile, urllib.request
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

# ================= INSTALL / SELF UPDATE =================
APP_VERSION = "1.4.8"
GITHUB_BASE = "https://raw.githubusercontent.com/royalguard14/PyGit/main/pc/client/"
CONTROL_URL = GITHUB_BASE + "control.json"
APP_DIR = os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "PisoNetClient")
APP_EXE = os.path.join(APP_DIR, "PisoNet.exe")
LOCAL_CONTROL = os.path.join(APP_DIR, "control.json")
LOG_FILE = os.path.join(APP_DIR, "setup.log")
STARTUP_DIR = os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
STARTUP_LINK = os.path.join(STARTUP_DIR, "PisoNet.lnk")
FIREWALL_RULE = "PisoNet TCP 5000"

def setup_log(message):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass

def setup_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def relaunch_admin():
    if setup_admin():
        return False
    executable = sys.executable
    args = " ".join(f'"{a}"' for a in sys.argv[1:])
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, args, os.path.dirname(os.path.abspath(sys.argv[0])), 1
    )
    if result <= 32:
        raise PermissionError("Administrator privileges are required.")
    return True

def fetch_setup_bytes(url):
    request = urllib.request.Request(
        url + ("&" if "?" in url else "?") + "_=" + os.urandom(8).hex(),
        headers={"User-Agent": "PisoNet", "Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()

def version_tuple(value):
    try:
        return tuple(int(x) for x in str(value).split("."))
    except Exception:
        return (0,)

def save_local_control(control):
    os.makedirs(APP_DIR, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=".control.", suffix=".json", dir=APP_DIR, text=True)
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(control, f, indent=2)
            f.write("\n")
        os.replace(path, LOCAL_CONTROL)
    finally:
        if os.path.exists(path):
            os.remove(path)

def configure_firewall():
    subprocess.run(
        ["netsh", "advfirewall", "firewall", "add", "rule",
         "name=" + FIREWALL_RULE, "dir=in", "action=allow",
         "protocol=TCP", "localport=5000", "profile=any", "enable=yes"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )

def configure_startup():
    os.makedirs(STARTUP_DIR, exist_ok=True)
    ps = (
        '$ws=New-Object -ComObject WScript.Shell;'
        f'$s=$ws.CreateShortcut("{STARTUP_LINK}");'
        f'$s.TargetPath="{APP_EXE}";'
        f'$s.WorkingDirectory="{APP_DIR}";'
        '$s.WindowStyle=7;$s.Save()'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )

def install_self():
    if not getattr(sys, "frozen", False):
        return True
    current = os.path.normcase(os.path.abspath(sys.executable))
    target = os.path.normcase(os.path.abspath(APP_EXE))
    if current == target:
        return True
    os.makedirs(APP_DIR, exist_ok=True)
    shutil.copy2(current, APP_EXE)
    setup_log("Installed PisoNet.exe to Program Files.")
    subprocess.Popen([APP_EXE], cwd=APP_DIR, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return False

def request_self_update(remote):
    if not getattr(sys, "frozen", False):
        return False
    url = remote.get("download", GITHUB_BASE + "PisoNet.exe")
    fd, new_path = tempfile.mkstemp(prefix=".PisoNet.new.", suffix=".exe", dir=APP_DIR)
    os.close(fd)
    try:
        with open(new_path, "wb") as f:
            f.write(fetch_setup_bytes(url))
        script_fd, script_path = tempfile.mkstemp(prefix=".PisoNet.update.", suffix=".cmd", dir=APP_DIR, text=True)
        os.close(script_fd)
        current_pid = os.getpid()
        with open(script_path, "w", encoding="utf-8") as f:
            f.write("@echo off\n")
            f.write("setlocal\n")
            f.write(f"set PID={current_pid}\n")
            f.write(f'set NEW="{new_path}"\n')
            f.write(f'set TARGET="{APP_EXE}"\n')
            f.write('for /l %%i in (1,1,30) do (tasklist /fi "PID eq %PID%" | findstr /r /c:" %PID% " >nul || goto stopped) & timeout /t 1 /nobreak >nul\n')
            f.write(":stopped\n")
            f.write("copy /y %NEW% %TARGET% >nul\n")
            f.write('start "" %TARGET%\n')
            f.write("del /q %NEW% >nul 2>&1\n")
            f.write('del /q "%~f0" >nul 2>&1\n')
        subprocess.Popen(["cmd", "/c", script_path], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        setup_log("New version downloaded; restarting.")
        return True
    except Exception as exc:
        setup_log("Update failed: " + str(exc))
        if os.path.exists(new_path):
            os.remove(new_path)
        return False

def initialize_installation():
    if relaunch_admin():
        return False
    if not install_self():
        return False

    os.makedirs(APP_DIR, exist_ok=True)
    try:
        remote = json.loads(fetch_setup_bytes(CONTROL_URL).decode("utf-8"))
    except Exception as exc:
        setup_log("GitHub check failed: " + str(exc))
        remote = None

    local = None
    try:
        with open(LOCAL_CONTROL, "r", encoding="utf-8") as f:
            local = json.load(f)
    except Exception:
        pass

    if remote and "version" in remote:
        remote_version = version_tuple(remote["version"])
        local_version = version_tuple(local.get("version", APP_VERSION)) if local else version_tuple(APP_VERSION)
        if remote_version > local_version and request_self_update(remote):
            return False
        save_local_control(remote)

    configure_firewall()
    configure_startup()
    return True

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
background_item = None
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

    PC_NAME = str(data.get("PcName", PC_NAME)).strip() or PC_NAME
    shop_name = str(data.get("pisonetName", "PisoNet")).strip() or "PisoNet"

    def parse_hhmm(value, fallback):
        try:
            text = str(value).strip()
            hour, minute = map(int, text.split(":"))

            # Accept 24:00 as midnight/end-of-day.
            if hour == 24 and minute == 0:
                return 24 * 60

            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour * 60 + minute
        except Exception:
            pass

        return fallback

    open_minutes = parse_hhmm(data.get("time_open", "08:00"), 8 * 60)
    close_minutes = parse_hhmm(data.get("time_close", "22:30"), 22 * 60 + 30)
    dev_btn = bool(data.get("dev_btn", True))

    def display_time(total):
        if total == 24 * 60:
            return "12:00 AM"
        hour = (total // 60) % 24
        minute = total % 60
        suffix = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        return f"{display_hour}:{minute:02d} {suffix}"

    operation_text = (
        f"SHOP OPERATION: {display_time(open_minutes)} - "
        f"{display_time(close_minutes)}"
    )

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

    # 24:00 means midnight at the end of the day.
    normalized_open = open_minutes % (24 * 60)
    normalized_close = close_minutes % (24 * 60)

    # Same start/end means 24-hour operation.
    if open_minutes == close_minutes:
        return "OPEN", now

    if close_minutes == 24 * 60:
        is_open = current >= normalized_open
    elif open_minutes < close_minutes:
        is_open = normalized_open <= current < normalized_close
    else:
        # Overnight schedule, e.g. 20:00 -> 04:00.
        is_open = current >= normalized_open or current < normalized_close

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

    if not root or not canvas or not background_item:
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
            canvas.itemconfig(background_item, image=background_photo)
        except Exception:
            canvas.itemconfig(background_item, image="")
    else:
        canvas.itemconfig(background_item, image="")

    canvas.tag_lower(background_item)

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
    global root, canvas, timer_text, status_text, background_item

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

    # This must be an IMAGE item, not a rectangle.
    # A rectangle does not support the Canvas -image option.
    background_item = canvas.create_image(
        root.winfo_screenwidth() // 2,
        root.winfo_screenheight() // 2,
        image="",
        anchor="center",
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

    maintenance_button = tk.Button(
        root,
        text="MAINTENANCE / EXIT",
        command=exit_kiosk,
        font=("Arial", 16, "bold"),
        padx=18,
        pady=8,
        bg="white",
        fg="black",
        activebackground="lightgray",
        relief="raised",
        bd=3,
        cursor="hand2"
    )

    canvas.create_window(
        root.winfo_screenwidth() - 130,
        root.winfo_screenheight() - 45,
        window=maintenance_button,
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

def exit_kiosk():
    try:
        unlock_input()
    except Exception:
        pass

    try:
        unmute()
    except Exception:
        pass

    if root:
        root.destroy()


# ================= START =================
if not initialize_installation():
    sys.exit(0)

threading.Thread(target=server, daemon=True).start()
threading.Thread(target=countdown, daemon=True).start()

build_main_ui()
refresh_ui()

if root:
    root.after(SLIDE_INTERVAL * 1000, next_background)

root.mainloop()
