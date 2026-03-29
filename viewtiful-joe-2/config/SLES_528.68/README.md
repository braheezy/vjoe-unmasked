- `SLES_528.68.yaml`: Main Splat segmentation file

  This is where you decide:
  - which regions are `c`
  - which regions are `asm`
  - how coarse or fine the text/data splits are
  - which data sections exist

- `splat.config.yaml`: Global Splat options for this target.

  Controls the overall split behavior and binary assumptions used by Splat.

- `symbol_addrs.txt`: Known symbols for this executable.

  Used by Splat and generally useful for reverse engineering. This is also the symbol import source you would care about when loading the target in Ghidra.

- `categories.json`: Progress categories for objdiff/decomp reporting.

  This is metadata for reports, not build logic.

- `checksum.sha`: Expected checksum for the rebuilt ROM/executable bytes.

  The final `ninja` verification step compares against this.
