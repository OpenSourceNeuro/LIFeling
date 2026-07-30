# Repository migration guide

This folder is a replacement for the current `SPICE/` validation implementation, not a patch to the older behavioural generator.

## Recommended integration

1. Create a branch from the repository commit recorded in `reports/repository_snapshot.json`.
2. Preserve the current `SPICE/` directory as an archive or compare-only tag.
3. Copy this rebuild into `SPICE/`.
4. Keep `sources/LIFeling.net` synchronized with `PCBs/LIFeling/LIFeling.net`, or invoke `Spice.py` with `--netlist` pointing directly to the current export.
5. Run `run_full_validation.ps1 -GenerateOnly` first. Review `reports/connectivity_audit.md`, `reports/component_model_coverage.csv`, and `reports/model_manifest.csv`.
6. Install ngspice and run the complete suite without `-GenerateOnly`.
7. Do not select the strict `vendor` profile until downloaded model declarations and wrappers are reviewed and smoke-tested.
8. Commit generated reports only if repository policy intentionally tracks simulation artifacts. Generated transient CSV/PNG data can be large.

## Deliberate breaking changes

- The old stage/backend compatibility flags are removed.
- Electrical connectivity is never recreated from historical block equations.
- Missing active model rules and silent component omissions are fatal.
- Vendor models are never activated from a package filename alone.
- `TPS610995DRVR` is treated as the 3.6 V fixed-output part.
- The latest netlist's output-injection resistor is `R96`; no fictitious `R97` is created.

## Suggested repository layout

```text
SPICE/
├─ Spice.py
├─ run_full_validation.ps1
├─ lifeling_spice/
├─ models/
│  ├─ portable/
│  ├─ provided/
│  ├─ downloads/       # normally ignored
│  └─ vendor/          # normally ignored unless redistribution is permitted
├─ sources/
├─ tests/
├─ generated/          # generated decks and simulation outputs
└─ reports/
```
