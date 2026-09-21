#!/bin/bash
# ============================================================
#  Bulletin Premium — Build pour Windows (one-file .exe)
#  Usage : ./build_windows.sh
#  Prerequis : 
#    - PyInstaller 6.x
#    - mingw-w64 cross-compiler
#    - Windows PyQt6 binaries (.pyd/.dll)
#    - Patched PyInstaller to use Windows bootloader
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Setup cross-compiler
export PATH="/home/iblis/.local/mingw/usr/bin:$PATH"
export CC=x86_64-w64-mingw32-gcc-win32
export CXX=x86_64-w64-mingw32-g++-win32

# Setup Windows binaries
export WIN_PYQT6="/home/iblis/.local/lib/python3.14/site-packages/PyQt6"

# Patch PyInstaller to use Windows bootloader
python3 -c "
with open('/home/iblis/.local/lib/python3.14/site-packages/PyInstaller/building/api.py', 'r') as f:
    content = f.read()
old = \"exe = self._bootloader_file('run', '.exe' if is_win or is_cygwin else '')\"
new = \"exe = self._bootloader_file('run', '.exe')\"
content = content.replace(old, new)
old2 = \"bootloader_file = os.path.join(HOMEPATH, 'PyInstaller', 'bootloader', PLATFORM, exe)\"
new2 = \"bootloader_file = os.path.join(HOMEPATH, 'PyInstaller', 'bootloader', 'Windows-64bit-intel', exe)\"
content = content.replace(old2, new2)
with open('/home/iblis/.local/lib/python3.14/site-packages/PyInstaller/building/api.py', 'w') as f:
    f.write(content)
print('PyInstaller patched for Windows build')
"

# Ensure Windows binaries are in place
cp /tmp/win-pyqt6/PyQt6/*.pyd "$WIN_PYQT6/" 2>/dev/null || true
cp -r /tmp/win-pyqt6/PyQt6/Qt6 "$WIN_PYQT6/" 2>/dev/null || true

# Clean previous builds
rm -rf dist build __pycache__

# Build
echo "Building Bulletin.exe for Windows..."
python3 -m PyInstaller --onefile --name Bulletin main.py

# Restore PyInstaller
python3 -c "
with open('/home/iblis/.local/lib/python3.14/site-packages/PyInstaller/building/api.py', 'r') as f:
    content = f.read()
old = \"exe = self._bootloader_file('run', '.exe')\"
new = \"exe = self._bootloader_file('run', '.exe' if is_win or is_cygwin else '')\"
content = content.replace(old, new)
old2 = \"bootloader_file = os.path.join(HOMEPATH, 'PyInstaller', 'bootloader', 'Windows-64bit-intel', exe)\"
new2 = \"bootloader_file = os.path.join(HOMEPATH, 'PyInstaller', 'bootloader', PLATFORM, exe)\"
content = content.replace(old2, new2)
with open('/home/iblis/.local/lib/python3.14/site-packages/PyInstaller/building/api.py', 'w') as f:
    f.write(content)
print('PyInstaller restored')
"

echo ""
echo "Build complete! Output: dist/Bulletin"
echo "Size: $(du -h dist/Bulletin | cut -f1)"
file dist/Bulletin
