# vjoe-unmasked

Decompilation project for the PlayStation 2 release of Viewtiful Joe 2.

## Setup

1. From your legally-owned Viewtiful Joe 2 ISO, copy the `SLES_528.68` file to `rom/SLES_528.68`.

2. Run one-time setup:

```sh
ninja setup
```

That bootstraps the Python environment, toolchain, ROM symlink, split asm/data
outputs, and generated GNU linker script.

3. (Re-)Build with Ninja:

```sh
ninja
```

## Common targets

- `ninja`
  Normal build, link, and final match verification.
- `ninja setup`
  One-time setup after cloning. Syncs Python deps, checks toolchain, and runs
  the initial split.
- `ninja configure`
  Regenerates `build.ninja`.
- `ninja split`
  Reruns Splat and regenerates split outputs after YAML/config changes.
- `ninja report`
  Generates the objdiff report JSON.
- `ninja diff`
  Reruns only the final ROM verification step.
- `ninja clean`
  Removes generated build and split outputs.
