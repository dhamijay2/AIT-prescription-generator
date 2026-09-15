# Building the AIT Generator Executable

## Quick Start
Simply double-click **`BUILD.bat`** in this folder to compile the application.

## What It Does
1. ✅ Installs dependencies if needed (tkcalendar, reportlab, pyinstaller)
2. ✅ Closes any running instances of the app
3. ✅ Cleans up old build files
4. ✅ Compiles the Python code into an executable
5. ✅ Offers options to open the dist folder or run the app

## System Requirements
- Windows 10 or later
- Python 3.7+ installed and in PATH
- Internet connection (for first-time dependency installation)

## Build Time
- First build: 2-3 minutes (includes dependency installation)
- Subsequent builds: 1-2 minutes

## Output
The compiled executable will be located in: **`dist\UC Immunotherapy.exe`**

This is a 33 MB standalone file that can be:
- Distributed to other computers
- Placed on a shared drive
- Installed on any Windows machine without requiring Python

## Troubleshooting
- If the script fails, check that Python is installed: `python --version`
- If you get permission errors, try running CMD as Administrator
- Delete the `build/` folder manually if the script gets stuck

## Notes
- Keep this script in the main AIT Generator folder
- The source code (`ait gen.py`) must be in the same folder
- Icon file (`ait-generator.ico`) must also be present
