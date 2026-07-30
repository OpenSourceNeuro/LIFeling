# Compatibility patch v4 — ngspice 46 parser fixes

- Replaced unsupported `mod()` in the portable TPS610995 oscillator with a standard parameterised `PULSE` sawtooth source.
- Preserved the official Microchip file unchanged and added `models/compatible/MCP6001_ngspice.lib`, translating only `R61 ... TC a b` to ngspice `TC=a,b`.
- Decks now include the compatibility copy.
- Explicit invalid ngspice paths now fail rather than silently falling back to another executable.
- Version reporting now extracts `ngspice-46` instead of the banner delimiter.
- Added three regression tests for these fixes.

# LIFeling SPICE reconstruction — release notes

Version: `2026.07.29-reconstruction-3`  
Authoritative netlist SHA-256: `d5a0bf3aa70e19a4470710342be6b2e11441efbc97374f23ff95af703fe9eeea`  
Stable source-lock SHA-256: `3d646856dcfc6cf83bdad7bc2d7c16ead7ec400a898091fd7690fa8e39884344`  
Full run-manifest SHA-256: `87eb637357a1027260e2ffd1ce82e50840871a28e3e1585e6bfe0e2e5fd3a9e3`

## Delivered state

- The electrical model is rebuilt from the attached KiCad netlist exported on 2026-07-29 at 20:56:15 by Eeschema 10.0.1.
- All 216 exported references and 112 nets are inventoried; there are no silent omissions or unresolved references in the hybrid profile.
- All package-pin and requested topology gates pass. The static test suite passes 20 tests with no failures or errors.
- 48 relocatable, deterministic ngspice decks are generated. Repeated generation with the same source lock produces identical deck filenames and SHA-256 hashes.
- ngspice was not installed in the execution environment, so the 48 transient decks are marked `not_executed`. No numerical or hardware-validation claim is made from them.

## Explicit warnings

1. The attached export uses `R96 = 100 kΩ` between `V_Stim_Drive` and `Vm_Int`; `R97` is absent.
2. `TPS610995DRVR` is the fixed 3.6 V variant. The old 3.3 V boost assumption is rejected.
3. REF3020 physical DBZ pins are verified, but the official TINA macro-model terminal declaration remains gated until its downloaded file is inspected and wrapped.

## Model policy

The default hybrid profile uses the provided official Microchip MCP6001/2/4 macro-model for U1-U3. Other devices use documented portable models until official packages are downloaded, terminal declarations are inspected and ngspice smoke tests pass. The strict vendor profile fails closed instead of guessing pin order or silently substituting a fallback.

## Run on Windows

```powershell
.\run_full_validation.ps1 -Profile hybrid -NgspiceBinary "C:\Spice64\bin\ngspice.exe"
```

Review `reports/validation_report.md`, `reports/connectivity_audit.md`, `reports/model_manifest.csv` and `reports/validation_verdict.md` after execution.
