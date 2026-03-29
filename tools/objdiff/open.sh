#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
unit_name="${1:-}"
workspace_dir=""
default_objdiff="~/.bin/objdiff-gui"

if [[ -z "$unit_name" ]]; then
    echo "usage: $0 FUNC_NAME" >&2
    exit 1
fi

workspace_dir="$project_root/tools/objdiff/workspaces/$unit_name"
if [[ ! -d "$workspace_dir" ]]; then
    echo "workspace not found: $workspace_dir" >&2
    exit 1
fi

log_file="$project_root/build/objdiff-gui.log"
mkdir -p "$(dirname "$log_file")"

if [[ -n "${OBJDIFF_APP:-}" ]]; then
    nohup "${OBJDIFF_APP}" -p "$workspace_dir" >"$log_file" 2>&1 &
    echo "launched objdiff app; log: $log_file"
    exit 0
fi

if [[ -x "$default_objdiff" ]]; then
    nohup "$default_objdiff" -p "$workspace_dir" >"$log_file" 2>&1 &
    echo "launched objdiff app; log: $log_file"
    exit 0
fi

if [[ -n "${OBJDIFF_CMD:-}" ]]; then
    exec ${OBJDIFF_CMD} diff -p "$workspace_dir" -u "$unit_name" "$unit_name"
fi

if command -v objdiff >/dev/null 2>&1; then
    exec objdiff diff -p "$workspace_dir" -u "$unit_name" "$unit_name"
fi

echo "objdiff launcher not found." >&2
echo "Set OBJDIFF_APP to the desktop app path, or OBJDIFF_CMD to the CLI path." >&2
exit 1
