<p align="left"><img width="270" height="170" src="/Images/SpikyLogo.png">

<h1 align="center"> LIFeling </h1></p>
<h3 align="center">  An analog LIF/AdEx “silicon neuron” for teaching & exploration</h3></p>
<p align="center"><h6 align="right">developed by M.J.Y. Zimmermann, A. Koumoundourou</h6></p>

<br></br>


## What is LIFeling
<div>
<p style='text-align: justify;'>
LIFeling is a low-cost, through-hole–friendly analog circuit that emulates a spiking neuron in real time. It implements the Leaky Integrate-and-Fire (LIF) and Adaptive Exponential Integrate-and-Fire (AdEx) dynamics using op-amps, RC networks, comparators, and simple transistor/MOSFET logic.


<p style='text-align: justify;'>
Students can turn knobs (capacitance, leak, synaptic gains, adaptation, threshold, reset) and immediately see how membrane voltage and spikes change—just like a patch-clamp demo, but on an interactive PCB.
</p>

<p style='text-align: justify;'>
LIFeling lives alongside our digital <a href="https://github.com/OpenSourceNeuro/Spikeling">Spikeling</a>: project; where Spikeling runs code, LIFeling is purely analog, making the math–to–hardware mapping very explicit. (For background on AdEx/LIF and neuromorphic “silicon neurons”, <a href="https://www-sop.inria.fr/members/Mathieu.Desroches/teaching/MTSN/Articles/Brette_Gertsner_JNeurophysiol_2005.pdf?utm_source=chatgpt.com">See the references</a>).
</p>

<p style='text-align: justify;'>
<img align="right" src="/Images/Spiky_3D.png" width="246" height="106" >

This project is licensed under the [GNU General Public License v3.0](https://github.com/OpenSourceNeuro/Spikeling-V2/blob/main/LICENSE)<br>
The hardware is licensed under the [CERN OHL v1.2](https://github.com/OpenSourceNeuro/Spikeling-V2/blob/main/PCB%20-%202.2c/LICENSE)
</p>
</div>

<br>

***


## Objectives
- **Pedagogy** first: Make classical neuron equations tangible with knobs, LEDs, and BNC/TTL I/O so learners can fit parameters from data and build intuition.


- **Open, repairable, reproducible**: THT-preferred BOM where possible; common op-amps (e.g., MCP6004), LM339-class comparators, simple passives; documented test procedures.

- **Immediate feedback**: Real-time dynamics without sampling/latency; scope-friendly nodes for Vm, synaptic currents, threshold comparator, adaptation current.


- **Bridging models**: Start with LIF; switch in AdEx features (exp spike term + adaptation) to show how richer behaviours emerge with just a few components.


- **Teaching exercises**: Provide ready-to-run lab activities (τm measurement, I–F curves, refractory period, synaptic summation, adaptation fitting, noise & reliability). (See Exercises below.)

- **Interoperability**: Optional headers/IO for stimulus/recording from microcontrollers (ESP32/Arduino) and classroom oscilloscopes.


## The models LIFeling implements

#### 1) Leaky Integrate-and-Fire (LIF)

```math
C_m * dV/dt = -g_L * (V - E_L) + I_syn(t) + I_inj(t) - w(t)
```

If V >= V_th  ⇒  V ← V_reset  and hold for τ_ref

with synaptic drive typically modeled as:

```math
I_syn(t) = Σ_i g_i(t) * (E_i - V)
```

LIF captures integration, leakage, threshold, reset, and refractory with minimal parameters.

### Adaptive Exponential Integrate-and-Fire (AdEx)

```math
C_m * dV/dt = -g_L * (V - E_L)
              + g_L * Δ_T * exp((V - V_T)/Δ_T)
              - w
              + I_syn(t) + I_inj(t)

τ_w * dw/dt = a * (V - E_L) - w

If V >= V_spike  ⇒  V ← V_reset  and  w ← w + b
```

AdEx adds a soft, exponential spike-initiation term and an adaptation state w, reproducing rich firing patterns with few parameters.

- Further reading: Brette & Gerstner 2005 (AdEx); Dayan & Abbott 2001 (LIF fundamentals); Indiveri et al. 2011 (neuromorphic neuron circuits).


## Circuit ↔ equation map

| Equation term | Biological meaning | Circuit element(s) | What to adjust / observe |
|---|---|---|---|
| `C_m` | Membrane capacitance (area/biophysics) | Selectable capacitor bank; front-panel selector | Larger `C_m` → slower `V_m` dynamics; measure a step response to estimate `τ_m = C_m / g_L`. |
| `g_L`, `E_L` | Leak conductance & resting potential | Potentiometer or resistor ladder to ground/bias; optional reference sets `E_L` | Increasing `g_L` lowers input resistance and shortens `τ_m`; trimming `E_L` shifts the baseline. |
| `I_syn = Σ g_i(t) · (E_i − V)` | Synaptic drive (EPSC/IPSC) with reversal | 4× synapse shapers (RC) with gain/polarity pots; bias selects excitatory vs inhibitory | Temporal summation, shunting inhibition; switch time constants (fast/slow) to compare PSP shapes. |
| `Δ_T`, `V_T` | Spike-onset sharpness & soft threshold (AdEx) | Exponential I–V subcircuit (diode/transconductance shaping) feeding the membrane node | Increase `Δ_T` for smoother onset; adjust `V_T` to shift effective threshold and excitability. |
| `w`, `a`, `b`, `τ_w` | Adaptation current and kinetics | Slow RC + transconductance; spike-triggered charge increment into `w` | Fit `a`, `b`, `τ_w` from step protocols; observe spike-frequency adaptation and after-spike effects. |
| Spike detect & reset | Action potential event and absolute refractory | LM339-class comparator → MOSFET/analog switch clamp to `V_reset`; monostable sets `τ_ref` | Tune `V_th`, `V_reset`, `τ_ref`; verify with ISI histograms and two-pulse tests. |
| `I_inj` | Current clamp / external stimulus | BNC/3.5 mm input, on-board button, or photodiode path | Use steps/ramps/noise to probe `f–I` curves, threshold, reliability, and dynamic range. |


## Biological correspondence: what’s faithful vs abstracted

Faithful: passive membrane (R–C), synaptic time courses (first-order), EPSP/IPSP summation, threshold/reset phenomenology, refractory period, spike-frequency adaptation.

Abstracted: no detailed action-potential waveform (we model its effect via threshold/reset); ion-channel kinetics are lumped into **g_L**, the exponential term, and **w** rather than Hodgkin–Huxley-style gates.

Optional background: when teaching resting potentials and synaptic reversal, connect channel-specific reversal potentials **E_i** to Nernst/GHK equations (see References).

## Front-panel controls (typical)

**Membrane**: C_m selector, Leak pot (g_L), E_L trim.

**Synapses (×4)**: Gain pot, Polarity switch (E/I), τ_s switch (fast/slow).

**AdEx**: V_T, Δ_T trims (soft threshold), Adaptation (a, b, τ_w) pots.

**Spiking**: V_th, V_reset, τ_ref trims; Spike LED.

**I/O**: Vm out (scope), Spike out (TTL), Stim in (BNC/3.5 mm), light-sensor jack.

Start with τ_m ≈ 5–100 ms and spike thresholds ~0.8–1.8 V relative to your virtual ground (adjust for your supply).

## Quick start (bench)

Power & baseline. Power the board; set all gains mid-range; choose C_m, set leak mid.

Wire the scope. CH1 = Vm; CH2 = Spike TTL.

Elicit spikes. Inject a 0.5–2 s current step; adjust threshold/reset until regular spiking appears.

Add small Δ_T and adaptation (τ_w ≈ 200–500 ms). Watch firing adapt down.

Play with synapses. Use fast EPSPs and slower IPSPs to demonstrate temporal summation and shunting inhibition.

## Suggested classroom exercises

**Measure membrane time constant τ_m.**
Inject a small subthreshold step; fit V(t) = E_L + ΔV*(1 - exp(-t/τ_m)). Recover C_m or g_L and compare to knob settings.

**I–F (f–I) curve & rheobase.**
Ramp I_inj and record firing rate. Fit slope and rheobase; show how g_L and C_m change slope/offset.

**Refractory period.**
Deliver two pulses separated by Δt; find minimum Δt producing two spikes; compare to τ_ref.

**Synaptic summation and shunting.**
Pair an EPSP with a near-coincident IPSP; demonstrate divisive gain control by increasing inhibitory conductance (shunting).

**Spike-frequency adaptation (AdEx).**
Step-current protocol; fit a, b, τ_w from the early/late rates and the post-spike adaptation jump.

**Soft vs hard threshold.**
Compare LIF (hard V_th) to AdEx (Δ_T > 0). Show smoother onset and different ISI variability with AdEx.

**Noise & reliability.**
Add small noise to I_inj; plot spike-time jitter vs g_L. Discuss reliability/variability trade-offs.



**Analog vs digital (optional).**
Recreate one exercise on a microcontroller neuron (e.g., Izhikevich) and compare dynamics, latency, and parameter identifiability.

## Acknowledgments

Foundation: This project is based on Lu.i — https://github.com/giant-axon/lu.i-neuron-pcb

Thanks to the neuromorphic-hardware community for decades of open designs and teaching inspiration.

## References & further reading

AdEx model — Brette, R. & Gerstner, W. (2005). Adaptive Exponential Integrate-and-Fire Model as an Effective Description of Neuronal Activity. Journal of Neurophysiology, 94(5), 3637–3642. https://doi.org/10.1152/jn.00686.2005

LIF & synapses — Dayan, P. & Abbott, L. F. (2001). Theoretical Neuroscience. MIT Press. (See chapters on LIF, synapses, and I–F curves.)

Neuromorphic circuits — Indiveri, G., Linares-Barranco, B., et al. (2011). Neuromorphic Silicon Neuron Circuits. Frontiers in Neuroscience, 5:73. https://doi.org/10.3389/fnins.2011.00073
 (Open access)

Spiking for teaching (digital reference) — Baden, T., James, B., et al. (2018). Spikeling: a low-cost hardware implementation of a spiking neuron for neuroscience teaching and outreach. PLOS Biology. https://doi.org/10.1371/journal.pbio.2006760

Ion channels & reversals (background) — Hille, B. (2001). Ion Channels of Excitable Membranes (3rd ed.). Sinauer. (Nernst/GHK chapters)

## Contributing

Issues and PRs welcome!
When reporting results, please include:

Scope captures (Vm & Spike TTL),

Knob settings (Cm, gL, ΔT, Vth, Vreset, τref, a, b, τw),

The stimulus used (step amplitude, duration, ramp slope, synaptic timing),

Supply voltage and any modifications to the reference design.

## FAQ

Is this a “real” action potential?
No—the analog spike is implicit (threshold/reset). That’s by design and matches reduced-model pedagogy.

Why analog instead of a microcontroller?
Zero-latency dynamics and a literal circuit-to-equation mapping you can probe with a scope—excellent for intuition building.

Can I add more biology?
Yes: add synapse types (different τ_s), noise sources, or a second compartment. Use the AdEx literature and neuromorphic reviews as guidance.
