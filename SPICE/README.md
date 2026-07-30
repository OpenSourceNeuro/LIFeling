# LIFeling physical-netlist SPICE validation system

This reconstruction replaces the earlier block-level behavioural generator with a physical-pin-driven workflow for the attached KiCad export dated **2026-07-29 20:56:15**.

## Core rule

`sources/LIFeling.net` is authoritative for references, values, physical pins and nets. The schematic is retained as a visual cross-check. No intended equation or historical mapping is allowed to create electrical connectivity independently of the export.

## What the system produces

- `reports/source_manifest.json` and `.csv`: source sizes, SHA-256 hashes, export metadata, repository comparison commit and execution environment.
- `reports/source_lock.json`: stable source-only fingerprint payload used for reproducible deck names; volatile timestamps and host paths are excluded.
- `reports/netlist_inventory.csv`: one row per physical component pin, with manufacturer, part, net, functional block and model mapping.
- `reports/component_model_coverage.csv`: one row per reference; no silent omissions are permitted.
- `reports/model_manifest.json` and `.csv`: exact part/manufacturer, source/package, model revision/date, actual installed declaration, wrapper requirement, compatibility gate, checksum, licence status and limitations.
- `reports/connectivity_audit.md`: package-pin and functional-topology audit.
- `reports/schematic_crosscheck.md`: every exported reference and footprint checked against placed schematic symbols.
- `generated/*.cir`: reproducible ngspice decks with source hashes embedded in comments.
- `generated/*.csv`, diagnostics and logs after execution.
- `reports/validation_report.md`: reader-facing result and limitation report.
- `OFFICIAL_MODEL_SOURCES.md`: official-package register and activation policy.
- `REPOSITORY_MIGRATION.md`: replacement/integration instructions for the GitHub repository.
- `THIRD_PARTY_MODELS.md`: licence and manufacturer-mismatch notes.

## Profiles

- `hybrid` (default): supplied official Microchip MCP6001/2/4 macro-model plus explicit portable models for uninstalled/unapproved device packages.
- `portable`: same deterministic topology with only locally inspectable model sources.
- `vendor`: strict gate. It refuses to run until every required official package is installed, its actual declaration is inspected, an adapter terminal order is approved, and `models/vendor/vendor_adapters.lib` exposes all stable wrapper interfaces. The vendor deck includes that adapter library instead of the portable library; it never guesses a model terminal order.

## Commands

From this folder. `Spice.py` reruns the packaged static reconstruction tests automatically unless `--skip-static-tests` is supplied:

```powershell
python -m unittest discover -s tests -v
python Spice.py generate --suite
python Spice.py run --suite --ngspice-binary auto
```

On Windows, the complete runner is:

```powershell
.\run_full_validation.ps1 -Profile hybrid -NgspiceBinary "C:\Spice64\bin\ngspice.exe"
```

Generate without simulation:

```powershell
.\run_full_validation.ps1 -GenerateOnly
```

Inspect/download current official model packages from the URLs locked in `model_registry.json`:

```powershell
python Spice.py fetch-models
```

Downloaded TI packages are placed under `models/downloads/` and extracted under `models/vendor/`. The downloader records checksums and every actual `.SUBCKT` declaration, but does not approve or use a newly discovered terminal order automatically.

## Important authoritative findings

- Corrected TLV7044 PW-14 physical pins are present on U4, U5 and U6.
- RV4 physically selects 470 nF, 1 µF, 2.2 µF, 4.7 µF and 10 µF through U9–U13.
- `Peak_Window` is active-high and controls U14 and U20.
- U23 is physically wired as the TLV9041 stimulus amplifier; its transfer emerges from U23 and R92–R96.
- The attached export uses **R96**, not R97, as the 100 kΩ `V_Stim_Drive` to `Vm_Int` resistor. R97 is absent.
- U6B has INB+ at VDD, INB− at GNDREF and an unconnected output.
- `TPS610995DRVR` is the fixed **3.6 V** variant; the old 3.3 V boost assumption is not retained.
- U21 matches the official REF3020 DBZ physical order: pin 1 IN, pin 2 OUT, pin 3 GND; vendor macro-model terminal order remains separately gated.

## Validation boundary

Passing simulations show that a documented SPICE representation behaves as specified under the model assumptions. They do not prove hardware operation, ESD survival, sustained classroom-fault tolerance, battery life, PCB parasitics, EMC, production yield or safety. Bench correlation requirements are listed in `reports/validation_report.md`.
