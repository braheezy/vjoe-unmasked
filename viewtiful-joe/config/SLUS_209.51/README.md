This directory is the initial scaffold for the USA executable `SLUS_209.51`.

What is real here:
- `SLUS_209.51.yaml`: starting Splat config for Viewtiful Joe 1
- `splat.config.yaml`: generic PS2/Splat options
- `symbol_addrs.txt`: currently empty placeholder
- `categories.json`: generic report category metadata
- `checksum.sha`: SHA-256 of the target executable bytes

What is intentionally empty for now:
- `asm/`: no split output has been generated yet
- `linkers/`: no GNU ld script has been generated yet
- `rom/`: local symlink/output dir placeholder only

Important:
- This scaffold is not wired into the default `ninja` build yet.
- The copied VJ2 layout was removed on purpose.
- The executable layout, entry point, section map, and `gp_value` for
  `SLUS_209.51` still need to be determined before setup/splitting.
