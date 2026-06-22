#!/bin/bash
# Build standalone Linux executable for Ouroboros: CTF Tracker
# Usage: ./build_linux.sh
#
# IMPORTANT:
#   On Debian/Ubuntu etc you MUST have the Tcl/Tk runtime:
#     sudo apt install python3-tk
#   Then run this script from a full desktop environment.

set -euo pipefail

echo "==> Verifying tkinter is available (required for bundling)..."
python3 -c "import tkinter; print('tkinter OK:', tkinter.TkVersion)"

echo "==> Installing build dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller

echo "==> Cleaning previous builds..."
rm -rf build/ dist/ *.spec

echo "==> Building with PyInstaller (--onefile --noconsole)..."
python3 -m PyInstaller \
    --onefile \
    --noconsole \
    --name "ouroboros-ctf-tracker" \
    --hidden-import=tkinter \
    --hidden-import=_tkinter \
    --collect-all=customtkinter \
    --add-data "assets:assets" \
    ctf_timer.py

# Stage the .desktop file so users have it ready for desktop integration
cp ouroboros.desktop dist/ 2>/dev/null || true

echo ""
echo "==> Build complete!"
echo "Executable: dist/ouroboros-ctf-tracker"
echo ""
echo "Quick test (if you have a display): ./dist/ouroboros-ctf-tracker"
echo ""
echo "Install system-wide (optional):"
echo "  sudo install -Dm755 dist/ouroboros-ctf-tracker /usr/local/bin/ouroboros-ctf-tracker"
echo ""
echo "For proper Linux desktop integration (launcher icon + name 'Ouroboros', not 'Tk'):"
echo "  See the 'Desktop Integration on Linux' section in README.md"
echo ""
ls -lh dist/ouroboros-ctf-tracker dist/ouroboros.desktop 2>/dev/null || true
