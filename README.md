# Ouroboros: CTF Tracker

Brutal, minimalist countdown timer designed to fight sunk-cost fallacy during CTFs.

**Built with**: CustomTkinter (native dark mode + Linux compositor friendly)

![Ouroboros Logo](assets/ouroboros_logo_small.png)

## Features

- **Two modes**
  - Standard: 20:00
  - Blitz: 10:00
- **+5 Min Protocol**: One-time extension per problem. Button locks after use.
- **Flag Captured**: Ends run early → moves to **Kills** with strikethrough + exact time taken.
- **Drop & Flag**: Immediately stops and sends current target to **Ghosts**.
- **Ego-Drop on Timeout**:
  - Harsh synthesized buzzer plays (5 beeps).
  - Timer goes crimson.
  - 3-second modal "circuit breaker" overlay locks UI + shows randomized brutal truth.
- **Sidebar**: Live Kills + Ghosts lists.
- **Always on Top** toggle — perfect over Burp / browser.
- **Persistence**: On exit (or manual Export), dumps `ctf_session_YYYY-MM-DD.md` in current directory.

## Install & Run (Development)

On Debian/Ubuntu-based distros first install Tk:

```bash
sudo apt install python3-tk
python3 -m pip install -r requirements.txt
python3 ctf_timer.py
```

> **Note**: Pillow is included for logo display and is pulled via requirements.

### HiDPI / Scaling (fonts too small)

On high-resolution or fractional-scaled displays (Wayland/GNOME/KDE/4K), the UI and especially the big timer can render tiny.

**Quick fix (try this first):**

```bash
CTF_TIMER_SCALE=1.5 python3 ctf_timer.py
# Good values are usually 1.3 – 1.7
```

The application now defaults to 1.35× scaling. Change the default in `main()` or keep using the `CTF_TIMER_SCALE` environment variable.

## Build Standalone Executable (Linux)

**Prerequisite:**

```bash
sudo apt install python3-tk
python3 -m pip install -r requirements.txt
```

Build:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

Run the built binary with custom scaling:

```bash
CTF_TIMER_SCALE=1.5 ./dist/ouroboros-ctf-tracker
```

Install globally (optional):

```bash
sudo install -Dm755 dist/ouroboros-ctf-tracker /usr/local/bin/ouroboros-ctf-tracker
```

## Colors (per spec)

- Background: `#121212`
- Muted text: `#888888`
- Flag Captured: `#2563eb` (blue)
- +5 Min: `#d97706` (amber)
- Timeout / harsh: `#b91c1c` (crimson)

## Usage Flow (Intended)

1. Type problem name (required).
2. Choose mode (if you want).
3. Hit **START TIMER** (or Enter).
4. When you solve → **FLAG CAPTURED**.
5. When you decide it's dead → **DROP & FLAG**.
6. +5 is available once — use it only when you are sure.

On 00:00 the app forces detachment for you.

## Notes

- The buzzer is generated at runtime using only the Python standard library (no external .wav files committed).
- Audio playback prefers native Linux tools (`paplay`, `pw-play`, `aplay`). Falls back to terminal bell.
- The app exports Markdown on close automatically.
- Tested targeting modern Linux (Wayland + X11).

## 12-Day Sprint Tip

Run this every day. Export the session file. Review your Ghosts at the start of each day. Delete the ones that aged out.

Good luck, operator.
