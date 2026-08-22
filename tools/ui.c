/* ui.exe - mouse/keyboard driver for the Buildo window, run inside Wine.
   macOS Accessibility is not granted to the terminal, so synthetic input has
   to originate on the Windows side.
     ui.exe click  <x> <y>              press and release at client coords
     ui.exe down   <x> <y>              press and hold
     ui.exe up                          release wherever the cursor is
     ui.exe drag   <x1> <y1> <x2> <y2>  press, glide, release
     ui.exe move   <x> <y>
     ui.exe key    <vk> [ms]            hold a virtual key
     ui.exe type   <text>
   Coordinates are client-relative to the largest visible foreign window. */
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

static void abs_pos(HWND h, int x, int y, LONG *ax, LONG *ay) {
    POINT p = { x, y };
    ClientToScreen(h, &p);
    int vx = GetSystemMetrics(SM_CXVIRTUALSCREEN); if (vx < 2) vx = 2;
    int vy = GetSystemMetrics(SM_CYVIRTUALSCREEN); if (vy < 2) vy = 2;
    *ax = (LONG)((double)p.x * 65535.0 / (double)(vx - 1));
    *ay = (LONG)((double)p.y * 65535.0 / (double)(vy - 1));
    SetCursorPos(p.x, p.y);
}

static void mouse(DWORD flags, LONG ax, LONG ay) {
    INPUT in; ZeroMemory(&in, sizeof in);
    in.type = INPUT_MOUSE;
    in.mi.dx = ax; in.mi.dy = ay;
    in.mi.dwFlags = flags | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE;
    SendInput(1, &in, sizeof in);
}

int main(int argc, char **argv) {
    if (argc < 2) { printf("see the header of ui.c\n"); return 2; }
    g_self = GetCurrentProcessId();
    EnumWindows(pick, 0);
    if (!g_best) { printf("no target window\n"); return 1; }
    SetForegroundWindow(g_best);
    BringWindowToTop(g_best);
    Sleep(150);

    const char *cmd = argv[1];
    LONG ax, ay;
    if (!strcmp(cmd, "click") && argc >= 4) {
        abs_pos(g_best, atoi(argv[2]), atoi(argv[3]), &ax, &ay);
        mouse(0, ax, ay); Sleep(60);
        mouse(MOUSEEVENTF_LEFTDOWN, ax, ay); Sleep(80);
        mouse(MOUSEEVENTF_LEFTUP, ax, ay);
    } else if (!strcmp(cmd, "down") && argc >= 4) {
        abs_pos(g_best, atoi(argv[2]), atoi(argv[3]), &ax, &ay);
        mouse(0, ax, ay); Sleep(60);
        mouse(MOUSEEVENTF_LEFTDOWN, ax, ay);
    } else if (!strcmp(cmd, "up")) {
        POINT p; GetCursorPos(&p);
        int vx = GetSystemMetrics(SM_CXVIRTUALSCREEN); if (vx < 2) vx = 2;
        int vy = GetSystemMetrics(SM_CYVIRTUALSCREEN); if (vy < 2) vy = 2;
        mouse(MOUSEEVENTF_LEFTUP, (LONG)((double)p.x*65535.0/(vx-1)),
                                  (LONG)((double)p.y*65535.0/(vy-1)));
    } else if (!strcmp(cmd, "move") && argc >= 4) {
        abs_pos(g_best, atoi(argv[2]), atoi(argv[3]), &ax, &ay);
        mouse(0, ax, ay);
    } else if (!strcmp(cmd, "drag") && argc >= 6) {
        int x1 = atoi(argv[2]), y1 = atoi(argv[3]);
        int x2 = atoi(argv[4]), y2 = atoi(argv[5]);
        int steps = argc >= 7 ? atoi(argv[6]) : 20;
        if (steps < 2) steps = 2;
        abs_pos(g_best, x1, y1, &ax, &ay);
        mouse(0, ax, ay); Sleep(80);
        mouse(MOUSEEVENTF_LEFTDOWN, ax, ay); Sleep(120);
        for (int i = 1; i <= steps; ++i) {
            int x = x1 + (x2 - x1) * i / steps;
            int y = y1 + (y2 - y1) * i / steps;
            abs_pos(g_best, x, y, &ax, &ay);
            mouse(0, ax, ay);
            Sleep(25);
        }
        Sleep(120);
        mouse(MOUSEEVENTF_LEFTUP, ax, ay);
    } else if (!strcmp(cmd, "key") && argc >= 3) {
        int vk = atoi(argv[2]), ms = argc >= 4 ? atoi(argv[3]) : 120;
        INPUT in; ZeroMemory(&in, sizeof in);
        in.type = INPUT_KEYBOARD; in.ki.wVk = (WORD)vk;
        SendInput(1, &in, sizeof in);
        Sleep(ms);
        in.ki.dwFlags = KEYEVENTF_KEYUP;
        SendInput(1, &in, sizeof in);
    } else if (!strcmp(cmd, "type") && argc >= 3) {
        for (const char *s = argv[2]; *s; ++s) {
            PostMessageA(g_best, WM_CHAR, (WPARAM)(unsigned char)*s, 1);
            Sleep(30);
        }
    } else {
        printf("bad args\n"); return 2;
    }
    return 0;
}
