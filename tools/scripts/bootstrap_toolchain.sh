#!/usr/bin/env bash
set -euo pipefail

stamp_path="$1"

ensure_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

download_file() {
  local url="$1"
  local output="$2"
  mkdir -p "$(dirname "$output")"
  curl -L --fail --output "$output" "$url"
}

extract_tarball() {
  local url="$1"
  local output_dir="$2"
  mkdir -p "$output_dir"
  curl -L --fail "$url" | tar xzv -C "$output_dir"
}

ensure_executable_file() {
  local path="$1"
  local url="$2"

  if [[ -x "$path" ]]; then
    return
  fi

  download_file "$url" "$path"
  chmod +x "$path"
}

ensure_extracted_tool() {
  local path="$1"
  local url="$2"
  local output_dir="$3"

  if [[ -x "$path" ]]; then
    return
  fi

  extract_tarball "$url" "$output_dir"
  chmod +x "$path"
}

ensure_binutils() {
  if [[ -x "$AS_PATH" && -x "$OBJCOPY_PATH" ]]; then
    return
  fi

  extract_tarball "$BINUTILS_URL" "$(dirname "$AS_PATH")"
  chmod +x "$(dirname "$AS_PATH")"/*
}

ensure_command curl
ensure_command tar

if [[ ! -f "$SOURCE_EXECUTABLE" ]]; then
  echo "$SOURCE_EXECUTABLE is missing, please provide this file." >&2
  exit 1
fi

ensure_executable_file "$WIBO_PATH" "$WIBO_URL"
ensure_extracted_tool "$EE_GCC_PATH" "$EE_GCC_URL" "$(dirname "$(dirname "$EE_GCC_PATH")")"
ensure_binutils
ensure_executable_file "$OBJDIFF_PATH" "$OBJDIFF_URL"

mkdir -p "$(dirname "$stamp_path")"
touch "$stamp_path"
