# LIFeling SPICE simulation

This folder contains the Python/ngspice simulation workflow for the Vm-relevant part of the **LIFeling** analog neuron circuit.

The main simulation file is:

```text
Spice.py
```

`Spice.py` generates a SPICE deck, runs a transient simulation, saves compact trace data, creates plots, and writes a text report with validation diagnostics.

The model is a **controlled behavioural SPICE model**. It is not a raw KiCad-exported netlist. Its purpose is to make the important LIFeling circuit blocks easy to simulate, inspect, and validate while keeping the generated SPICE deck readable.

---

## 1. What this simulation is for

The simulation is intended to answer practical circuit questions such as:

- Does the membrane voltage integrate and leak as expected?
- Does the threshold comparator trigger at the intended point?
- Does the AP / spike pulse path fire correctly?
- Does the peak/reset sequence recover, or does it latch?
- Does the external live output `Vm_Ext` show a usable neuron-like trace?
- Does the adaptation path affect firing over time?
- Do synaptic inputs perturb the membrane in the expected direction?
- Does the buffered `V_Leak_Ref_Max` reference remain stable when RV1 and RV6-RV9 are connected?
- How do RV1, RV2, RV3, RV4, RV5, RV6, RV7, RV8, and RV9 affect behaviour?

The most important user-facing trace is:

```text
Vm_Ext
```

`Vm_Ext` is the modelled physical/live analog output. `Vm_Int` is still saved because it is the internal membrane computation node, but it is not the final output that a user would normally probe.

---

## 2. Model fidelity and limitations

This model is best used for **functional validation**, debugging, and design exploration. It is not intended to replace final analogue verification against the PCB, oscilloscope captures, and component-level measurements.

Important simplifications:

| Area | How it is represented |
|---|---|
| Op-amps | Default mode uses robust behavioural/follower approximations. Vendor models are optional. |
| Comparators | Default mode uses an open-drain behavioural comparator approximation. |
| TS5A3166 switches | Represented by idealised switch models with finite on-resistance. |
| Coin-cell supply | Optional simplified `VBAT_RAW -> RBAT -> VDD` model with local decoupling. |
| RV4 capacitor selection | Represented as an idealised membrane-capacitor selector. |
| RGB LEDs and visual indicators | Omitted to keep the Vm model focused. |
| Boost converter / full power front end | Not modelled in detail. |
| PCB parasitics | Not modelled except for selected explicit capacitors/resistors. |

The default fallback models are intentionally stable and readable. Use `--strict-vendor` only when the required vendor model files are present and their pin order has been checked.

---

## 3. Circuit blocks currently modelled

| Circuit block | Modelled purpose |
|---|---|
| Supply rail | Ideal `VDD` or simplified coin-cell model `VBAT_RAW -> RBAT -> VDD`, with local decoupling. |
| `V_Leak_Ref_Max` reference | R4/R5 raw divider followed by U2A buffer. The buffered node feeds downstream reference uses. |
| RV1 / leak reference | Sets `/V_Leak_ref`, then U1A buffers it to `V_Leak`. |
| Passive membrane | RV2 leak path, selected membrane capacitor, `Vm_Int`, and clamp approximations. |
| External stimulus path | `Stimulus_Ext` through the U19B closed-loop equivalent into `Vm_Int`. |
| Threshold detection | U6B comparator, AP generation, `/Rising_AP`, `Spike_Pulse`, and negative clamp. |
| Peak injection | R8/R9 peak reference, U2C buffer, R49/U14 peak switch into `Vm_Int`. |
| Reset window | U6A/U6C timing, peak/reset windows, reset-current injection chain. |
| Spike output | U6D/R81/R82/D18 approximation for `Spike_Out`. |
| Adaptation | U1B/U1C/U1D, `/Vkick`, `Vw`, and Q2 adaptation current sink. |
| Synaptic inputs | Syn1-Syn4 input clamps, switches, set voltages, RV5 decay, and `V_Syn_State`. |
| Live Vm output | `Vm_Int -> R90/C38 Vm_Display_In`, optional display-spike charge through U20/R91, then U8/R1/C14 to `Vm_Ext`. |
| Component tolerances | Optional deterministic random resistor/capacitor/pot variation. |

---

## 4. Current reference and Vm output paths

### 4.1 Buffered leak reference

The current model represents the updated hardware reference path:

```text
R4/R5 -> V_Leak_Ref_Max_Raw -> U2A buffer -> V_Leak_Ref_Max
```

The buffered `V_Leak_Ref_Max` node is then used as the high-side reference for RV1 and, when synaptic circuitry is enabled, for RV6-RV9.

This matters because RV6-RV9 should not load the raw R4/R5 divider directly during synaptic tests.

### 4.2 Internal membrane vs live output

The model distinguishes between two membrane-related traces:

| Trace | Meaning |
|---|---|
| `Vm_Int` | Internal membrane computation node. |
| `Vm_Ext` | External/live analog output after display-spike synthesis and the U8 output path. |

The live-output path is:

```text
Vm_Int
  -> R90/C38 -> Vm_Display_In
  -> U8/R1/C14 -> Vm_Ext
```

In `threshold_reset` and `threshold_reset_adapt` stages, a short display-spike charge is also injected into `Vm_Display_In` through:

```text
V_Peak_Drive -> R91 -> U20 -> Vm_Display_In
```

This means `Vm_Ext` can show a more visible spike-like output while `Vm_Int` remains the internal LIF computation node.

---

## 5. Folder layout

Expected folder structure:

```text
SPICE/
├─ Spice.py
├─ README.md
├─ run_full_validation.ps1
├─ models/
│  ├─ MCP6001.txt
│  ├─ MMBT3904.spice.txt
│  ├─ 1n4148_spice.lib
│  ├─ TLV7044.lib              optional / required only for --strict-vendor
│  ├─ BSS138.lib               optional / required only for --strict-vendor
│  └─ RB521S30.lib             optional / required only for --strict-vendor
├─ LIFeling_pyspice_output/    generated simulation decks, logs, CSV files, reports, and PNG plots
└─ LIFeling_validation_logs/   validation-suite console summaries, when committed
```

`LIFeling_pyspice_output/` is created automatically when `Spice.py` runs. It contains generated SPICE decks, CSV traces, PNG plots, ngspice logs, and text reports.

`run_full_validation.ps1` is the current validation-suite entry point. It runs a practical battery of syntax, threshold/reset, Vm output, cold-start, synapse, stimulus, and RV behaviour checks. Some comments or default path names inside older versions of that script may still contain legacy Spiky wording; the README uses the current LIFeling project naming.

---

## 6. Requirements

### 6.1 Required for normal use

You need:

1. Python 3.
2. The Python packages used by the script:

```powershell
pip install numpy pandas matplotlib
```

3. ngspice installed and available either on the system `PATH` or through an explicit path.

The recommended backend is:

```text
--backend ngspice-cli
```

### 6.2 Optional PySpice backend

`Spice.py` also contains a PySpice backend:

```text
--backend pyspice
```

This is optional. For most Windows/PyCharm workflows, the command-line ngspice backend is simpler and more robust.

### 6.3 Optional vendor models

Normal runs use internal fallback models. Vendor model files are only required when using:

```text
--strict-vendor
```

Before using strict-vendor mode, confirm that all expected model files exist in `SPICE/models/` and that the wrapper pin orders match the vendor `.SUBCKT` definitions.

---

## 7. ngspice path setup

The script can search automatically:

```powershell
--ngspice-binary auto
```

You can also pass the full path explicitly. On Windows, prefer quoting the path and using either escaped backslashes or forward slashes:

```powershell
--ngspice-binary "./Spice64/bin/ngspice.exe"
```

or:

```powershell
--ngspice-binary ".\Spice64\bin\ngspice.exe"
```

You can also define an environment variable named `NGSPICE_BINARY` pointing to `ngspice.exe`.

---

## 8. Quick start

Open a terminal in the `SPICE` folder.

Check that you are in the correct folder:

```powershell
dir
```

You should see at least:

```text
Spice.py
README.md
```

### 8.1 Syntax check

This only checks that Python can parse the script:

```powershell
.\.venv\Scripts\python.exe -m py_compile .\Spice.py
```

No output means the syntax check passed.

### 8.2 Recommended first simulation

Run a complete LIF path without synaptic inputs:

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set core --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --tstop 1.5 --tstep 1u --maxstep 1u
```

This is the recommended first check because it includes the passive membrane, threshold, reset, peak injection, adaptation, supply model, and live output.

### 8.3 Same run with debug traces

Use debug traces when something looks wrong:

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set debug --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --tstop 500m --tstep 1u --maxstep 1u
```

### 8.4 Full LIF with all synaptic inputs enabled

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set core --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --syn-all-enable --rv5 0.5 --rv6 0.5 --rv7 0.5 --rv8 0.5 --rv9 0.5 --syn1-delay 150m --syn2-delay 180m --syn3-delay 210m --syn4-delay 240m --syn1-width 5m --syn2-width 5m --syn3-width 5m --syn4-width 5m --tstop 1.5 --tstep 1u --maxstep 1u
```

### 8.5 Stimulus path check

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set debug --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --stim-dc 0.2 --tstop 500m --tstep 1u --maxstep 1u
```

### 8.6 Cold-start stress test

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set core --supply-mode coin --vbat 3 --rbat 50 --startup-mode cold --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --tstop 1.5 --tstep 1u --maxstep 1u
```

---

## 9. Simulation stages

The `--stage` option controls how much of the circuit is included.

| Stage | Included blocks | Main use |
|---|---|---|
| `passive` | Supply/reference path, leak, membrane capacitor, `Vm_Int`, `Vm_Ext` output path without reset/peak switching. | Passive leak and charging checks. |
| `threshold` | Passive stage plus threshold comparator and AP/spike-pulse generation. | Threshold logic checks. |
| `threshold_reset` | Threshold stage plus peak injection, reset window, reset current, and `Spike_Out`. | Spike/reset behaviour without adaptation. |
| `threshold_reset_adapt` | Full model: reset, adaptation, optional stimulus, optional synapses. | Main operating mode. |

Most project checks should use:

```text
--stage threshold_reset_adapt
```

---

## 10. Trace sets

### 10.1 Core trace set

Use:

```text
--trace-set core
```

for normal runs. Core traces are intended to keep CSV files and plots readable.

Typical core traces include:

```text
Vm_Ext
Vm_Int
V_Leak
VDD              when using coin supply
V_Threshold
AP
Spike_Pulse
Spike_Out
Peak_Window
Reset_Window
Vw
Vw_buff
```

When synapses are enabled, core traces also include:

```text
V_Syn_State
Syn1_Spike / V_Syn1_Set
Syn2_Spike / V_Syn2_Set
Syn3_Spike / V_Syn3_Set
Syn4_Spike / V_Syn4_Set
```

### 10.2 Debug trace set

Use:

```text
--trace-set debug
```

when you need internal reference and control nodes.

Debug traces can include:

```text
V_Leak_Ref_Max_Raw
V_Leak_Ref_Max
V_Peak_Ref
V_Peak_Drive
Peak injection switch node
Reset timer/reference nodes
Reset injection enable/gate nodes
U1B adaptation output
Stimulus amplifier internal nodes
V_Syn_Drive
RV5 decay node
```

---

## 11. Main command-line options

### 11.1 Power options

| Option | Meaning |
|---|---|
| `--supply-mode ideal` | Perfect voltage source on `VDD`. Best for isolating circuit logic from supply sag. |
| `--supply-mode coin` | Battery model: `VBAT_RAW -> RBAT -> VDD`. Best for realistic stress checks. |
| `--vdd 3` | Ideal supply voltage when using `--supply-mode ideal`. |
| `--vbat 3` | Battery open-circuit/source voltage when using `--supply-mode coin`. |
| `--rbat 50` | Battery/internal resistance in ohms when using `--supply-mode coin`. |
| `--cdec-local` | Local bypass capacitance. |
| `--cdec-bulk` | Board-level bulk capacitance. |
| `--cdec-reservoir` | Larger reservoir capacitance. |
| `--cdec-esr` | ESR applied to decoupling capacitors. |

### 11.2 Startup options

| Option | Meaning |
|---|---|
| `--startup-mode operating` | Starts VDD capacitors and reset timer precharged. Best for normal behaviour. |
| `--startup-mode cold` | Starts VDD capacitors, reset timer, and Vm from cold initial conditions. Best for power-on tests. |
| `--ignore-start-ms 20` | Ignores the first 20 ms for event counts and VDD sag diagnostics. |
| `--cold-vm-initial 0` | Vm initial condition used only in cold-start mode. |

### 11.3 Potentiometers

All RV values are fractions from 0 to 1.

| Option | Circuit meaning |
|---|---|
| `--rv1` | Leak reference set point. |
| `--rv2` | Leak conductance / membrane leak rate. |
| `--rv3` | Adaptation strength/decay path control. |
| `--rv4` | Idealised membrane capacitance selector when `--cmem-mode rv4` is used. |
| `--rv5` | Synaptic-state decay back toward `V_Leak`. |
| `--rv6` | Synapse 1 set voltage. |
| `--rv7` | Synapse 2 set voltage. |
| `--rv8` | Synapse 3 set voltage. |
| `--rv9` | Synapse 4 set voltage. |

Examples:

```text
--rv1 0.7
--rv2 0.5
--rv4 0.3
--rv9 1.0
```

### 11.4 Membrane capacitance options

Use RV4-style selection:

```text
--cmem-mode rv4 --rv4 0.3
```

or manually force a capacitance:

```text
--cmem-mode manual --cmem 2.2u
```

Supported SPICE suffix examples:

```text
470n
1u
2.2u
4.7u
10u
```

### 11.5 Time options

| Option | Meaning |
|---|---|
| `--tstop 1.5` | Simulate for 1.5 seconds. |
| `--tstep 1u` | Requested output time step. |
| `--maxstep 1u` | Maximum internal ngspice step. Smaller values are slower but more precise. |

SPICE suffixes:

```text
m = milli = 1e-3
u = micro = 1e-6
n = nano  = 1e-9
```

Examples:

```text
150m = 150 ms
1u   = 1 microsecond
```

### 11.6 Synaptic options

| Option | Meaning |
|---|---|
| `--syn1-enable` | Enable synapse 1. |
| `--syn2-enable` | Enable synapse 2. |
| `--syn3-enable` | Enable synapse 3. |
| `--syn4-enable` | Enable synapse 4. |
| `--syn-all-enable` | Enable all four synapses. |
| `--syn-amp` | Synaptic input pulse high voltage. |
| `--syn1-delay`, `--syn1-width`, `--syn1-period` | Synapse 1 pulse timing. Equivalent options exist for synapses 2-4. |
| `--syn-ref-mode schematic` | Current schematic behaviour: RV6-RV9 use buffered `V_Leak_Ref_Max`. |
| `--syn-ref-mode legacy_direct` | Comparison mode: RV6-RV9 use raw `V_Leak_Ref_Max_Raw`. |

For normal use, keep:

```text
--syn-ref-mode schematic
```

`buffered` is accepted as a deprecated alias of the schematic behaviour.

### 11.7 Tolerance options

The model can apply deterministic random tolerances:

```powershell
--tol-mode random --tol-seed 1 --res-tol-pct 1 --cap-tol-pct 10 --pot-tol-pct 5
```

Tolerance mode is useful for sensitivity checks. Because the randomisation is deterministic for a given seed, runs can be repeated exactly.

---

## 12. Generated files

Each normal run writes files into:

```text
LIFeling_pyspice_output/
```

Typical files:

| File pattern | Meaning |
|---|---|
| `LIFeling_vm_<suffix>.cir` | Generated SPICE deck. Useful for checking the exact ngspice input. |
| `LIFeling_vm_<suffix>.csv` | Compact saved traces used for plotting and later analysis. |
| `LIFeling_vm_<suffix>.png` | Multi-trace plot of all saved traces. |
| `LIFeling_vm_<suffix>_vmint_vmext.png` | Clean comparison plot of `Vm_Int` and `Vm_Ext`. |
| `LIFeling_vm_<suffix>_results.txt` | Text report containing configuration, paths, trace list, min/max/end values, event counts, reset timing, and VDD sag. |
| `LIFeling_vm_<suffix>.ngspice.log` | Raw ngspice log. Check this first when a run fails. |

The `<suffix>` is intentionally compact and includes a short hash so different simulation configurations do not overwrite each other.

Note: the committed example PNGs in this repository may still use the old `spiky_vm_...` prefix. Current versions of `Spice.py` write new normal-run files as `LIFeling_vm_...`.

---

## 13. Example plots from `LIFeling_pyspice_output/`

The repository contains committed PNG examples in:

```text
SPICE/LIFeling_pyspice_output/
```

The example plot files below were generated before the final filename-prefix rename, so their filenames still begin with `spiky_vm_...`. They are still valid examples of the LIFeling SPICE output folder. Current versions of `Spice.py` write new outputs with the `LIFeling_vm_...` prefix.

### 13.1 Baseline LIF output: `Vm_Int` vs `Vm_Ext`

This is the cleanest first plot to show in the README because it compares the internal membrane node with the external/live output path.

![Baseline LIFeling Vm_Int and Vm_Ext comparison](LIFeling_pyspice_output/spiky_vm_trac_r0p7-0p5-0p8_m0p3c1u_b3r50_op_i20_t1p5_h6326f65a_vmint_vmext.png)

Corresponding full multi-trace diagnostic plot:

![Baseline LIFeling full diagnostic traces](LIFeling_pyspice_output/spiky_vm_trac_r0p7-0p5-0p8_m0p3c1u_b3r50_op_i20_t1p5_h6326f65a.png)

This example corresponds to a full `threshold_reset_adapt` run using RV1/RV2/RV3 = `0.7/0.5/0.8`, RV4-selected membrane capacitance, a simplified 3 V coin-cell supply with 50 ohm source resistance, operating startup mode, and 20 ms ignored startup.

### 13.2 Debug trace example

This plot uses the debug trace set and is useful when diagnosing reset, peak injection, reference, or internal control nodes.

![LIFeling debug trace example](LIFeling_pyspice_output/spiky_vm_trad_r0p7-0p5-0p8_m0p3c1u_b3r50_op_i20_t500m_h87feec65.png)

Use this type of plot when the baseline `Vm_Ext` output looks wrong and you need to inspect internal nodes.

### 13.3 Synaptic response example

This example enables all four synaptic inputs with staggered pulse timings.

![LIFeling synaptic response diagnostic traces](LIFeling_pyspice_output/spiky_vm_trac_r0p7-0p5-0p8_m0p3c1u_b3r50_op_i20_s1234k0p5g0p5_d150m-180m-210m-240m_w5m_t1p5_h2c8e40ea.png)

Corresponding `Vm_Int` / `Vm_Ext` comparison:

![LIFeling synaptic Vm_Int and Vm_Ext comparison](LIFeling_pyspice_output/spiky_vm_trac_r0p7-0p5-0p8_m0p3c1u_b3r50_op_i20_s1234k0p5g0p5_d150m-180m-210m-240m_w5m_t1p5_h2c8e40ea_vmint_vmext.png)

Use this plot when checking RV5 synaptic decay, RV6-RV9 set voltages, and the `V_Syn_State -> V_Syn_Drive -> Vm_Int` path.

### 13.4 Stimulus-path example

This plot shows a debug run with a positive DC stimulus command.

![LIFeling stimulus path debug example](LIFeling_pyspice_output/spiky_vm_trad_r0p7-0p5-0p8_m0p3c1u_b3r50_op_i20_u0p2_t500m_h7edf8773.png)

Use this plot to check that the `Stimulus_Ext -> U19B equivalent -> Vm_Int` path affects the membrane as expected.

### 13.5 Cold-start example

This example shows the same full LIF path under cold-start initial conditions.

![LIFeling cold-start Vm_Int and Vm_Ext comparison](LIFeling_pyspice_output/spiky_vm_trac_r0p7-0p5-0p8_m0p3c1u_b3r50_cd_i20_t1p5_haf26903a_vmint_vmext.png)

Cold-start plots are useful for separating normal operating behaviour from power-on transients.

---

## 14. How to interpret results

Open the generated text report first:

```text
*_results.txt
```

It contains the run configuration, trace list, summary statistics, and event diagnostics.

### 14.1 `Vm_Ext`

`Vm_Ext` is the physically relevant live output trace.

A healthy full run should show:

- membrane-like charging,
- a visible spike-like peak during the peak/display window,
- reset and recovery,
- repeated events if the selected parameters produce oscillation.

The cleanest plot to inspect is:

```text
*_vmint_vmext.png
```

### 14.2 `Vm_Int`

`Vm_Int` is the internal membrane node.

Use it to distinguish between internal LIF behaviour and the display/live-output path.

If `Vm_Int` spikes but `Vm_Ext` does not, inspect:

```text
Vm_Int -> R90/C38 -> Vm_Display_In -> U8/R1/C14 -> Vm_Ext
```

If neither `Vm_Int` nor `Vm_Ext` spikes, inspect the peak injection path:

```text
V_Peak_Ref -> V_Peak_Drive -> R49/U14 -> Vm_Int
```

Use:

```text
--trace-set debug
```

to include `V_Peak_Ref`, `V_Peak_Drive`, and the peak-injection switch node.

### 14.3 Threshold and spike counts

The report prints lines similar to:

```text
Threshold crossing count after ignore = ...
Spike_Pulse rising-edge count >1 V after ignore = ...
Reset_Window rising-edge count >1 V after ignore = ...
```

These counts should usually be similar. If they diverge strongly, one event-generation path is failing.

### 14.4 Reset window timing

The reset timing section reports:

```text
Reset_Window timing analysis >1 V after ignore:
  State at end = HIGH or LOW
  Duty cycle after ignore = ...
  Rising edges after ignore = ...
  Falling edges after ignore = ...
  Reset pulse width median = ...
  Reset pulse width max = ...
```

Important: `State at end = HIGH` does not automatically mean the circuit latched. The simulation may simply have stopped during a normal reset pulse.

A real latch concern is more likely if:

- `State at end = HIGH`,
- the open high pulse at the end is unusually long,
- falling edges are missing,
- reset pulse width is much larger than usual,
- Vm does not recover after reset.

### 14.5 VDD sag

When using `--supply-mode coin`, the report includes:

```text
VDD sag from Vbat = ... V
Approx peak battery current after ignore = ... mA
```

With:

```text
--vbat 3 --rbat 50
```

small VDD sag means the simulated circuit is not heavily loading the battery model. Large sag or oscillatory VDD behaviour means the chosen battery assumptions may be too weak or the simulated loading may be excessive.

### 14.6 Synaptic state

When synapses are enabled, inspect:

```text
V_Syn_State
V_Syn1_Set
V_Syn2_Set
V_Syn3_Set
V_Syn4_Set
```

Expected behaviour:

- low RV6-RV9 set values pull `V_Syn_State` lower,
- high RV6-RV9 set values push `V_Syn_State` higher,
- RV5 controls decay of `V_Syn_State` back toward `V_Leak`,
- the synaptic state should not permanently rail unless the run is an intentional stress test.

### 14.7 Buffered reference stability

In debug mode, inspect:

```text
V_Leak_Ref_Max_Raw
V_Leak_Ref_Max
```

The buffered node should remain stable under RV loading. If the raw node moves but the buffered node is stable, the buffer is doing its job. If both move only because VDD sags, that is expected under the simplified coin-cell model.

---

## 15. Built-in sweep mode

`Spice.py` includes an internal sweep mode:

```powershell
.\.venv\Scripts\python.exe .\Spice.py --sweep --stage threshold_reset_adapt --backend ngspice-cli --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --cmem-mode rv4 --rv4 0.3 --tstop 1.5 --tstep 1u --maxstep 1u
```

Default sweep values:

```text
RV1: 0.3, 0.5, 0.7, 1.0
RV2: 0.2, 0.5, 0.8
RV3: 0.2, 0.5, 0.8
```

Sweep outputs are written into:

```text
LIFeling_pyspice_output/sweep/
```

Typical sweep files:

```text
sweep_summary.csv
sweep_all_traces.csv
```

`Sweep_summary.csv` is usually the first file to inspect because it contains one row per run with key measurements and plot paths.

---

## 16. Suggested validation workflow after editing `Spice.py`

### Step 1: syntax check

```powershell
.\.venv\Scripts\python.exe -m py_compile .\Spice.py
```

### Step 2: short functional run

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set core --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --tstop 500m --tstep 1u --maxstep 1u
```

### Step 3: inspect outputs

Open:

```text
*_results.txt
*_vmint_vmext.png
*.ngspice.log
```

### Step 4: debug trace run if needed

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set debug --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --tstop 500m --tstep 1u --maxstep 1u
```

### Step 5: synaptic test

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set debug --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --syn-all-enable --rv5 0.5 --rv6 0.2 --rv7 0.4 --rv8 0.6 --rv9 0.8 --syn1-delay 150m --syn2-delay 180m --syn3-delay 210m --syn4-delay 240m --syn1-width 5m --syn2-width 5m --syn3-width 5m --syn4-width 5m --tstop 1.5 --tstep 1u --maxstep 1u
```

---

## 17. Practical pass/fail checklist

A normal full LIF run should show:

- `Vm_Ext` has a clear neuron-like spike/reset waveform.
- `Vm_Int` and `Vm_Ext` are consistent with the expected display/output path.
- Threshold crossing count, `Spike_Pulse` count, and `Reset_Window` count are broadly consistent.
- Reset pulses close again after opening.
- Reset pulse widths are stable.
- `VDD` sag is reasonable for the selected battery model.
- Synaptic runs move `V_Syn_State` in the expected direction.
- Debug runs show `V_Leak_Ref_Max_Raw` and buffered `V_Leak_Ref_Max` behaving as expected.
- The `.ngspice.log` file contains no fatal ngspice errors.

---

## 18. Common problems and fixes

### Problem: ngspice is not found

Pass the executable path explicitly:

```powershell
--ngspice-binary "C:/Users/mzimm/Documents/Spice64/bin/ngspice.exe"
```

or add the folder containing `ngspice.exe` to the Windows `PATH`.

### Problem: no CSV file is created

Open the matching `.ngspice.log` file.

Common causes:

- ngspice path is wrong,
- a saved node does not exist in the selected stage,
- a vendor model is missing in `--strict-vendor` mode,
- the vendor subcircuit pin order is wrong,
- convergence failed.

### Problem: generated filenames are too long

The script already uses shortened suffixes and a configuration hash, but Windows path limits can still be reached if the repository is deeply nested.

Move the repository closer to the drive root, for example:

```text
C:\GitHub\LIFeling\SPICE
```

### Problem: final `Reset_Window` is high

Do not immediately conclude that reset is latched. Check:

```text
Open high pulse at end duration
Reset pulse width median
Reset pulse width max
Rising edges after ignore
Falling edges after ignore
```

If rising and falling edges continue and pulse widths are stable, the transient probably ended during a normal reset pulse.

### Problem: `Vm_Ext` does not spike

Run with:

```text
--trace-set debug
```

Check:

```text
V_Peak_Ref
V_Peak_Drive
Peak_Window
Vm_Display_In
Vm_Int
Vm_Ext
```

If `Vm_Int` spikes but `Vm_Ext` does not, inspect the output/display path. If `Peak_Window` fires but `Vm_Int` does not spike, inspect R49/U14 peak injection.

### Problem: synapses do not affect Vm

Check that at least one synapse is enabled:

```text
--syn1-enable
```

or:

```text
--syn-all-enable
```

Then inspect:

```text
Syn*_Spike
V_Syn*_Set
V_Syn_State
V_Syn_Drive
Vm_Int
```

Also confirm that the synaptic pulse occurs after the ignored startup interval set by `--ignore-start-ms`.

---

## 19. Reading the code

The main sections of `Spice.py` are:

| Section | Purpose |
|---|---|
| User-editable model configuration | Paths and names for optional vendor models. |
| SPICE-safe aliases | Maps schematic/KiCad concepts to SPICE-safe node names. |
| Trace definitions | Defines core and debug traces. |
| `SimConfig` | Stores all command-line options. |
| Selection/naming helpers | Capacitance selection, output suffixes, timing tags, hashes. |
| Generic utilities | SPICE suffix parsing, tolerance handling, path handling. |
| Model includes/wrappers | Fallback models and optional strict-vendor support. |
| Netlist generation | Adds supply, references, membrane, threshold, reset, adaptation, stimulus, synapses, and output path. |
| Simulation runners | Runs ngspice CLI or PySpice. |
| Plotting and diagnostics | Creates PNGs and writes event/timing/power summaries. |
| Sweep helpers | Runs parameter sweeps and writes summary CSVs. |
| Command-line parser | Defines the CLI interface. |

The most important circuit-building functions are:

| Function | Adds |
|---|---|
| `add_supply_and_decoupling()` | Ideal or coin-cell supply model. |
| `add_references_and_passive_vm()` | Buffered leak reference, RV1/RV2, membrane capacitor, clamps. |
| `add_external_stimulus()` | Stimulus input path and U19B equivalent. |
| `add_threshold()` | U6B threshold comparator and AP/spike-pulse path. |
| `add_peak_and_reset()` | Peak injection, reset windows, reset current, `Spike_Out`. |
| `add_adaptation()` | Adaptation path and Q2 sink. |
| `add_synaptic_circuits()` | Synaptic set voltages, input switches, state decay, and injection. |
| `add_vm_external_output()` | `Vm_Ext` display/live-output path. |
| `build_spice_deck()` | Assembles the final SPICE deck. |

---

## 20. Notes for future contributors

When adding or updating schematic blocks:

1. Use schematic-like component names where possible.
2. Use SPICE-safe node names and comment the original KiCad net name.
3. Keep `core` traces compact and readable.
4. Put internal diagnostic nodes in the `debug` trace set.
5. Keep output filenames short; rely on the hash for uniqueness.
6. Add an explicit test command to this README when a new block becomes important.
7. Keep `*_results.txt` useful for non-coders: it should explain enough for a user to decide whether a run passed.
8. When committing example PNG plots, link them with exact relative Markdown paths and avoid wildcards.

<!-- LIFELING_SPICE_AUTOGENERATED_START -->

## Auto-generated SPICE validation walkthrough

This section is generated from the latest files in `LIFeling_pyspice_output/`. Do not edit it by hand; rerun the validation suite or run `Spice.py --update-readme-only` to regenerate it.

The validation suite uses `Spice.py` to build a controlled behavioural SPICE model from the KiCad netlist, run ngspice simulations, write numerical diagnostics, and turn those outputs into documentation of the circuit behaviour. The goal is not only to check whether the simulations ran, but to explain what each validation run demonstrates about the LIFeling analogue neuron.

### Latest validation-suite status

- Script version: `validation-suite-v6-readme-walkthrough`
- Suite start: `2026-07-03T16:12:51.6199691+02:00`
- Suite end: `2026-07-03T16:18:21.8422475+02:00`
- Total runs: `43`
- Failed runs: `0`
- Overall verdict: **PASS WITH WARNINGS**
- Output folder: [`LIFeling_pyspice_output`](LIFeling_pyspice_output)

### Model scope and limitations

This is a functional behavioural model. Passive components are instantiated from the KiCad netlist, while active devices such as op-amps, comparators, analogue switches, the boost converter, and protection devices are represented by stable behavioural approximations. That is deliberate: the model is meant to validate circuit function, signal polarity, timing, operating ranges, and interactions between subcircuits.

It is not a full transistor-level or vendor-accurate simulation of every integrated circuit. It does not prove PCB parasitics, real comparator propagation delay, op-amp output-current limits, battery chemistry, contact resistance, or classroom fault tolerance. Before treating the hardware as physically proven, the simulated behaviours below still need to be checked on the assembled PCB with oscilloscope measurements and realistic loading.

### Step 1: Netlist-driven model and component coverage

**What is being tested.** This step checks that the schematic components exported from KiCad are either electrically included in the generated model or explicitly accounted for as behavioural, terminal, or mechanical entries.

**Why it matters.** A SPICE validation is only useful if it remains tied to the actual schematic. Coverage makes model drift visible: a missing resistor, an unaccounted analogue switch, or an unclassified connector can otherwise make the simulation look healthy while no longer representing the board.

**Evidence source.** `component_model_coverage.csv`.

| Quantity | Latest validation result |
|---|---:|
| Coverage by model class | electrical: 165; behavioural: 36; terminal: 6; mechanical: 6 |

**Verdict.** PASS. Behavioural entries are intentional circuit-block approximations, not vendor-accurate macromodels.

No plot is required for this step because it is a model-coverage check rather than a transient waveform check.

### Step 2: Reference rails and supply model

**What is being tested.** The baseline self-spiking coin-cell run checks the 2.048 V reference, the derived 1.024 V midpoint reference, and the simplified coin-cell supply model under normal oscillating operation.

**Why it matters.** The LIFeling analogue neuron depends on stable references: the 2.048 V rail defines the upper analogue reference, while the 1.024 V midpoint is used as a neutral centre for several functions. Supply sag is also important because a weak coin cell can move comparator thresholds and reduce pulse amplitudes.

**Evidence source.** Run-label fragment: `02_baseline_self_spiking_coin`.
**Key signals.** `VREF_2V048`, `VREF_1V024`, `VDD`, `Vm_Int`, `AP`.
**Verdict.** PASS.

| Quantity | Latest validation result |
|---|---:|
| VREF_2V048 range | 2.048 V |
| VREF_1V024 range | 1.024 V |
| VDD range | 2.851–2.981 V |
| Maximum VDD sag from battery model | 0.1488 V |
| Estimated peak battery current | 2.977 mA |

![Reference rails and baseline supply behaviour — full trace set](LIFeling_pyspice_output/LIFeling_updated_02_baseline_self_spiking_coin_rv0p70_0p50_0p80_0p30_vb3_t1p5_d99654c1.png)

### Step 3: Baseline LIF behaviour

**What is being tested.** The baseline run checks that the membrane integrates toward threshold, fires repeatedly, resets, and exposes a usable external Vm output.

**Why it matters.** This is the core LIFeling behaviour: `Vm_Int` is the internal membrane computation node, `Vm_Ext` is the live output presented to the outside world, `V_Threshold` defines the firing point, and the AP/reset path must return the membrane to a repeatable state instead of latching.

**Evidence source.** Run-label fragment: `02_baseline_self_spiking_coin`.
**Key signals.** `Vm_Int`, `Vm_Ext`, `V_Threshold`, `AP`, `Reset_Window`, `Spike_Out`.
**Verdict.** PASS.

| Quantity | Latest validation result |
|---|---:|
| Vm_Int range | 0.4637–0.8832 V |
| Vm_Ext range | 0.4744–2.502 V |
| V_Threshold range | 0.8469–0.8692 V |
| AP rising edges | 27 |
| Reset_Window rising edges | 27 |
| Spike_Out rising edges | 27 |
| Mean AP period | 53.89 ms |

![Baseline LIF behaviour — Vm_Int and Vm_Ext](LIFeling_pyspice_output/LIFeling_updated_02_baseline_self_spiking_coin_rv0p70_0p50_0p80_0p30_vb3_t1p5_d99654c1_vmint_vmext.png)

### Step 4: Spike-generation and reset timing

**What is being tested.** The debug self-spiking run saves the internal timing signals that turn a threshold crossing into an AP pulse, a peak/display event, a reset window, and an external spike output.

**Why it matters.** The membrane waveform alone cannot show whether the timing chain is healthy. The AP, `Spike_Pulse`, `Peak_Window`, `Reset_Window`, and `Spike_Out` traces make it possible to detect missing pulses, pulse-count mismatches, or reset windows that fail to close.

**Evidence source.** Run-label fragment: `03_debug_self_spiking_short`.
**Key signals.** `AP`, `Spike_Pulse`, `Peak_Window`, `Reset_Window`, `Spike_Out`.
**Verdict.** PASS.

| Quantity | Latest validation result |
|---|---:|
| AP rising edges | 7 |
| Spike_Pulse rising edges | 7 |
| Peak_Window rising edges | 7 |
| Reset_Window rising edges | 6 |
| Spike_Out rising edges | 7 |
| Mean AP period | 53.71 ms |

![Spike-generation and reset timing — full trace set](LIFeling_pyspice_output/LIFeling_updated_03_debug_self_spiking_short_rv0p70_0p50_0p80_0p30_vb3_t400m_7adaaf98.png)

### Step 5: Quiet subthreshold condition

**What is being tested.** This run lowers the operating point so that the neuron should remain below threshold when no synapse is active.

**Why it matters.** A controllable teaching neuron must be able to stay silent. If the model spikes in this condition, the leak reference, threshold, reset bias, or hidden stimulus path may be unintentionally driving the membrane.

**Evidence source.** Run-label fragment: `05_quiet_subthreshold_no_synapse`.
**Key signals.** `Vm_Int`, `Vm_Ext`, `V_Threshold`, `AP`.
**Verdict.** PASS.

| Quantity | Latest validation result |
|---|---:|
| Vm_Int maximum | 0.51 V |
| Vm_Ext maximum | 0.5609 V |
| AP rising edges | 0 |

![Quiet subthreshold condition — Vm_Int and Vm_Ext](LIFeling_pyspice_output/LIFeling_updated_05_quiet_subthreshold_no_synapse_rv0p35_0p50_0p80_0p30_vb3_t400m_9a2196b1_vmint_vmext.png)

### Step 6: Synapse midpoint zero-effect

**What is being tested.** The synaptic state is set near the 1.024 V midpoint, where the centred synapse drive should be neutral.

**Why it matters.** The signed synapse architecture should not inject excitation or inhibition when the synaptic state is at its midpoint. This is the condition that lets a connected synapse be electrically present without significantly perturbing the membrane.

**Evidence source.** Run-label fragment: `06_synapse_midpoint_zero_effect_single`.
**Key signals.** `V_Syn_State`, `VREF_1V024`, `Vm_Int`, `Vm_Ext`, `AP`.
**Verdict.** PASS.

| Quantity | Latest validation result |
|---|---:|
| V_Syn_State range | 1.004–1.018 V |
| Vm_Int maximum | 0.5107 V |
| Delta versus quiet Vm_Int maximum | 0.7374 mV |
| AP rising edges | 0 |

![Synapse midpoint zero-effect — Vm_Int and Vm_Ext](LIFeling_pyspice_output/LIFeling_updated_06_synapse_midpoint_zero_effect_single_rv0p35_0p50_0p80_0p30_vb3_t400m_syn1234_b8d2aa40_vmint_vmext.png)

### Step 7: Excitatory synapse

**What is being tested.** The synaptic set voltage is driven high so that the synapse should push the membrane in the excitatory direction.

**Why it matters.** A high synaptic state should raise `Vm_Int` relative to the quiet subthreshold case. This validates the sign of the centred synapse drive and the injection path into the membrane node.

**Evidence source.** Run-label fragment: `07_synapse_excitatory_single_high`.
**Key signals.** `V_Syn_State`, `/V_Syn_Drive`, `Vm_Int`, `Vm_Ext`.
**Verdict.** PASS.

| Quantity | Latest validation result |
|---|---:|
| V_Syn_State range | 1.004–1.603 V |
| Vm_Int maximum | 0.6283 V |
| Delta versus quiet Vm_Int maximum | 118.3 mV |
| AP rising edges | 0 |

![Excitatory synapse — Vm_Int and Vm_Ext](LIFeling_pyspice_output/LIFeling_updated_07_synapse_excitatory_single_high_rv0p35_0p50_0p80_0p30_vb3_t400m_syn1234_079c8a68_vmint_vmext.png)

### Step 8: Inhibitory synapse

**What is being tested.** The synaptic set voltage is driven low while the neuron is otherwise in a self-spiking configuration.

**Why it matters.** Inhibition should reduce excitability. In this validation suite, the clearest numerical sign is a longer AP period than the baseline self-spiking run, meaning the membrane takes longer to reach threshold.

**Evidence source.** Run-label fragment: `08_synapse_inhibitory_single_low`.
**Key signals.** `V_Syn_State`, `Vm_Int`, `Vm_Ext`, `AP`.
**Verdict.** PASS.

| Quantity | Latest validation result |
|---|---:|
| Baseline mean AP period | 53.89 ms |
| Inhibitory mean AP period | 70.03 ms |
| Period increase | 16.14 ms |
| Inhibitory AP rising edges | 7 |

![Inhibitory synapse — Vm_Int and Vm_Ext](LIFeling_pyspice_output/LIFeling_updated_08_synapse_inhibitory_single_low_rv0p70_0p50_0p80_0p30_vb3_t500m_syn1234_2408b779_vmint_vmext.png)

### Step 9: Cold-start behaviour

**What is being tested.** The cold-start run begins from discharged or low initial conditions rather than from the normal biased operating point.

**Why it matters.** This is a power-on robustness check. It helps separate normal operating behaviour from startup transients and shows whether the model can recover into a valid oscillating regime after initial conditions are unfavourable.

**Evidence source.** Run-label fragment: `04_cold_start_self_spiking_coin`.
**Key signals.** `VDD`, `Vm_Int`, `Vm_Ext`, `AP`, `Reset_Window`.
**Verdict.** PASS. Cold-start is a stress condition, not the normal operating initial condition.

| Quantity | Latest validation result |
|---|---:|
| Vm_Int range | 0.6024–1.632 V |
| Vm_Ext range | 0.8433–2.567 V |
| AP rising edges | 58 |
| Estimated peak battery current | 1.974 mA |

![Cold-start behaviour — Vm_Int and Vm_Ext](LIFeling_pyspice_output/LIFeling_updated_04_cold_start_self_spiking_coin_rv0p70_0p50_0p80_0p30_vb3_t800m_d0c63a1e_vmint_vmext.png)

### Step 10: Low-battery / high-impedance stress

**What is being tested.** This stress run lowers the battery voltage and raises the source resistance to test whether the simplified supply model sags enough to disturb spike generation.

**Why it matters.** Coin-cell impedance can reduce pulse amplitude and upset comparator-level assumptions. A run can still be useful even when it warns: the warning identifies where the validation threshold no longer matches the reduced signal level.

**Evidence source.** Run-label fragment: `12_low_battery_high_impedance_stress`.
**Key signals.** `VDD`, `Vm_Int`, `Spike_Pulse`, `AP`, `Spike_Out`.
**Verdict.** WARNING. Spike_Pulse edge counting may need a lower/comparator-relative threshold in low-battery conditions.

| Quantity | Latest validation result |
|---|---:|
| VDD range | 2.518–2.549 V |
| Maximum VDD sag from battery model | 0.1819 V |
| Estimated peak battery current | 1.516 mA |
| Spike_Pulse maximum | 0.9884 V |
| Spike_Pulse rising edges counted above 1 V | 0 |

Note: Spike_Pulse edge counting may need a lower/comparator-relative threshold in low-battery conditions.

![Low-battery / high-impedance stress — full trace set](LIFeling_pyspice_output/LIFeling_updated_12_low_battery_high_impedance_stress_rv0p70_0p50_0p80_0p30_vb2p7_t500m_aa379177.png)

### Step 11: External stimulus path

**What is being tested.** The positive and negative external stimulus runs check whether a command applied at `Stimulus_Ext` changes the membrane through the stimulus-drive path.

**Why it matters.** The stimulus input is intended to be a controlled way to bias or perturb the neuron from outside the board. Polarity matters: a positive command should not accidentally behave like an inhibitory command unless that inversion is explicitly intended and documented.

**Evidence source.** Run-label fragment: `09_external_stimulus_positive_subthreshold / 10_external_stimulus_negative_subthreshold`.
**Key signals.** `Stimulus_Ext`, `V_Stim_Drive`, `Vm_Int`, `Vm_Ext`.
**Verdict.** WARNING. If this warns, run a dedicated Stimulus_Ext -> V_Stim_Drive -> Vm_Int polarity sweep.

| Quantity | Latest validation result |
|---|---:|
| Positive stimulus Vm_Int maximum | 0.448 V |
| Positive stimulus delta versus quiet | -61.95 mV |
| Negative stimulus Vm_Int maximum | 0.4249 V |
| Negative stimulus delta versus quiet | -85.12 mV |
| Positive V_Stim_Drive range | 0.0001804–0.01947 V |
| Negative V_Stim_Drive range | 0.00018–0.0001874 V |

Current interpretation: both positive and negative stimulus commands suppress `Vm_Int` in the latest diagnostics, so this block remains a warning rather than a confirmed bidirectional stimulus transfer.

Next validation improvement: add a dedicated `Stimulus_Ext -> V_Stim_Drive -> Vm_Int` transfer sweep so the polarity, gain, and linear range of the stimulus path are documented directly.

![Positive external stimulus — Vm_Int and Vm_Ext](LIFeling_pyspice_output/LIFeling_updated_09_external_stimulus_positive_subthreshold_rv0p35_0p50_0p80_0p30_vb3_t400m_d6b0544f_vmint_vmext.png)

![Negative external stimulus — Vm_Int and Vm_Ext](LIFeling_pyspice_output/LIFeling_updated_10_external_stimulus_negative_subthreshold_rv0p35_0p50_0p80_0p30_vb3_t400m_b27fb7e2_vmint_vmext.png)

### Step 12: Parameter sweeps

**What is being tested.** The sweep runs vary the front-panel controls and synaptic set levels to check that the model responds in the expected direction across more than one operating point.

**Why it matters.** A single successful waveform can hide a wrong knob direction or a narrow operating point. Sweeps make the controls easier to interpret for readers and provide regression metrics for future schematic changes.

| Sweep | Expected control meaning | Runs found | Latest observation | Verdict |
|---|---|---:|---|---|
| RV1 leak/reference | Moves the leak reference and therefore the ease of reaching threshold. | 5 | AP edges changed from 0 to 18. | PASS |
| RV2 leak-rate | Changes membrane leak conductance and therefore the charging/discharging rate. | 3 | Finite AP periods: 53.81 ms, 28.07 ms. | PASS |
| RV3 adaptation | Changes the adaptation path strength or recovery behaviour. | 4 | 4 runs completed. | PASS; Interpretation should verify that the knob direction matches the front-panel label. |
| RV4 capacitance bank | Selects the effective membrane capacitance and therefore the time scale. | 5 | 5 runs completed. | PASS; A dedicated Cmem-selection table can be added later if exact one-hot switch state is required. |
| RV5 synaptic decay | Changes how quickly the synaptic state returns toward its neutral/leak value. | 5 | 5 runs completed. | PASS; Interpretation should verify that the knob direction matches the front-panel label. |
| Synaptic sign/weight | Checks that low, midpoint, and high synaptic set values move the state in the expected direction. | 5 | 5 runs completed. | PASS |

### Files generated by the validation suite

These files are kept as separate artifacts so the README can stay readable while the raw numerical results remain available for inspection and regression checks.

- [Diagnostics summary CSV](LIFeling_pyspice_output/validation_diagnostics_summary.csv)
- [Component model coverage CSV](LIFeling_pyspice_output/component_model_coverage.csv)
- [Block-level validation verdict Markdown](LIFeling_pyspice_output/LIFeling_validation_verdict.md)
- [Block-level validation verdict CSV](LIFeling_pyspice_output/LIFeling_validation_verdict.csv)
- [Key validation metrics CSV](LIFeling_pyspice_output/LIFeling_key_validation_metrics.csv)

<!-- LIFELING_SPICE_AUTOGENERATED_END -->
