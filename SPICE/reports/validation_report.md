# LIFeling SPICE reconstruction and validation report

## Executive conclusion

The electrical model was reconstructed from the attached KiCad export dated **2026-07-29T20:56:15**, produced by **Eeschema 10.0.1**. The export contains **216 components** and **112 nets**. Connectivity in generated decks is derived from physical pins in that export; intended equations and previous behavioural mappings are not used as connectivity sources.

The static topology audit has **0 blocking failures** and **3 explicit warnings**. No blocking topology failure remains.

Transient execution status: **48 passed**, **0 failed**, **0 not executed**. A non-executed run is not reported as electrical validation.

Static reconstruction tests: **0 passed, 0 failures, 0 errors** (skipped).

> This system validates a SPICE representation. It does not constitute hardware validation, ESD qualification, battery-life certification, sustained-fault survival proof, PCB-parasitic validation, or production test evidence.

## 1. Source and version lock

- Authoritative netlist SHA-256: `d5a0bf3aa70e19a4470710342be6b2e11441efbc97374f23ff95af703fe9eeea`
- Stable source-lock SHA-256: `55df884890c53c1af35b7f03e638c13b9e68e5c5d7e3ac005e109ba13a78201c`
- Full run-manifest SHA-256: `3f0746a8e6198edcea1070234103bbd79e6cfbd6e052a2894bebc786696f99df`
- KiCad source recorded in export: `C:\Users\mjyzi\Documents\GitHub\LIFeling\PCBs\LIFeling\LIFeling.kicad_sch`
- Export date: `2026-07-29T20:56:15`
- KiCad tool: `Eeschema 10.0.1`
- Repository comparison commit: `272b9b74c9f78c5c64ee9d9609b1ea035339ad1e`
- Repository commit date: `2026-07-08T10:47:48Z`
- Attached files newer than repository comparison: **yes**

When attached and repository files differ, the attached netlist controls electrical connectivity. The schematic is a visual cross-check. The earlier Python implementation and historical outputs are comparison material only.

Schematic cross-check: **416 placed symbols**, **0 blocking mismatches**, **0 metadata warnings**. Escaped KiCad property strings are decoded before comparison, so the BT1 simulation-parameter value is compared exactly rather than truncated.

### Source hashes

| File | Type | Bytes | SHA-256 |
|---|---|---:|---|
| `LIFeling(2).net` | authoritative KiCad netlist | 818149 | `d5a0bf3aa70e19a4470710342be6b2e11441efbc97374f23ff95af703fe9eeea` |
| `LIFeling(1).kicad_sch` | latest attached KiCad schematic cross-check | 2117205 | `9971cd95cc7011216b15f5ae127d027145e486473367b6c6d7d025a09745f5dd` |
| `Spice.py` | previous simulator comparison only | 117013 | `ee80d67884d0251fd4be509421c598d7f54c33abc61fb264b8e0f9e031878975` |
| `run_full_validation.ps1` | previous runner comparison only | 21524 | `c4e7164bf972fe5fc2df11760d341ab6fec97b3cfbc8d3f28c87cc4e7528fb34` |
| `1n4148_spice.lib` | provided vendor/cross-vendor model | 1629 | `f48fd3b8722660f0dc06039a58b67a6b6423628b10276128246971aa5b78be47` |
| `lm2901.lib` | provided legacy/unused comparator model | 7521 | `622338a26a2f7cd185f254f7596c729f52e8c8ac69585009a8feae129c8d7296` |
| `MCP6001.txt` | provided official Microchip family model | 5990 | `c510804933f8b3224f7c0b2064c98f7728ec81d3ce2052046a9b754dd8d482bf` |
| `MCP6001_ngspice.lib` | ngspice syntax-normalised copy of official Microchip family model | 6101 | `982f2bf0b7d801135bb665831d4e3c2053b3ff0ff6a19948eabf69fe772ffdd6` |
| `MMBT3904.spice.txt` | provided cross-manufacturer discrete model | 1587 | `49c344a0aaa461869b9a6f7a67e8afc0afbb0050a6b4f7e19e44025b076a6d2d` |
| `BOM.csv` | uploaded supplementary BOM context; not authoritative for connectivity | 17833216 | `657aa5d14b832c269e664859ccc5e4f8da446c86de3a581b27c9f7f8bb221b48` |

## 2. Verified hardware corrections

### U4 uses the corrected TLV7044 PW-14 physical pin order.

**PASS.** All 14 physical pin functions match.

### U5 uses the corrected TLV7044 PW-14 physical pin order.

**PASS.** All 14 physical pin functions match.

### U6 uses the corrected TLV7044 PW-14 physical pin order.

**PASS.** All 14 physical pin functions match.

### MCP6004 physical package pins match the approved package map for U1, U2, U3.

**PASS.** All physical pin functions match.

### TLV9001 physical package pins match the approved package map for U8, U22.

**PASS.** All physical pin functions match.

### TLV9041 physical package pins match the approved package map for U23.

**PASS.** All physical pin functions match.

### TLV7031 physical package pins match the approved package map for U19.

**PASS.** All physical pin functions match.

### TS5A3166 physical package pins match the approved package map for U9, U10, U11, U12, U13, U14, U15, U16, U17, U18, U20.

**PASS.** All physical pin functions match.

### TPS610995 physical package pins match the approved package map for U7.

**PASS.** All physical pin functions match.

### RV4 selector comparator polarity is derived from physical pins and forms the intended five windows.

**PASS.** Physical comparator channels match the one-hot window equations.

### RV4 selects 470 nF, 1 µF, 2.2 µF, 4.7 µF, then 10 µF through U9–U13.

**PASS.** Monotonic physical switch/capacitor chain confirmed.

### Peak_Window is an active-high event pulse generated by U6A and pulled up by R51.

**PASS.** U6A pins: OUT=Peak_Window, IN+=Spike_Pulse, IN-=V_Threshold; R51=['Peak_Window', 'VDD']; U14/U20 controls=[('U14', '4'), ('U20', '4')].

### U23 is the physical TLV9041 stimulus amplifier and all four gain-setting resistors are present.

**PASS.** Electrical topology matches the intended transfer; the output-to-Vm resistor is physically R96, not R97.

### The latest electrical topology uses R96 between V_Stim_Drive and Vm_Int, while the requested design note calls this resistor R97.

**WARNING.** R97 is absent. R96 is 100 kΩ between V_Stim_Drive and Vm_Int; there is no VDD pull-up on V_Stim_Drive.

### U6B is unused and forced into a deterministic state.

**PASS.** INB+=VDD, INB-=GNDREF, OUTB=unconnected-(U6B-OUTB-Pad7)

### The fitted TPS610995DRVR is the fixed 3.6 V variant, not the 3.3 V TPS610994 variant.

**WARNING.** Netlist U7 value=TPS610995DRVR. Portable switching model VSET is locked to 3.6 V; previous 3.3 V behavioural assumptions are rejected.

### REF3020AIDBZR physical DBZ package pins match the official IN=1, OUT=2, GND=3 order.

**PASS.** KiCad mapping: pin1=VDD, pin2=VREF_2V048, pin3=GNDREF.

## 3. Important netlist findings

1. The TLV7044 channel-A correction is present on U4, U5 and U6 and the full physical PW-14 mapping is audited before channel instances are emitted.
2. RV4’s five comparator windows and TS5A3166/capacitor mapping are generated from physical comparator inputs and switch pins. The intended monotonic sequence is confirmed by topology, not hard-coded as a selector outcome.
3. `Peak_Window` is physically active-high: U6A compares `Spike_Pulse` at IN+ against `V_Threshold` at IN−, R51 pulls up the open-drain output, and U14/U20 use that node as an active-high control.
4. U23 is a physical TLV9041 stage with R92–R95 forming the closed-loop network. The transfer is not replaced by a behavioural voltage source.
5. The output-to-`Vm_Int` resistor is **R96 = 100 kΩ** in the attached export. **R97 is absent.** Electrically this is the intended injection resistor, but the designator differs from the requested description.
6. U6B is unused: INB+ is tied to VDD, INB− to GNDREF, and OUTB is unconnected.
7. U7 is `TPS610995DRVR`, which is the fixed 3.6 V member. The prior hard-coded 3.3 V boost assumption is rejected; 3.3 V would correspond to TPS610994.
8. REF3020 KiCad physical pins are pin 1 input, pin 2 output and pin 3 ground. A downloaded TINA macro-model is never instantiated until its actual terminal declaration is inspected and wrapped.

## 4. Model coverage and hierarchy

The default `hybrid` profile uses the supplied official Microchip MCP6001/2/4 family macro-model for all twelve MCP6004 channels and documented portable models for devices whose official packages are not yet installed and smoke-tested. `pin_model_mapping.csv` records every active/discrete physical pin, connected net, wrapper terminal and model terminal. The `vendor` profile is intentionally strict: it fails rather than silently substituting an unapproved model or guessed terminal order.

| Family | References | Selected status | Model/subcircuit | Confidence | Known limitation |
|---|---|---|---|---|---|
| `MCP6004T-I/ST` | U1, U2, U3 | installed vendor/model source | `MCP6001` | high | Inspected .SUBCKT at MCP6001_ngspice.lib:5. |
| `TLV7044PWR` | U4, U5, U6 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `TLV7031DCKR` | U19 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `TLV9001IDBVR` | U22, U8 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `TLV9041IDBVR` | U23 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `TS5A3166DCKR` | U10, U11, U12, U13, U14, U15, U16, U17, U18, U20, U9 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `TPS610995DRVR` | U7 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `REF3020AIDBZR` | U21 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `TPD1E05U06DPYT` | D1, D18, D19 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `BSS138` | Q1, Q3, Q4, Q5, Q6, Q7 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `MMBT3904` | Q2, Q8 | installed comparison model; portable fallback selected | `models\provided\MMBT3904.spice.txt` | medium | Inspected .MODEL DI_MMBT3904 (NPN) at MMBT3904.spice.txt:18. The supplied model manufacturer does not match the ordered/netlist manufacturer and is not instantiated by the hybrid deck. |
| `BAT54WS L9` | D10, D11, D12, D13, D14, D15, D16, D17, D2, D21, D22, D3 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `1N4148WS` | D4, D5, D7 | installed comparison model; portable fallback selected | `1N4148` | medium | Inspected .SUBCKT at 1n4148_spice.lib:14. The supplied model manufacturer does not match the ordered/netlist manufacturer and is not instantiated by the hybrid deck. |
| `RB521S30T1G` | D20, D6, D8 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `19-237/R6GHBHC-A01/2T` | D9 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `CR2032` | BT1 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |
| `ANR3015T2R2M` | L1 | portable fallback | `portable rule` | medium | Official package is not installed/verified; using documented portable model. |

### Explicit approximations remaining in the portable/hybrid profile

- TLV7044 and TLV7031: rail-aware comparator wrappers include open-drain/push-pull topology, quiescent current, finite output resistance, input loading, hysteresis and a propagation-delay pole. They are not substitutes for the official TI model’s complete overdrive and supply dependence.
- TLV9001 and TLV9041: finite open-loop gain, dominant pole, rail clipping, output resistance and quiescent current are represented. Input offset, detailed output-current limiting and every datasheet corner are not fully reproduced.
- TS5A3166: active-high supply-referenced logic, on-resistance, leakage and capacitance are represented. Charge injection, exact powered-off isolation and process corners remain approximate.
- TPS610995: the fallback is a 3.6 V switching macro-model using the physical L1 and output capacitors. It is not an official efficiency or control-loop sign-off model. The official unencrypted transient package should be smoke-tested separately before replacing it.
- REF3020: startup, dropout, finite source resistance, source-only behaviour and quiescent current are approximated. Noise and complete line/load-regulation surfaces are not sign-off quality.
- TPD1E05U06: capacitance, leakage, breakdown and dynamic resistance are datasheet-derived. This cannot prove IEC ESD robustness or sustained overvoltage survival.
- CR2032: the actual cell manufacturer is unspecified; both fixed source-resistance sweeps and a dynamic equivalent are supported, but battery-life predictions are provisional.
- L1 and MLCCs: DCR/ESR/ESL, tolerance, leakage and conservative DC-bias derating are included. Exact vendor nonlinear curves are not embedded unless supplied.
- BSS138, MMBT3904, BAT54WS, 1N4148WS, RB521S30 and the RGB LED use explicit vendor-mismatch or datasheet-derived models where an exact ordered-part model was unavailable.

## 5. Validation test matrix

| Test | Purpose | Acceptance evidence | Hardware claim allowed? |
|---|---|---|---|
| Full operating transient | Integrate, threshold, AP, peak, reset, adaptation, synapse, outputs | Numeric edge counts, rail ranges, periods and trace CSV | No; functional SPICE correlation only |
| RV4 selector sweep | Confirm one-hot physical comparator/switch selection over five regions | S0–S4 states and effective membrane transient ordering | No |
| U23 stimulus transfer sweep | Confirm gain, polarity, clipping, settling and injection current emerge from U23/R92–R96 | `V_Stim_Drive - [Vm_Int + 0.5(V_Stim_Cmd−VREF)]` error inside linear region | No |
| Peak-window event | Confirm active-high `Peak_Window`, U14/U20 closure and positive external pulse | event timing and polarity | No |
| Cold and low-battery startup | Check reference, comparator and boost startup under source impedance | startup time, rail sag, failure mode | No battery-life or safety claim |
| Synapse sign and decay sweeps | Confirm midpoint neutrality, excitatory/inhibitory polarity and RV5 decay | differential Vm response and state decay | No |
| Tolerance/temperature Monte Carlo | Identify functional margins and fragile parameter combinations | percentile distributions and failing seeds | No production yield claim without measured distributions |

## 6. Execution record

| Test | Status | ngspice | Message |
|---|---|---|---|
| `01_full_operating` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `02_peak_window_active_high` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `03_stimulus_transfer_0V` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `04_stimulus_transfer_1V024` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `05_stimulus_transfer_2V048` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `06_cold_start_dynamic_battery` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `07_low_battery_high_impedance` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `08_synapse_midpoint` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `09_power_switch_off` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `10_vm_ext_loaded_10k` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `11_spike_out_loaded_10k` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `20_rv4_selector_region_1` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `20_rv4_selector_region_2` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `20_rv4_selector_region_3` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `20_rv4_selector_region_4` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `20_rv4_selector_region_5` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `30_rv1_leak_1` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `30_rv1_leak_2` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `30_rv1_leak_3` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `31_rv2_leak_rate_1` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `31_rv2_leak_rate_2` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `31_rv2_leak_rate_3` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `32_rv3_adaptation_1` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `32_rv3_adaptation_2` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `32_rv3_adaptation_3` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `33_rv5_synapse_decay_1` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `33_rv5_synapse_decay_2` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `33_rv5_synapse_decay_3` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv6_syn1_low` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv6_syn1_mid` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv6_syn1_high` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv7_syn2_low` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv7_syn2_mid` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv7_syn2_high` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv8_syn3_low` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv8_syn3_mid` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv8_syn3_high` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv9_syn4_low` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv9_syn4_mid` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `40_rv9_syn4_high` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `50_temperature_m20p0C` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `50_temperature_25p0C` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `50_temperature_60p0C` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `60_tolerance_seed_1` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `60_tolerance_seed_2` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `60_tolerance_seed_3` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `60_tolerance_seed_4` | **passed** | ngspice-46 : Circuit level simulation program | completed |
| `60_tolerance_seed_5` | **passed** | ngspice-46 : Circuit level simulation program | completed |

## 7. Build gates

The build fails when any new active component lacks a registry rule, any functional reference/net is absent, any required installed model is missing in strict-vendor mode, a named subcircuit cannot be found, a locked terminal count/order disagrees, or any exported reference is neither instantiated nor deliberately classified as terminal/mechanical.

## 8. Required bench correlation before production

The final PCB should be correlated at minimum for VDD/boost startup, 2.048 V and 1.024 V references, RV4 one-hot selection, U23 gain/clipping, AP/Peak/Reset timing, Spike_Out levels into representative loads, synaptic midpoint neutrality, quiescent current, CR2032 pulse sag, output protection under realistic classroom faults, and temperature/tolerance extremes. Those measurements should be stored beside the SPICE CSVs with board serial number, instruments, probe points and firmware/test conditions.
