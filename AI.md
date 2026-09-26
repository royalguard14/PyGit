# PyGit Project

## Purpose

PyGit is the remote-update and deployment system for the PisoNet project.

The goal is simple: install the client once, then control normal application updates from GitHub without manually visiting every client PC.

---

# PisoNet Deployment Architecture

```text
Developer PC
│
├── PisoNetTimer.py
│       │
│       └── PyInstaller
│               ↓
│       PisoNetClient.exe
│
└── Push release files to GitHub
                │
                ▼
             GitHub
                │
                ▼
          Client PC
                │
        PisoNetSetup.exe
                │
                ├── checks GitHub
                ├── downloads latest PisoNetClient.exe
                └── starts/updates client
```

The deployed client should not need Python, pip, PyInstaller, or manual module installation.

---

# Project Milestones

## Milestone 1 — Clean PisoNetTimer

Completed cleanup:

- Removed crash recovery.
- Removed `PC1:shutdown`.
- Removed `PC1:restart`.
- Removed admin-key commands such as `PC1:+10:admin:KEY`.
- Kept normal timer commands such as `PC1:+10` and `PC1:-10`.
- Kept NTP time checking and time-tampering protection.
- Kept shop opening/closing schedule.
- Kept fullscreen kiosk behavior.
- Kept keyboard lock capability.
- Kept mute/unmute capability.
- Kept Google logging.
- Kept automatic PC identification.
- Kept single-instance protection.
- Added the **INSERT COIN** manual/test button.

---

## Milestone 2 — Build PisoNetClient.exe

Current milestone.

Build the cleaned `PisoNetTimer.py` using PyInstaller.

Target:

```text
PisoNetClient.exe
```

The EXE must contain the required Python runtime and application dependencies.

### Milestone 2 test

1. Build the EXE.
2. Copy the EXE to a test folder.
3. Run it on the development PC.
4. Verify fullscreen kiosk mode starts.
5. Verify the PC name is displayed.
6. Verify the timer is displayed.
7. Verify **INSERT COIN** adds the test time.
8. Verify normal network time addition works.
9. Verify the fullscreen/locked behavior when time reaches zero.
10. Verify shop open/close behavior.
11. Verify NTP/time-tampering protection.
12. Verify the EXE runs without manually installing the bundled modules.

Do not move to the updater until the standalone EXE is working.

---

## Milestone 3 — Basic setup.py

`setup.py` will become the stable client installer/updater.

First-run flow:

```text
PisoNetSetup
    ↓
Check GitHub
    ↓
Read control.json
    ↓
Download latest PisoNetClient.exe
    ↓
Save locally
    ↓
Register Windows auto-start
    ↓
Run PisoNetClient.exe
```

The client does not need Git, `git pull`, the PisoNet source code, or manual Python package installation.

---

## Milestone 4 — Kiosk Auto-Start

After the first installation, the client should automatically start `PisoNetClient.exe` when Windows starts/logs in.

Expected behavior:

```text
Install PisoNetSetup.exe once
        ↓
Download PisoNetClient.exe
        ↓
Register auto-start
        ↓
Run client
        ↓
Restart Windows
        ↓
PisoNetClient starts automatically
        ↓
Fullscreen kiosk mode
```

The auto-start registration should be managed by the setup/updater, not hardcoded into the application itself.

---

## Milestone 5 — Test Setup on One Client

Use one test client first.

Expected result:

```text
PisoNetSetup.exe
       ↓
downloads PisoNetClient.exe
       ↓
registers auto-start
       ↓
runs PisoNetClient.exe
       ↓
PisoNet application works
```

Test a Windows restart and confirm the client starts automatically.

---

## Milestone 6 — GitHub Automatic Application Updates

After the initial installation and auto-start work, add automatic update checking.

Example:

```text
Client version: 1.0.0

GitHub:
version: 1.0.1

        ↓

New version detected
        ↓
Download new PisoNetClient.exe
        ↓
Stop old client
        ↓
Start new client
```

Client PCs update automatically while retaining their auto-start configuration.

---

## Milestone 7 — NodeMCU Coin Integration

After the standalone PisoNet client and updater are stable, integrate the NodeMCU coin controller.

Expected flow:

```text
Physical Coin
     ↓
NodeMCU
     ↓
COIN:10
     ↓
PisoNetClient
     ↓
+10 minutes
```

The manual **INSERT COIN** button remains available for testing.

NodeMCU will remain the coin-control device and will manage which PC is currently active.

---

# GitHub Release Structure

Intended structure:

```text
PyGit/
└── pc/
    └── client/
        ├── setup.py
        ├── control.json
        ├── PisoNetTimer.py
        └── releases/
            └── PisoNetClient.exe
```

---

# control.json

The updater will use a small control file to identify the current release.

Example:

```json
{
  "version": "1.0.0",
  "app": "PisoNetClient.exe"
}
```

---

# Development Workflow

```text
1. Edit PisoNetTimer.py
2. Test locally
3. Build PisoNetClient.exe
4. Test the EXE
5. Update control.json
6. Push release to GitHub
7. Client PyGit updater detects the new version
8. Client downloads and runs the new EXE
```

The developer should not manually edit or copy application files on every client PC.

---

# Important Rules

- Keep existing PisoNet functionality unless a change is explicitly requested.
- **INSERT COIN must remain available for manual testing.**
- Client deployment uses the compiled EXE, not raw Python source.
- Client PCs should not require manual Python module installation.
- Normal application updates come from GitHub.
- Do not require Git on client PCs.
- Do not require `git pull` on client PCs.
- Keep the updater simple and stable.
- Test every release on one client before wider deployment.
- NodeMCU integration comes after the standalone EXE and updater are stable.
- NodeMCU Wi-Fi credentials must never be committed to GitHub.

---

# Current Status

### Completed
- PyGit live-update concept tested successfully.
- PisoNetTimer identified as the main PisoNet client application.
- Deployment milestone plan established.
- Milestone 1 cleanup pushed.
- Basic fullscreen kiosk UI added.
- **INSERT COIN** manual/test button added.

### Current milestone
**Milestone 2 — Build and test PisoNetClient.exe**

### Next goal
Build and test the standalone EXE. After that, create the simple `setup.py` and package it as `PisoNetSetup.exe` for one-client testing.
