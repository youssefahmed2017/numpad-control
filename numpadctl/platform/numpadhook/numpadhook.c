/* numpadhook.dll: stops the numpad's keys from typing, without a driver.
 *
 * NumpadPilot's service installs KeyboardProc as a WH_KEYBOARD hook, so Windows loads
 * this DLL into apps. Just before an app receives a key that a number pad has, the hook
 * asks the service's window whether that key came from the numpad. The service already
 * knows: Windows told it (Raw Input) before the key reached the app. If the answer is
 * yes, the app never sees the key. Keys a number pad doesn't have never leave the app.
 *
 * Build (see build.sh): x86_64-w64-mingw32-gcc -O2 -shared -o numpadhook.dll numpadhook.c -luser32
 */

#include <windows.h>

#define QUERY_MESSAGE (WM_APP + 0x4E50) /* must match QUERY_MESSAGE in windows_rawinput.py */
#define SERVER_CLASS L"NumpadCtlHookServer"
#define QUERY_TIMEOUT_MS 100            /* a busy service lets the key through rather than freeze the app */

static HWND server;

static int numpad_scan_code(UINT scan)
{
    switch (scan) {
    case 0x45: case 0x35: case 0x37: case 0x0E:             /* NumLock / * Backspace */
    case 0x47: case 0x48: case 0x49: case 0x4A:             /* 7 8 9 - */
    case 0x4B: case 0x4C: case 0x4D: case 0x4E:             /* 4 5 6 + */
    case 0x4F: case 0x50: case 0x51: case 0x1C:             /* 1 2 3 Enter */
    case 0x52: case 0x53:                                   /* 0 . */
        return 1;
    default:
        return 0;
    }
}

__declspec(dllexport) LRESULT CALLBACK KeyboardProc(int code, WPARAM wParam, LPARAM lParam)
{
    if (code >= 0 && numpad_scan_code((UINT)((lParam >> 16) & 0xFF))) {
        if (!server || !IsWindow(server))
            server = FindWindowW(SERVER_CLASS, NULL);
        DWORD_PTR block = 0;
        if (server && SendMessageTimeoutW(server, QUERY_MESSAGE, wParam, lParam,
                                          SMTO_ABORTIFHUNG | SMTO_BLOCK, QUERY_TIMEOUT_MS, &block)
            && block == 1)
            return 1; /* the numpad's key: the app doesn't get it */
    }
    return CallNextHookEx(NULL, code, wParam, lParam);
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH)
        DisableThreadLibraryCalls(instance);
    return TRUE;
}
