#!/usr/bin/env bash
# Compilation du binaire Windows (PE32+ GUI) depuis Linux.
#
# Prérequis :
#   - rustup avec la cible x86_64-pc-windows-gnu
#   - une chaîne mingw-w64 (x86_64-w64-mingw32-gcc)
#
# Le script détecte mingw dans le PATH puis dans les emplacements usuels.
set -euo pipefail
cd "$(dirname "$0")"

TARGET=x86_64-pc-windows-gnu

find_tool() {
    local name="$1"
    if command -v "$name" >/dev/null 2>&1; then
        command -v "$name"
        return 0
    fi
    for candidate in \
        "/home/iblis/.local/mingw/usr/bin/$name" \
        "/usr/bin/$name" \
        "/usr/local/bin/$name" \
        "/opt/mingw64/bin/$name"; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

GCC=$(find_tool x86_64-w64-mingw32-gcc || find_tool x86_64-w64-mingw32-gcc-win32 || true)
AR=$(find_tool x86_64-w64-mingw32-ar || true)
RANLIB=$(find_tool x86_64-w64-mingw32-ranlib || true)
WINDRES=$(find_tool x86_64-w64-mingw32-windres || true)

if [ -z "$GCC" ]; then
    echo "Erreur : x86_64-w64-mingw32-gcc est introuvable." >&2
    echo "Installez mingw-w64 ou ajoutez-le au PATH." >&2
    exit 1
fi

# dlltool est appelé par le linker : le dossier de mingw doit être dans le PATH.
export PATH="$(dirname "$GCC"):$PATH"
export CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER="$GCC"
export CC_x86_64_pc_windows_gnu="$GCC"
[ -n "$AR" ] && export AR_x86_64_pc_windows_gnu="$AR"
[ -n "$RANLIB" ] && export RANLIB_x86_64_pc_windows_gnu="$RANLIB"
[ -n "$WINDRES" ] && export WINDRES_x86_64_pc_windows_gnu="$WINDRES"

rustup target add "$TARGET" >/dev/null

cargo build --release -p bulletin-app --target "$TARGET"

OUT="target/$TARGET/release/bulletin-app.exe"
echo
echo "Binaire Windows : $OUT"
ls -lh "$OUT"
