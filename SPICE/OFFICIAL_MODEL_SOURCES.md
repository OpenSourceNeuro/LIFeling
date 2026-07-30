# Official model-source register

The machine-readable authority is `model_registry.json`; this document is a reader-facing index. Downloaded packages are not trusted merely because the filename matches. The workflow records the checksum, inspects every actual `.SUBCKT` declaration, requires an approved wrapper terminal order, and requires an ngspice smoke test before strict-vendor use.

| Device | Official source/package | Intended use |
|---|---|---|
| MCP6004T-I/ST | Microchip AN1297 MCP6001/2/4 PSpice macro-model | Supplied `MCP6001.txt`; one instance per physical MCP6004 channel. |
| TLV7044PWR | TI `SLVMDH0.ZIP` | Inspect whether package is single/quad channel; preserve open-drain outputs and physical PW-14 mapping. |
| TLV7031DCKR | TI `SLVMDG0A.ZIP` | Push-pull comparator; DCK physical wrapper. |
| TLV9001IDBVR | TI TLV900x PSpice package (`SBOMAL2D.ZIP` currently identified) | Verify normal DBV pinout and channel extraction; do not substitute the U-pinout variant. |
| TLV9041IDBVR | TI `SBOMB62B.ZIP` | Verify normal TLV9041 DBV pinout and model declaration. |
| TS5A3166DCKR | TI `SCDJ032.ZIP` HSPICE model | Convert only after syntax and active-high control smoke tests. |
| TPS610995DRVR | TI `SLVMCO7A.ZIP` unencrypted transient model | Exact fixed 3.6 V variant; verify DRV terminal declaration and external L/C use. |
| REF3020AIDBZR | TI `SBVM736A.TSM` | Physical DBZ pins are verified; TINA terminal order and ngspice conversion remain gated. |
| TPD1E05U06DPYT | Exact catalog part exposes IBIS/S-parameter resources; TI Q1 variant has `SLVME60.ZIP` | Default remains a clearly labelled datasheet-derived transient clamp model. |

Discrete exact-vendor models remain conditional on the actual ordered manufacturer. The model manifest distinguishes exact matches, cross-manufacturer comparison files and datasheet-derived fallbacks.

## Strict-vendor adapter contract

After terminal orders are approved, create `models/vendor/vendor_adapters.lib` from the provided template. The strict deck includes this library instead of the portable library. The build fails if any required wrapper subcircuit or exact-device model card is missing. This prevents a nominal `vendor` profile from silently continuing to use portable models.
