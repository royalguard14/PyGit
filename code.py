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

# --- FULL MONITOR CLICK-BLOCKING OVERLAY ---
def launch_full_overlay():
    """Gumagawa ng full-screen overlay na humaharang sa lahat ng mouse clicks."""
    root = tk.Tk()
    root.overrideredirect(True)          # Tinatanggal ang window borders at taskbar blocks
    root.attributes("-topmost", True)     # Pinupwersang laging nasa ibabaw ng lahat
    
    # Sakupin ang buong resolution ng monitor
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.geometry(f"{screen_width}x{screen_height}+0+0")
    
    # Gawing bahagyang transparent ang buong window (0.3 = 30% opacity)
    # Magmumukha itong tinted glass para kita pa rin ang desktop pero bawal i-click
    root.configure(bg='black')
    root.attributes("-alpha", 0.3)
    
    # Puwersahing makuha ng window na ito ang lahat ng focus para hindi ma-click ang likod
    root.focus_force()
    root.grab_set() 
    
    # Lagyan ng malaking "Hello World" label sa gitna ng screen
    label = tk.Label(
        root, 
        text="Hello world", 
        font=("Consolas", 48, "bold"), 
        fg="#00FF00", # Neon Green
        bg="black"
    )
    label.place(relx=0.5, rely=0.5, anchor="center")
    
    # Kusang magsasara pagkatapos ng 50 segundo (50000 milliseconds)
    root.after(50000, root.destroy)
    root.mainloop()

def main():
    clear_screen()
    
    # Patakbuhin ang full-screen barrier gamit ang Thread upang hindi ma-stuck ang terminal
    overlay_thread = threading.Thread(target=launch_full_overlay, daemon=True)
    overlay_thread.start()
    
    # Terminal Execution (Habang naka-lock ang screen sa likod)
    print(f"{BOLD}{RED}" + "="*50)
    print(f"       SYSTEM LOCK INITIATED // FULL SCREEN BLOCK     ")
    print("="*50 + f"{RESET}\n")
    
    time.sleep(0.5)
    typewriter("Deploying digital security perimeter...", color=YELLOW)
    typewriter(f"{BOLD}{RED}[ALERT] Monitor click-lock active for 50 seconds.{RESET}\n", delay=0.02)
    
    # Kunwaring may ginagawang system diagnostic habang naka-lock
    progress_bar("Securing Desktop Input")
    progress_bar("Syncing Crypt Keys", duration=3)
    progress_bar("Analyzing Threat Vector", duration=2)
    
    print(f"\n{BOLD}{GREEN}[!] Main program running seamlessly in background.{RESET}")
    print(f"{CYAN}Maghihintay ang terminal hanggang matapos ang 50 segundo ng overlay...{RESET}\n")
    
    # Panatilihing buhay ang terminal hanggang kusang mamatay ang overlay thread
    time.sleep(45) 
    typewriter("Overlay termination sequence standby...", color=YELLOW)
    time.sleep(5)
    
    print(f"\n{BOLD}{GREEN}[!] SYSTEM UNLOCKED. Control returned to user.{RESET}")

if __name__ == "__main__":
    main()
