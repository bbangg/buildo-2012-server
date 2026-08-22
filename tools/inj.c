/* inj.exe - load a DLL into a running process (classic CreateRemoteThread).
   Usage: inj.exe <exe-name-substring> <C:\path\to.dll>  */
#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <string.h>

static DWORD find_pid(const char *needle)
{
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32 pe = { sizeof pe };
    DWORD self = GetCurrentProcessId(), pid = 0;
    if (Process32First(snap, &pe)) do {
        if (pe.th32ProcessID == self) continue;
        if (strstr(pe.szExeFile, needle)) { pid = pe.th32ProcessID; break; }
    } while (Process32Next(snap, &pe));
    CloseHandle(snap);
    return pid;
}

int main(int argc, char **argv)
{
    if (argc < 3) { printf("usage: inj.exe <exe-substr> <dll-path>\n"); return 2; }
    DWORD pid = find_pid(argv[1]);
    if (!pid) { printf("no process matching '%s'\n", argv[1]); return 1; }
    HANDLE p = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!p) { printf("OpenProcess failed %lu\n", GetLastError()); return 1; }
    size_t n = strlen(argv[2]) + 1;
    void *mem = VirtualAllocEx(p, NULL, n, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!mem) { printf("VirtualAllocEx failed %lu\n", GetLastError()); return 1; }
    SIZE_T wrote = 0;
    WriteProcessMemory(p, mem, argv[2], n, &wrote);
    HMODULE k = GetModuleHandleA("kernel32.dll");
    LPTHREAD_START_ROUTINE ll = (LPTHREAD_START_ROUTINE)GetProcAddress(k, "LoadLibraryA");
    HANDLE t = CreateRemoteThread(p, NULL, 0, ll, mem, 0, NULL);
    if (!t) { printf("CreateRemoteThread failed %lu\n", GetLastError()); return 1; }
    WaitForSingleObject(t, 10000);
    DWORD code = 0; GetExitCodeThread(t, &code);
    printf("injected into pid %lu, LoadLibraryA -> 0x%lx\n", pid, code);
    return code ? 0 : 1;
}
