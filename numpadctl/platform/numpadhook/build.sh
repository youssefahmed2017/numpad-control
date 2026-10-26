#!/bin/sh
# Rebuilds numpadhook.dll (for 64-bit apps) next to windows_rawinput.py, with MinGW-w64 (Debian/Ubuntu: apt install gcc-mingw-w64).
# The built DLL is committed, so installing Numpad Control never needs a compiler.
set -e
here=$(dirname "$0")
out="$here/.."
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -shared -s -static-libgcc -o "$out/numpadhook.dll" "$here/numpadhook.c" -luser32
echo "built $out/numpadhook.dll"
