#!/usr/bin/env bash
set -euo pipefail

name="${1:-}"
compiler="${2:-ee-gcc2.95.3-136}"
project_root="$(cd "$(dirname "$0")/../.." && pwd)"
objdiff_dir="$project_root/tools/objdiff"
workspaces_dir="$objdiff_dir/workspaces"
serial="SLES_528.68"
config_dir="$project_root/viewtiful-joe/config/$serial"

if [[ -z "$name" ]]; then
    echo "usage: $0 FUNC_NAME" >&2
    exit 1
fi

workspace="$workspaces_dir/$name"
mkdir -p "$workspace"

current_c="$workspace/current.c"
current_ctx="$workspace/current.ctx.h"
target_s="$workspace/target.s"
objdiff_json="$workspace/objdiff.json"
workspace_mk="$workspace/Makefile"

target_src=""
target_func_source=""
for candidate in \
    "$config_dir/asm/nonmatchings"/*/"$name".s \
    "$config_dir/asm/nonmatchings"/"$name".s \
    "$config_dir/asm"/"$name".s; do
    if [[ -f "$candidate" ]]; then
        target_src="$candidate"
        break
    fi
done

if [[ -z "$target_src" ]]; then
    while IFS= read -r candidate; do
        if rg -q "^glabel $name\$" "$candidate"; then
            target_func_source="$candidate"
            break
        fi
    done < <(rg --files "$config_dir/asm" -g '*.s' | sort)
fi

if [[ -z "$target_src" && -z "$target_func_source" ]]; then
    echo "could not find asm source for $name under $config_dir/asm" >&2
    exit 1
fi

if [[ ! -f "$target_s" ]]; then
    {
        printf '.include "macro.inc"\n\n'
        printf '.section .text, "ax"\n\n'
        if [[ -n "$target_src" ]]; then
            cat "$target_src"
        else
            sed -n "/^glabel $name\$/,/^endlabel $name\$/p" "$target_func_source"
        fi
        printf '\n'
    } > "$target_s"
fi

if [[ ! -f "$current_ctx" ]]; then
    cat > "$current_ctx" <<EOF
#ifndef VJOE_OBJDIFF_${name}_CTX_H
#define VJOE_OBJDIFF_${name}_CTX_H

typedef signed char s8;
typedef unsigned char u8;
typedef signed short s16;
typedef unsigned short u16;
typedef signed int s32;
typedef unsigned int u32;
typedef float f32;
typedef double f64;

/* Add local typedefs, structs, enums, externs, and prototypes for $name here. */

#endif
EOF
fi

if [[ ! -f "$current_c" ]]; then
    cat > "$current_c" <<EOF
#include "current.ctx.h"

void $name(void) {
}
EOF
fi

cat > "$objdiff_json" <<EOF
{
  "\$schema": "https://raw.githubusercontent.com/encounter/objdiff/main/config.schema.json",
  "custom_make": "make",
  "build_target": true,
  "build_base": true,
  "watch_patterns": [
    "*.c",
    "*.h",
    "*.s",
    "Makefile",
    "objdiff.json"
  ],
  "ignore_patterns": [
    ".stage/**/*"
  ],
  "units": [
    {
      "name": "$name",
      "target_path": "target.o",
      "base_path": "base.o",
      "metadata": {
        "complete": false
      }
    }
  ]
}
EOF

cat > "$workspace_mk" <<EOF
REPO_ROOT := ../../../..
UNIT := $name
COMPILER := $compiler

WIBO := \$(abspath \$(REPO_ROOT))/tools/wibo-macos
MWCC := \$(abspath \$(REPO_ROOT))/tools/mwcps2/3.0.3/mwccps2.exe
AS := \$(abspath \$(REPO_ROOT))/tools/binutils-mips-ps2-decompals/mips-ps2-decompals-as
EE_GCC_2953_136 := \$(abspath \$(REPO_ROOT))/tools/ee-gcc2.95.3-136/bin/ee-gcc.exe

MWCC_FLAGS := -O2,p -sym=off,noelf -sdatathreshold 0 -str readonly -cwd source
AS_FLAGS := -EL -march=r5900 -mabi=eabi -mno-pdr
INCLUDE_DIR := \$(abspath \$(REPO_ROOT))/viewtiful-joe/include
CONFIG_DIR := \$(abspath \$(REPO_ROOT))/viewtiful-joe/config/$serial

.PHONY: all clean

all: target.o base.o

target.o: target.s \$(INCLUDE_DIR)/macro.inc
	"\$(AS)" \$(AS_FLAGS) -I "\$(INCLUDE_DIR)" -I "\$(CONFIG_DIR)" -o \$@ \$<

base.o: current.c current.ctx.h
ifeq (\$(COMPILER),mwccps2)
	rm -rf .stage
	mkdir -p .stage
	cp current.c .stage/
	cp current.ctx.h .stage/
	cd .stage && MWCIncludes=. "\$(WIBO)" "\$(MWCC)" \$(MWCC_FLAGS) -i . -o "\$(UNIT).o" -c current.c
	mv ".stage/\$(UNIT).o" \$@
else ifeq (\$(COMPILER),ee-gcc2.95.3-136)
	PATH="\$(dir \$(EE_GCC_2953_136)):\$$PATH" "\$(WIBO)" "\$(EE_GCC_2953_136)" -c -O2 -o \$@ current.c
else
	@echo "unsupported compiler: \$(COMPILER)" >&2
	@exit 1
endif

clean:
	rm -rf base.o target.o .stage
EOF

printf '%s\n' "$workspace"
