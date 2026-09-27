VERSION = "0.1.0"

# Development build: keep keyboard hooks disabled so Ctrl+C can stop Python.
DEV_MODE = True

import json
import os
import socket
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageTk, ImageOps

try:
    import keyboard
except Exception:
    keyboard = None

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import POINTER, cast
except Exception:
    AudioUtilities = None
    IAudioEndpointVolume = None
    CLSCTX_ALL = None
    POINTER = cast = None

IMAGE_FOLDER = r"C:\sufyan"
DETAIL_JSON = os.path.join(IMAGE_FOLDER, "detail.json")
PC_PORT = 5000
NODEMCU_PORT = 5001
DISCOVERY_TIMEOUT = 0.35
DISCOVERY_WORKERS = 32
SLIDE_INTERVAL = 5
MAINTENANCE_MINUTES = 5
CONTROL_HEARTBEAT_INTERVAL = 3
BLOCK_KEYS = ["tab", "esc", "windows", "alt", "ctrl", "shift", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12"]

root = canvas = background_item = background_photo = None
timer_items = []
pc_items = []
shop_items = []
status_items = []
coin_button = maintenance_button = insert_overlay = None
images = []
current_image_index = 0
remaining_seconds = 0
timer_lock = threading.Lock()
pc_name = "PC1"
shop_name = "PISONET"
operation_text = ""
shop_open = 0
shop_close = 24 * 60

# requesting = discovery/connection in progress
# receiving = NodeMCU receiver is connected and the kiosk is READY for coins
receiving = requesting = False

node_socket = None
node_socket_lock = threading.Lock()
nodemcu_ip = None
shutdown_event = threading.Event()


def load_detail_config():
    global pc_name, shop_name, operation_text, shop_open, shop_close
    try:
        with open(DETAIL_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    pc_name = str(data.get("PcName", "PC1")).strip() or "PC1"
    shop_name = str(data.get("pisonetName", "PISONET")).strip() or "PISONET"

    def parse_time(value, fallback):
        try:
            h, m = map(int, str(value).strip().split(":"))
            if h == 24 and m == 0:
                return 1440
            if 0 <= h <= 23 and 0 <= m <= 59:
                return h * 60 + m
        except Exception:
            pass
        return fallback

    shop_open = parse_time(data.get("time_open", "08:00"), 8 * 60)
    shop_close = parse_time(data.get("time_close", "24:00"), 24 * 60)

    def display(total):
        if total == 1440:
            return "12:00 AM"
        h = (total // 60) % 24
        m = total % 60
        return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"

    operation_text = f"SHOP OPERATION: {display(shop_open)} - {display(shop_close)}"


def load_images():
    global images
    images = []
    if not os.path.isdir(IMAGE_FOLDER):
        return

    try:
        for filename in sorted(os.listdir(IMAGE_FOLDER)):
            path = os.path.join(IMAGE_FOLDER, filename)
            if os.path.isfile(path) and filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")
            ):
                images.append(path)
    except Exception:
        images = []


def get_local_ip():
    for target in ("8.8.8.8", "1.1.1.1"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            pass
        finally:
            s.close()

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass

    return "127.0.0.1"


def discover_nodemcu(local_ip):
    parts = local_ip.split(".")
    if len(parts) != 4:
        return None, None

    prefix = ".".join(parts[:3])
    own_last = int(parts[3])
    candidates = [f"{prefix}.{i}" for i in range(1, 255) if i != own_last]

    def probe(ip):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(DISCOVERY_TIMEOUT)

        try:
            sock.connect((ip, NODEMCU_PORT))
            sock.settimeout(1.5)
            sock.sendall(f"REQUEST|{pc_name}|{local_ip}|{PC_PORT}\n".encode("utf-8"))

            response = sock.recv(256).decode("utf-8", errors="ignore").strip()

            if response.startswith("ACCEPTED|"):
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
                return result[0], (result[1], result[2])

    return None, None


def start_pc_receiver():
    """Listen for NodeMCU coin messages on TCP port 5000."""

    def server_loop():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            server.bind(("0.0.0.0", PC_PORT))
            server.listen(5)
            server.settimeout(1.0)
            print(f"[PISONET] PC receiver listening on TCP {PC_PORT}")

        except OSError as exc:
            print(f"[PISONET] Cannot start PC receiver on port {PC_PORT}: {exc}")
            server.close()
            return

        while not shutdown_event.is_set():
            try:
                client, address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(
                target=handle_pc_receiver,
                args=(client, address),
                daemon=True,
            ).start()

        server.close()

    threading.Thread(target=server_loop, daemon=True).start()


def handle_pc_receiver(sock, address):
    """Handle NodeMCU receiver messages on TCP port 5000."""
    global receiving, requesting

    buffer = ""
    print(f"[PISONET] NodeMCU receiver connected from {address[0]}:{address[1]}")

    try:
        sock.settimeout(1.0)

        while not shutdown_event.is_set():
            try:
                data = sock.recv(1024)
            except socket.timeout:
                continue

            if not data:
                break

            buffer += data.decode("utf-8", errors="ignore")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()

                if not line:
                    continue

                if line == "PYGIT READY":
                    # This is the actual signal that the NodeMCU has
                    # connected to the PC receiver. Only now do we say
                    # the kiosk is READY TO COLLECT COIN.
                    receiving = True
                    requesting = False
                    print("[PISONET] PYGIT READY received.")
                    print("[PISONET] READY TO COLLECT COIN.")
                    if root:
                        root.after(0, update_coin_button)

                elif line.startswith("COIN:"):
                    try:
                        minutes = int(line.split(":", 1)[1])
                    except ValueError:
                        print(f"[PISONET] Invalid coin message: {line}")
                        continue

                    if minutes > 0 and receiving:
                        add_minutes(minutes)
                        print(f"[PISONET] COIN received: +{minutes} minute(s)")

                        try:
                            sock.sendall(b"COIN_RECEIVED\n")
                        except OSError:
                            pass

                elif line.startswith("COIN_IDLE|"):
                    receiving = False
                    print(f"[PISONET] {line} - coin window ended.")
                    if root:
                        root.after(0, update_coin_button)

    except OSError as exc:
        print(f"[PISONET] Receiver connection ended: {exc}")

    finally:
        try:
            sock.close()
        except OSError:
            pass

        # Receiver channel ended. Keep the NodeMCU control channel alive,
        # but remove the READY state so the UI cannot claim coin readiness.
        receiving = False

        if root:
            root.after(0, update_coin_button)


def control_heartbeat(sock):
    """Keep the NodeMCU control TCP connection alive."""
    while not shutdown_event.is_set():
        time.sleep(CONTROL_HEARTBEAT_INTERVAL)

        with node_socket_lock:
            if node_socket is not sock:
                return

            try:
                sock.sendall(b"PING\n")
            except OSError:
                return


def request_node_receiving():
    global receiving, requesting, node_socket, nodemcu_ip

    local_ip = get_local_ip()
    ip, result = discover_nodemcu(local_ip)

    if not ip or not result:
        receiving = False
        requesting = False
        set_status("")
        root.after(0, update_coin_button)
        return

    sock, response = result
    nodemcu_ip = ip

    with node_socket_lock:
        if node_socket:
            try:
                node_socket.close()
            except OSError:
                pass

        node_socket = sock

    # Do not show READY yet. The NodeMCU still has to establish
    # its separate receiver connection and send PYGIT READY.
    receiving = False
    requesting = True

    set_status("")
    root.after(0, update_coin_button)

    threading.Thread(
        target=listen_to_nodemcu,
        args=(sock,),
        daemon=True,
    ).start()

    threading.Thread(
        target=control_heartbeat,
        args=(sock,),
        daemon=True,
    ).start()


def release_node():
    global receiving, requesting, node_socket

    receiving = False
    requesting = False

    with node_socket_lock:
        sock = node_socket
        node_socket = None

    if sock:
        try:
            sock.sendall(f"RELEASE|{pc_name}\n".encode("utf-8"))
        except OSError:
            pass

        try:
            sock.close()
        except OSError:
            pass

    if root:
        root.after(0, update_coin_button)


def listen_to_nodemcu(sock):
    global receiving, requesting, node_socket

    buffer = ""

    try:
        while not shutdown_event.is_set():
            data = sock.recv(1024)

            if not data:
                break

            buffer += data.decode("utf-8", errors="ignore")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()

                if not line:
                    continue

                if line in ("PYGIT READY", "PONG"):
                    continue

                if line.startswith("COIN:"):
                    try:
                        minutes = int(line.split(":", 1)[1])
                    except ValueError:
                        continue

                    if receiving and minutes > 0:
                        add_minutes(minutes)

                        try:
                            sock.sendall(b"COIN_RECEIVED\n")
                        except OSError:
                            pass

                elif line.startswith("COIN_IDLE|"):
                    receiving = False
                    print(f"[PISONET] {line} - coin window ended.")
                    root.after(0, update_coin_button)

                elif line.startswith("ACCEPTED|"):
                    # Control-channel confirmation. The visible READY
                    # state still waits for PYGIT READY on port 5000.
                    requesting = True
                    root.after(0, update_coin_button)

    except OSError:
        pass

    finally:
        receiving = False
        requesting = False

        with node_socket_lock:
            if node_socket is sock:
                node_socket = None

        if root:
            root.after(0, update_coin_button)


def format_time(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def add_minutes(minutes):
    global remaining_seconds

    if minutes <= 0:
        return

    with timer_lock:
        remaining_seconds += minutes * 60

    if root:
        root.after(0, refresh_ui)


def countdown_loop():
    global remaining_seconds

    while not shutdown_event.is_set():
        time.sleep(1)

        with timer_lock:
            before = remaining_seconds

            if remaining_seconds > 0:
                remaining_seconds -= 1

            after = remaining_seconds

        if before > 0 and after == 0:
            enter_expired_state()

        if root:
            root.after(0, refresh_ui)


def mute_audio():
    if not AudioUtilities:
        return

    try:
        dev = AudioUtilities.GetSpeakers()
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(iface, POINTER(IAudioEndpointVolume))
        volume.SetMute(1, None)
    except Exception:
        pass


def unmute_audio():
    if not AudioUtilities:
        return

    try:
        dev = AudioUtilities.GetSpeakers()
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(iface, POINTER(IAudioEndpointVolume))
        volume.SetMute(0, None)
    except Exception:
        pass


def lock_keyboard():
    if DEV_MODE or not keyboard:
        return

    for key in BLOCK_KEYS:
        try:
            keyboard.block_key(key)
        except Exception:
            pass


def unlock_keyboard():
    if DEV_MODE or not keyboard:
        return

    for key in BLOCK_KEYS:
        try:
            keyboard.unblock_key(key)
        except Exception:
            pass


def enter_expired_state():
    mute_audio()
    lock_keyboard()


def stroked_text(
    x,
    y,
    text,
    font,
    fill="white",
    stroke="black",
    width=3,
    anchor="center",
    tags="ui",
):
    for dx, dy in [
        (-width, -width),
        (0, -width),
        (width, -width),
        (-width, 0),
        (width, 0),
        (-width, width),
        (0, width),
        (width, width),
    ]:
        canvas.create_text(
            x + dx,
            y + dy,
            text=text,
            fill=stroke,
            font=font,
            anchor=anchor,
            tags=tags,
        )

    return canvas.create_text(
        x,
        y,
        text=text,
        fill=fill,
        font=font,
        anchor=anchor,
        tags=tags,
    )


def set_status(message):
    def update():
        for item in status_items:
            canvas.itemconfig(item, text=message)

    if root:
        root.after(0, update)


def update_coin_button():
    if not coin_button:
        return

    if receiving:
        coin_button.config(
            text="PLEASE INSERT COIN NOW",
            bg="#16a34a",
            activebackground="#15803d",
            state="normal",
        )

    elif requesting:
        coin_button.config(
            text="CONNECTING...",
            bg="#f59e0b",
            activebackground="#d97706",
            state="disabled",
        )

    else:
        coin_button.config(
            text="INSERT COIN",
            bg="#16a34a",
            activebackground="#15803d",
            state="normal",
        )


def insert_coin():
    global requesting

    if requesting or receiving:
        return

    requesting = True
    set_status("")
    update_coin_button()

    threading.Thread(
        target=request_node_receiving,
        daemon=True,
    ).start()


def maintenance_add_time():
    add_minutes(MAINTENANCE_MINUTES)
    set_status("")


def enter_insert_overlay():
    global insert_overlay
    insert_overlay = None


def leave_insert_overlay():
    global insert_overlay
    insert_overlay = None


def refresh_ui():
    if not root or not canvas:
        return

    with timer_lock:
        seconds = remaining_seconds

    for item in timer_items:
        canvas.itemconfig(
            item,
            text=format_time(seconds) if seconds > 0 else "",
            fill="#ff3333" if 0 < seconds <= 10 else "#00ff66",
        )

    if seconds <= 0:
        enter_insert_overlay()
        mute_audio()
        lock_keyboard()
    else:
        leave_insert_overlay()
        unmute_audio()
        unlock_keyboard()

    if status_items:
        if receiving:
            message = "READY TO COLLECT COIN"

        elif requesting:
            message = ""

        elif seconds <= 0:
            message = "INSERT COIN"

        else:
            message = "TIME REMAINING"

        for item in status_items:
            canvas.itemconfig(item, text=message)

    root.after(250, refresh_ui)


def update_background():
    global background_photo

    if not root or not canvas or not background_item:
        return

    width = max(1, root.winfo_width())
    height = max(1, root.winfo_height())

    if not images:
        canvas.itemconfig(background_item, image="")
        return

    try:
        path = images[current_image_index % len(images)]

        with Image.open(path) as source:
            image = ImageOps.fit(
                source.convert("RGB"),
                (width, height),
                method=Image.Resampling.LANCZOS,
            )

        background_photo = ImageTk.PhotoImage(image)
        canvas.itemconfig(background_item, image=background_photo)
        canvas.tag_lower(background_item)

    except Exception:
        canvas.itemconfig(background_item, image="")


def next_background():
    global current_image_index

    if not root:
        return

    if images:
        current_image_index = (current_image_index + 1) % len(images)
        update_background()

    root.after(SLIDE_INTERVAL * 1000, next_background)


def build_ui():
    global root, canvas, background_item, coin_button, maintenance_button
    global timer_items, pc_items, shop_items, status_items

    root = tk.Tk()
    root.title("PisoNet Standalone")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg="black", cursor="arrow")
    root.protocol("WM_DELETE_WINDOW", lambda: None)

    canvas = tk.Canvas(
        root,
        bg="black",
        highlightthickness=0,
        cursor="arrow",
    )
    canvas.pack(fill="both", expand=True)

    w = root.winfo_screenwidth()
    h = root.winfo_screenheight()

    background_item = canvas.create_image(
        w // 2,
        h // 2,
        image="",
        anchor="center",
        tags="background",
    )
    update_background()

    pc_items = [
        stroked_text(
            w / 2,
            45,
            pc_name,
            ("Arial", 28, "bold"),
        )
    ]

    timer_items = [
        stroked_text(
            w - 35,
            45,
            "",
            ("Arial", 34, "bold"),
            fill="#00ff66",
            anchor="ne",
        )
    ]

    shop_items = [
        stroked_text(
            w / 2,
            h / 2 - 105,
            shop_name.upper(),
            ("Arial", 54, "bold"),
        ),
        stroked_text(
            w / 2,
            h / 2 - 48,
            operation_text,
            ("Arial", 20, "bold"),
        ),
    ]

    status_items = [
        stroked_text(
            w / 2,
            h / 2 + 5,
            "INSERT COIN",
            ("Arial", 24, "bold"),
        )
    ]

    coin_button = tk.Button(
        root,
        text="INSERT COIN",
        command=insert_coin,
        font=("Arial", 24, "bold"),
        padx=60,
        pady=18,
        bg="#16a34a",
        fg="white",
        activebackground="#15803d",
        activeforeground="white",
        disabledforeground="white",
        relief="flat",
        bd=0,
        highlightthickness=0,
        cursor="hand2",
    )

    canvas.create_window(
        w / 2,
        h / 2 + 150,
        window=coin_button,
        tags="ui",
    )

    maintenance_button = tk.Button(
        root,
        text="MAINTENANCE +5 MIN",
        command=maintenance_add_time,
        font=("Arial", 13, "bold"),
        padx=14,
        pady=7,
        bg="white",
        fg="black",
        relief="raised",
        bd=3,
        cursor="hand2",
    )

    canvas.create_window(
        w - 130,
        h - 40,
        window=maintenance_button,
        tags="ui",
    )

    root.bind("<Alt-F4>", lambda event: "break")
    root.bind("<Escape>", lambda event: "break")
    root.bind("<Key>", lambda event: "break")
    root.bind("<Configure>", lambda event: update_background())


def exit_kiosk():
    shutdown_event.set()

    try:
        release_node()
    except Exception:
        pass

    unlock_keyboard()
    unmute_audio()

    if root:
        root.destroy()


def main():
    load_detail_config()
    load_images()
    build_ui()
    start_pc_receiver()

    threading.Thread(
        target=countdown_loop,
        daemon=True,
    ).start()

    root.after(100, refresh_ui)
    root.after(SLIDE_INTERVAL * 1000, next_background)

    root.mainloop()


if __name__ == "__main__":
    main()
