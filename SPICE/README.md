# Spiky-Lu.i SPICE simulation

This folder contains a Python/ngspice simulation of the Vm-relevant part of the **Spiky-Lu.i** analog neuron circuit.

The main file is:

```text
Spice.py
```

It builds a SPICE circuit deck, runs a transient simulation, saves compact visualisation data, plots the results, and prints a validation report. The helper PowerShell file:

```text
run_spiky_full_validation.ps1
```

runs a complete validation suite.

This README is written for both electronics/software users and non-coders. The most useful sections are **Quick start**, **What files are produced**, and **How to interpret the results**.

---

## 1. What this simulation is

`Spice.py` is a **controlled behavioural SPICE model** of the current KiCad design. It is not a raw KiCad-exported netlist. Instead, it recreates the important analog-neuron blocks using readable SPICE elements and schematic-aligned names.

The goal is to answer questions such as:

- Does the membrane voltage behave like a neuron trace?
- Does the live output `Vm_Ext` show a usable spike-like waveform?
- Does threshold detection trigger correctly?
- Does reset recover correctly, or does it latch?
- Do synaptic inputs perturb the membrane as expected?
- Does the buffered `V_Leak_Ref_Max` reference remain stable under synaptic loading?
- How do RV1, RV2, RV3, RV5, RV6, RV7, RV8, and RV9 affect behaviour?

The clean live trace is now:

```text
Vm_Ext
```

not `Vm_Int`. `Vm_Ext` is the trace intended to match the physical output used during operation of the device.

---

## 2. Hardware blocks currently modelled

The script models the following functional blocks:

| Circuit block | Purpose in the simulation |
|---|---|
| Power rail model | Either ideal `VDD` or a simplified coin-cell model `VBAT_RAW -> RBAT -> VDD` with local decoupling. |
| `V_Leak_Ref_Max` reference | R4/R5 raw divider followed by U2A buffer. This feeds RV1 and RV6-RV9. |
| Passive membrane | Leak reference, RV2 leak path, selected membrane capacitor, `Vm_Int`. |
| Vm external output | `Vm_Int -> U8 -> R1/C14 -> Vm_Ext`, used for the clean live trace plot. |
| Threshold detection | U6B comparator, AP generation, `/Rising_AP`, `Spike_Pulse`. |
| Vm peak injection | R8/R9 peak reference, U2C buffer, R49/U14 peak switch into `Vm_Int`. This is what gives the membrane trace an AP-like peak. |
| Reset window | U6A/U6C, peak/reset windows, reset timer, reset-current injection chain. |
| Spike output | U6D/R81/R82/D18 approximation for `Spike_Out`. |
| Adaptation | U1B/U1C/U1D, Vw path, Q2 adaptation current sink. |
| External stimulus | U19 stimulus path from `Stimulus_Ext` to `Vm_Int`. |
| Synaptic inputs | Syn1-Syn4 input clamp/switch/set-voltage paths, RV5 synaptic-state decay, RV6-RV9 set voltages. |
| Component tolerances | Optional deterministic random resistor/capacitor/pot tolerances. |

---

## 3. Hardware blocks intentionally not modelled

These are intentionally simplified or omitted:

| Not modelled | Reason |
|---|---|
| Real RV4 membrane-capacitor selector network | The script uses an ideal one-hot capacitor selector controlled by `--rv4` or manual `--cmem`. |
| RGB LED / visual-indicator loading | Omitted to keep the Vm model focused and readable. |
| Real boost converter / power front end | Replaced by an ideal supply or simple coin-cell internal-resistance model. |
| Full TS5A3166 non-ideal switch physics | Switches are approximated with idealised `SW` models with finite on-resistance. |
| Exact vendor macromodels by default | Fallback models are used unless `--strict-vendor` is requested. |

This means the model is best used for **functional validation**, not final production-level analogue accuracy.

---

## 4. Folder layout

Recommended folder structure:

```text
SPICE/
├─ Spice.py
├─ run_spiky_full_validation.ps1
├─ README.md
├─ models/
│  ├─ MCP6001.txt
│  ├─ TLV7044.lib
│  ├─ BSS138.lib
│  ├─ MMBT3904.spice.txt
│  ├─ 1n4148_spice.lib
│  └─ RB521S30.lib
├─ spiky_pyspice_output/        generated automatically
└─ spiky_validation_logs/       generated automatically by the .ps1 validation script
```

The `models/` folder is only strictly required if you run with:

```text
--strict-vendor
```

Without `--strict-vendor`, the script uses internal fallback models.

---

## 5. Requirements

You need:

1. Python installed and available in a virtual environment.
2. Python packages:

```powershell
pip install numpy pandas matplotlib
```

3. ngspice installed.

On the current Windows setup, ngspice is commonly located at:

```text
C:\Users\mzimm\Documents\Spice64\bin\ngspice.EXE
```

The script can also search automatically with:

```text
--ngspice-binary auto
```

---

## 6. Quick start

Open a terminal in the `SPICE` folder. In PyCharm, this is usually the terminal at the bottom of the window.

First check that you are in the correct folder:

```powershell
dir
```

You should see:

```text
Spice.py
run_spiky_full_validation.ps1
```

### 6.1 Compile-check the Python script

This checks only that Python can parse the file:

```powershell
.\.venv\Scripts\python.exe -m py_compile .\Spice.py
```

If there is no output, the syntax check passed.

### 6.2 Run a standard full LIF simulation

Copy and paste this command:

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set core --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --tstop 1.5 --tstep 1u --maxstep 1u
```

This is the recommended first run. It simulates the full LIF path without synaptic inputs.

### 6.3 Run the full validation suite

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1
```

For a shorter first check without the longer sweeps:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1 `
  -SkipRV123Sweep `
  -SkipRV5Sweep `
  -SkipLongSynapseSweep
```

If ngspice is not found automatically, pass its path explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1 `
  -PythonExe ".\.venv\Scripts\python.exe" `
  -SpicePy ".\Spice.py" `
  -NgspiceBinary "C:\Users\mzimm\Documents\Spice64\bin\ngspice.EXE"
```

---

## 7. What files are produced

Each run writes files into:

```text
spiky_pyspice_output/
```

Typical outputs are:

| File | Meaning |
|---|---|
| `spiky_vm_<suffix>.cir` | The SPICE deck generated by Python. Useful for debugging the actual ngspice input. |
| `spiky_vm_<suffix>.csv` | Compact saved traces for plotting or later analysis. |
| `spiky_vm_<suffix>.png` | Multi-trace plot. |
| `spiky_vm_<suffix>_vmext.png` | Clean plot of `Vm_Ext`, the live physical output trace. |
| `spiky_vm_<suffix>_results.txt` | Full printed report from the run: configuration, paths, trace list, summary values, event counts, reset timing, VDD sag. |
| `spiky_vm_<suffix>.ngspice.log` | Raw ngspice log. Useful if ngspice fails. |

The validation script also writes logs into:

```text
spiky_validation_logs/
```

Typical files:

| File | Meaning |
|---|---|
| `validation_suite_<timestamp>.txt` | Suite-level summary: pass/fail for each run. |
| `<run_name>.console.txt` | Full console output for one validation run. |

---

## 8. Simulation stages

The `--stage` option chooses how much of the circuit to include.

| Stage | Includes | Use it for |
|---|---|---|
| `passive` | References, leak, membrane capacitor, `Vm_Int`, `Vm_Ext`. | Checking passive charging/leak behaviour. |
| `threshold` | Passive stage plus threshold comparator and AP pulse generation. | Internal threshold logic checks. For `Spike_Out`, prefer `threshold_reset`. |
| `threshold_reset` | Threshold stage plus peak injection, reset window, reset current, `Spike_Out`. | Checking `Vm_Ext` spike/reset behaviour without adaptation. |
| `threshold_reset_adapt` | Full model: reset plus adaptation and optional synapses/stimulus. | Main operating mode. Use this for most tests. |

Most users should use:

```text
--stage threshold_reset_adapt
```

---

## 9. Trace sets: core vs debug

Use:

```text
--trace-set core
```

for normal runs. This saves a compact set of traces meant for visualisation.

Use:

```text
--trace-set debug
```

when something is wrong and you need internal reference/control nodes.

### Core traces usually include

```text
Vm_Ext
Vm_Int
V_Leak
VDD
V_Threshold
AP
Spike_Pulse
Spike_Out
Peak_Window
Reset_Window
Vw
Vw_buff
```

When synapses are enabled, core also includes:

```text
V_Syn_State
Syn1_Spike / V_Syn1_Set
Syn2_Spike / V_Syn2_Set
Syn3_Spike / V_Syn3_Set
Syn4_Spike / V_Syn4_Set
```

### Debug traces can add

```text
V_Leak_Ref_Max_Raw
V_Leak_Ref_Max
V_Peak_Ref
V_Peak_Drive
Peak injection switch node
Reset timer/reference nodes
U1B adaptation output
Stimulus amplifier internal nodes
Synaptic decay node
```

---

## 10. Main command-line options explained

The script uses options beginning with `--`. You do not need to memorise them; copy the examples and change only the values you need.

### Power options

| Option | Meaning |
|---|---|
| `--supply-mode ideal` | Perfect voltage source on VDD. Useful for debugging. |
| `--supply-mode coin` | Battery model: `VBAT_RAW -> Rbat -> VDD`. Recommended for realistic checks. |
| `--vbat 3` | Battery open-circuit voltage. |
| `--rbat 50` | Battery/internal resistance in ohms. |

### Startup options

| Option | Meaning |
|---|---|
| `--startup-mode operating` | Starts VDD capacitors and reset timer precharged. Best for normal behaviour. |
| `--startup-mode cold` | Starts VDD capacitors and reset timer discharged. Best for power-on stress. |
| `--ignore-start-ms 20` | Ignore the first 20 ms when counting events and VDD sag. |

### Potentiometers

| Option | Hardware meaning |
|---|---|
| `--rv1` | Leak reference set point. |
| `--rv2` | Leak conductance / membrane leak rate. |
| `--rv3` | Adaptation strength/decay control. |
| `--rv4` | Membrane capacitance selector, idealised by the model. |
| `--rv5` | Synaptic-state decay back toward `V_Leak`. |
| `--rv6` | Synapse 1 set voltage. |
| `--rv7` | Synapse 2 set voltage. |
| `--rv8` | Synapse 3 set voltage. |
| `--rv9` | Synapse 4 set voltage. |

All RV values are fractions between 0 and 1.

Examples:

```text
--rv1 0.7
--rv6 0.3
--rv9 1.0
```

### Time options

| Option | Meaning |
|---|---|
| `--tstop 1.5` | Simulate for 1.5 seconds. |
| `--tstep 1u` | Requested output time step. |
| `--maxstep 1u` | Maximum internal ngspice step. Smaller is slower but more precise. |

SPICE suffixes are supported:

```text
m = milli = 1e-3
u = micro = 1e-6
n = nano  = 1e-9
```

So:

```text
150m = 150 ms
1u   = 1 microsecond
```

---

## 11. Useful copy-paste commands

### 11.1 Full LIF, no synapses

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set core --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --tstop 1.5 --tstep 1u --maxstep 1u
```

### 11.2 Same run, with debug traces

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set debug --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --tstop 500m --tstep 1u --maxstep 1u
```

### 11.3 Full LIF with all synapses enabled, staggered inputs

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set core --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --syn-all-enable --rv5 0.5 --rv6 0.5 --rv7 0.5 --rv8 0.5 --rv9 0.5 --syn1-delay 150m --syn2-delay 180m --syn3-delay 210m --syn4-delay 240m --syn1-width 5m --syn2-width 5m --syn3-width 5m --syn4-width 5m --tstop 1.5 --tstep 1u --maxstep 1u
```

### 11.4 Cold-start stress test

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set core --supply-mode coin --vbat 3 --rbat 50 --startup-mode cold --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --tstop 1.5 --tstep 1u --maxstep 1u
```

### 11.5 Stimulus path check

```powershell
.\.venv\Scripts\python.exe .\Spice.py --stage threshold_reset_adapt --backend ngspice-cli --ngspice-binary auto --trace-set debug --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --rv1 0.7 --rv2 0.5 --rv3 0.8 --cmem-mode rv4 --rv4 0.3 --stim-dc 0.2 --tstop 500m --tstep 1u --maxstep 1u
```

---

## 12. Full validation suite

The validation suite is the easiest way to check that the main circuit behaviours still work after editing `Spice.py`.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1
```

It currently checks:

1. Python syntax.
2. Threshold/reset/AP/`Spike_Out` path.
3. Full LIF with `Vm_Ext` and peak injection.
4. Full LIF debug traces.
5. Cold start.
6. Synapses present but no pulse during analysis.
7. Simultaneous low synaptic stress.
8. Simultaneous high synaptic stress.
9. Stimulus path.
10. RV1 behaviour sweep.
11. RV2 behaviour sweep.
12. RV3 behaviour sweep.
13. RV5 synaptic decay sweep.
14. RV6-RV9 staggered synaptic level sweep.

To skip the longer sweeps:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1 `
  -SkipRV123Sweep `
  -SkipRV5Sweep `
  -SkipLongSynapseSweep
```

To keep running even if one run fails:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1 -ContinueOnError
```

---

## 13. How to interpret the results

Open the generated:

```text
*_results.txt
```

file first. It contains the most useful diagnostics.

### 13.1 `Vm_Ext`

`Vm_Ext` is the physically relevant live output trace.

A healthy run should show:

- a membrane-like charging phase,
- a spike-like peak during the peak window,
- a reset/recovery phase,
- repeated events if the neuron is oscillating.

The clean plot:

```text
*_vmext.png
```

is the first image to inspect.

### 13.2 `Vm_Int`

`Vm_Int` is the internal membrane node. It is still saved because it helps check whether the output buffer is behaving correctly.

If `Vm_Int` spikes but `Vm_Ext` does not, check the U8/R1/C14 output path.

If neither spikes, check the peak injection path:

```text
V_Peak_Ref -> V_Peak_Drive -> R49/U14 -> Vm_Int
```

Run with:

```text
--trace-set debug
```

to include `V_Peak_Ref`, `V_Peak_Drive`, and the peak-injection switch node.

### 13.3 Threshold crossing count

The results file prints lines like:

```text
Threshold crossing count after ignore = 42
Spike_Pulse rising-edge count >1 V after ignore = 42
Reset_Window rising-edge count >1 V after ignore = 42
```

These counts should usually be similar. If they diverge strongly, one of the event-generation paths is failing.

### 13.4 Reset window timing

The results include:

```text
Reset_Window timing analysis >1 V after ignore:
  State at end = HIGH or LOW
  Duty cycle after ignore = ...
  Rising edges after ignore = ...
  Falling edges after ignore = ...
  Reset pulse width median = ...
  Reset pulse width max = ...
```

Important: `State at end = HIGH` does **not** automatically mean the circuit is latched. The simulation may simply have stopped during a normal reset pulse.

A true latch concern is more likely if:

- `State at end = HIGH`, and
- there is a very long `Open high pulse at end duration`, and
- there are missing falling edges, and
- the reset pulse width is far larger than usual.

If rising and falling edges continue and the pulse widths stay consistent, reset is recovering normally.

### 13.5 VDD sag

The results include:

```text
VDD sag from Vbat = ... V
Approx peak battery current after ignore = ... mA
```

With the standard coin-cell stress model:

```text
--vbat 3 --rbat 50
```

small sag means the simulated circuit is not overloading the rail. Large sag or unstable VDD means the model may be too demanding for the chosen battery assumptions.

### 13.6 Synaptic state

When synapses are enabled, inspect:

```text
V_Syn_State min/max
V_Syn1_Set ... V_Syn4_Set
```

Expected behaviour:

- RV6-RV9 low values pull `V_Syn_State` lower.
- RV6-RV9 high values push `V_Syn_State` higher.
- RV5 controls the decay of `V_Syn_State` back toward `V_Leak`.

The synaptic state should not permanently rail unless that is the intended stress test.

### 13.7 Buffered reference stability

In debug mode, check:

```text
V_Leak_Ref_Max_Raw
V_Leak_Ref_Max buffered
```

They should track closely. If the buffered node is stable but the raw node collapses, the reference divider is overloaded. If both move together only with VDD sag, that is usually acceptable.

---

## 14. Reading the code: main sections and functions

The code is organised in sections. You do not need to understand all of them to run the simulation.

### Configuration

| Code item | Purpose |
|---|---|
| `SimConfig` | Stores all command-line options as one configuration object. |
| `Trace` | Defines one saved/plotted voltage trace. |
| `CORE_*_TRACES` | Compact visualisation traces saved in CSV. |
| `DEBUG_*_TRACES` | Extra traces for validation/debugging. |

### Naming and helper functions

| Function | Purpose |
|---|---|
| `selected_cmem()` | Chooses the membrane capacitor from RV4 or manual value. |
| `output_suffix()` | Builds short, collision-safe output filenames. |
| `run_identity_hash()` | Adds a short hash to avoid overwriting different runs. |
| `_to_float_suffix()` | Converts SPICE values like `150m`, `1u`, `10k` into numbers. |
| `split_pot_toleranced()` | Converts a pot fraction into two resistances. |

### Circuit-building functions

| Function | Adds this circuit block |
|---|---|
| `add_supply_and_decoupling()` | Ideal or coin-cell VDD model. |
| `add_references_and_passive_vm()` | Leak references, RV1/RV2, membrane capacitor, peak reference. |
| `add_vm_external_output()` | U8 live output path to `Vm_Ext`. |
| `add_threshold()` | U6B threshold comparator, AP, `Spike_Pulse`. |
| `add_peak_and_reset()` | Peak injection, reset windows, reset current, `Spike_Out`. |
| `add_adaptation()` | Vw/adaptation path. |
| `add_external_stimulus()` | U19 stimulus input path. |
| `add_synaptic_circuits()` | Synaptic state, RV5 decay, Syn1-Syn4 set/input/switch paths. |
| `build_spice_deck()` | Calls the block functions and writes the final SPICE deck. |

### Running, plotting, diagnostics

| Function | Purpose |
|---|---|
| `run_with_ngspice_cli()` | Runs ngspice as a command-line process. |
| `run_with_pyspice()` | Alternative PySpice backend. Usually not needed. |
| `plot_results()` | Multi-trace plot. |
| `plot_vm_only()` | Clean `Vm_Ext` plot. |
| `print_diagnostics()` | Prints min/max/end values and event summaries. |
| `digital_pulse_timing_stats()` | Measures reset-window pulse widths/duty cycle. |
| `print_reset_window_timing_summary()` | Reports reset latch/recovery diagnostics. |
| `tee_stdout()` | Copies console output to `*_results.txt`. |
| `run_sweep()` | Built-in Python sweep mode. The PowerShell suite is usually easier. |

---

## 15. Built-in Python sweep mode

`Spice.py` also has an internal sweep mode:

```powershell
.\.venv\Scripts\python.exe .\Spice.py --sweep --stage threshold_reset_adapt --backend ngspice-cli --supply-mode coin --vbat 3 --rbat 50 --startup-mode operating --ignore-start-ms 20 --cmem-mode rv4 --rv4 0.3 --tstop 1.5 --tstep 1u --maxstep 1u
```

Default sweep values are:

```text
RV1: 0.3, 0.5, 0.7, 1.0
RV2: 0.2, 0.5, 0.8
RV3: 0.2, 0.5, 0.8
```

The sweep writes:

```text
spiky_pyspice_output/sweep/.../sweep_summary.csv
spiky_pyspice_output/sweep/.../sweep_all_traces.csv
```

The PowerShell validation suite is recommended for normal project validation because it includes specific circuit tests with clearer run names.

---

## 16. Common problems and fixes

### Problem: PowerShell blocks the script

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1
```

### Problem: ngspice not found

Pass the path explicitly:

```powershell
--ngspice-binary "C:\Users\mzimm\Documents\Spice64\bin\ngspice.EXE"
```

or in the validation script:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1 `
  -NgspiceBinary "C:\Users\mzimm\Documents\Spice64\bin\ngspice.EXE"
```

### Problem: no CSV created

Open the `.ngspice.log` file. This usually means ngspice failed before `wrdata` could write the CSV.

Common causes:

- a node was requested in `.save` but does not exist in that stage,
- ngspice path is wrong,
- a model file is missing in `--strict-vendor` mode,
- convergence failed.

### Problem: filenames are too long

The current script uses shortened suffixes and a hash, but Windows can still complain if the project folder path is very long.

Try moving the repository closer to the drive root, for example:

```text
C:\GitHub\Spiky-Lu.i\SPICE
```

### Problem: final `Reset_Window` is high

Do not conclude immediately that reset latched. Check:

```text
Open high pulse at end duration
Reset pulse width median
Reset pulse width max
Rising edges after ignore
Falling edges after ignore
```

If the open high pulse is normal length and rising/falling edges continue, the simulation probably ended during a normal reset pulse.

### Problem: `Vm_Ext` does not spike

Run with debug traces:

```text
--trace-set debug
```

Check:

```text
V_Peak_Ref
V_Peak_Drive
Peak_Window
Peak injection switch NO
Vm_Int
Vm_Ext
```

If `Vm_Int` spikes but `Vm_Ext` does not, inspect the U8 output path. If `Peak_Window` fires but `Vm_Int` does not spike, inspect the peak-injection path R49/U14.

---

## 17. Recommended workflow after editing `Spice.py`

1. Syntax check:

```powershell
.\.venv\Scripts\python.exe -m py_compile .\Spice.py
```

2. Short validation:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1 `
  -SkipRV123Sweep `
  -SkipRV5Sweep `
  -SkipLongSynapseSweep
```

3. Inspect the generated `*_vmext.png` and `*_results.txt` files.

4. Full validation:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_spiky_full_validation.ps1
```

5. Commit only after the full suite passes or after documenting any intentional failure.

---

## 18. Practical pass/fail checklist

A normal full LIF run should show:

- `Vm_Ext` has a clear neuron-like spike/reset waveform.
- `Vm_Int` and `Vm_Ext` are consistent.
- `Threshold crossing count`, `Spike_Pulse count`, and `Reset_Window count` are similar.
- Reset pulse widths are stable.
- VDD sag is reasonable for the selected battery model.
- Synaptic runs change `V_Syn_State` in the expected direction.
- Debug runs show `V_Leak_Ref_Max_Raw` and buffered `V_Leak_Ref_Max` tracking closely.
- No ngspice errors in `.ngspice.log`.
- Validation suite reports `Failures: 0`.

---

## 19. Notes for future contributors

When adding schematic blocks to the model:

1. Use schematic-like component names where possible.
2. Use SPICE-safe node names, then comment the KiCad net name.
3. Add only important traces to the core CSV.
4. Put internal debug nodes in the debug trace set.
5. Keep filenames short; rely on the hash for uniqueness.
6. Add a validation run to `run_spiky_full_validation.ps1` when a new block becomes important.
7. Keep `*_results.txt` readable: it should explain enough for a non-coder to decide whether the run passed.

