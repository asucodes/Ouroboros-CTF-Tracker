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
    --name "Ouroboros" \
    --hidden-import=tkinter \
    --hidden-import=_tkinter \
    --collect-all=customtkinter \
    --add-data "assets:assets" \
    ctf_timer.py

# Stage the .desktop file so users have it ready for desktop integration
cp -f ouroboros.desktop dist/ 2>/dev/null || true

echo ""
echo "==> Build complete!"
echo "Executable: dist/Ouroboros"
echo ""

# Auto-install to user directories so the launcher (dock/menu) always gets the correct name and logo.
# This prevents it from reverting to "Tk" after rebuilds.
echo "==> Auto-installing to user launcher (updates name/icon in dock/menu)..."
mkdir -p ~/.local/bin ~/.local/share/applications

# Install icons at ALL standard sizes (prevents generic/"poor icon" in Fedora/GNOME dock)
# We resize from the high-res source using Pillow (already in requirements).
echo "==> Installing perfect icons for every size..."
python3 - <<'PYEOF'
import os
from PIL import Image
src = "assets/ouroboros_logo_256.png"
if not os.path.exists(src):
    src = "assets/ouroboros_logo.png"
img = Image.open(src).convert("RGBA")
sizes = [16, 22, 24, 32, 48, 64, 128, 256, 512]
for sz in sizes:
    outdir = os.path.expanduser(f"~/.local/share/icons/hicolor/{sz}x{sz}/apps")
    os.makedirs(outdir, exist_ok=True)
    resized = img.resize((sz, sz), Image.LANCZOS)
    resized.save(os.path.join(outdir, "ouroboros.png"))
print("Installed ouroboros.png in all hicolor sizes.")
PYEOF

cp -f dist/Ouroboros ~/.local/bin/Ouroboros
chmod +x ~/.local/bin/Ouroboros

cp -f ouroboros.desktop ~/.local/share/applications/ouroboros.desktop
# Patch Exec to use the installed path (absolute so it always launches our binary)
sed -i "s|^Exec=.*|Exec=${HOME}/.local/bin/Ouroboros|" ~/.local/share/applications/ouroboros.desktop || true

update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

# Force refresh icon cache (critical on Fedora/GNOME for new icon to appear)
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor/ 2>/dev/null || true
fi

# Extra nudge for some desktop environments
if command -v xdg-desktop-menu >/dev/null 2>&1; then
    xdg-desktop-menu forceupdate 2>/dev/null || true
fi

echo "Launcher entry updated for 'Ouroboros: CTF Tracker' with correct logo."
echo "If the dock still shows the old one for a few seconds:"
echo "  - Alt+F2, type 'r', Enter   (restarts GNOME shell on Fedora)"
echo "  - Or log out and back in once."
echo ""

echo "Quick test (if you have a display): ~/.local/bin/Ouroboros"
echo ""
echo "Install system-wide (optional):"
echo "  sudo install -Dm755 dist/Ouroboros /usr/local/bin/Ouroboros"
echo ""
ls -lh dist/Ouroboros dist/ouroboros.desktop 2>/dev/null || true
