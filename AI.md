# PyGit Project

## Purpose

PyGit is the remote-update system for the PisoNet project.

The main idea is that a client PC only needs a stable local launcher (setup.py / built PyGit executable). The actual application code can be updated from GitHub without manually visiting every client PC.

## Current Python Architecture

```text
GitHub
├── setup.py              # Stable local updater/launcher
├── setup_backup.py       # Golden backup of setup.py
├── code.py               # Live Python application code
├── control.json          # Current remote version + code filename
└── nodemcu/              # ESP8266 development/test files

Client PC
└── PyGit.exe
    ├── checks GitHub
    ├── downloads newer code.py
    └── runs the latest application
```

## Important Python files

- setup.py — updater/launcher. It checks GitHub, downloads the latest runtime code, validates it, keeps a backup, and runs the application.
- setup_backup.py — stable/golden backup. Do not modify casually; update it only when intentionally refreshing the known-good backup.
- code.py — the live Python application fetched by PyGit.
- control.json — controls the remote application version and code filename.
- requirements.txt — optional Python dependencies for the live application, when present.
- .pygit_runtime/ — local runtime/cache files created by PyGit. These are deployment/runtime artifacts, not source code.

## Update Workflow

For the Python client:

1. Edit code.py.
2. Test it locally.
3. Increase the version in control.json.
4. Push the changes to GitHub.
5. Running PyGit clients detect the newer version.
6. PyGit downloads the new code.py, validates it, and restarts the application.

`git pull` is needed on the developer PC when setup.py itself changes. Deployed client PCs do not need git pull for normal application updates.

## NodeMCU Test

The NodeMCU is separate from the Python updater.

Current production relationship:

```text
Coinslot
   ↓
NodeMCU
   ↓ WiFi / TCP :5000
PisoNetKiosk
```

For the first GitHub experiment, **do not modify node.ino**.

The test files are kept under:

```text
nodemcu/
├── node_github_test.ino
└── node_test.txt
```

The test works like this:

```text
NodeMCU
   ↓
connect WiFi
   ↓
GitHub raw file
   ↓
download node_test.txt
   ↓
print its contents to Serial Monitor
```

This first stage proves that the ESP8266 can connect to WiFi and retrieve content from GitHub.

### NodeMCU test procedure

1. Pull the latest PyGit repository on the development PC.
2. Open nodemcu/node_github_test.ino in Arduino IDE.
3. Select the ESP8266 NodeMCU board.
4. Replace YOUR_WIFI and YOUR_PASSWORD with the test WiFi credentials.
5. Upload over USB.
6. Open Serial Monitor at 115200 baud.
7. Confirm WiFi connected, HTTP 200, the GitHub message, and TEST SUCCESSFUL.

### Security note

The first HTTPS test uses WiFiClientSecure::setInsecure() only to simplify the connectivity experiment. This skips certificate verification and must not be considered production-grade OTA security.

## Next NodeMCU Phase

After the text-download test succeeds, the next phase is firmware OTA:

```text
GitHub
   ↓
firmware .bin
   ↓
NodeMCU checks version
   ↓
downloads firmware
   ↓
OTA update
   ↓
reboot
```

The existing node.ino remains the baseline until an explicit decision is made to integrate OTA into it.

## Project Rules

- Keep the existing PisoNet kiosk code as the baseline unless explicitly asked to modify it.
- Keep node.ino unchanged during the initial NodeMCU GitHub test.
- Prefer separate test files before integrating experimental OTA functionality into production code.
- setup.py should remain stable on deployed PCs; normal application changes belong in code.py.
- Never require client PCs to use git pull for normal PyGit application updates.

## Future Plans

### PyGit / PisoNet

- automatic client application updates
- robust rollback
- dependency management
- signed/verified updates
- hidden production launcher
- application crash recovery
- kiosk/admin controls

### NodeMCU

- GitHub firmware version checking
- OTA firmware update
- safe rollback/recovery
- firmware integrity verification
- eventually separate configuration updates from firmware updates
