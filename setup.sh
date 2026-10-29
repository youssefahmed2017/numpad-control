#!/usr/bin/env bash
# NumpadPilot setup: install, uninstall, or reinstall/update. Run it and pick from the menu.
#
#   curl -fsSL https://raw.githubusercontent.com/youssefahmed2017/numpad-pilot/main/setup.sh | bash
#   ./setup.sh                    # from a clone
#
# Options (skip the menu):
#   --install | --uninstall | --update    do that and quit (--update = reinstall: keeps your settings)
#   --dir PATH    where to put the code (default: ~/numpad-control)
#   --no-deps     don't install system packages
#   --yes         don't ask questions (skips the optional boot/sleep fix)
#   --dry-run     only print what would be changed
set -euo pipefail

REPO_URL="${NUMPAD_CONTROL_REPO:-https://github.com/youssefahmed2017/numpad-pilot.git}"
DIR="${NUMPAD_CONTROL_DIR:-$HOME/numpad-control}"
DEPS=1 ASSUME_YES=0 DRY_RUN=0 ACTION=
DEFAULT_VENDOR=c0f4 DEFAULT_PRODUCT=05f5   # the numpad this was built with

while [ $# -gt 0 ]; do
    case "$1" in
        --dir) DIR="$2"; shift ;;
        --no-deps) DEPS=0 ;;
        --yes) ASSUME_YES=1 ;;
        --dry-run) DRY_RUN=1 ;;
        --install) ACTION=install ;;
        --uninstall) ACTION=uninstall ;;
        --update|--reinstall) ACTION=update ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }
warn() { printf '  \033[33m! %s\033[0m\n' "$*"; }

# Every change goes through run / write so --dry-run can show it instead.
run() {
    if [ "$DRY_RUN" = 1 ]; then printf '  [dry-run] %s\n' "$*"; else "$@"; fi
}
write() {  # write DEST MODE  (content on stdin)
    if [ "$DRY_RUN" = 1 ]; then printf '  [dry-run] write %s\n' "$1"; cat > /dev/null; return; fi
    mkdir -p "$(dirname "$1")"
    cat > "$1"
    chmod "$2" "$1"
}
render() {  # fill a template from dist/
    sed -e "s|@DIR@|$DIR|g" -e "s|@HOME@|$HOME|g" \
        -e "s|@VENDOR@|${VENDOR:-}|g" -e "s|@PRODUCT@|${PRODUCT:-}|g" "$DIR/dist/$1"
}
ask() {  # ask "question" -> 0 for yes (reads the terminal even when piped from curl)
    [ "$ASSUME_YES" = 1 ] && return 1
    local answer=""
    printf '  %s [y/N] ' "$1"
    read -r answer < /dev/tty || true
    [[ "$answer" =~ ^[Yy] ]]
}


has_desktop() { command -v "$1" > /dev/null 2>&1; }

# ---------------------------------------------------------------- the look
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != dumb ]; then
    if [[ "${COLORTERM:-}" == *truecolor* || "${COLORTERM:-}" == *24bit* ]]; then
        TILE=$'\e[48;2;124;78;127m' KEY=$'\e[48;2;255;255;255m' INK=$'\e[38;2;236;190;255m'
        ACCENT=$'\e[1;38;2;236;190;255m'
    else
        TILE=$'\e[48;5;96m' KEY=$'\e[48;5;255m' INK=$'\e[38;5;219m' ACCENT=$'\e[1;38;5;219m'
    fi
    DIM=$'\e[2m' RST=$'\e[0m' COLOR=1
else
    TILE="" KEY="" INK="" ACCENT="" DIM="" RST="" COLOR=0
fi

banner() {
    # The logo (a rounded tile with the numpad's keys) in coloured cells, and SETUP next to it.
    local logo=("............." ".###.###.###." ".###.###.###." "............." ".###.###.###."
                ".###.###.###." ".........###." ".#######.###." ".#######.###." ".............")
    local S=(" ####" "#    " " ### " "    #" "#### ") E=("#####" "#    " "#### " "#    " "#####")
    local T=("#####" "  #  " "  #  " "  #  " "  #  ") U=("#   #" "#   #" "#   #" "#   #" " ### ")
    local P=("#### " "#   #" "#### " "#    " "#    ")
    local r c ch text line
    echo
    for r in 0 1 2 3 4 5 6 7 8 9; do
        line="  "
        for ((c = 0; c < 13; c++)); do
            ch="${logo[r]:c:1}"
            if [ "$ch" = "#" ]; then
                if [ "$COLOR" = 1 ]; then line+="${KEY}  ${RST}"; else line+="██"; fi
            else
                if [ "$COLOR" = 1 ]; then line+="${TILE}  ${RST}"; else line+="░░"; fi
            fi
        done
        text=""
        if [ "$r" -ge 2 ] && [ "$r" -le 6 ]; then
            local k=$((r - 2))
            for letter in S E T U P; do
                local -n glyph=$letter
                text+="${glyph[k]} "
            done
            text="${text//#/█}"
            line+="    ${INK}${text}${RST}"
        elif [ "$r" = 8 ]; then
            line+="    ${ACCENT}NumpadPilot${RST}${DIM}  your \$10 numpad, now a control deck${RST}"
        fi
        printf '%s\n' "$line"
    done
    echo
}

menu() {
    # Sets ACTION from the menu (or to "install" when there is no terminal to ask on).
    if [ ! -r /dev/tty ]; then ACTION=install; return; fi
    local choice
    while :; do
        printf '  %sOptions:%s\n' "$ACCENT" "$RST"
        printf '    %s[1]%s Install\n    %s[2]%s Uninstall\n    %s[3]%s Reinstall / Update\n    %s[0]%s Quit\n\n' \
            "$ACCENT" "$RST" "$ACCENT" "$RST" "$ACCENT" "$RST" "$ACCENT" "$RST"
        printf '  Choose %s[0-3]%s: ' "$ACCENT" "$RST"
        read -r choice < /dev/tty || choice=0
        case "$choice" in
            1) ACTION=install; return ;;
            2) ACTION=uninstall; return ;;
            3) ACTION=update; return ;;
            0|q|Q) ACTION=quit; return ;;
            *) printf '\n  %sPlease type 1, 2, 3 or 0.%s\n\n' "$DIM" "$RST" ;;
        esac
    done
}

# ---------------------------------------------------------------- uninstall
do_uninstall() {  # do_uninstall [keep]: "keep" never asks about deleting your settings
    bold "Removing NumpadPilot"
    run systemctl --user disable --now numpad-control 2> /dev/null || true
    run rm -f "$HOME/.config/systemd/user/numpad-control.service" "$HOME/.local/bin/numpad-control" \
        "$HOME/.local/share/applications/numpad-control.desktop" "$HOME/.config/autostart/numpad-control.desktop"
    run systemctl --user daemon-reload
    if [ -e /etc/udev/rules.d/70-numpad-control.rules ]; then
        note "removing the numpad permission rule (needs sudo)"
        run sudo rm -f /etc/udev/rules.d/70-numpad-control.rules
        run sudo udevadm control --reload
    fi
    if [ -e /etc/systemd/system/numpad-control-usb.service ]; then
        note "removing the automatic re-detect fix (needs sudo)"
        run sudo systemctl disable --now numpad-control-usb.service || true
        run sudo rm -f /etc/systemd/system/numpad-control-usb.service /usr/local/bin/numpad-control-usb-kick \
            /usr/lib/systemd/system-sleep/numpad-control
        run sudo rm -rf /etc/numpad-control
        run sudo systemctl daemon-reload
    fi
    if [ "${1:-}" != keep ]; then
        if ask "Also delete your settings (~/.config/numpad-control) and the program folder ($DIR)?"; then
            run rm -rf "$HOME/.config/numpad-control" "$DIR"
        else
            note "Your settings stay in ~/.config/numpad-control, the program in $DIR."
        fi
    fi
    bold "Done"
}

# ---------------------------------------------------------------- install
do_install() {

# ---------------------------------------------------------------- 1. packages

if [ "$DEPS" = 1 ]; then
    bold "1/7  System packages"
    if command -v pacman > /dev/null; then
        packages=(git python python-gobject libnotify xdg-utils wl-clipboard
                  ydotool playerctl wireplumber libpulse)
        has_desktop Hyprland && packages+=(swayosd grim slurp dunst hyprlock)
        has_desktop plasmashell && packages+=(spectacle)
        run sudo pacman -S --needed --noconfirm "${packages[@]}"
        if has_desktop plasmashell && ! command -v kdotool > /dev/null; then
            helper=$(command -v yay || command -v paru || true)
            if [ -n "$helper" ]; then
                run "$helper" -S --needed --noconfirm kdotool
            else
                warn "KDE window actions need kdotool from the AUR (no yay/paru found): https://aur.archlinux.org/packages/kdotool"
            fi
        fi
    elif command -v apt-get > /dev/null; then
        run sudo apt-get install -y git python3 python3-venv python3-gi \
            libnotify-bin xdg-utils wl-clipboard ydotool playerctl wireplumber pulseaudio-utils
        warn "Install your desktop's extras yourself if needed (Hyprland: swayosd grim slurp dunst; KDE: kdotool spectacle)."
    elif command -v dnf > /dev/null; then
        run sudo dnf install -y git python3 python3-gobject libnotify xdg-utils \
            wl-clipboard ydotool playerctl wireplumber pulseaudio-utils
        warn "Install your desktop's extras yourself if needed (Hyprland: swayosd grim slurp dunst; KDE: kdotool spectacle)."
    else
        warn "Unknown package manager: install git, Python 3 and python-gobject yourself."
    fi
else
    bold "1/7  System packages (skipped)"
fi

# ---------------------------------------------------------------- 2. code
bold "2/7  Code"
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$here" ] && [ -d "$here/numpadctl" ] && [ -f "$here/dist/numpad-control.service" ]; then
    DIR="$here"   # running from a clone: install that one
    note "using $DIR"
elif [ -d "$DIR/.git" ]; then
    if [ -n "$(git -C "$DIR" status --porcelain)" ]; then
        warn "$DIR has local changes; not updating it"
    else
        run git -C "$DIR" pull --ff-only
    fi
else
    run git clone "$REPO_URL" "$DIR"
fi

# ---------------------------------------------------------------- 3. python
bold "3/7  Python environment"
# --system-site-packages: GTK's Python bindings come from the system packages.
[ -x "$DIR/.venv/bin/python" ] || run python3 -m venv --system-site-packages "$DIR/.venv"
run "$DIR/.venv/bin/pip" install --quiet --upgrade -r "$DIR/requirements.txt"
if [ "$DRY_RUN" = 0 ]; then
    "$DIR/.venv/bin/python" -c 'import PySide6.QtWidgets' \
        || { echo "Qt for Python (PySide6) didn't install - see the messages above." >&2; exit 1; }
fi

# ---------------------------------------------------------------- 4. numpad
bold "4/7  Your numpad"
VENDOR="" PRODUCT=""
config="${XDG_CONFIG_HOME:-$HOME/.config}/numpad-control/config.json"
if [ -f "$config" ]; then
    read -r VENDOR PRODUCT < <("$DIR/.venv/bin/python" -c 'import sys; sys.path.insert(0, sys.argv[1])
from numpadctl import config
d = config.load()["device"]; print(d["vendor"], d["product"])' "$DIR")
    note "using the numpad from your settings ($VENDOR:$PRODUCT)"
elif [ "$DRY_RUN" = 0 ]; then
    note "Press any key on the numpad you want to use (15 seconds)…"
    # Reading keyboards needs root until the permission rule below exists.
    spec=$(sudo "$DIR/.venv/bin/python" -c 'import sys; sys.path.insert(0, sys.argv[1])
from numpadctl import daemon
import json; print(json.dumps(daemon.detect_device()))' "$DIR" || echo null)
    if [ "$spec" != "null" ]; then
        read -r VENDOR PRODUCT < <(python3 -c 'import json, sys; d = json.loads(sys.argv[1]); print(d["vendor"], d["product"])' "$spec")
        note "found $VENDOR:$PRODUCT"
        "$DIR/.venv/bin/python" -c 'import json, sys; sys.path.insert(0, sys.argv[1])
from numpadctl import config
c = config.load(); c["device"] = json.loads(sys.argv[2]); config.save(c)' "$DIR" "$spec"
    else
        VENDOR=$DEFAULT_VENDOR PRODUCT=$DEFAULT_PRODUCT
        warn "no key press seen; using $VENDOR:$PRODUCT. Use Settings → Detect later, then run this again."
    fi
else
    VENDOR=$DEFAULT_VENDOR PRODUCT=$DEFAULT_PRODUCT
    note "[dry-run] would ask you to press a key on the numpad"
fi

# ---------------------------------------------------------------- 5. permission
bold "5/7  Permission to read the numpad"
render 70-numpad-control.rules | if [ "$DRY_RUN" = 1 ]; then
    printf '  [dry-run] write /etc/udev/rules.d/70-numpad-control.rules:\n'; sed 's/^/    /'
else
    sudo tee /etc/udev/rules.d/70-numpad-control.rules > /dev/null
fi
run sudo udevadm control --reload
run sudo udevadm trigger --subsystem-match=input

# ---------------------------------------------------------------- 6. service
bold "6/7  Background service"
render numpad-control.service | write "$HOME/.config/systemd/user/numpad-control.service" 644
run systemctl --user daemon-reload
run systemctl --user enable numpad-control
run systemctl --user restart numpad-control
if systemctl --user cat ydotool.service > /dev/null 2>&1; then
    run systemctl --user enable --now ydotool   # for the Type text / Press keys actions
fi

# ---------------------------------------------------------------- 7. launcher
bold "7/7  Launcher and login"
render numpad-control | write "$HOME/.local/bin/numpad-control" 755
render numpad-control.desktop | write "$HOME/.local/share/applications/numpad-control.desktop" 644
# KDE starts it hidden at login (with a tray icon); the entry is ignored elsewhere.
render numpad-control-autostart.desktop | write "$HOME/.config/autostart/numpad-control.desktop" 644
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) warn "add ~/.local/bin to your PATH to run 'numpad-control' from a terminal" ;; esac

bold "Optional: numpads that need replugging after boot or sleep"
note "Some cheap numpads aren't detected at boot, or go silent after sleep, until replugged."
if ask "Install the automatic re-detect fix (needs sudo)?"; then
    run "$DIR/install-usb-fix.sh"
fi

bold "Done"
note "Open \"NumpadPilot\" from your app menu to choose what each key does."
has_desktop Hyprland && note "Hyprland: to start it hidden at login, add to your Hyprland autostart:  $HOME/.local/bin/numpad-control --hidden"
note "Service log: journalctl --user -u numpad-control -f"
}

# ---------------------------------------------------------------- go
[ "$(id -u)" = 0 ] && { echo "Run this as your normal user (it uses sudo when needed)." >&2; exit 1; }
if [ -z "$ACTION" ]; then
    banner
    menu
fi
case "$ACTION" in
    install) do_install ;;
    uninstall) do_uninstall ;;
    update) do_uninstall keep; do_install ;;
    quit) echo "  Nothing changed." ;;
esac
