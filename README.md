# Bulletin Premium

Application de gestion de bulletins scolaires avec PyQt6.

## Build Windows (One-file .exe)

### Prerequisites
- Python 3.14
- PyInstaller 6.22.3
- mingw-w64 cross-compiler
- Windows PyQt6 binaries (.pyd/.dll)

### Quick Build
```bash
./build_windows.sh
```

### Manual Build
1. Install dependencies: `pip install -r requirements.txt`
2. Install Windows PyQt6 binaries (see `build_windows.sh`)
3. Patch PyInstaller for Windows bootloader (see `build_windows.sh`)
4. Run: `pyinstaller Bulletin.spec`
5. Output: `dist/Bulletin` (PE32+ Windows .exe, ~115MB)

### Cross-compilation Notes
- Built on Linux using mingw-w64 cross-compiler
- Windows bootloader: `/home/iblis/.local/lib/python3.14/site-packages/PyInstaller/bootloader/Windows-64bit-intel/run.exe`
- Cross-compiler: `/home/iblis/.local/mingw/usr/bin/x86_64-w64-mingw32-gcc-win32`
# Bulletin Premium
