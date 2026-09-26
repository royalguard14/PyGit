# PyGit Project

## Purpose

PyGit is the remote-update and deployment system for the PisoNet project.

The main goal is simple:

> Install the client once, then control normal application updates from GitHub without manually visiting every client PC.

---

# PisoNet Deployment Architecture

The production deployment will use a compiled Windows EXE.

```
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

The client PC should not need Python, pip, PyInstaller, or manual module installation for the deployed application.

---

# Project Milestones

## Milestone 1 — Clean PisoNetTimer

Current target:

- Keep the existing PisoNet timer behavior.
- Remove crash recovery.
- Remove `PC1:shutdown`.
- Remove `PC1:restart`.
- Remove admin-key commands such as `PC1:+10:admin:KEY`.
- Remove the admin-key configuration.
- Keep normal timer commands such as `PC1:+10` and `PC1:-10`.
- Keep NTP time checking and time-tampering protection.
- Keep shop opening/closing schedule.
- Keep fullscreen overlay.
- Keep keyboard lock.
- Keep mute/unmute.
- Keep Google logging.
- Keep automatic PC identification.
- Keep the single-instance protection.
- Keep the **INSERT COIN** button/manual coin test capability when the client UI is integrated.

Milestone 1 code cleanup has been pushed to `pc/client/PisoNetTimer.py`.

---

## Milestone 2 — Build PisoNetClient.exe

Build the cleaned PisoNetTimer source using PyInstaller.

The result should be:

```
PisoNetClient.exe
```

The EXE must contain the required Python runtime and application dependencies.

The developer machine may use PyInstaller and Python packages. Client machines should not need to install those packages separately.

Example build pattern:

```
pyinstaller --noconsole --onefile --manifest admin.manifest --name PisoNetClientvXXX main.py
```

The exact filename/version will be finalized during the build test.

### Milestone 2 test

Before moving to the updater:

1. Build the EXE.
2. Copy the EXE to a test folder.
3. Run it on the development PC.
4. Verify the timer starts correctly.
5. Verify normal time addition works.
6. Verify the **INSERT COIN** button works.
7. Verify the fullscreen overlay appears when time reaches zero.
8. Verify shop open/close behavior.
9. Verify NTP/time-tampering protection.
10. Verify the application runs without manually installing the bundled modules.

Do not move to the installer/updater until the standalone EXE is working.

---

## Milestone 3 — Basic setup.py

`setup.py` will become the stable client installer/updater.

Its first version should remain intentionally simple.

First-run flow:

```
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
Run PisoNetClient.exe
```

The client does not need Git.

The client does not need `git pull`.

The client does not need the PisoNet source code.

The client only needs the setup/updater EXE.

---

## Milestone 4 — Test Setup on One Client

Use one test client first.

Expected result:

```
PisoNetSetup.exe
       ↓
downloads PisoNetClient.exe
       ↓
runs PisoNetClient.exe
       ↓
PisoNet application works
```

Test the complete client installation before deploying to other PCs.

---

## Milestone 5 — GitHub Automatic Application Updates

After the initial installation works, add automatic update checking.

Example:

```
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

The user should only need to build the new EXE and push the release information to GitHub.

Client PCs update automatically.

---

## Milestone 6 — NodeMCU Coin Integration

After the standalone PisoNet client and updater are stable, integrate the NodeMCU coin controller.

Expected flow:

```
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

The intended client release structure is:

```
PyGit/
└── pc/
    └── client/
        ├── setup.py
        ├── control.json
        ├── PisoNetTimer.py
        └── releases/
            └── PisoNetClient.exe
```

The exact release location can be adjusted if a simpler GitHub layout is found during implementation.

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

When a new application is released, update the version and publish the new EXE.

---

# Development Workflow

Normal development should be:

```
1. Edit PisoNetTimer.py
2. Test locally
3. Build PisoNetClient.exe
4. Test the EXE
5. Update control.json
6. Push release to GitHub
7. Client PyGit updater detects the new version
8. Client downloads and runs the new EXE
```

The developer should not manually edit or copy files on every client PC.

---

# Important Rules

- Keep the PisoNetTimer application functionality intact unless a change is explicitly requested.
- **INSERT COIN must remain available for manual testing.**
- Client deployment should use the compiled EXE, not raw Python source.
- Client PCs should not require manual Python module installation.
- Normal application updates should come from GitHub.
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
- Milestone plan established.
- PisoNetTimer cleanup for Milestone 1 pushed to GitHub.

### Current milestone
**Milestone 2 — Build and test PisoNetClient.exe**

### Next major goal
Create a simple `setup.py`, build it as `PisoNetSetup.exe`, install it on one client, and verify that it can download and launch the current PisoNetClient from GitHub.
