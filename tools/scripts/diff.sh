#!/bin/bash
set -euo pipefail

SERIAL="$1"
CONFIG="$2"
BUILD="$3"
OBJCOPY="$4"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ -z "$SERIAL" ]]; then
    echo "usage: $0 <SERIAL> (e.g. SLUS_206.22)" >&2
    exit 1
fi

ROM="$ROOT_DIR/rom/$SERIAL"
CHECKSUM_FILE="$CONFIG/checksum.sha"

BUILD_BIN="$BUILD/$SERIAL"
ROM_BIN="$ROM/$SERIAL"

BUILD_ROM="$BUILD_BIN.rom"
ROM_ROM="$ROM_BIN.rom"

pass() {
    printf '✨ %s\n' "$1"
}

fail() {
    printf '🔴 %s\n' "$1" >&2
}

if [[ ! -f "$BUILD_BIN" ]]; then
    fail "linked ELF missing: $BUILD_BIN"
    exit 1
fi

if [[ ! -f "$ROM_BIN" ]]; then
    fail "target ELF missing: $ROM_BIN"
    exit 1
fi

$OBJCOPY -O binary "$BUILD_BIN" "$BUILD_ROM"

$OBJCOPY -O binary "$ROM_BIN" "$ROM_ROM"

source_sha=$(sha256sum "$BUILD_ROM" | awk '{print $1}')
target_sha=$(sha256sum "$ROM_ROM" | awk '{print $1}')

if [[ "$source_sha" == "$target_sha" ]]; then
    pass "built ROM matches target ROM"
    exit 0
else
    fail "built ROM does not match target ROM"
    exit 1
fi
