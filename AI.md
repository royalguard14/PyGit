# PyGit Project

## Purpose

PyGit is a simple Python remote-code system where `setup.py` acts as the local launcher and checks GitHub for updated code.

## Current Architecture

- `setup.py` - local permanent launcher
- `AI.md` - project documentation and development plan
- `code.txt` - Python code to be executed
- `control.json` - version and update control

## Current Version

1.0.0

## Current Test

The system should print:

Hello from PyGit!
My name is Ghaizar.

## Update Logic

1. setup.py starts.
2. Read the local version.
3. Check GitHub's control.json.
4. Compare versions.
5. If GitHub has a newer version:
   - download the latest code.txt
   - update the local control information
6. Execute code.txt.

## Future Plans

- Automatic update checking
- Version management
- Error handling
- Backup of previous code
- Rollback
- Multiple remote modules
- Configuration management
- Secure update verification
- Logging
- Eventually support ESP/embedded devices

## Important Design Principle

`setup.py` should remain local and stable. Remote code should be controlled through GitHub.
