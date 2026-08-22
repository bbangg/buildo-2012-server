/* cap.dll - screenshot + memory-probe helper injected into Buildo.exe.
 *
 * Why this exists: the game renders through OpenGL, so GDI BitBlt (shot.exe)
 * returns an all-black bitmap, and macOS `screencapture` refuses without
 * Screen Recording permission. The only place the pixels are readable is
 * inside the process, with the GL context current -- i.e. in SwapBuffers.
 *
 * It hooks the main executable's import-address-table entry for
 * GDI32!SwapBuffers, and on each frame:
 *   - if C:\shot.req exists, glReadPixels the framebuffer into C:\shot.bmp
 *     and delete the request file.
 * Then it chains to the real SwapBuffers.
 */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <GL/gl.h>

typedef BOOL (WINAPI *SwapFn)(HDC);
static SwapFn g_real = NULL;
static volatile LONG g_frame = 0;

#define REQ  "C:\\shot.req"
#define SHOT "C:\\shot.bmp"

static void write_bmp(const char *path, int w, int h, unsigned char *rgb)
{
    /* 24-bit BMP is bottom-up, and so is glReadPixels, so rows go out as-is.
       Only the R/B swap is needed. */
    int stride = (w * 3 + 3) & ~3;
    int imgsz  = stride * h;
    unsigned char fh[14] = {0}, ih[40] = {0};
    fh[0]='B'; fh[1]='M';
    *(int*)(fh+2)  = 14 + 40 + imgsz;
    *(int*)(fh+10) = 14 + 40;
    *(int*)(ih+0)  = 40;
    *(int*)(ih+4)  = w;
    *(int*)(ih+8)  = h;
    *(short*)(ih+12) = 1;
    *(short*)(ih+14) = 24;
    *(int*)(ih+20) = imgsz;
    FILE *f = fopen(path, "wb");
    if (!f) return;
    fwrite(fh, 1, 14, f);
    fwrite(ih, 1, 40, f);
    unsigned char *row = (unsigned char*)calloc(1, stride);
    for (int y = 0; y < h; ++y) {
        unsigned char *src = rgb + (size_t)y * w * 3;
        for (int x = 0; x < w; ++x) {
            row[x*3+0] = src[x*3+2];
            row[x*3+1] = src[x*3+1];
            row[x*3+2] = src[x*3+0];
        }
        fwrite(row, 1, stride, f);
    }
    free(row);
    fclose(f);
}

static void grab(void)
{
    GLint vp[4] = {0,0,0,0};
    glGetIntegerv(GL_VIEWPORT, vp);
    int w = vp[2], h = vp[3];
    if (w <= 0 || h <= 0 || w > 8192 || h > 8192) return;
    size_t n = (size_t)w * h * 3;
    unsigned char *buf = (unsigned char*)malloc(n);
    if (!buf) return;
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE, buf);
    write_bmp(SHOT, w, h, buf);
    free(buf);
}


/* ---------- item table dump ----------
   ItemInfoManager is *(void**)0x4EBE60 + 0x7A0  (GetItemInfoManager, VA 0x401150).
   Its item vector is {begin @ +0x0C, end @ +0x10}, stride 0xAC, indexed by item id
   (imul ebp,ebp,0xac / add ebp,[esi+0xc] at VA 0x443916).
   MSVC std::string here is {void* proxy; char _Bx[16]; size_t size; size_t res;}
   -- res >= 16 means _Bx holds a pointer (the SSO test at VA 0x4439b8). */
#define ITEMS_REQ "C:\\items.req"
#define ITEMS_OUT "C:\\items.txt"

static const char *rd_str(unsigned char *s)
{
    unsigned int res  = *(unsigned int *)(s + 0x18);
    return (res >= 16) ? *(const char **)(s + 4) : (const char *)(s + 4);
}

static void dump_items(void)
{
    FILE *f = fopen(ITEMS_OUT, "w");
    if (!f) return;
    unsigned char *app = *(unsigned char **)0x4EBE60;
    if (!app) { fprintf(f, "app pointer null\n"); fclose(f); return; }
    unsigned char *mgr = app + 0x7A0;
    unsigned char *beg = *(unsigned char **)(mgr + 0x0C);
    unsigned char *end = *(unsigned char **)(mgr + 0x10);
    if (!beg || end < beg) { fprintf(f, "no item vector (%p..%p)\n", beg, end); fclose(f); return; }
    int n = (int)((end - beg) / 0xAC);
    fprintf(f, "# ItemInfoManager %p  vector %p..%p  count=%d stride=0xAC\n", mgr, beg, end, n);
    fprintf(f, "# idx id mat vis hash x48 color fx fy stor x58 x5c hp maxhold body x84 x86 xA4 xA8 x6c..x6f x70 x74 x78 x7a x7c | name | file | str3\n");
    for (int i = 0; i < n; ++i) {
        unsigned char *it = beg + (size_t)i * 0xAC;
        fprintf(f,
            "%3d id=%-4d mat=%-3d vis=%-3d hash=%-11d x48=%-3d color=%08X fx=%-3d fy=%-3d "
            "stor=%-3d x58=%-3d x5c=%-3d hp=%-3d hold=%-5d body=%-3d "
            "x84=%-5d x86=%-3d xA4=%-11d xA8=%-11d "
            "seed=%d,%d,%d,%d x70=%d x74=%d x78=%d x7a=%d x7c=%d "
            "| %s | %s | %s\n",
            i,
            *(int*)(it+0x00), *(int*)(it+0x04), *(int*)(it+0x08),
            *(int*)(it+0x28), *(int*)(it+0x48), *(unsigned*)(it+0x4C),
            it[0x50], it[0x51], *(int*)(it+0x54), *(int*)(it+0x58),
            *(int*)(it+0x5C), *(int*)(it+0x60), *(int*)(it+0x64), *(int*)(it+0x68),
            *(unsigned short*)(it+0x84), it[0x86],
            *(int*)(it+0xA4), *(int*)(it+0xA8),
            it[0x6C], it[0x6D], it[0x6E], it[0x6F],
            *(int*)(it+0x70), *(int*)(it+0x74),
            *(unsigned short*)(it+0x78), *(unsigned short*)(it+0x7A), *(int*)(it+0x7C),
            rd_str(it+0x0C), rd_str(it+0x2C), rd_str(it+0x88));
    }
    fclose(f);
}


/* ---------- generic vtable scan ----------
   Every class here is polymorphic and its RTTI-derived vtable address is a
   fixed VA, so an object is found by scanning committed writable memory for a
   dword equal to that vtable. Beats chasing `this` through boost::function.
   Bounded on purpose: only the low 1 GB, only regions <= 64 MB, and each hit
   has to pass a caller-supplied sanity check -- an unvalidated hit on the
   stack once sent the dumper off a wild pointer and wedged the render thread. */
typedef int (*validate_fn)(unsigned char *obj);

static void *find_object(unsigned int vtable, validate_fn ok, int nth)
{
    MEMORY_BASIC_INFORMATION mbi;
    unsigned char *p = NULL;
    int seen = 0;
    while ((ULONG_PTR)p < 0x40000000u && VirtualQuery(p, &mbi, sizeof mbi) == sizeof mbi) {
        unsigned char *next = (unsigned char *)mbi.BaseAddress + mbi.RegionSize;
        if (mbi.State == MEM_COMMIT && mbi.RegionSize <= (64u << 20) &&
            (mbi.Protect & (PAGE_READWRITE | PAGE_EXECUTE_READWRITE)) &&
            !(mbi.Protect & PAGE_GUARD)) {
            unsigned int *q   = (unsigned int *)mbi.BaseAddress;
            unsigned int *end = (unsigned int *)next;
            for (; q + 64 < end; ++q)
                if (*q == vtable && (!ok || ok((unsigned char *)q)) && seen++ == nth)
                    return q;
        }
        if (next <= p) break;
        p = next;
    }
    return NULL;
}

static int readable(const void *p, size_t n)
{
    MEMORY_BASIC_INFORMATION mbi;
    if (!p) return 0;
    if (VirtualQuery(p, &mbi, sizeof mbi) != sizeof mbi) return 0;
    if (mbi.State != MEM_COMMIT || (mbi.Protect & PAGE_GUARD)) return 0;
    if (!(mbi.Protect & (PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY |
                         PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE))) return 0;
    return (ULONG_PTR)p + n <= (ULONG_PTR)mbi.BaseAddress + mbi.RegionSize;
}

#define VT_PLAYERITEMS 0x004CBE34u
#define VT_WORLD       0x004CC090u

#define INV_REQ   "C:\\inv.req"
#define INV_OUT   "C:\\inv.txt"
#define WORLD_REQ "C:\\world.req"
#define WORLD_OUT "C:\\world.txt"

/* PlayerItems (serializer 0x43db00): +0x04 capacity,
   std::list at +0x14 {proxy, _Myhead @+0x18, _Mysize @+0x1c},
   node {_Next, _Prev, uint16 id @+8, uint8 amount @+0xa, uint8 flags @+0xb}. */
static int ok_playeritems(unsigned char *pi)
{
    unsigned char *head = *(unsigned char **)(pi + 0x18);
    unsigned int  size  = *(unsigned int *)(pi + 0x1C);
    return size <= 4096 && readable(head, 12);
}

static void dump_inventory(void)
{
    FILE *f = fopen(INV_OUT, "w");
    if (!f) return;
    for (int n = 0; n < 4; ++n) {
        unsigned char *pi = (unsigned char *)find_object(VT_PLAYERITEMS, ok_playeritems, n);
        if (!pi) break;
        unsigned char *head = *(unsigned char **)(pi + 0x18);
        unsigned int   size = *(unsigned int *)(pi + 0x1C);
        /* +0x20 is the selected item (0x43d602 writes it when the Fist or the
           Wrench is picked), and +0x06..+0x11 are the six worn slots the
           clothing renderer reads (0x43dcd0). Printing them is how a click on
           an inventory cell can be checked instead of guessed. */
        fprintf(f, "PlayerItems#%d @%p capacity=%u listSize=%u selected=%u\n"
                   "  worn: hat=%u shirt=%u pants=%u shoes=%u face=%u hand=%u\n",
                n, pi, pi[4], size, *(unsigned short *)(pi + 0x20),
                *(unsigned short *)(pi + 0x06), *(unsigned short *)(pi + 0x08),
                *(unsigned short *)(pi + 0x0a), *(unsigned short *)(pi + 0x0c),
                *(unsigned short *)(pi + 0x0e), *(unsigned short *)(pi + 0x10));
        if (!head || size > 4096) { fprintf(f, "  (bad list)\n"); continue; }
        unsigned char *node = *(unsigned char **)head;
        for (unsigned int i = 0; i < size && node && node != head; ++i) {
            fprintf(f, "  [%2u] id=%-5u amount=%-4u flags=0x%02x\n", i,
                    *(unsigned short *)(node + 8), node[0x0A], node[0x0B]);
            node = *(unsigned char **)node;
        }
    }
    fclose(f);
}

/* World (0x43f450): +0x04 WorldTileMap, +0x38 version, +0x74 header dword.
   WorldTileMap (0x441b60): +0x04 width, +0x08 height,
   tile vector begin @+0x10 / end @+0x14, stride 0x38.
   Tile (0x43e850 / 0x43e6d0): +0x00 fg, +0x02 bg, +0x04 flags,
   +0x06 x, +0x07 y, +0x0a fgFrame, +0x0c bgFrame, +0x0e blocked,
   +0x10 collision (copied from ItemInfo+0x5c), +0x24 TileExtra*, +0x34 extra. */
static int ok_world(unsigned char *w)
{
    unsigned char *tm = w + 4;
    int width  = *(int *)(tm + 0x04);
    int height = *(int *)(tm + 0x08);
    unsigned char *beg = *(unsigned char **)(tm + 0x10);
    unsigned char *end = *(unsigned char **)(tm + 0x14);
    if (width < 1 || width > 4096 || height < 1 || height > 4096) return 0;
    if (!readable(beg, 0x38) || end <= beg) return 0;
    if (((ULONG_PTR)end - (ULONG_PTR)beg) % 0x38) return 0;
    return (int)(((ULONG_PTR)end - (ULONG_PTR)beg) / 0x38) == width * height;
}

static void dump_world(void)
{
    FILE *f = fopen(WORLD_OUT, "w");
    if (!f) return;
    unsigned char *w = (unsigned char *)find_object(VT_WORLD, ok_world, 0);
    if (!w) { fprintf(f, "no World object found\n"); fclose(f); return; }
    unsigned char *tm  = w + 4;
    int width  = *(int *)(tm + 0x04);
    int height = *(int *)(tm + 0x08);
    unsigned char *beg = *(unsigned char **)(tm + 0x10);
    unsigned char *end = *(unsigned char **)(tm + 0x14);
    int n = (int)((end - beg) / 0x38);
    fprintf(f, "World @%p version=%u hdr=%u  %dx%d tiles=%d\n",
            w, *(unsigned short *)(w + 0x38), *(unsigned int *)(w + 0x74),
            width, height, n);
    /* one line per non-empty tile, capped so the file stays readable */
    int printed = 0;
    for (int i = 0; i < n && printed < 4000; ++i) {
        unsigned char *t = beg + (size_t)i * 0x38;
        unsigned short fg = *(unsigned short *)(t + 0x00);
        unsigned short bg = *(unsigned short *)(t + 0x02);
        if (!fg && !bg) continue;
        fprintf(f, "%5d (%3d,%3d) fg=%-4u bg=%-4u flags=0x%04x fgFrame=%-3u "
                   "bgFrame=%-3u blocked=%u coll=%d extra=%p x34=%u\n",
                i, i % (width ? width : 1), i / (width ? width : 1),
                fg, bg, *(unsigned short *)(t + 0x04), *(unsigned short *)(t + 0x0A),
                *(unsigned short *)(t + 0x0C), t[0x0E], *(int *)(t + 0x10),
                *(void **)(t + 0x24), *(unsigned short *)(t + 0x34));
        ++printed;
    }
    fclose(f);
}


/* InventoryComponent is the global at 0x4EC158 (0x436440 loads it before
   rebuilding the bar). Its tool list is a vector<int> of item ids at
   +0x98/+0x9c, refilled from the player's item list at 0x435ac8. */
#define BAR_REQ "C:\\bar.req"
#define BAR_OUT "C:\\bar.txt"

static void dump_bar(void)
{
    FILE *f = fopen(BAR_OUT, "w");
    if (!f) return;
    unsigned char *ic = *(unsigned char **)0x004EC158;
    if (!readable(ic, 0xB0)) { fprintf(f, "InventoryComponent %p unreadable\n", ic); fclose(f); return; }
    int *beg = *(int **)(ic + 0x98);
    int *end = *(int **)(ic + 0x9C);
    fprintf(f, "InventoryComponent @%p toolVector %p..%p\n", ic, beg, end);
    if (!readable(beg, 4) || end < beg || (end - beg) > 512) { fprintf(f, "  (bad vector)\n"); fclose(f); return; }
    for (int *q = beg; q < end; ++q) fprintf(f, "  slot %ld = item %d\n", (long)(q - beg), *q);
    fclose(f);
}


/* ---------- NetAvatar probe ----------
   Added to answer one question with data instead of inference: what does the
   client think is under the avatar's feet when it stops falling in mid-air?
   NetAvatar's vtable is 0x4cc32c. Field offsets come from the state serialiser
   at 0x4467d0 (+0x04 x, +0x08 y, +0xe8 velX, +0xec velY, +0xe4 onGround,
   +0x18c pending state flags) and the ground check at 0x447070 (+0x10, and
   tile+0x18 which it compares against int(+0x10)+int(y)). */
#define VT_NETAVATAR 0x004CC32Cu
#define AV_REQ  "C:\\av.req"
#define AV_OUT  "C:\\av.txt"

static int ok_netavatar(unsigned char *a)
{
    /* A bare vtable match hits copies of the pointer on the stack, which read
       back as an avatar at 0,0 with a garbage collision rect. Require a
       position inside a world and a collision rect the size of a sprite. */
    float x = *(float *)(a + 4), y = *(float *)(a + 8);
    float w = *(float *)(a + 0x0c), h = *(float *)(a + 0x10);
    if (!(x >= 32.0f && x < 200000.0f) || !(y >= 32.0f && y < 200000.0f)) return 0;
    if (!(w >= 1.0f && w <= 256.0f) || !(h >= 1.0f && h <= 256.0f)) return 0;
    return readable(a, 0x200);
}

static void dump_avatar(void)
{
    FILE *f = fopen(AV_OUT, "w");
    if (!f) return;
    for (int n = 0; n < 4; ++n) {
        unsigned char *a = (unsigned char *)find_object(VT_NETAVATAR, ok_netavatar, n);
        if (!a) break;
        float x = *(float *)(a + 4), y = *(float *)(a + 8);
        fprintf(f, "NetAvatar#%d @%p pos=%.2f,%.2f vel=%.2f,%.2f\n"
                   "  netID?(+0x2c)=%d (+0x30)=%d (+0x34)=%d\n"
                   "  +0x10=%.2f  onGround(+0xe4)=%u  jumpReq(+0xf4)=%u  "
                   "coyote(+0x198)=%u  +0x189=%u  stateFlags(+0x18c)=0x%x  "
                   "+0x180=%p  +0xd1=%u\n",
                n, a, x, y, *(float *)(a + 0xe8), *(float *)(a + 0xec),
                *(int *)(a + 0x2c), *(int *)(a + 0x30), *(int *)(a + 0x34),
                *(float *)(a + 0x10), a[0xe4], a[0xf4], a[0x198], a[0x189],
                *(unsigned int *)(a + 0x18c), *(void **)(a + 0x180), a[0xd1]);
        if (n == 0) {
            /* the column under the avatar, empty tiles included */
            unsigned char *w = (unsigned char *)find_object(VT_WORLD, ok_world, 0);
            if (!w) { fprintf(f, "  (no World)\n"); continue; }
            unsigned char *tm = w + 4;
            int width = *(int *)(tm + 0x04), height = *(int *)(tm + 0x08);
            unsigned char *beg = *(unsigned char **)(tm + 0x10);
            int cx = (int)(x / 32.0f);
            int feet = (int)(y + *(float *)(a + 0x10));
            fprintf(f, "  column x=%d  (feet y=%d -> row %d)\n", cx, feet, feet / 32);
            if (cx < 0 || cx >= width) { continue; }
            for (int ry = 0; ry < height; ++ry) {
                unsigned char *t = beg + ((size_t)ry * width + cx) * 0x38;
                if (!readable(t, 0x38)) break;
                fprintf(f, "   (%3d,%3d) fg=%-4u bg=%-4u flags=0x%04x blocked=%u "
                           "coll=%d  +0x14=%d +0x18=%d(%.2f) +0x1c=%d\n",
                        cx, ry, *(unsigned short *)(t + 0x00),
                        *(unsigned short *)(t + 0x02), *(unsigned short *)(t + 0x04),
                        t[0x0E], *(int *)(t + 0x10), *(int *)(t + 0x14),
                        *(int *)(t + 0x18), *(float *)(t + 0x18), *(int *)(t + 0x1C));
            }
        }
    }
    fclose(f);
}

static BOOL WINAPI hook_swap(HDC hdc)
{
    LONG f = InterlockedIncrement(&g_frame);
    /* Poll for a request file. Checking every frame is a cheap attribute
       lookup and keeps latency at one frame. */
    if ((f & 3) == 0 && GetFileAttributesA(REQ) != INVALID_FILE_ATTRIBUTES) {
        DeleteFileA(REQ);
        grab();
    }
    if ((f & 3) == 1 && GetFileAttributesA(ITEMS_REQ) != INVALID_FILE_ATTRIBUTES) {
        DeleteFileA(ITEMS_REQ);
        dump_items();
    }
    if ((f & 3) == 2 && GetFileAttributesA(INV_REQ) != INVALID_FILE_ATTRIBUTES) {
        DeleteFileA(INV_REQ);
        dump_inventory();
    }
    if ((f & 3) == 3 && GetFileAttributesA(WORLD_REQ) != INVALID_FILE_ATTRIBUTES) {
        DeleteFileA(WORLD_REQ);
        dump_world();
    }
    if ((f & 7) == 5 && GetFileAttributesA(BAR_REQ) != INVALID_FILE_ATTRIBUTES) {
        DeleteFileA(BAR_REQ);
        dump_bar();
    }
    if ((f & 7) == 7 && GetFileAttributesA(AV_REQ) != INVALID_FILE_ATTRIBUTES) {
        DeleteFileA(AV_REQ);
        dump_avatar();
    }
    return g_real ? g_real(hdc) : TRUE;
}

/* Patch the main module's IAT slot for GDI32!SwapBuffers. */
static int patch_iat(void)
{
    HMODULE base = GetModuleHandleA(NULL);
    unsigned char *b = (unsigned char*)base;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER*)b;
    IMAGE_NT_HEADERS *nt  = (IMAGE_NT_HEADERS*)(b + dos->e_lfanew);
    DWORD rva = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if (!rva) return 0;
    IMAGE_IMPORT_DESCRIPTOR *imp = (IMAGE_IMPORT_DESCRIPTOR*)(b + rva);
    for (; imp->Name; ++imp) {
        const char *dll = (const char*)(b + imp->Name);
        if (_stricmp(dll, "GDI32.dll") != 0) continue;
        IMAGE_THUNK_DATA *orig = (IMAGE_THUNK_DATA*)(b + (imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk));
        IMAGE_THUNK_DATA *iat  = (IMAGE_THUNK_DATA*)(b + imp->FirstThunk);
        for (; orig->u1.AddressOfData; ++orig, ++iat) {
            if (orig->u1.Ordinal & IMAGE_ORDINAL_FLAG) continue;
            IMAGE_IMPORT_BY_NAME *n = (IMAGE_IMPORT_BY_NAME*)(b + orig->u1.AddressOfData);
            if (strcmp((const char*)n->Name, "SwapBuffers") != 0) continue;
            DWORD old;
            if (!VirtualProtect(&iat->u1.Function, sizeof(void*), PAGE_READWRITE, &old))
                return 0;
            g_real = (SwapFn)(ULONG_PTR)iat->u1.Function;
            iat->u1.Function = (ULONG_PTR)hook_swap;
            VirtualProtect(&iat->u1.Function, sizeof(void*), old, &old);
            return 1;
        }
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r)
{
    (void)h; (void)r;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        int ok = patch_iat();
        FILE *f = fopen("C:\\cap.log", "a");
        if (f) { fprintf(f, "cap.dll attached, iat patch=%d real=%p\n", ok, (void*)g_real); fclose(f); }
    }
    return TRUE;
}
