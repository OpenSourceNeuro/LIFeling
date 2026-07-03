# LIFeling SPICE validation verdict

Script version: `validation-suite-v5-readme`
Overall verdict: **PASS WITH WARNINGS**

Validation suite: `43` total steps, `0` failed.

## Block-level verdict

| Circuit block | Verdict | Evidence | Caveat |
|---|---|---|---|
| Simulation execution / convergence | **PASS** | 43 suite steps, 0 failed. |  |
| Component model coverage | **PASS** | behavioural: 36, electrical: 165, mechanical: 6, terminal: 6 | Behavioural entries are intentional circuit-block approximations, not vendor-accurate macromodels. |
| Reference rails VREF_2V048 / VREF_1V024 | **PASS** | Baseline VREF_2V048=2.048..2.048 V; VREF_1V024=1.024..1.024 V. |  |
| Core LIF oscillation / threshold / AP / reset / Spike_Out | **PASS** | Baseline AP=27, Reset_Window=27, Spike_Out=27; Vm_Int=0.4637..0.8832 V. |  |
| Quiet subthreshold operating point | **PASS** | Quiet-subthreshold AP_rising_edges=0; Vm_Int_max=0.51 V. |  |
| Cold-start behaviour | **PASS** | Cold-start AP_rising_edges=58; Vm_Int_max=1.632 V. | Cold-start is a stress condition, not the normal operating initial condition. |
| Synapse midpoint zero-effect | **PASS** | Midpoint minus quiet Vm_Int_max delta=0.7374 mV; AP_rising_edges=0. |  |
| Excitatory synapse sign | **PASS** | Excitatory minus quiet Vm_Int_max delta=118.3 mV. |  |
| Inhibitory synapse sign | **PASS** | Baseline AP period=53.89 ms; inhibitory AP period=70.03 ms. |  |
| External stimulus path | **WARNING** | Positive stimulus delta=-61.95 mV; negative stimulus delta=-85.12 mV. | If this warns, run a dedicated Stimulus_Ext -> V_Stim_Drive -> Vm_Int polarity sweep. |
| RV1 leak/reference sweep | **PASS** | First sweep AP edges=0; last sweep AP edges=18. |  |
| RV2 leak-rate sweep | **PASS** | Finite AP mean periods observed: 53.81 ms, 28.07 ms. |  |
| RV3 adaptation sweep | **PASS** | 4 RV3 adaptation sweep runs completed. | Interpretation should verify that the knob direction matches the front-panel label. |
| RV4 capacitance-bank sweep | **PASS** | 5 RV4 capacitance-bank sweep runs completed. | A dedicated Cmem-selection table can be added later if exact one-hot switch state is required. |
| RV5 synaptic decay sweep | **PASS** | 5 RV5 synaptic decay sweep runs completed. | Interpretation should verify that the knob direction matches the front-panel label. |
| Synaptic sign/weight sweep | **PASS** | 5 synaptic sign/weight sweep runs completed. |  |
| Low-battery / high-impedance stress | **WARNING** | VDD_min=2.518 V; estimated peak battery current=1.516 mA; Spike_Pulse_max=0.9884 V. | Spike_Pulse edge counting may need a lower/comparator-relative threshold in low-battery conditions. |

## Generated files

- `validation_diagnostics_summary.csv`: aggregate numerical diagnostics, one row per validation run.
- `component_model_coverage.csv`: electrical/behavioural/mechanical model coverage for schematic components.
- `LIFeling_validation_verdict.csv`: machine-readable block-level verdict.
- `LIFeling_key_validation_metrics.csv`: selected regression metrics.

