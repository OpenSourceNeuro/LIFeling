# LIFeling SPICE validation verdict

Source lock SHA-256: `55df884890c53c1af35b7f03e638c13b9e68e5c5d7e3ac005e109ba13a78201c`

| Block | Status | Evidence | Limitation |
|---|---|---|---|
| Simulation execution | **PASS** | 48 decks; 0 failed; 0 not executed. |  |
| Power and reference rails | **WARNING** | V_Boost=0.66170496; VREF_2V048=0.296546701; VREF_1V024=0.680819542. | Portable models are not production sign-off models. |
| Core LIF activity | **WARNING** | AP rising edges=0; Vm threshold crossings=0. |  |
| Active-high Peak_Window and Spike_Out | **WARNING** | Peak_Window edges=0; Spike_Out edges=0. |  |
| U23 closed-loop stimulus transfer | **WARNING** | Maximum linear-equation residual=unavailable V. | Residual is interpreted only while U23 is not clipping. |
| RV4 one-hot monotonic selector | **WARNING** | Observed high outputs=[['S0'], ['S0', 'S1'], ['S1', 'S2'], ['S3'], ['S4']]. |  |
| Power-off state | **PASS** | VDD_end=0.000876163986 V. |  |
| Cold-start and low-battery operation | **WARNING** | 06_cold_start_dynamic_battery: VDD=-7.69570818e-06..0.701003027 V, VREF2=0.438434053 V; 07_low_battery_high_impedance: VDD=1.40656109e-05..0.701002906 V, VREF2=0.555849644 V | Battery chemistry and converter fallback remain approximate. |
| External output loading | **WARNING** | 10 kOhm Vm_Ext peak reduction=0.004176555000000026 V; loaded Spike_Out edges=0. |  |
| RV1 leak-reference control | **PASS** | V_Leak end values=[0.0290713251, 0.147139142, 0.265378656]. |  |
| RV2 membrane-leak-rate control | **WARNING** | AP periods=[]; Vm_Int maxima=[0.0114157916, 0.0103844092, 0.00979871664]. |  |
| RV3 adaptation control | **WARNING** | Vw maxima=[1.79897911e-05, 1.79881874e-05, 1.79738852e-05]; AP periods=[]. |  |
| RV5 synaptic-decay control | **PASS** | V_Syn_State end values=[0.00465864659, 0.00772245929, 0.0227512323]. |  |
| Synaptic sign, midpoint and RV6-RV9 weight controls | **WARNING** | Syn1 Vm_Int max low/mid/high=[0.0103856783, 0.0103856701, 0.0103857277]; state max=[0.00772414644, 0.00772245929, 0.00772808764]; Syn2 Vm_Int max low/mid/high=[0.0103856899, 0.0103857213, 0.0103857613]; state max=[0.00771691551, 0.00772245932, 0.00772808738]; Syn3 Vm_Int max low/mid/high=[0.0103856221, 0.010385709, 0.0103857029]; state max=[0.00771691524, 0.00772245556, 0.0077280878]; Syn4 Vm_Int max low/mid/high=[0.0103857514, 0.0103856813, 0.010385788]; state max=[0.00771691489, 0.00772245568, 0.00772808792] | Direction is checked at the physical membrane response; exact biological equivalence is not claimed. |
| Temperature sweep | **WARNING** | 50_temperature_25p0C: VDD_end=0.70100329, AP=0; 50_temperature_60p0C: VDD_end=0.701876064, AP=0; 50_temperature_m20p0C: VDD_end=0.701003343, AP=1 | Portable model temperature laws are incomplete. |
| Component-tolerance seeds | **WARNING** | Five deterministic seeds executed; rail-level failures=['60_tolerance_seed_1', '60_tolerance_seed_2', '60_tolerance_seed_3', '60_tolerance_seed_4', '60_tolerance_seed_5']. | Five seeds are a regression screen, not a production-yield Monte Carlo study. |
| ESD and sustained external-fault survival | **NOT CLAIMED** | Protection devices are represented only for normal-signal loading and limited clamp-transient exploration. | No SPICE result from this suite constitutes IEC ESD qualification or sustained-overvoltage survival proof. |
