"""Names of the programs running now (lower case, e.g. "valorant-win64-shipping.exe").

Linux reads /proc; Windows takes a Toolhelp snapshot. No extra packages.
"""

import ctypes
import os
from pathlib import Path

from . import IS_WINDOWS


def running():
    return _windows() if IS_WINDOWS else _linux()


def _basename(path):
    return path.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _linux(proc=Path("/proc")):
    names = set()
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv0 = (entry / "cmdline").read_bytes().split(b"\0", 1)[0].decode(errors="replace")
            if argv0:
                names.add(_basename(argv0))  # also a Windows game under Wine/Proton: C:\...\Game.exe
            names.add((entry / "comm").read_text().strip().lower())
        except OSError:  # the process ended meanwhile, or isn't ours to read
            continue
    names.discard("")
    return names


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_uint32), ("cntUsage", ctypes.c_uint32), ("th32ProcessID", ctypes.c_uint32),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", ctypes.c_uint32),
                ("cntThreads", ctypes.c_uint32), ("th32ParentProcessID", ctypes.c_uint32),
                ("pcPriClassBase", ctypes.c_int32), ("dwFlags", ctypes.c_uint32),
                ("szExeFile", ctypes.c_wchar * 260)]


def _windows():
    TH32CS_SNAPPROCESS, INVALID_HANDLE = 0x2, ctypes.c_void_p(-1).value
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    kernel32.Process32FirstW.argtypes = kernel32.Process32NextW.argtypes = \
        [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE:
        raise OSError(f"Windows wouldn't list the running programs (error {ctypes.get_last_error()})")
    names = set()
    try:
        entry = PROCESSENTRY32W(dwSize=ctypes.sizeof(PROCESSENTRY32W))
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            names.add(entry.szExeFile.lower())
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return names


if __name__ == "__main__":
    print(*sorted(running()), sep="\n")
    print(f"({len(running())} programs, pid {os.getpid()} is this one)")
