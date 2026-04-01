#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
import re
import shlex
import subprocess
import sys
import tomllib
import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

WIBO_HOST = "https://github.com/decompals/wibo/releases/download/1.0.1"
COMPILERS_HOST = "https://github.com/decompme/compilers/releases/download/compilers"
BINUTILS_HOST = "https://github.com/dreamingmoths/binutils-mips-ps2-decompals/releases/download/v0.8-aarch64"
OBJDIFF_HOST = "https://github.com/encounter/objdiff/releases/download/v3.6.0"
BINUTILS_FLAVOR = "mips-ps2-decompals"
MWCCGAP_AS_FLAGS = ["-mno-pdr"]
UV_CACHE_DIR = ".uv-cache"
INCLUDE_ASM_RE = re.compile(
    r'^\s*INCLUDE_ASM\(\s*"(?P<asm_dir>[^"]+)"\s*,\s*(?P<func>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;\s*$'
)


@dataclass(frozen=True)
class ProjectConfig:
    project: str
    serial: str
    default_opt_level: str
    special_opt_level: str
    ee_gcc_path: str
    ee_gcc_tar: str
    ee_gcc_flags: tuple[str, ...]


@dataclass(frozen=True)
class IncludeAsmRef:
    asm_dir: str
    func: str


@dataclass(frozen=True)
class CUnit:
    source: Path
    compile_source: Path
    include_asm_refs: tuple[IncludeAsmRef, ...]


@dataclass(frozen=True)
class ObjdiffUnitMetadata:
    progress_categories: list[str]
    source_path: str | None


@dataclass(frozen=True)
class ObjdiffUnit:
    name: str
    base_path: str | None
    target_path: str
    metadata: ObjdiffUnitMetadata


class NinjaWriter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def line(self, text: str = "") -> None:
        self.lines.append(text)

    def comment(self, text: str) -> None:
        self.line(f"# {text}")

    def variable(self, key: str, value: str) -> None:
        self.line(f"{key} = {value}")

    def rule(self, name: str, **kwargs: str | bool) -> None:
        self.line(f"rule {name}")
        for key, value in kwargs.items():
            if value in ("", None, False):
                continue
            if value is True:
                value = "1"
            self.line(f"  {key} = {value}")
        self.line()

    def build(
        self,
        outputs: str | list[str],
        rule: str,
        inputs: list[str] | None = None,
        implicit: list[str] | None = None,
        order_only: list[str] | None = None,
        variables: dict[str, str] | None = None,
    ) -> None:
        output_text = outputs if isinstance(outputs, str) else " ".join(outputs)
        parts = [f"build {output_text}: {rule}"]
        if inputs:
            parts.append(" ".join(inputs))
        if implicit:
            parts.append("| " + " ".join(implicit))
        if order_only:
            parts.append("|| " + " ".join(order_only))
        self.line(" ".join(parts))
        if variables:
            for key, value in variables.items():
                self.line(f"  {key} = {value}")
        self.line()

    def default(self, targets: list[str]) -> None:
        self.line(f"default {' '.join(targets)}")
        self.line()

    def render(self) -> str:
        return "\n".join(self.lines)


def rel(path: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    return path.relative_to(ROOT).as_posix()


def q(value: str | Path) -> str:
    return shlex.quote(str(value))


def write_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def relative_to_name(path_str: str, folder: str) -> str:
    folder = f"{folder}/"
    if folder in path_str:
        path_str = folder + path_str.split(folder)[1]
    return path_str


def normalize_object_path(path: Path, prefix_path: Path) -> str:
    path_str = path.as_posix()
    path_str = relative_to_name(path_str, "src")
    path_str = relative_to_name(path_str, "asm")
    return (prefix_path / path_str).as_posix()


def to_expected_path(base_path: str) -> Path:
    base_path = base_path.replace(".c.o", ".s.o")
    base_path = base_path.replace("src/", "asm/")
    return Path(base_path)


def ensure_path_and_write(output_path: Path, contents: str) -> None:
    output_path.parent.mkdir(exist_ok=True, parents=True)
    output_path.write_text(contents)


def run(args: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+", shlex.join(args))
    subprocess.run(args, cwd=ROOT, check=True, env=env)


def load_project_config() -> ProjectConfig:
    config_path = ROOT / "viewtiful-joe-2" / "build_config.toml"
    with config_path.open("rb") as f:
        data = tomllib.load(f)

    return ProjectConfig(
        project=data["project"],
        serial=data["serial"],
        default_opt_level=data["default_opt_level"],
        special_opt_level=data["special_opt_level"],
        ee_gcc_path=data["ee_gcc_path"],
        ee_gcc_tar=data["ee_gcc_tar"],
        ee_gcc_flags=tuple(data["ee_gcc_flags"]),
    )


def platform_info() -> tuple[str, str, str]:
    arch = platform.machine()
    kernel = platform.system()
    platform_name = "macos" if kernel == "Darwin" else "linux"
    os_name = f"{platform_name}-{arch.replace('_', '-')}"
    return arch, platform_name, os_name


def uv_sync() -> None:
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(ROOT / UV_CACHE_DIR)
    run(["uv", "sync", "--frozen"], env=env)


def ensure_source_executable(rom_dir: Path, source_executable: Path, serial: str) -> None:
    rom_dir.mkdir(parents=True, exist_ok=True)
    if source_executable.exists():
        return

    orig_source = Path("/orig") / serial
    if orig_source.exists():
        source_executable.write_bytes(orig_source.read_bytes())


def yaml_files(config_dir: Path) -> list[Path]:
    return sorted(path for path in config_dir.glob("*.yaml") if not path.name.endswith(".config.yaml"))


SLES_TEXT_UNITS = [
    "early_state_rest",
    "text_00106810",
    "text_0013FF98",
    "text_00180030",
    "text_001BFFE0",
    "text_001FFFA8",
    "text_0023FE88",
    "text_0027FE80",
    "text_002BF7A0",
    "text_002FFF48",
    "entry",
    "text_00382200",
]


def postprocess_split_sources(config: ProjectConfig, config_dir: Path, build_dir: Path) -> None:
    if config.serial != "SLES_528.68":
        return

    asm_dir = config_dir / "asm"
    data_dir = asm_dir / "data"

    text_00382200 = asm_dir / "text_00382200.s"
    if text_00382200.exists():
        text = text_00382200.read_text()
        text = text.replace(
            '    /* 2C3E20 003C2E20 00000000 */  nop\n'
            '    /* 2C3E24 003C2E24 00000000 */  nop\n'
            '    /* 2C3E28 003C2E28 00000000 */  nop\n'
            '    /* 2C3E2C 003C2E2C 00000000 */  nop\n'
            '    /* 2C3E30 003C2E30 00000000 */  nop\n'
            '    /* 2C3E34 003C2E34 00000000 */  nop\n'
            '    /* 2C3E38 003C2E38 00000000 */  nop\n'
            '    /* 2C3E3C 003C2E3C 00000000 */  nop\n'
            '    /* 2C3E40 003C2E40 00000000 */  nop\n'
            '    /* 2C3E44 003C2E44 00000000 */  nop\n'
            '    /* 2C3E48 003C2E48 00000000 */  nop\n'
            '    /* 2C3E4C 003C2E4C 00000000 */  nop\n'
            '    /* 2C3E50 003C2E50 00000000 */  nop\n'
            '    /* 2C3E54 003C2E54 00000000 */  nop\n'
            '    /* 2C3E58 003C2E58 00000000 */  nop\n'
            '    /* 2C3E5C 003C2E5C 00000000 */  nop\n'
            '    /* 2C3E60 003C2E60 00000000 */  nop\n'
            '    /* 2C3E64 003C2E64 00000000 */  nop\n'
            '    /* 2C3E68 003C2E68 00000000 */  nop\n'
            '    /* 2C3E6C 003C2E6C 00000000 */  nop\n'
            '    /* 2C3E70 003C2E70 00000000 */  nop\n'
            '    /* 2C3E74 003C2E74 00000000 */  nop\n'
            '    /* 2C3E78 003C2E78 00000000 */  nop\n'
            '    /* 2C3E7C 003C2E7C 00000000 */  nop\n',
            "",
        )
        text_00382200.write_text(text)

    data_path = data_dir / "data.data.s"
    vudata_path = data_dir / "vudata.vudata.s"
    if data_path.exists():
        lines = data_path.read_text().splitlines()
        split_index = next((i for i, line in enumerate(lines) if line.startswith("dlabel D_00445750")), None)
        if split_index is not None:
            header = [
                '.include "macro.inc"',
                "",
                '.section .vudata, "wa"',
                "",
                "/* Generated by configure_build.py from data.data.s */",
                "",
            ]
            data_lines = lines[:split_index]
            while data_lines and data_lines[-1] == "":
                data_lines.pop()
            data_lines.append("")
            vudata_lines = header + lines[split_index:]
            data_path.write_text("\n".join(data_lines) + "\n")
            vudata_path.write_text("\n".join(vudata_lines) + "\n")

            data_text = data_path.read_text().replace(
                '    /* 346744 00445744 00000000 */ .word 0x00000000\n'
                '    /* 346748 00445748 00000000 */ .word 0x00000000\n'
                '    /* 34674C 0044574C 00000000 */ .word 0x00000000\n'
                'enddlabel D_00445728\n',
                'enddlabel D_00445728\n',
            )
            data_path.write_text(data_text)

            vudata_text = vudata_path.read_text().replace(
                '    /* 3491E0 004481E0 00000000 */ .word 0x00000000\n'
                '    /* 3491E4 004481E4 00000000 */ .word 0x00000000\n'
                '    /* 3491E8 004481E8 00000000 */ .word 0x00000000\n'
                '    /* 3491EC 004481EC 00000000 */ .word 0x00000000\n'
                '    /* 3491F0 004481F0 00000000 */ .word 0x00000000\n'
                '    /* 3491F4 004481F4 00000000 */ .word 0x00000000\n'
                '    /* 3491F8 004481F8 00000000 */ .word 0x00000000\n'
                '    /* 3491FC 004481FC 00000000 */ .word 0x00000000\n'
                'enddlabel D_00446FC0\n',
                'enddlabel D_00446FC0\n',
            )
            vudata_path.write_text(vudata_text)

    rodata_path = data_dir / "rodata.rodata.s"
    if rodata_path.exists():
        rodata_text = rodata_path.read_text().replace(
            '    /* 35FB68 0045EB68 */ .byte 0x00\n'
            '    /* 35FB69 0045EB69 */ .byte 0x00\n'
            '    /* 35FB6A 0045EB6A */ .byte 0x00\n'
            '    /* 35FB6B 0045EB6B */ .byte 0x00\n'
            '    /* 35FB6C 0045EB6C */ .byte 0x00\n'
            '    /* 35FB6D 0045EB6D */ .byte 0x00\n'
            '    /* 35FB6E 0045EB6E */ .byte 0x00\n'
            '    /* 35FB6F 0045EB6F */ .byte 0x00\n'
            '    /* 35FB70 0045EB70 */ .byte 0x00\n'
            '    /* 35FB71 0045EB71 */ .byte 0x00\n'
            '    /* 35FB72 0045EB72 */ .byte 0x00\n'
            '    /* 35FB73 0045EB73 */ .byte 0x00\n'
            '    /* 35FB74 0045EB74 */ .byte 0x00\n'
            '    /* 35FB75 0045EB75 */ .byte 0x00\n'
            '    /* 35FB76 0045EB76 */ .byte 0x00\n'
            '    /* 35FB77 0045EB77 */ .byte 0x00\n'
            '    /* 35FB78 0045EB78 */ .byte 0x00\n'
            '    /* 35FB79 0045EB79 */ .byte 0x00\n'
            '    /* 35FB7A 0045EB7A */ .byte 0x00\n'
            '    /* 35FB7B 0045EB7B */ .byte 0x00\n'
            '    /* 35FB7C 0045EB7C */ .byte 0x00\n'
            '    /* 35FB7D 0045EB7D */ .byte 0x00\n'
            '    /* 35FB7E 0045EB7E */ .byte 0x00\n'
            '    /* 35FB7F 0045EB7F */ .byte 0x00\n'
            'enddlabel D_0045EA68\n',
            'enddlabel D_0045EA68\n',
        )
        rodata_path.write_text(rodata_text)

    sbss_path = data_dir / "sbss.sbss.s"
    if sbss_path.exists():
        sbss_text = sbss_path.read_text().replace(
            'dlabel D_0045F930\n    /* 0045F930 */ .space 0x50\n',
            'dlabel D_0045F930\n    /* 0045F930 */ .space 0x04\n',
        )
        sbss_path.write_text(sbss_text)

    write_sles_gnu_ld(config_dir, build_dir)


def write_sles_gnu_ld(config_dir: Path, build_dir: Path) -> None:
    linkers_dir = config_dir / "linkers"
    ld_path = linkers_dir / "SLES_528.68.ld"
    undefined_funcs = (linkers_dir / "viewtiful_joe_undefined_funcs_auto.main.txt").read_text().strip()
    undefined_syms = (linkers_dir / "viewtiful_joe_undefined_syms_auto.main.txt").read_text().strip()
    asm_root = rel(build_dir / "asm")
    src_root = rel(build_dir / "src")

    def unit_obj(unit: str) -> str:
        if (ROOT / "viewtiful-joe-2" / "src" / f"{unit}.c").exists():
            return f"{src_root}/{unit}.c.o"
        return f"{asm_root}/{unit}.s.o"

    text_entries = "\n".join(f"        {unit_obj(name)}(.text)" for name in SLES_TEXT_UNITS)
    data_entries = "\n".join(
        [f"        {unit_obj(name)}(.data)" for name in SLES_TEXT_UNITS] +
        [f"        {asm_root}/data/data.data.s.o(.data)"]
    )
    rodata_entries = "\n".join(
        [f"        {unit_obj(name)}(.rodata)" for name in SLES_TEXT_UNITS] +
        [f"        {asm_root}/data/rodata.rodata.s.o(.rodata)"]
    )
    bss_entries = "\n".join(
        [f"        {unit_obj(name)}(.bss)" for name in SLES_TEXT_UNITS] +
        [f"        {asm_root}/data/bss.bss.s.o(.bss)"]
    )
    script = f"""ENTRY(entry)
{undefined_funcs}
{undefined_syms}

SECTIONS
{{
    . = 0x00100000;

    .text 0x00100000 :
    {{
{text_entries}
    }}

    .vutext 0x003C2E20 :
    {{
        BYTE(0)
    }}

    .data 0x003C2E80 :
    {{
{data_entries}
    }}

    .vudata 0x00445750 :
    {{
        {asm_root}/data/vudata.vudata.s.o(.vudata)
    }}

    .rodata 0x00448200 :
    {{
{rodata_entries}
    }}

    _gp = 0x466B70;
    .sdata 0x0045EB80 :
    {{
        {asm_root}/data/sdata.sdata.s.o(.sdata)
    }}

    .sbss 0x0045F700 (NOLOAD) :
    {{
        {asm_root}/data/sbss.sbss.s.o(.sbss)
    }}

    .bss 0x0045F980 (NOLOAD) :
    {{
{bss_entries}
    }}

    /DISCARD/ :
    {{
        *(.comment)
        *(.pdr)
        *(.mdebug*)
        *(.reginfo)
        *(.MIPS.abiflags)
        *(.gnu.attributes)
        *(*)
    }}
}}
"""
    write_if_changed(ld_path, script)


def generate_linker_dependencies(config_path: Path, build_path: Path) -> None:
    import splat.scripts.split as splat_split
    import splat.util.options as splat_options
    from splat.segtypes.linker_entry import clean_up_path

    linker_writer = splat_split.linker_writer
    path_strs: list[str] = []
    output = f"{(build_path / clean_up_path(splat_options.opts.elf_path)).as_posix()}:"

    for entry in linker_writer.dependencies_entries:
        if entry.object_path is None:
            continue
        path_str = normalize_object_path(entry.object_path, build_path)
        path_strs.append(path_str)
        output += f" \\\n+    {path_str}"

    output += "\n"
    for path_str in path_strs:
        output += f"{path_str}:\n"

    ensure_path_and_write(splat_options.opts.ld_script_path.with_suffix(".d"), output)


def run_splat_generate(
    *,
    config_path: Path,
    build_path: Path,
    verbose: bool,
    no_objdiff: bool,
    objdiff_output_path: Path | None,
    make_full_disasm_for_code: bool,
    yamls: list[Path],
) -> None:
    import splat.scripts.split as splat_split

    old_cwd = os.getcwd()
    try:
        get_relative_path = lambda path: Path(path).relative_to(config_path)
        os.chdir(config_path)
        splat_split.main(
            list(map(get_relative_path, yamls)),
            modes="all",
            verbose=verbose,
            use_cache=False,
            make_full_disasm_for_code=make_full_disasm_for_code,
        )
        generate_linker_dependencies(config_path, build_path)
        if not no_objdiff and objdiff_output_path is not None:
            generate_objdiff_units(build_path=build_path, output_path=objdiff_output_path)
    finally:
        os.chdir(old_cwd)


def generate_objdiff_units(*, build_path: Path, output_path: Path) -> None:
    import splat.scripts.split as splat_split

    units: list[dict] = []
    for entry in splat_split.linker_writer.entries:
        segment = entry.segment
        parent = segment.parent
        segment_type = segment.type

        if segment.name == "sce":
            continue
        if segment.name.startswith("sdk/") or segment.name == "sdk":
            continue
        if segment.name.startswith("cri/"):
            continue
        if segment.name == "crt0":
            continue
        if segment_type not in {"asm", "c"}:
            continue
        if not parent or parent.type != "code":
            continue
        if len(entry.src_paths) > 1:
            raise Exception("Unhandled case: len(src_paths) > 1")

        source_path = str(entry.src_paths[0])
        object_path = str(entry.object_path)
        is_code = source_path.endswith(".c")
        metadata = ObjdiffUnitMetadata(
            progress_categories=[parent.name == "engine" and "engine" or "stages"],
            source_path=source_path if is_code else None,
        )
        base_path = normalize_object_path(Path(object_path), build_path) if is_code else None
        target_path = normalize_object_path(to_expected_path(object_path), build_path)
        units.append(
            {
                "name": entry.segment.name,
                "base_path": base_path,
                "target_path": target_path,
                "metadata": {
                    "progress_categories": metadata.progress_categories,
                    "source_path": metadata.source_path,
                },
            }
        )

    ensure_path_and_write(output_path, json.dumps(units))


def merge_objdiff_units(*, categories_path: Path | None, output_path: Path, fragments: list[Path]) -> None:
    units = []
    for path in fragments:
        units.extend(json.loads(path.read_text()))

    units.sort(key=lambda unit: unit["name"])

    progress_categories = None
    if categories_path is not None:
        progress_categories = json.loads(categories_path.read_text())

    ensure_path_and_write(
        output_path,
        json.dumps(
            {
                "$schema": "https://raw.githubusercontent.com/encounter/objdiff/main/config.schema.json",
                "build_base": False,
                "build_target": False,
                "progress_categories": progress_categories,
                "units": units,
            }
        ),
    )


def split_outputs(
    config: ProjectConfig,
    config_dir: Path,
    build_dir: Path,
    include_dir: Path,
) -> list[Path]:
    python_exe = ROOT / ".venv" / "bin" / "python"
    if not python_exe.exists():
        raise SystemExit("missing .venv/bin/python after uv sync")

    splat_config = config_dir / "splat.config.yaml"

    for yaml_path in yaml_files(config_dir):
        args = [
            str(python_exe),
            str(ROOT / "tools" / "scripts" / "configure_build.py"),
            "splat-generate",
            "--verbose",
            "--build-path",
            str(build_dir),
            "--config-path",
            str(config_dir),
            "--no-objdiff",
            "--make-full-disasm-for-code",
        ]
        args.extend([str(splat_config), str(yaml_path)])
        run(args)

    postprocess_split_sources(config, config_dir, build_dir)

    return sorted((config_dir / "linkers").glob("*.d"))


def split_stamp_path() -> Path:
    return ROOT / "build" / "stamps" / "split.stamp"


def scan_sources(root: Path, suffix: str) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob(f"*{suffix}") if path.is_file())


def scan_asm_sources(asm_dir: Path) -> list[Path]:
    sources: list[Path] = []
    for path in scan_sources(asm_dir, ".s"):
        if "matchings" in path.parts or "nonmatchings" in path.parts:
            continue
        sources.append(path)
    return sources


def c_object_path(path: Path, project_dir: Path, base_dir: Path) -> Path:
    return (base_dir / "src" / path.relative_to(project_dir / "src")).with_suffix(".c.o")


def asm_object_path(path: Path, config_dir: Path, base_dir: Path) -> Path:
    return (base_dir / "asm" / path.relative_to(config_dir / "asm")).with_suffix(".s.o")


def include_asm_object_path(source: Path, func: str, project_dir: Path, base_dir: Path) -> Path:
    rel_source = source.relative_to(project_dir / "src").with_suffix("")
    return base_dir / "include_asm" / rel_source / f"{func}.s.o"


def partial_c_object_path(source: Path, project_dir: Path, base_dir: Path) -> Path:
    return (base_dir / "partial_c" / source.relative_to(project_dir / "src")).with_suffix(".c.o")


def stripped_c_path(source: Path, project_dir: Path, base_dir: Path) -> Path:
    return base_dir / "generated" / "src" / source.relative_to(project_dir / "src")


def include_asm_wrapper_path(source: Path, func: str, project_dir: Path, base_dir: Path) -> Path:
    rel_source = source.relative_to(project_dir / "src").with_suffix("")
    return base_dir / "generated" / "include_asm" / rel_source / f"{func}.s"


def write_include_asm_wrapper(
    asm_source: Path, source: Path, func: str, project_dir: Path, base_dir: Path
) -> Path:
    wrapper = include_asm_wrapper_path(source, func, project_dir, base_dir)
    write_if_changed(
        wrapper,
        '.include "macro.inc"\n\n'
        ".set noat\n"
        ".set noreorder\n\n"
        '.section .text, "ax"\n\n'
        f'.include "{rel(asm_source)}"\n'
    )
    return wrapper


def analyze_c_source(source: Path, project_dir: Path, base_dir: Path) -> CUnit:
    text = source.read_text()
    refs: list[IncludeAsmRef] = []
    stripped_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        match = INCLUDE_ASM_RE.match(line)
        if match is None:
            stripped_lines.append(line)
            continue
        refs.append(IncludeAsmRef(match.group("asm_dir"), match.group("func")))
        stripped_lines.append("\n" if line.endswith("\n") else "")

    if not refs:
        return CUnit(source=source, compile_source=source, include_asm_refs=())

    compile_source = stripped_c_path(source, project_dir, base_dir)
    write_if_changed(compile_source, "".join(stripped_lines))
    return CUnit(source=source, compile_source=compile_source, include_asm_refs=tuple(refs))


def generator_inputs(config: ProjectConfig, config_dir: Path, project_dir: Path) -> list[str]:
    inputs = {
        "pyproject.toml",
        "uv.lock",
        "tools/scripts/configure_build.py",
        "tools/scripts/bootstrap_toolchain.sh",
        "tools/scripts/diff.sh",
        "decomp.yaml",
        rel(project_dir / "build_config.toml"),
        rel(config_dir),
        rel(ROOT / "rom" / config.serial),
    }

    for path in scan_sources(ROOT / "tools" / "scripts", ".py"):
        inputs.add(rel(path))
    for path in scan_sources(project_dir / "src", ".c"):
        inputs.add(rel(path))
    for path in scan_sources(project_dir / "src", ".h"):
        inputs.add(rel(path))
    for path in scan_sources(project_dir / "include", ".h"):
        inputs.add(rel(path))
    for path in scan_sources(project_dir / "include", ".inc"):
        inputs.add(rel(path))
    for path in config_dir.iterdir():
        if path.name == "rom":
            continue
        inputs.add(rel(path))
    return sorted(inputs)


def shell_flags(values: list[str] | tuple[str, ...]) -> str:
    return " ".join(q(value) for value in values)


def write_build_ninja(
    config: ProjectConfig,
    c_units: list[CUnit],
    asm_sources: list[Path],
) -> None:
    arch, platform_name, os_name = platform_info()
    project_dir = ROOT / config.project
    config_dir = project_dir / "config" / config.serial
    include_dir = project_dir / "include"
    src_dir = project_dir / "src"
    build_dir = ROOT / "build" / config.serial
    expected_dir = build_dir / "expected"
    linkers_dir = config_dir / "linkers"
    rom_dir = ROOT / "rom" / config.serial
    source_executable = rom_dir / config.serial
    linker_script = linkers_dir / f"{config.serial}.ld"
    checksum_file = config_dir / "checksum.sha"
    categories_path = config_dir / "categories.json"
    python_exe = Path(".venv/bin/python")
    ee_gcc_path = Path(config.ee_gcc_path)
    wibo_binary = f"wibo-{'macos' if arch == 'arm64' else arch}"
    wibo_path = Path("tools") / wibo_binary
    binutils_dir = Path("tools") / f"binutils-{BINUTILS_FLAVOR}"
    as_path = binutils_dir / f"{BINUTILS_FLAVOR}-as"
    ld_path = binutils_dir / f"{BINUTILS_FLAVOR}-ld"
    objcopy_path = binutils_dir / f"{BINUTILS_FLAVOR}-objcopy"
    objdiff_binary = f"objdiff-cli-{platform_name}-{arch}"
    objdiff_path = Path("tools") / objdiff_binary
    build_stamp_dir = Path("build") / "stamps"
    python_stamp = build_stamp_dir / "python.stamp"
    toolchain_stamp = build_stamp_dir / "toolchain.stamp"
    split_stamp = split_stamp_path()
    force_target = build_stamp_dir / "force"
    report_path = build_dir / "report.json"
    objdiff_config = build_dir / "objdiff.json"

    current_headers = [
        rel(path)
        for path in scan_sources(include_dir, ".h") + scan_sources(include_dir, ".inc")
    ]

    split_inputs = [rel(config_dir / "splat.config.yaml")] + [rel(path) for path in yaml_files(config_dir)]
    split_inputs.extend(rel(path) for path in config_dir.glob("*.txt"))
    split_inputs.extend([rel(categories_path), rel(source_executable)])

    writer = NinjaWriter()
    writer.comment("Generated by tools/scripts/configure_build.py")
    writer.variable("ninja_required_version", "1.7")
    writer.line()

    writer.rule(
        "configure",
        command="python3 tools/scripts/configure_build.py",
        description="CONFIGURE build.ninja",
        generator=True,
    )
    writer.rule(
        "uv_sync",
        command=f"UV_CACHE_DIR={q(UV_CACHE_DIR)} uv sync --frozen && mkdir -p {q(rel(build_stamp_dir))} && touch $out",
        description="UV sync",
        restat=True,
    )
    bootstrap_env = {
        "ROOT_DIR": rel(ROOT),
        "ROM_DIR": rel(rom_dir),
        "SOURCE_EXECUTABLE": rel(source_executable),
        "WIBO_PATH": rel(wibo_path),
        "WIBO_URL": f"{WIBO_HOST}/{wibo_binary}",
        "EE_GCC_PATH": rel(ee_gcc_path),
        "EE_GCC_URL": f"{COMPILERS_HOST}/{config.ee_gcc_tar}",
        "AS_PATH": rel(as_path),
        "OBJCOPY_PATH": rel(objcopy_path),
        "BINUTILS_URL": f"{BINUTILS_HOST}/binutils-{BINUTILS_FLAVOR}-{os_name}.tar.gz",
        "OBJDIFF_PATH": rel(objdiff_path),
        "OBJDIFF_URL": f"{OBJDIFF_HOST}/{objdiff_binary}",
    }
    bootstrap_prefix = " ".join(f"{key}={q(value)}" for key, value in bootstrap_env.items())
    writer.rule(
        "bootstrap_toolchain",
        command=f"{bootstrap_prefix} bash tools/scripts/bootstrap_toolchain.sh $out",
        description="SETUP toolchain",
        restat=True,
    )
    writer.rule(
        "split_outputs",
        command=f"python3 tools/scripts/configure_build.py split && mkdir -p {q(rel(build_stamp_dir))} && touch $out",
        description="SPLIT assets",
        restat=True,
    )
    ee_gcc_common_flags = [config.default_opt_level, *config.ee_gcc_flags]
    writer.rule(
        "compile_c",
        command=(
            f"PATH={q(rel(ee_gcc_path.parent))}:$PATH {q(rel(wibo_path))} {q(rel(ee_gcc_path))} "
            f"{shell_flags(ee_gcc_common_flags)} -c $in -o $out"
        ),
        description="CC $out",
    )
    writer.rule(
        "compile_c_expected",
        command=(
            f"PATH={q(rel(ee_gcc_path.parent))}:$PATH {q(rel(wibo_path))} {q(rel(ee_gcc_path))} "
            f"{shell_flags(ee_gcc_common_flags)} -c $in -o $out"
        ),
        description="CC(expected) $out",
    )
    writer.rule(
        "compile_asm",
        command=(
            f"{q(rel(as_path))} "
            f"{shell_flags(['-EL', '-march=r5900', '-mabi=eabi', '-G=0', *MWCCGAP_AS_FLAGS, f'-I{rel(include_dir)}', f'-I{rel(config_dir)}'])} "
            "-o $out $in"
        ),
        description="AS $out",
    )
    writer.rule(
        "compile_asm_expected",
        command=(
            f"{q(rel(as_path))} "
            f"{shell_flags(['-EL', '-march=r5900', '-mabi=eabi', '-G=0', *MWCCGAP_AS_FLAGS, f'-I{rel(include_dir)}', f'-I{rel(config_dir)}'])} "
            "-o $out $in"
        ),
        description="AS(expected) $out",
    )
    writer.rule(
        "partial_link",
        command=f"{q(rel(ld_path))} -r -EL -o $out $in",
        description="LD -r $out",
    )
    writer.rule(
        "link",
        command=f"{q(rel(ld_path))} -EL -T {q(rel(linker_script))} -e entry -Map $out.map -o $out @$out.rsp",
        description="LINK $out",
        rspfile="$out.rsp",
        rspfile_content="$in",
    )
    writer.rule(
        "merge_objdiff",
        command=(
            f"{q(python_exe)} tools/scripts/configure_build.py merge-objdiff "
            f"--categories-path {q(rel(categories_path))} --output-path $out $in"
        ),
        description="MERGE $out",
    )
    writer.rule(
        "generate_objdiff",
        command=(
            f"{q(python_exe)} tools/scripts/configure_build.py splat-generate --verbose "
            f"--build-path $build_path "
            f"--config-path {q(rel(config_dir))} "
            "--make-full-disasm-for-code "
            "--objdiff-output-path=$out "
            f"{q(rel(config_dir / 'splat.config.yaml'))} $in"
        ),
        description="OBJDIFF $out",
    )
    writer.rule(
        "report",
        command=f"{q(rel(objdiff_path))} report generate -o $out {q(rel(objdiff_config))}",
        description="REPORT $out",
    )
    writer.rule(
        "diff",
        command=f"tools/scripts/diff.sh {q(config.serial)} {q(rel(config_dir))} {q(rel(build_dir))} {q(rel(objcopy_path))} && mkdir -p {q(rel(build_stamp_dir))} && touch $out",
        description="DIFF",
    )
    writer.rule(
        "clean_tree",
        command=(
            f"rm -rf {q(rel(build_dir))} {q(rel(config_dir / 'asm'))} {q(rel(config_dir / 'assets'))} "
            f"{q(rel(config_dir / 'linkers'))} && mkdir -p {q(rel(build_stamp_dir))} && touch $out"
        ),
        description="CLEAN",
    )
    writer.rule(
        "clean_toolchain",
        command=(
            f"rm -rf {q(rel(binutils_dir))} tools/wibo-* tools/objdiff-cli-* {q(rel(toolchain_stamp))} "
            f"&& mkdir -p {q(rel(build_stamp_dir))} && touch $out"
        ),
        description="CLEAN toolchain",
    )

    writer.build("build.ninja", "configure", inputs=generator_inputs(config, config_dir, project_dir))
    writer.build(rel(python_stamp), "uv_sync", inputs=["pyproject.toml", "uv.lock"])
    writer.build(
        rel(toolchain_stamp),
        "bootstrap_toolchain",
        inputs=["tools/scripts/bootstrap_toolchain.sh", rel(source_executable)],
    )
    writer.build(
        rel(split_stamp),
        "split_outputs",
        inputs=split_inputs,
        implicit=["tools/scripts/configure_build.py"] + [rel(path) for path in scan_sources(ROOT / "tools" / "scripts", ".py")],
        order_only=[rel(python_stamp), rel(toolchain_stamp)],
    )
    writer.build(rel(force_target), "phony")

    actual_c_objects: list[str] = []
    expected_c_objects: list[str] = []
    asm_implicit = [rel(path) for path in scan_sources(include_dir, ".inc")]

    for unit in c_units:
        source = unit.source
        actual_output = rel(c_object_path(source, project_dir, build_dir))
        expected_output = rel(c_object_path(source, project_dir, expected_dir))
        implicit_inputs = current_headers.copy()
        implicit_inputs.append(rel(source))

        actual_compile_output = actual_output
        expected_compile_output = expected_output
        actual_partial_inputs: list[str] = []
        expected_partial_inputs: list[str] = []
        if unit.include_asm_refs:
            actual_compile_output = rel(partial_c_object_path(source, project_dir, build_dir))
            expected_compile_output = rel(partial_c_object_path(source, project_dir, expected_dir))

        writer.build(
            actual_compile_output,
            "compile_c",
            inputs=[rel(unit.compile_source)],
            implicit=implicit_inputs,
            order_only=[rel(python_stamp), rel(toolchain_stamp), rel(split_stamp)],
        )
        writer.build(
            expected_compile_output,
            "compile_c_expected",
            inputs=[rel(unit.compile_source)],
            implicit=implicit_inputs,
            order_only=[rel(toolchain_stamp), rel(split_stamp)],
        )
        actual_partial_inputs.append(actual_compile_output)
        expected_partial_inputs.append(expected_compile_output)

        for ref in unit.include_asm_refs:
            asm_source = config_dir / ref.asm_dir / f"{ref.func}.s"
            wrapper_source = write_include_asm_wrapper(
                asm_source, source, ref.func, project_dir, build_dir
            )
            actual_include_output = rel(include_asm_object_path(source, ref.func, project_dir, build_dir))
            expected_include_output = rel(include_asm_object_path(source, ref.func, project_dir, expected_dir))
            expected_wrapper_source = write_include_asm_wrapper(
                asm_source, source, ref.func, project_dir, expected_dir
            )
            writer.build(
                actual_include_output,
                "compile_asm",
                inputs=[rel(wrapper_source)],
                implicit=asm_implicit,
                order_only=[rel(toolchain_stamp), rel(split_stamp)],
            )
            writer.build(
                expected_include_output,
                "compile_asm_expected",
                inputs=[rel(expected_wrapper_source)],
                implicit=asm_implicit,
                order_only=[rel(toolchain_stamp), rel(split_stamp)],
            )
            actual_partial_inputs.append(actual_include_output)
            expected_partial_inputs.append(expected_include_output)

        if unit.include_asm_refs:
            writer.build(
                actual_output,
                "partial_link",
                inputs=actual_partial_inputs,
                order_only=[rel(toolchain_stamp), rel(split_stamp)],
            )
            writer.build(
                expected_output,
                "partial_link",
                inputs=expected_partial_inputs,
                order_only=[rel(toolchain_stamp), rel(split_stamp)],
            )

        actual_c_objects.append(actual_output)
        expected_c_objects.append(expected_output)

    actual_asm_objects: list[str] = []
    expected_asm_objects: list[str] = []
    for source in asm_sources:
        actual_output = rel(asm_object_path(source, config_dir, build_dir))
        expected_output = rel(asm_object_path(source, config_dir, expected_dir))
        writer.build(
            actual_output,
            "compile_asm",
            inputs=[rel(source)],
            implicit=asm_implicit,
            order_only=[rel(toolchain_stamp), rel(split_stamp)],
        )
        writer.build(
            expected_output,
            "compile_asm_expected",
            inputs=[rel(source)],
            implicit=asm_implicit,
            order_only=[rel(toolchain_stamp), rel(split_stamp)],
        )
        actual_asm_objects.append(actual_output)
        expected_asm_objects.append(expected_output)

    main_binary = rel(build_dir / config.serial)
    writer.build(
        main_binary,
        "link",
        inputs=actual_c_objects + actual_asm_objects,
        implicit=[rel(linker_script)],
        order_only=[rel(toolchain_stamp), rel(split_stamp)],
    )

    fragment_outputs: list[str] = []
    for yaml_path in yaml_files(config_dir):
        fragment_path = rel(build_dir / "objdiff" / f"{yaml_path.stem}.json")
        writer.build(
            fragment_path,
            "generate_objdiff",
            inputs=[rel(yaml_path)],
            implicit=split_inputs,
            order_only=[rel(python_stamp), rel(split_stamp)],
            variables={"build_path": rel(expected_dir)},
        )
        fragment_outputs.append(fragment_path)

    writer.build(
        rel(objdiff_config),
        "merge_objdiff",
        inputs=fragment_outputs,
        implicit=["tools/scripts/configure_build.py"],
        order_only=[rel(python_stamp)],
    )
    writer.build(
        rel(report_path),
        "report",
        inputs=[rel(objdiff_config)] + expected_c_objects + expected_asm_objects,
        order_only=[rel(toolchain_stamp)],
    )
    writer.build(
        rel(build_stamp_dir / "diff.stamp"),
        "diff",
        inputs=[main_binary, rel(checksum_file)],
        order_only=[rel(toolchain_stamp)],
    )
    writer.build(
        rel(build_stamp_dir / "clean.stamp"),
        "clean_tree",
        inputs=[rel(force_target)],
    )
    writer.build(
        rel(build_stamp_dir / "clean-toolchain.stamp"),
        "clean_toolchain",
        inputs=[rel(force_target)],
    )

    writer.build("configure", "phony", inputs=["build.ninja"])
    writer.build("split", "phony", inputs=[rel(split_stamp)])
    writer.build("setup", "phony", inputs=[rel(python_stamp), rel(toolchain_stamp), rel(split_stamp)])
    writer.build("report", "phony", inputs=[rel(report_path)])
    writer.build("diff", "phony", inputs=[rel(build_stamp_dir / "diff.stamp")])
    writer.build("clean", "phony", inputs=[rel(build_stamp_dir / "clean.stamp")])
    writer.build("clean-toolchain", "phony", inputs=[rel(build_stamp_dir / "clean-toolchain.stamp")])
    writer.build("all", "phony", inputs=[rel(build_stamp_dir / "diff.stamp")])
    writer.default(["all"])

    (ROOT / "build.ninja").write_text(writer.render())


def main() -> int:
    config = load_project_config()
    project_dir = ROOT / config.project
    config_dir = project_dir / "config" / config.serial
    include_dir = project_dir / "include"
    build_dir = ROOT / "build" / config.serial
    rom_dir = ROOT / "rom" / config.serial
    source_executable = rom_dir / config.serial

    if not source_executable.exists():
        raise SystemExit(f"{rel(source_executable)} is missing, please provide this file.")

    mode = sys.argv[1] if len(sys.argv) > 1 else "configure"

    if mode == "splat-generate":
        ensure_source_executable(rom_dir, source_executable, config.serial)
        args = sys.argv[2:]
        verbose = False
        no_objdiff = False
        build_path: Path | None = None
        config_path: Path | None = None
        objdiff_output_path: Path | None = None
        yamls: list[Path] = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--verbose":
                verbose = True
                i += 1
            elif arg == "--no-objdiff":
                no_objdiff = True
                i += 1
            elif arg == "--build-path":
                build_path = Path(args[i + 1])
                i += 2
            elif arg == "--config-path":
                config_path = Path(args[i + 1])
                i += 2
            elif arg == "--objdiff-output-path":
                objdiff_output_path = Path(args[i + 1])
                i += 2
            elif arg == "--make-full-disasm-for-code":
                i += 1
            else:
                yamls.append(Path(arg))
                i += 1
        if build_path is None or config_path is None or not yamls:
            raise SystemExit("splat-generate requires --build-path, --config-path, and yaml inputs")
        run_splat_generate(
            config_path=config_path,
            build_path=build_path,
            verbose=verbose,
            no_objdiff=no_objdiff,
            objdiff_output_path=objdiff_output_path,
            make_full_disasm_for_code=True,
            yamls=yamls,
        )
        return 0

    if mode == "merge-objdiff":
        args = sys.argv[2:]
        categories_path: Path | None = None
        output_path: Path | None = None
        fragments: list[Path] = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--categories-path":
                categories_path = Path(args[i + 1])
                i += 2
            elif arg == "--output-path":
                output_path = Path(args[i + 1])
                i += 2
            elif arg == "--verbose":
                i += 1
            else:
                fragments.append(Path(arg))
                i += 1
        if output_path is None or not fragments:
            raise SystemExit("merge-objdiff requires --output-path and fragment inputs")
        merge_objdiff_units(categories_path=categories_path, output_path=output_path, fragments=fragments)
        return 0

    if mode == "split":
        ensure_source_executable(rom_dir, source_executable, config.serial)
        uv_sync()
        split_outputs(config, config_dir, build_dir, include_dir)
        return 0
    if mode != "configure":
        raise SystemExit(f"unknown mode: {mode}")

    ensure_source_executable(rom_dir, source_executable, config.serial)
    c_sources = scan_sources(project_dir / "src", ".c")
    c_units = [analyze_c_source(path, project_dir, build_dir) for path in c_sources]
    c_stems = {path.stem for path in c_sources}
    asm_sources = [
        path for path in scan_asm_sources(config_dir / "asm") if path.stem not in c_stems
    ]
    write_build_ninja(config, c_units, asm_sources)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
