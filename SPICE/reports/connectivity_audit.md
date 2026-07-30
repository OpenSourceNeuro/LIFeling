# LIFeling connectivity and pin-map audit

Netlist: `LIFeling.net`
Export: `2026-07-29T20:56:15` using `Eeschema 10.0.1`

| Check | Severity | Result | Evidence |
|---|---|---|---|
| `pinmap.U4.tlv7044` | error | **PASS** | All 14 physical pin functions match. |
| `pinmap.U5.tlv7044` | error | **PASS** | All 14 physical pin functions match. |
| `pinmap.U6.tlv7044` | error | **PASS** | All 14 physical pin functions match. |
| `pinmap.family.mcp6004` | error | **PASS** | All physical pin functions match. |
| `pinmap.family.tlv9001` | error | **PASS** | All physical pin functions match. |
| `pinmap.family.tlv9041` | error | **PASS** | All physical pin functions match. |
| `pinmap.family.tlv7031` | error | **PASS** | All physical pin functions match. |
| `pinmap.family.ts5a3166` | error | **PASS** | All physical pin functions match. |
| `pinmap.family.tps610995` | error | **PASS** | All physical pin functions match. |
| `topology.rv4.comparators` | error | **PASS** | Physical comparator channels match the one-hot window equations. |
| `topology.rv4.capacitors` | error | **PASS** | Monotonic physical switch/capacitor chain confirmed. |
| `topology.peak_window.active_high` | error | **PASS** | U6A pins: OUT=Peak_Window, IN+=Spike_Pulse, IN-=V_Threshold; R51=['Peak_Window', 'VDD']; U14/U20 controls=[('U14', '4'), ('U20', '4')]. |
| `topology.stimulus.u23` | error | **PASS** | Electrical topology matches the intended transfer; the output-to-Vm resistor is physically R96, not R97. |
| `naming.stimulus.r96_r97` | warning | **WARNING** | R97 is absent. R96 is 100 kΩ between V_Stim_Drive and Vm_Int; there is no VDD pull-up on V_Stim_Drive. |
| `topology.u6b.unused` | error | **PASS** | INB+=VDD, INB-=GNDREF, OUTB=unconnected-(U6B-OUTB-Pad7) |
| `power.boost.tps610995_fixed_output` | warning | **WARNING** | Netlist U7 value=TPS610995DRVR. Portable switching model VSET is locked to 3.6 V; previous 3.3 V behavioural assumptions are rejected. |
| `pinmap.u21.ref3020_physical` | error | **PASS** | KiCad mapping: pin1=VDD, pin2=VREF_2V048, pin3=GNDREF. |
| `model.u21.ref3020_vendor_terminal_order` | warning | **WARNING** | The physical package order is verified, but the downloaded model's actual .SUBCKT terminal order must still be inspected and wrapped before vendor instantiation. |
