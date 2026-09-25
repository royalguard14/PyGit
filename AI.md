# PyGit Project

## Purpose

PyGit is the remote-update system for the PisoNet project.

The project has two update paths:

1. Windows client application updates through PyGit.
2. NodeMCU firmware updates through GitHub OTA.

The goal is that deployed client PCs and NodeMCU units do not need to be manually visited for normal software/firmware updates.

---

## Python / Windows Architecture

```
GitHub
├── setup.py              # Stable local updater/launcher
├── setup_backup.py       # Golden backup of setup.py
├── code.py               # Live Python application
├── control.json          # Current remote version + code filename
└── nodemcu/              # ESP8266 source and firmware

Client PC
└── PyGit.exe
    ├── checks GitHub
    ├── compares control.json version
    ├── downloads newer code.py
    └── restarts the application
```

### Python Update Workflow

1. Edit `code.py`.
2. Test it locally.
3. Increase the version in `control.json`.
4. Push the changes to GitHub.
5. Running PyGit clients detect the newer version.
6. PyGit downloads the new `code.py`, validates it, and restarts the application.

If the remote and local versions are the same, the client keeps running the existing code and does not download it again.

`git pull` is needed on the developer PC when `setup.py` itself changes. Deployed client PCs do not need git pull for normal application updates.

---

## Important Python Files

- `setup.py` — stable updater/launcher.
- `setup_backup.py` — stable/golden backup. Do not modify casually.
- `code.py` — live Python application fetched by PyGit.
- `control.json` — remote application version and code filename.
- `requirements.txt` — optional Python dependencies.
- `.pygit_runtime/` — local runtime/cache files created by PyGit.

---

# NodeMCU Architecture

The NodeMCU is the coin controller for the PisoNet clients.

```
Coinslot
   ↓
Custom Board
   ↓
D6 / GPIO12
   ↓
NodeMCU
   ↑
D5 / GPIO14
   ↑
Client ADD trigger
   ↓
Selected PC
   ↓
PisoNetKiosk TCP :5000
```

### Current GPIO assignments

- **D6 / GPIO12** — COIN pulse input.
- **D5 / GPIO14** — client trigger / target selection.
- COIN pulse is approximately 50 ms.
- Coin input uses edge detection rather than relying on the exact pulse duration.
- A selected client has a timeout so a stuck selection does not remain active indefinitely.
- After GPIO14 is released, the target is cleared and the NodeMCU is ready for the next client.

---

# NodeMCU Wi-Fi Configuration

Wi-Fi credentials are **not stored in source code**.

They are loaded from LittleFS:

```
nodemcu/
└── data/
    └── wifi_config.json
```

Example:

```json
{
  "ssid": "YOUR_WIFI_NAME",
  "password": "YOUR_WIFI_PASSWORD"
}
```

The real `wifi_config.json` must remain local and is ignored by Git.

---

# NodeMCU GitHub Connection Test

The initial GitHub connection test is:

```
nodemcu/
├── node_github_test.ino
└── node_test.txt
```

The test has been successfully verified on the NodeMCU:

- Wi-Fi connection succeeded.
- GitHub returned HTTP 200.
- `node_test.txt` was downloaded.
- GitHub content was displayed in Serial Monitor.
- The test therefore proved that the ESP8266 can reach the GitHub repository over HTTPS.

`node_github_test.ino` reads Wi-Fi credentials from LittleFS and does not require ArduinoJson.

---

# NodeMCU Firmware OTA

The production firmware is **`node.ino`**.

There are no firmware version numbers on the NodeMCU.

Instead, firmware identity is based on **SHA-256**.

GitHub publishes:

```
nodemcu/
├── firmware.bin
└── firmware.sha256
```

The GitHub Actions workflow automatically builds `node.ino` into `firmware.bin` and calculates its SHA-256 hash.

## OTA Startup Flow

Every NodeMCU startup:

```
Start
  ↓
Mount LittleFS
  ↓
Load Wi-Fi configuration
  ↓
Connect Wi-Fi
  ↓
Download firmware.sha256
  ↓
Compare remote hash with local hash
```

If the hashes are equal:

```
SAME
 ↓
No download
 ↓
Run current firmware
```

If the hashes differ:

```
DIFFERENT
 ↓
Download firmware.bin
 ↓
Calculate SHA-256 while downloading
 ↓
Compare downloaded hash with GitHub hash
 ↓
If mismatch → abort update
 ↓
If match → write OTA firmware
 ↓
Save new hash to LittleFS
 ↓
Restart
```

The local hash is changed **only after the firmware update has completed successfully**.

If the download, hash verification, or OTA write fails, the old hash is retained. The NodeMCU therefore retries the update on a later startup instead of falsely marking the old firmware as current.

---

# GitHub Actions

`.github/workflows/build.yml` builds both systems.

### PyGit

The workflow builds:

```
setup.py
   ↓
PyInstaller
   ↓
PyGit.exe
```

### NodeMCU

The workflow builds:

```
node.ino
   ↓
Arduino CLI + ESP8266 core
   ↓
nodemcu/firmware.bin
   ↓
SHA-256
   ↓
nodemcu/firmware.sha256
```

The generated firmware and hash are committed back to the main branch automatically.

The workflow uses GitHub Actions `GITHUB_TOKEN` with contents write permission for this generated firmware commit.

---

# Arduino IDE / LittleFS

The development firmware is initially uploaded to the NodeMCU through USB.

The LittleFS data contains the local Wi-Fi configuration.

For Arduino IDE 1.x, the ESP8266 LittleFS uploader is required:

```
Tools
└── ESP8266 LittleFS Data Upload
```

The first firmware upload must be done over USB. After the OTA updater is running correctly, later firmware updates can happen through Wi-Fi.

---

# Security

The current GitHub HTTPS implementation uses `WiFiClientSecure::setInsecure()` for the initial OTA system.

This provides encrypted transport but does not verify the GitHub server certificate. The SHA-256 check protects against accidental or corrupted firmware downloads, but it is not a cryptographic signature.

A future hardening phase can add signed firmware verification so the NodeMCU accepts firmware only when it was signed by the trusted project key.

---

# Project Rules

- Keep the existing PisoNet kiosk code as the baseline unless explicitly asked to modify it.
- Normal Windows application changes belong in `code.py`.
- Deployed Windows clients must not require `git pull` for normal application updates.
- NodeMCU Wi-Fi credentials must remain in local LittleFS configuration and must never be committed.
- NodeMCU does not use firmware version numbers for OTA decisions.
- NodeMCU compares SHA-256 hashes.
- Only save the new local firmware hash after a successful OTA update.
- Keep `node_github_test.ino` and `node_test.txt` as development/connection-test files.
- `node.ino` is the production NodeMCU firmware.
- Do not casually modify `setup_backup.py`.

---

# Current Project Direction

The intended final deployment is:

```
                  GITHUB
                     │
          ┌──────────┴──────────┐
          │                     │
       PyGit                  NodeMCU
          │                     │
   control.json             firmware.sha256
          │                     │
   compare version           compare hash
          │                     │
       changed?              changed?
       /     \\               /     \\
     YES      NO             YES      NO
      ↓        ↓              ↓        ↓
  download    run          OTA       run
      ↓                     ↓
   restart                restart
```

The developer only needs to edit/test the source and push to GitHub. Deployed systems perform the necessary update checks automatically.
