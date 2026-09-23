import os
import sys
import time
import random
import threading
import tkinter as tk

# ANSI Escape Codes para sa makukulay na Terminal Outputs
GREEN = "\033[38;5;46m"
RED = "\033[38;5;196m"
CYAN = "\033[38;5;51m"
YELLOW = "\033[38;5;226m"
PURPLE = "\033[38;5;129m"
RESET = "\033[0m"
BOLD = "\033[1m"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def typewriter(text, delay=0.03, color=GREEN):
    for char in text:
        sys.stdout.write(color + char + RESET)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def progress_bar(task_name, duration=2):
    sys.stdout.write(f"{CYAN}{task_name:<25} [")
    steps = 20
    for i in range(steps + 1):
        percent = int((i / steps) * 100)
        bar = "█" * i + " " * (steps - i)
        sys.stdout.write(f"\r{CYAN}{task_name:<25} [{GREEN}{bar}{CYAN}] {percent}%")
        sys.stdout.flush()
        time.sleep(duration / steps)
    print(f" {BOLD}{GREEN}SUCCESS{RESET}")

def generate_hacker_alias():
    prefixes = ["Neo", "Zero", "Phreak", "Byte", "Cipher", "Vortex", "Quantum", "Shadow"]
    suffixes = ["Ghost", "Overlord", "Daemon", "Glitch", "Synapse", "Vector", "Echo"]
    return f"{random.choice(prefixes)}_{random.choice(suffixes)}{random.randint(10, 99)}"

def matrix_rain(duration=3):
    end_time = time.time() + duration
    symbols = ["0", "1", "X", "Y", "Ω", "µ", "§", "#", "$", "%", "&"]
    print(GREEN)
    while time.time() < end_time:
        line = "".join(random.choice(symbols) + " " for _ in range(30))
        print(f"   {line}")
        time.sleep(0.05)
    print(RESET)

# --- ITO ANG MAGIC NG OVERLAY WINDOW ---
def launch_overlay():
    """Gumagawa ng transparent overlay sa top-right ng iyong monitor."""
    root = tk.Tk()
    root.overrideredirect(True)          # Tinatanggal ang window borders at title bar
    root.attributes("-topmost", True)     # Pinupwersang laging nasa ibabaw ng lahat ng windows
    
    # Gawing transparent ang background (Gumagana nang maayos sa Windows)
    root.config(bg='black')
    root.wm_attributes('-transparentcolor', 'black')
    
    # Alamin ang sukat ng iyong screen para mailagay sa eksaktong TOP-RIGHT
    screen_width = root.winfo_screenwidth()
    window_width = 300
    window_height = 80
    x_offset = screen_width - window_width - 20 # 20px allowance mula sa kanang dulo
    y_offset = 20                               # 20px allowance mula sa itaas
    
    root.geometry(f"{window_width}x{window_height}+{x_offset}+{y_offset}")
    
    # Ang disenyo ng "Hello World" text overlay
    label = tk.Label(
        root, 
        text="Hello world", 
        font=("Consolas", 28, "bold"), 
        fg="#00FF00", # Neon Green
        bg="black"
    )
    label.pack(expand=True)
    
    # Kusang magsasara pagkatapos ng 20 segundo (20000 milliseconds)
    root.after(20000, root.destroy)
    root.mainloop()

def main():
    clear_screen()
    
    # Pinapatakbo ang overlay gamit ang Thread para hindi ma-freeze ang terminal program
    overlay_thread = threading.Thread(target=launch_overlay, daemon=True)
    overlay_thread.start()
    
    # 1. Terminal Header
    print(f"{BOLD}{CYAN}" + "="*50)
    print(f"       CORE_SYSTEM_OS v4.02 // INITIALIZATION     ")
    print("="*50 + f"{RESET}\n")
    
    time.sleep(0.5)
    typewriter("Connecting to secure node protocols...", color=YELLOW)
    typewriter(f"{BOLD}{RED}[INFO] Top-right HUD Overlay activated for 20 seconds.{RESET}\n", delay=0.02)
    
    # 2. Loading Phase
    progress_bar("Bypassing Firewall")
    progress_bar("Injecting Py-Payload")
    progress_bar("Establishing Handshake", duration=1.5)
    
    print(f"\n{BOLD}{GREEN}[!] ACCESS GRANTED.{RESET}\n")
    time.sleep(0.8)
    
    # 3. Interactive Input at Choice
    alias = generate_hacker_alias()
    typewriter(f"System assigned codename: {BOLD}{PURPLE}{alias}{RESET}", delay=0.05)
    
    print(f"\n{BOLD}{CYAN}--- TERMINAL COMMAND OPTIONS ---{RESET}")
    print(f"[{GREEN}1{RESET}] Execute Matrix Digital Rain View")
    print(f"[{GREEN}2{RESET}] Self-Destruct Simulation")
    print(f"[{GREEN}3{RESET}] Disconnect Safely")
    
    choice = input(f"\n{BOLD}{YELLOW}Select protocol number: {RESET}")
    
    if choice == "1":
        clear_screen()
        typewriter("Booting matrix stream data...", color=GREEN)
        time.sleep(1)
        matrix_rain(duration=4)
        typewriter("\nStream paused. Goodbye, operative.", color=CYAN)
    elif choice == "2":
        clear_screen()
        print(f"{BOLD}{RED}!!! CRITICAL ALARM: SELF-DESTRUCT INITIATED !!!{RESET}\n")
        for i in range(5, 0, -1):
            print(f"{RED}System collapsing in... {i}{RESET}")
            time.sleep(1)
        print(f"\n{BOLD}{RED}[CRASH] Connection terminated.{RESET}")
    else:
        typewriter("\nTerminating terminal cleanly. Safe travels.", color=CYAN)

if __name__ == "__main__":
    main()
