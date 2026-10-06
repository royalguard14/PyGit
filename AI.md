# PyGit / PisoNetTimer Project

## Current Project Status

**STATUS: WORKING / OPERATIONAL**

The current PisoNetTimer deployment is already running successfully on the client PCs.

The compiled Windows EXE client is working, users can already play on the PCs, and the **single physical coin slot** is being used to serve the active PC through the NodeMCU coin controller.

The project is now in the **working production/test-deployment stage**, not the standalone-EXE planning stage.

---

# Current Working Architecture

```
                    ┌─────────────────────┐
                    │      Android App    │
                    │   Mobile Controller │
                    └──────────┬──────────┘
                               │
                    TCP 5000 / UDP 5051
                               │
                               ▼
┌───────────────┐      ┌─────────────────────┐
│   Coin Slot   │─────▶│      NodeMCU        │
│  ONE physical │      │  Active-PC control  │
│   coin slot   │      └──────────┬──────────┘
└───────────────┘                 │
                                  │ TCP 5001
                                  │ REQUEST / RELEASE
                                  ▼
                    ┌─────────────────────────┐
                    │     PisoNetTimer.exe    │
                    │       Client PC         │
                    │                         │
                    │ TCP 5000 command server │
                    │ Fullscreen kiosk UI     │
                    └─────────────────────────┘

                    Multiple PCs can run
                    PisoNetTimer.exe.

                    NodeMCU controls which
                    PC owns the single coin slot.
```

---

# Working Components

## 1. PisoNetTimer.exe

The main client application is compiled as a Windows EXE.

The client PC does **not** need Python or manual Python package installation.

Current client responsibilities:

- Fullscreen PisoNet interface.
- PC identification.
- Shop name display.
- Remaining-time countdown.
- Insert Coin manual/test button.
- Network time commands.
- Single-instance protection.
- NTP time checking.
- Time-tampering protection.
- Shop closing-time enforcement.
- NodeMCU coin integration.
- Google Sheet logging.
- Windows kiosk behavior.
- TCP command server on port **5000**.
- Communication with NodeMCU on port **5001**.

The client EXE is already running successfully on deployed/test PCs.

---

# 2. Windows Service

The Windows Service is responsible for starting and supervising the PisoNet client.

Current deployment uses:

```
SufyanPisoNetTimerService.exe
        ↓
Windows Service
        ↓
PisoNetTimer.exe
```

The service is installed with automatic startup.

The service is responsible for launching the GUI in the active interactive Windows session.

---

# 3. Installer

The project now uses a compiled installer EXE rather than the old standalone `install.ps1` approach.

Current release components include:

```
SufyanPisoNetTimerInstaller.exe
SufyanPisoNetTimer.exe
SufyanPisoNetTimerService.exe
uninstall_helper.exe
detail.json
wallpaper
```

The installer handles:

- Installing the application.
- Installing the Windows Service.
- Setting service startup to automatic.
- Starting the service.
- Creating the required Windows Firewall rules.
- Installing the required kiosk policies.
- Copying the client configuration.
- Installing the application files into the controlled installation directory.

The official uninstaller is handled by `uninstall_helper.exe`.

---

# 4. NodeMCU Single Coin Slot

The current system uses **one physical coin slot**.

The NodeMCU controls which PC is currently allowed to receive coins.

```
                 ONE COIN SLOT
                      │
                      ▼
                   NodeMCU
                      │
             ACTIVE PC = PCx
                      │
                      ▼
                Selected PC
```

Only one PC can own the coin slot at a time.

This prevents multiple PCs from receiving the same physical coin input.

---

# Coin Flow

Current working concept:

```
Physical Coin
     ↓
NodeMCU
     ↓
Active PC
     ↓
PisoNetTimer.exe
     ↓
Time added to PC
```

The NodeMCU handles the physical coin input and active-PC ownership.

The Python client handles the time calculation and sends the resulting command through TCP.

Example:

```
PC2:+18
```

This means PC2 receives 18 minutes.

---

# NodeMCU Communication

NodeMCU listens on:

```
TCP 5001
```

The client communicates with NodeMCU using short-lived TCP connections.

The important commands are:

```
REQUEST|PC2
RELEASE|PC2
```

When a PC successfully requests the coin slot:

```
PC2 → NodeMCU
REQUEST|PC2

NodeMCU
ACTIVE = PC2
GPIO14 = HIGH
```

When the PC releases it:

```
PC2 → NodeMCU
RELEASE|PC2

NodeMCU
ACTIVE = NONE
GPIO14 = LOW
```

---

# Coin Batching

Coin pulses are not immediately sent one-by-one to the client.

The current client uses:

- Approximately **50 ms debounce** between accepted pulses.
- A **1-second batching window** after the latest accepted coin.
- All coins inserted during the batch are converted into one time command.

Example:

```
6 accepted pulses
×
3 minutes per pulse
=
18 minutes
```

Then the client sends:

```
PC2:+18
```

The connection is closed after the transaction.

This avoids maintaining an unnecessary persistent NodeMCU control connection.

---

# Client TCP Port 5000

PisoNetTimer listens continuously on:

```
TCP 5000
```

This is the normal command channel for an individual PC.

Supported per-PC commands:

```
PC1:+10
PC1:-5
PC1:shutdown
PC1:restart
PC1:uninstall
```

### Important protocol rule

The time command format is:

```
PC1:+10
```

**Do not change it to:**

```
PC1:10
```

The `+` is part of the protocol and must remain because the mobile controller also uses this format.

The old `:admin`, `:admin:`, `opentime`, `closetime`, and `latesttime` command formats are no longer part of the current protocol.

---

# ALL-PC Broadcast Commands

The current system also supports commands intended for all PisoNet clients.

Broadcast port:

```
UDP 5051
```

Supported commands:

```
all:+10
all:-5
all:shutdown
all:restart
```

The Android/mobile controller can send these commands through UDP broadcast.

There is no response/acknowledgement mechanism for the UDP broadcast protocol.

---

# Mobile Controller

The Android controller communicates directly with the PisoNet clients.

## Individual PC

Uses:

```
TCP 5000
```

Examples:

```
PC1:+10
PC1:-5
PC1:shutdown
PC1:restart
PC1:uninstall
```

## All PCs

Uses:

```
UDP 5051
```

Examples:

```
all:+10
all:-5
all:shutdown
all:restart
```

The mobile controller must remain compatible with the current PisoNetTimer protocol.

---

# Current Network Ports

| Component | Protocol | Port | Purpose |
|---|---:|---:|---|
| PisoNetTimer | TCP | 5000 | PC commands / time commands |
| NodeMCU | TCP | 5001 | REQUEST / RELEASE / coin control |
| PisoNetTimer | UDP | 5051 | ALL-PC broadcast commands |

---

# Client Time Handling

The client maintains the countdown locally.

When time is added:

```
PC1:+10
```

the client's remaining time increases by the requested number of minutes.

When time is deducted:

```
PC1:-5
```

the client's remaining time decreases.

The client also retains:

- NTP time checking.
- Time-tampering protection.
- Shop closing-time checking.
- Recovery-file support.
- Google Sheet logging.

---

# Shop Configuration

Each PC has its own configuration in:

```
sufyan/detail.json
```

Example:

```json
{
  "pisonetName": "Sufyan Pisonet",
  "PcName": "PC2",
  "time_open": "06:00",
  "time_close": "22:30",
  "dev_btn": true,
  "RECOVERY_FILE": "E:/recovery.json"
}
```

The recovery file can be located on an external drive/path configured by the PC.

The configured recovery file should not be deleted simply because the application is uninstalled.

---

# GUI / Kiosk

The current GUI is already considered working and should not be changed casually.

Important existing UI behavior:

- PC name badge.
- Shop name badge.
- Current shop time.
- Large INSERT COIN button.
- Small INSERT COIN button.
- Remaining-time display.
- Countdown warning.
- Fullscreen kiosk mode.
- Window/taskbar hiding behavior.
- Keyboard restrictions.
- Shop closing behavior.

**Do not redesign the existing UI unless explicitly requested.**

---

# PyGit Role

PyGit is the project's remote-update/deployment concept.

The important goal remains:

> Install the system once on a client PC, then distribute future application updates through GitHub instead of manually copying files to every PC.

The deployed client uses the compiled EXE rather than requiring the raw Python source.

The development workflow is:

```
Edit source
   ↓
Test locally
   ↓
Build EXE
   ↓
Test EXE
   ↓
Push release to GitHub
   ↓
Deploy/update clients
```

---

# Current Release Build

The release build is generated using:

```
build_release.ps1
```

It builds:

```
SufyanPisoNetTimer.exe
SufyanPisoNetTimerService.exe
uninstall_helper.exe
SufyanPisoNetTimerInstaller.exe
```

The installer packages the required components into the deployment EXE.

---

# Current Project Milestones

## Completed

- PyGit live-update concept tested.
- PisoNetTimer cleaned and stabilized.
- Compiled PisoNetTimer EXE working.
- Client PCs can already run the PisoNet application.
- Players can already use the PCs normally.
- Single physical coin slot working through NodeMCU.
- NodeMCU active-PC locking implemented.
- NodeMCU REQUEST / RELEASE communication implemented.
- Coin debounce implemented.
- Coin batching implemented.
- Client TCP 5000 implemented.
- ALL-PC UDP 5051 broadcast implemented.
- Android/mobile command protocol aligned with current client protocol.
- Windows Service implemented.
- Automatic Windows Service startup implemented.
- Interactive GUI launch through the Windows Service implemented.
- Installer EXE implemented.
- Uninstaller helper implemented.
- Firewall setup implemented.
- Kiosk policies implemented.
- Google Sheet logging retained.
- NTP/time-tampering protection retained.
- Configurable shop closing time retained.
- External recovery-file support retained.

---

# Current Status

### WORKING

The core PisoNet system is operational.

The most important current result is:

```
ONE COIN SLOT
      ↓
NODEMCU
      ↓
ACTIVE PC
      ↓
PisoNetTimer.exe
      ↓
PLAYER RECEIVES TIME
      ↓
PLAYER CAN PLAY
```

Multiple client PCs can be deployed while the NodeMCU maintains ownership of the single physical coin slot.

The compiled EXE is already functioning on the client side.

---

# Current Development Priority

The project is no longer focused on proving whether the basic client works.

The basic client is already working.

Future work should focus on:

1. Deployment reliability.
2. Installer reliability.
3. Service reliability.
4. GitHub release/update reliability.
5. Mobile controller reliability.
6. NodeMCU reliability.
7. Recovery and fault handling.
8. Production testing across multiple PCs.
9. Keeping the existing working UI and protocol stable.

---

# Important Development Rules

- Preserve working functionality unless a change is explicitly requested.
- Do not casually redesign the working GUI.
- Keep the time protocol exactly compatible with the mobile controller.
- **Use `PC1:+10`, not `PC1:10`.**
- Do not reintroduce the removed admin command protocol.
- Do not reintroduce obsolete `opentime`, `closetime`, or `latesttime` commands unless explicitly requested.
- Keep TCP 5000 available while the client is running.
- Use UDP 5051 for ALL-PC broadcast commands.
- Keep NodeMCU communication on TCP 5001.
- Do not maintain unnecessary persistent NodeMCU control connections.
- Keep the single-coin-slot active-PC lock.
- Do not commit Wi-Fi credentials or other secrets to GitHub.
- Do not remove configured external recovery files during uninstall.
- Test release builds before deploying them widely.
- Treat the current working client as the baseline.
- Avoid changing multiple unrelated components when fixing one issue.

---

# Source of Truth

The GitHub repository is:

```
royalguard14/PyGit
```

The current working PisoNetTimer client is:

```
pc/client/PisoNetTimer.py
```

The Windows Service is:

```
pc/client/service.py
```

The release builder is:

```
pc/client/build_release.ps1
```

The installer is:

```
pc/client/installer.py
```

The uninstaller helper is:

```
pc/client/uninstall_helper.py
```

The PC configuration is:

```
pc/client/sufyan/detail.json
```

This document should be updated whenever the actual working architecture changes.
