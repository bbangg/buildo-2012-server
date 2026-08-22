/* shot.exe <out.bmp> [pw] - capture the Buildo window from inside Wine.
   Tries BitBlt by default, PrintWindow(PW_RENDERFULLCONTENT) with "pw". */
#include <windows.h>
#include <stdio.h>
#include <string.h>

#ifndef PW_RENDERFULLCONTENT
#define PW_RENDERFULLCONTENT 0x00000002
#endif

static HWND g_best; static long g_area; static DWORD g_self;
static BOOL CALLBACK pick(HWND h, LPARAM l) {
    (void)l;
    if (!IsWindowVisible(h)) return TRUE;
    DWORD pid=0; GetWindowThreadProcessId(h,&pid);
    if (pid==g_self) return TRUE;
    RECT r; if(!GetWindowRect(h,&r)) return TRUE;
    long a=(long)(r.right-r.left)*(long)(r.bottom-r.top);
    if(a>g_area){g_area=a;g_best=h;}
    return TRUE;
}

int main(int argc, char** argv) {
    if (argc < 2) { printf("usage: shot out.bmp [pw]\n"); return 2; }
    g_self = GetCurrentProcessId(); g_best=NULL; g_area=0;
    EnumWindows(pick, 0);
    if (!g_best) { printf("no window\n"); return 1; }
    RECT rc; GetClientRect(g_best, &rc);
    int w = rc.right, h = rc.bottom;
    if (w<=0||h<=0) { printf("bad size %dx%d\n",w,h); return 1; }

    HDC src = GetDC(g_best);
    HDC mem = CreateCompatibleDC(src);
    HBITMAP bmp = CreateCompatibleBitmap(src, w, h);
    HGDIOBJ old = SelectObject(mem, bmp);

    BOOL ok;
    if (argc>2 && !strcmp(argv[2],"pw")) {
        ok = PrintWindow(g_best, mem, PW_CLIENTONLY|PW_RENDERFULLCONTENT);
        printf("PrintWindow -> %d\n", ok);
    } else {
        ok = BitBlt(mem, 0,0,w,h, src, 0,0, SRCCOPY);
        printf("BitBlt -> %d\n", ok);
    }

    BITMAPINFOHEADER bi; ZeroMemory(&bi,sizeof bi);
    bi.biSize=sizeof bi; bi.biWidth=w; bi.biHeight=-h; bi.biPlanes=1;
    bi.biBitCount=24; bi.biCompression=BI_RGB;
    int stride=((w*3+3)/4)*4; int sz=stride*h;
    unsigned char* px=(unsigned char*)malloc(sz);
    int got=GetDIBits(mem,bmp,0,h,px,(BITMAPINFO*)&bi,DIB_RGB_COLORS);
    printf("GetDIBits -> %d (%dx%d, %d bytes)\n",got,w,h,sz);

    /* quick non-black check */
    long nz=0; for(int i=0;i<sz;i++) if(px[i]) nz++;
    printf("non-zero bytes: %ld / %d\n", nz, sz);

    BITMAPFILEHEADER fh; ZeroMemory(&fh,sizeof fh);
    fh.bfType=0x4D42; fh.bfOffBits=sizeof fh+sizeof bi; fh.bfSize=fh.bfOffBits+sz;
    FILE* f=fopen(argv[1],"wb");
    if(!f){printf("cannot open %s\n",argv[1]);return 1;}
    fwrite(&fh,1,sizeof fh,f); fwrite(&bi,1,sizeof bi,f); fwrite(px,1,sz,f); fclose(f);
    printf("wrote %s\n", argv[1]);
    SelectObject(mem,old); DeleteObject(bmp); DeleteDC(mem); ReleaseDC(g_best,src);
    return 0;
}
