/* poke.exe - drive the Buildo window from inside Wine via Win32 messages.
   Needed because macOS Accessibility is not granted, so synthetic input has
   to originate on the Windows side.
     poke.exe list                  - enumerate top-level windows
     poke.exe click <x> <y>         - left-click at client coords
     poke.exe text  <string>        - send WM_CHAR for each character
     poke.exe key   <vk>            - send WM_KEYDOWN/UP for a virtual key
   Target = largest visible window belonging to another process. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static HWND  g_best = NULL;
static long  g_bestArea = 0;
static DWORD g_self = 0;

static BOOL CALLBACK pick(HWND h, LPARAM lp) {
    (void)lp;
    if (!IsWindowVisible(h)) return TRUE;
    DWORD pid = 0; GetWindowThreadProcessId(h, &pid);
    if (pid == g_self) return TRUE;
    RECT r; if (!GetWindowRect(h, &r)) return TRUE;
    long a = (long)(r.right - r.left) * (long)(r.bottom - r.top);
    if (a > g_bestArea) { g_bestArea = a; g_best = h; }
    return TRUE;
}

static BOOL CALLBACK show(HWND h, LPARAM lp) {
    (void)lp;
    char t[256] = {0}, c[256] = {0};
    GetWindowTextA(h, t, sizeof t);
    GetClassNameA(h, c, sizeof c);
    RECT r = {0,0,0,0}; GetWindowRect(h, &r);
    DWORD pid = 0; GetWindowThreadProcessId(h, &pid);
    if (t[0] || c[0])
        printf("hwnd=%p pid=%-6lu vis=%d rect=(%ld,%ld)-(%ld,%ld) class='%s' title='%s'\n",
               (void*)h, (unsigned long)pid, IsWindowVisible(h),
               r.left, r.top, r.right, r.bottom, c, t);
    return TRUE;
}


static int real_click(HWND h, int x, int y) {
    POINT p = { x, y };
    ClientToScreen(h, &p);
    SetForegroundWindow(h);
    BringWindowToTop(h);
    Sleep(200);
    int vx = GetSystemMetrics(SM_CXVIRTUALSCREEN);
    int vy = GetSystemMetrics(SM_CYVIRTUALSCREEN);
    if (vx < 2) vx = 2;
    if (vy < 2) vy = 2;
    SetCursorPos(p.x, p.y);
    Sleep(120);
    INPUT in[3];
    ZeroMemory(in, sizeof in);
    in[0].type = INPUT_MOUSE;
    in[0].mi.dx = (LONG)((double)p.x * 65535.0 / (double)(vx - 1));
    in[0].mi.dy = (LONG)((double)p.y * 65535.0 / (double)(vy - 1));
    in[0].mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE;
    in[1].type = INPUT_MOUSE;
    in[1].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
    in[2].type = INPUT_MOUSE;
    in[2].mi.dwFlags = MOUSEEVENTF_LEFTUP;
    UINT n = SendInput(1, &in[0], sizeof(INPUT));
    Sleep(90);
    n += SendInput(1, &in[1], sizeof(INPUT));
    Sleep(110);
    n += SendInput(1, &in[2], sizeof(INPUT));
    printf("real_click client(%d,%d) screen(%ld,%ld) virt=%dx%d sent=%u\n",
           x, y, p.x, p.y, vx, vy, n);
    return n == 3;
}


static void real_text(HWND h, const char* str) {
    SetForegroundWindow(h); SetActiveWindow(h); SetFocus(h); Sleep(150);
    for (const char* p = str; *p; ++p) {
        INPUT in[2]; ZeroMemory(in, sizeof in);
        in[0].type = INPUT_KEYBOARD;
        in[0].ki.wVk = 0; in[0].ki.wScan = (WORD)(unsigned char)*p;
        in[0].ki.dwFlags = KEYEVENTF_UNICODE;
        in[1] = in[0];
        in[1].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
        SendInput(1, &in[0], sizeof(INPUT)); Sleep(45);
        SendInput(1, &in[1], sizeof(INPUT)); Sleep(45);
    }
    printf("real_text sent '%s'\n", str);
}

static void real_key(HWND h, int vk) {
    SetForegroundWindow(h); SetActiveWindow(h); SetFocus(h); Sleep(120);
    INPUT in[2]; ZeroMemory(in, sizeof in);
    in[0].type = INPUT_KEYBOARD; in[0].ki.wVk = (WORD)vk;
    in[1] = in[0]; in[1].ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(1, &in[0], sizeof(INPUT)); Sleep(80);
    SendInput(1, &in[1], sizeof(INPUT));
    printf("real_key vk=%d\n", vk);
}

/* Hold a key down for ms milliseconds, then release. rkey's 80 ms is too
   short to move the avatar a visible distance. */
static void real_hold(HWND h, int vk, int ms) {
    SetForegroundWindow(h); SetActiveWindow(h); SetFocus(h); Sleep(120);
    INPUT in; ZeroMemory(&in, sizeof in);
    in.type = INPUT_KEYBOARD; in.ki.wVk = (WORD)vk;
    SendInput(1, &in, sizeof(INPUT));
    Sleep(ms);
    in.ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(1, &in, sizeof(INPUT));
    printf("real_hold vk=%d ms=%d\n", vk, ms);
}

static HWND target(void) {
    g_self = GetCurrentProcessId();
    g_best = NULL; g_bestArea = 0;
    EnumWindows(pick, 0);
    return g_best;
}

int main(int argc, char** argv) {
    if (argc < 2) { printf("usage: poke list|click x y|rclick x y|aclick x y|activate|"
               "text s|rtext s|rkey vk|rhold vk ms|release\n"); return 2; }

    if (!strcmp(argv[1], "list")) { EnumWindows(show, 0); return 0; }

    HWND h = target();
    if (!h) { printf("no target window found\n"); return 1; }
    char t[256] = {0}; GetWindowTextA(h, t, sizeof t);
    RECT r; GetClientRect(h, &r);
    printf("target hwnd=%p title='%s' client=%ldx%ld\n",
           (void*)h, t, r.right, r.bottom);

    if (!strcmp(argv[1], "rtext") && argc >= 3) {
        real_text(h, argv[2]);
    } else if (!strcmp(argv[1], "rkey") && argc >= 3) {
        real_key(h, atoi(argv[2]));
    } else if (!strcmp(argv[1], "rhold") && argc >= 4) {
        real_hold(h, atoi(argv[2]), atoi(argv[3]));
    } else if (!strcmp(argv[1], "release")) {
        /* Clear any input the game might still think is held: mouse button,
           then every key we ever synthesise. */
        LPARAM p0 = MAKELPARAM(2, 2);
        PostMessageA(h, WM_MOUSEMOVE, 0, p0);
        PostMessageA(h, WM_LBUTTONUP, 0, p0);
        PostMessageA(h, WM_RBUTTONUP, 0, p0);
        SetForegroundWindow(h); SetActiveWindow(h); SetFocus(h); Sleep(80);
        int vks[] = {VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN, VK_SPACE,
                     'A', 'D', 'W', 'S'};
        for (int i = 0; i < (int)(sizeof vks / sizeof vks[0]); i++) {
            INPUT in; ZeroMemory(&in, sizeof in);
            in.type = INPUT_KEYBOARD; in.ki.wVk = (WORD)vks[i];
            in.ki.dwFlags = KEYEVENTF_KEYUP;
            SendInput(1, &in, sizeof(INPUT));
        }
        printf("released mouse + keys\n");
    } else if (!strcmp(argv[1], "activate")) {
        SetForegroundWindow(h); BringWindowToTop(h); SetActiveWindow(h); SetFocus(h);
        SendMessageA(h, WM_ACTIVATEAPP, TRUE, 0);
        SendMessageA(h, WM_ACTIVATE, WA_ACTIVE, 0);
        SendMessageA(h, WM_SETFOCUS, 0, 0);
        SendMessageA(h, WM_NCACTIVATE, TRUE, 0);
        printf("sent activation messages\n");
    } else if (!strcmp(argv[1], "aclick") && argc >= 4) {
        SendMessageA(h, WM_ACTIVATEAPP, TRUE, 0);
        SendMessageA(h, WM_ACTIVATE, WA_ACTIVE, 0);
        SendMessageA(h, WM_SETFOCUS, 0, 0);
        Sleep(150);
        real_click(h, atoi(argv[2]), atoi(argv[3]));
    } else if (!strcmp(argv[1], "rclick") && argc >= 4) {
        real_click(h, atoi(argv[2]), atoi(argv[3]));
    } else if (!strcmp(argv[1], "click") && argc >= 4) {
        int x = atoi(argv[2]), y = atoi(argv[3]);
        LPARAM pos = MAKELPARAM(x, y);
        SetForegroundWindow(h);
        Sleep(120);
        PostMessageA(h, WM_MOUSEMOVE,   0,           pos); Sleep(60);
        PostMessageA(h, WM_LBUTTONDOWN, MK_LBUTTON,  pos); Sleep(90);
        PostMessageA(h, WM_LBUTTONUP,   0,           pos);
        printf("clicked (%d,%d)\n", x, y);
    } else if (!strcmp(argv[1], "text") && argc >= 3) {
        SetForegroundWindow(h); Sleep(120);
        for (char* p = argv[2]; *p; ++p) {
            PostMessageA(h, WM_CHAR, (WPARAM)(unsigned char)*p, 1);
            Sleep(40);
        }
        printf("sent text '%s'\n", argv[2]);
    } else if (!strcmp(argv[1], "key") && argc >= 3) {
        int vk = atoi(argv[2]);
        SetForegroundWindow(h); Sleep(120);
        PostMessageA(h, WM_KEYDOWN, vk, 1); Sleep(70);
        PostMessageA(h, WM_KEYUP,   vk, 1);
        printf("sent vk %d\n", vk);
    } else { printf("bad args\n"); return 2; }
    return 0;
}
