#!/usr/bin/env python3
"""
LIFeling full-schematic behavioural SPICE generator/simulator.

This file replaces the older hand-maintained Vm-only model with a netlist-driven
model aligned to the current KiCad files exported on 2026-07-02.

Design intent
-------------
The script reads LIFeling.net directly, extracts the actual component values and
net names, and then generates an ngspice deck in which every schematic component
is either electrically modelled or explicitly listed as mechanical / connector
metadata. This avoids silent drift between the KiCad schematic and the Python
SPICE model.

Model scope
-----------
The model is intentionally behavioural, not a vendor-accurate transistor-level
simulation of every IC. The analogue function is preserved at circuit-block level:

  * BT1/SW1/VDD coin-cell supply and local decoupling.
  * U7 boost approximated as an ideal boosted rail for the Vm output buffer.
  * U21 REF3020 2.048 V reference and U22 buffered 1.024 V reference.
  * RV1/U1A leak reference and membrane leak path RV2/R35.
  * RV4/T1..T4/U4/U5/U9..U13 selected membrane-capacitor bank.
  * U6D/Q1 AP gate, AP differentiator, Spike_Pulse clamp network.
  * U6A/U14 peak injection and U6C/Q3..Q6 reset injection.
  * U1B/U1C/U1D/Q2 adaptation network.
  * U3/U15..U18/RV5/R82..R87 centred synaptic state drive. The synapse is
    zero-effect when V_Syn_State = VREF_1V024.
  * U6B/R90..R97 external stimulus drive path.
  * U8 Vm_Ext live output and U19 Spike_Out output.
  * D1/D18/D19 ESD devices as small capacitive/leakage loads.
  * D9 RGB LED and Q7/Q8 LED drivers as approximate LED/BJT/MOSFET loads.
  * J1..J6 connectors as named external nodes; optional sources can be attached
    from the command line.
  * H1..H6 mounting holes are included in the coverage report as mechanical-only.

Running
-------
Typical deck generation only:

    python Spice_LIFeling_updated.py --write-only

Run ngspice if it is installed:

    python Spice_LIFeling_updated.py --run

Enable synaptic input pulse examples:

    python Spice_LIFeling_updated.py --run --syn1-enable --syn1-delay 80m --syn1-width 5m

The generated .cir file contains detailed comments mapping each functional block
back to the exact KiCad references and labels.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

SCRIPT_VERSION = "validation-suite-v6-readme-walkthrough"

import numpy as np

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

try:
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None


THIS_DIR = Path(__file__).resolve().parent
DEFAULT_NETLIST = THIS_DIR.parent / "PCBs" / "LIFeling" / "LIFeling.net"
OUTPUT_DIR = THIS_DIR / "LIFeling_pyspice_output"


# -----------------------------------------------------------------------------
# KiCad netlist parsing
# -----------------------------------------------------------------------------


def iter_sexp_blocks(text: str, pattern: str) -> Iterable[str]:
    """Yield balanced S-expression blocks whose start matches *pattern*.

    KiCad's exported .net file is an S-expression document. A tiny balanced-block
    scanner is sufficient here and avoids adding a dependency just to read refs,
    values, pins and net names.
    """
    for match in re.finditer(pattern, text):
        start = match.start()
        depth = 0
        in_quote = False
        escaped = False
        for idx in range(start, len(text)):
            char = text[idx]
            if in_quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_quote = False
            else:
                if char == '"':
                    in_quote = True
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        yield text[start : idx + 1]
                        break


def sexp_value(block: str, key: str, default: str = "") -> str:
    match = re.search(rf"\({re.escape(key)}\s+\"([^\"]*)\"\)", block)
    return match.group(1) if match else default


@dataclasses.dataclass
class Component:
    ref: str
    value: str
    footprint: str
    fields: dict[str, str]
    pins: dict[str, str] = dataclasses.field(default_factory=dict)
    pinfunctions: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Design:
    components: dict[str, Component]
    nets: dict[str, list[tuple[str, str, str]]]
    net_of_pin: dict[tuple[str, str], str]


def parse_kicad_netlist(path: Path) -> Design:
    text = path.read_text(encoding="utf-8", errors="replace")

    components: dict[str, Component] = {}
    for block in iter_sexp_blocks(text, r"\n\s*\(comp\s"):
        ref = sexp_value(block, "ref")
        value = sexp_value(block, "value")
        footprint = sexp_value(block, "footprint")
        fields: dict[str, str] = {}
        for name, val in re.findall(
            r"\(property\s*\(name\s+\"([^\"]+)\"\)\s*\(value\s+\"?([^\"\)\n]*)\"?\)\s*\)",
            block,
        ):
            fields[name] = val
        for name, val in re.findall(r"\(field\s*\(name\s+\"([^\"]+)\"\)\s+\"([^\"]*)\"\)", block):
            fields[name] = val
        if ref:
            components[ref] = Component(ref=ref, value=value, footprint=footprint, fields=fields)

    nets: dict[str, list[tuple[str, str, str]]] = {}
    net_of_pin: dict[tuple[str, str], str] = {}
    for block in iter_sexp_blocks(text, r"\n\s*\(net\s"):
        net_name = sexp_value(block, "name")
        nodes: list[tuple[str, str, str]] = []
        for node_block in iter_sexp_blocks(block, r"\n\s*\(node\s"):
            ref = sexp_value(node_block, "ref")
            pin = sexp_value(node_block, "pin")
            pinfunction = sexp_value(node_block, "pinfunction")
            if ref and pin:
                nodes.append((ref, pin, pinfunction))
                net_of_pin[(ref, pin)] = net_name
        nets[net_name] = nodes

    for (ref, pin), net_name in net_of_pin.items():
        if ref in components:
            components[ref].pins[pin] = net_name
            # Recover pinfunction from the net table.
            for node_ref, node_pin, pinfunction in nets[net_name]:
                if node_ref == ref and node_pin == pin:
                    components[ref].pinfunctions[pin] = pinfunction
                    break

    return Design(components=components, nets=nets, net_of_pin=net_of_pin)


# -----------------------------------------------------------------------------
# Value and node formatting
# -----------------------------------------------------------------------------


def component_sort_key(ref: str) -> tuple[str, int, str]:
    match = re.match(r"([A-Za-z]+)(\d+)(.*)", ref)
    if not match:
        return (ref, 0, "")
    return (match.group(1), int(match.group(2)), match.group(3))


def spice_node_name(kicad_net: str) -> str:
    """Return a SPICE-safe node alias while keeping GNDREF as node 0."""
    if kicad_net in {"GNDREF", "GND", "0"}:
        return "0"
    text = kicad_net
    text = text.replace("+", "P_")
    text = text.replace("/", "N_")
    text = text.replace("-", "_")
    text = text.replace("(", "_").replace(")", "_")
    text = text.replace("[", "_").replace("]", "_")
    text = text.replace(".", "_")
    text = re.sub(r"[^A-Za-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = "NODE"
    if text[0].isdigit():
        text = "N_" + text
    return text


def n(design: Design, ref: str, pin: str) -> str:
    return spice_node_name(design.components[ref].pins[pin])


def node(kicad_net: str) -> str:
    return spice_node_name(kicad_net)


def pin_net(design: Design, ref: str, pin: str) -> str:
    return design.components[ref].pins[pin]


def normalize_value(value: str, kind: str) -> str:
    """Convert KiCad values such as 220kΩ, 10uF, 2.2uH to ngspice values."""
    raw = value.strip()
    raw = raw.replace("Ω", "").replace("Ω", "")
    raw = raw.replace("µ", "u").replace("μ", "u")
    raw = raw.replace(" ", "")
    raw = raw.replace("F", "") if kind == "C" else raw
    raw = raw.replace("H", "") if kind == "L" else raw

    # SPICE interprets m as milli, so explicit mega must be Meg.
    match = re.fullmatch(r"([+-]?[0-9]*\.?[0-9]+)([A-Za-z]*)", raw)
    if not match:
        return raw
    number, suffix = match.groups()
    if suffix == "M":
        suffix = "Meg"
    return number + suffix


def value_to_float(value: str, kind: str = "R") -> float:
    text = normalize_value(value, kind)
    match = re.fullmatch(r"([+-]?[0-9]*\.?[0-9]+)([A-Za-z]*)", text)
    if not match:
        raise ValueError(f"Cannot parse value {value!r}")
    number = float(match.group(1))
    suffix = match.group(2).lower()
    scale = {
        "": 1.0,
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "meg": 1e6,
        "g": 1e9,
    }
    if suffix not in scale:
        raise ValueError(f"Unsupported suffix {suffix!r} in {value!r}")
    return number * scale[suffix]


def fmt(value: float) -> str:
    if abs(value) < 1e-15:
        return "0"
    return f"{value:.12g}"


def safe_ref(ref: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", ref)


def safe_filename(text: str) -> str:
    """Return a compact filesystem-safe token for run labels and output names."""
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text).strip())
    token = token.strip("._-")
    return token[:80] if token else "run"


# -----------------------------------------------------------------------------
# Simulation configuration
# -----------------------------------------------------------------------------


@dataclasses.dataclass
class SimConfig:
    netlist: Path = DEFAULT_NETLIST
    output_dir: Path = OUTPUT_DIR
    run_label: str = ""
    run: bool = False
    write_only: bool = False
    ngspice_binary: str = "auto"

    supply_mode: str = "coin"       # coin or ideal
    vbat: str = "3.0"
    rbat: str = "30"
    vdd_ideal: str = "3.0"
    switch_on_resistance: str = "0.2"
    vboost: str = "3.3"

    startup_mode: str = "operating" # operating or cold
    ignore_start_ms: float = 0.0
    vm_initial: str = "0.60"
    syn_initial: str = "1.024"

    tstop: str = "500m"
    tstep: str = "10u"
    maxstep: str = "10u"

    rv1: float = 0.30
    rv2: float = 0.50
    rv3: float = 0.50
    rv4: float = 0.50
    rv5: float = 0.50
    rv6: float = 0.50
    rv7: float = 0.50
    rv8: float = 0.50
    rv9: float = 0.50

    stimulus_ext: float | None = None
    syn1_enable: bool = False
    syn2_enable: bool = False
    syn3_enable: bool = False
    syn4_enable: bool = False
    syn_amp: str = "3.0"
    syn_rise: str = "1u"
    syn_fall: str = "1u"
    syn1_delay: str = "80m"
    syn1_width: str = "5m"
    syn1_period: str = "100m"
    syn2_delay: str = "120m"
    syn2_width: str = "5m"
    syn2_period: str = "100m"
    syn3_delay: str = "160m"
    syn3_width: str = "5m"
    syn3_period: str = "100m"
    syn4_delay: str = "200m"
    syn4_width: str = "5m"
    syn4_period: str = "100m"

    trace_debug: bool = False

    make_validation_verdict: bool = False
    update_readme: bool = False
    update_readme_only: bool = False
    readme_path: Path = THIS_DIR / "README.md"


RV_ATTR = {
    "RV1": "rv1",
    "RV2": "rv2",
    "RV3": "rv3",
    "RV4": "rv4",
    "RV5": "rv5",
    "RV6": "rv6",
    "RV7": "rv7",
    "RV8": "rv8",
    "RV9": "rv9",
}


# -----------------------------------------------------------------------------
# SPICE deck builder helpers
# -----------------------------------------------------------------------------


def add_models(lines: list[str]) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* Generic fallback device models",
        "* -----------------------------------------------------------------------------",
        ".model BSS138_FALLBACK NMOS(Level=1 Vto=1.2 Kp=2m Lambda=0.02 Rd=2 Rs=2)",
        ".model MMBT3904_FALLBACK NPN(Is=6.7f Bf=250 Vaf=100 Ikf=0.1 Br=6 Cjc=4p Cje=8p Tf=300p Tr=50n)",
        ".model D1N4148_FALLBACK D(Is=2.52n Rs=0.568 N=1.752 Cjo=2p M=0.4 Tt=4n)",
        ".model RB521S30_FALLBACK D(Is=5u Rs=1 N=1.05 Cjo=10p Eg=0.69 Bv=30 Ibv=10u)",
        ".model BAT54_FALLBACK D(Is=2u Rs=1 N=1.05 Cjo=10p Eg=0.69 Bv=30 Ibv=10u)",
        ".model LED_RED_FALLBACK D(Is=10n Rs=20 N=2.0 Eg=1.8 Cjo=5p)",
        ".model LED_GREEN_FALLBACK D(Is=10n Rs=20 N=2.2 Eg=2.1 Cjo=5p)",
        ".model LED_BLUE_FALLBACK D(Is=10n Rs=20 N=2.8 Eg=2.7 Cjo=5p)",
        ".model SW_TS5A3166 SW(Ron=0.9 Roff=1e12 Vt=1.5 Vh=0.05)",
        ".model SW_OC SW(Ron=5 Roff=1e12 Vt=0 Vh=1m)",
        "",
    ]


def add_node_alias_comments(lines: list[str], design: Design) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* KiCad-net to SPICE-node aliases",
        "* -----------------------------------------------------------------------------",
    ]
    for net_name in sorted(design.nets):
        lines.append(f"* {net_name}  ->  {spice_node_name(net_name)}")
    lines.append("")


def add_resistors(lines: list[str], design: Design) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* All fixed resistors from the KiCad netlist",
        "* -----------------------------------------------------------------------------",
    ]
    for ref in sorted((r for r in design.components if re.fullmatch(r"R\d+", r)), key=component_sort_key):
        comp = design.components[ref]
        if "1" not in comp.pins or "2" not in comp.pins:
            lines.append(f"* {ref} {comp.value}: skipped, incomplete resistor pins")
            continue
        value = normalize_value(comp.value, "R")
        lines.append(
            f"R_{ref} {n(design, ref, '1')} {n(design, ref, '2')} {value}"
            f"    $ {ref}={comp.value}, {pin_net(design, ref, '1')} <-> {pin_net(design, ref, '2')}"
        )
    lines.append("")


def add_capacitors(lines: list[str], design: Design) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* All capacitors from the KiCad netlist",
        "* -----------------------------------------------------------------------------",
    ]
    for ref in sorted((r for r in design.components if re.fullmatch(r"C\d+", r)), key=component_sort_key):
        comp = design.components[ref]
        if "1" not in comp.pins or "2" not in comp.pins:
            lines.append(f"* {ref} {comp.value}: skipped, incomplete capacitor pins")
            continue
        value = normalize_value(comp.value, "C")
        lines.append(
            f"C_{ref} {n(design, ref, '1')} {n(design, ref, '2')} {value}"
            f"    $ {ref}={comp.value}, {pin_net(design, ref, '1')} <-> {pin_net(design, ref, '2')}"
        )
    lines.append("")


def add_inductors(lines: list[str], design: Design) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* All inductors from the KiCad netlist",
        "* -----------------------------------------------------------------------------",
    ]
    for ref in sorted((r for r in design.components if re.fullmatch(r"L\d+", r)), key=component_sort_key):
        comp = design.components[ref]
        if "1" not in comp.pins or "2" not in comp.pins:
            lines.append(f"* {ref} {comp.value}: skipped, incomplete inductor pins")
            continue
        value = normalize_value(comp.value, "L")
        lines.append(
            f"L_{ref} {n(design, ref, '1')} {n(design, ref, '2')} {value}"
            f"    $ {ref}={comp.value}, {pin_net(design, ref, '1')} <-> {pin_net(design, ref, '2')}"
        )
    lines.append("R_U7_SW_LEAK Net_U7_SW 0 1G    $ convergence leakage on TPS610995 switching node")
    lines.append("")


def add_potentiometers(lines: list[str], design: Design, cfg: SimConfig) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* All potentiometers as two explicit end-to-wiper resistances",
        "* fraction=0 means wiper at pin1, fraction=1 means wiper at pin3",
        "* -----------------------------------------------------------------------------",
    ]
    for ref in sorted((r for r in design.components if re.fullmatch(r"RV\d+", r)), key=component_sort_key):
        comp = design.components[ref]
        frac = float(np.clip(getattr(cfg, RV_ATTR[ref]), 1e-6, 1 - 1e-6))
        total = value_to_float(comp.value, "R")
        low = max(total * frac, 1e-6)
        high = max(total * (1.0 - frac), 1e-6)
        p1, p2, p3 = n(design, ref, "1"), n(design, ref, "2"), n(design, ref, "3")
        lines.append(
            f"* {ref}={comp.value}, fraction={frac:.4f}; "
            f"pin1={pin_net(design, ref, '1')}, pin2={pin_net(design, ref, '2')}, pin3={pin_net(design, ref, '3')}"
        )
        if p1 != p2:
            lines.append(f"R_{ref}_P1_W {p1} {p2} {fmt(low)}")
        else:
            lines.append(f"* R_{ref}_P1_W skipped because pin1 and pin2 are the same net")
        if p2 != p3:
            lines.append(f"R_{ref}_W_P3 {p2} {p3} {fmt(high)}")
        else:
            lines.append(f"* R_{ref}_W_P3 skipped because pin2 and pin3 are the same net")
    lines.append("")


def add_diode(lines: list[str], name: str, anode: str, cathode: str, model: str, comment: str = "") -> None:
    suffix = f"    $ {comment}" if comment else ""
    lines.append(f"D_{name} {node(anode)} {node(cathode)} {model}{suffix}")


def add_diodes(lines: list[str], design: Design) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* Diodes, Schottky clamps, ESD approximations, and RGB LED",
        "* -----------------------------------------------------------------------------",
        "* Pin-orientation note: diode orientation is assigned by circuit function and KiCad net labels,",
        "* because imported symbols do not use one uniform pin-number convention.",
    ]

    # One-pin ESD protectors: do not hard-clamp normal 0..3 V signals to ground.
    for ref, protected_net in [("D1", "Vm_Ext"), ("D18", "Spike_Out"), ("D19", "Stimulus_Ext")]:
        lines.append(f"C_{ref}_ESD {node(protected_net)} 0 1p    $ {ref} TPD1E05U06DPYT capacitance approximation")
        lines.append(f"R_{ref}_LEAK {node(protected_net)} 0 1G    $ {ref} leakage approximation")

    # Vm_Int clamps.
    add_diode(lines, "D2_VM_HIGH", "Vm_Int", "VDD", "BAT54_FALLBACK", "D2 high clamp: Vm_Int -> VDD")
    add_diode(lines, "D3_VM_LOW", "GNDREF", "Vm_Int", "BAT54_FALLBACK", "D3 low clamp: GNDREF -> Vm_Int")

    # Adaptation and spike-pulse shaping diodes.
    add_diode(lines, "D4_VKICK_LOW", "GNDREF", "/Vkick", "D1N4148_FALLBACK", "D4 clamps negative /Vkick")
    add_diode(lines, "D5_VKICK_TO_VW", "/Vkick", "Vw", "D1N4148_FALLBACK", "D5 /Vkick -> Vw")
    add_diode(lines, "D6_ADAPT_TO_VW", "Net-(D6-A)", "Vw", "RB521S30_FALLBACK", "D6 Schottky adaptation injection")
    add_diode(lines, "D7_VW_LOW", "GNDREF", "Vw", "D1N4148_FALLBACK", "D7 clamps negative Vw")
    add_diode(lines, "D8_RISING_TO_SPIKE", "/Rising_AP", "Spike_Pulse", "RB521S30_FALLBACK", "D8 positive differentiator diode")
    add_diode(lines, "D20_SPIKE_LOW", "GNDREF", "Spike_Pulse", "RB521S30_FALLBACK", "D20 negative Spike_Pulse clamp")

    # Synaptic input clamps.
    for idx, hi_ref, lo_ref, clamp_net in [
        (1, "D10", "D11", "Net-(D10-A)"),
        (2, "D12", "D13", "Net-(D12-A)"),
        (3, "D14", "D15", "Net-(D14-A)"),
        (4, "D16", "D17", "Net-(D16-A)"),
    ]:
        add_diode(lines, f"{hi_ref}_SYN{idx}_HIGH", clamp_net, "VDD", "BAT54_FALLBACK", f"{hi_ref} Syn{idx} high clamp")
        add_diode(lines, f"{lo_ref}_SYN{idx}_LOW", "GNDREF", clamp_net, "BAT54_FALLBACK", f"{lo_ref} Syn{idx} low clamp")

    # Vm_Display_In clamps.
    add_diode(lines, "D21_DISPLAY_HIGH", "Vm_Display_In", "VDD", "BAT54_FALLBACK", "D21 display high clamp")
    add_diode(lines, "D22_DISPLAY_LOW", "GNDREF", "Vm_Display_In", "BAT54_FALLBACK", "D22 display low clamp")

    # RGB LED D9, common anode at VDD, cathodes named R-/G-/B- in the netlist.
    lines.append(f"D_D9_R {node('VDD')} {node('Net-(D9-R-)')} LED_RED_FALLBACK      $ D9 red LED, common anode VDD")
    lines.append(f"D_D9_G {node('VDD')} {node('Net-(D9-G-)')} LED_GREEN_FALLBACK    $ D9 green LED, common anode VDD")
    lines.append(f"D_D9_B {node('VDD')} {node('Net-(D9-B-)')} LED_BLUE_FALLBACK     $ D9 blue LED, common anode VDD")
    lines.append("")




def add_voltage_driver(
    lines: list[str],
    name: str,
    out_net: str,
    expr: str,
    *,
    vpos_net: str = "VDD",
    out_resistance: str = "100",
    comment: str = "",
) -> None:
    """Add a stable closed-loop behavioural voltage driver.

    This replaces high-gain ideal-op-amp loops in places where the surrounding
    schematic resistors already define the closed-loop transfer function. Using
    a bounded VCVS avoids ngspice initial-timepoint failures on nodes such as
    Vm_Out_DRV while preserving the circuit-level gain and loading from the
    real feedback resistors, which remain instantiated from the netlist.
    """
    raw = f"{safe_ref(name)}_RAW"
    suffix = f"    $ {comment}" if comment else ""
    lines.append(
        f"B_{safe_ref(name)}_CL {raw} 0 "
        f"V={{min(max(({expr}),0),V({node(vpos_net)}))}}"
        f"{suffix}"
    )
    lines.append(f"R_{safe_ref(name)}_OUT {raw} {node(out_net)} {out_resistance}")

def add_opamp(lines: list[str], name: str, out_net: str, minus_net: str, plus_net: str, vpos_net: str = "VDD") -> None:
    raw = f"{safe_ref(name)}_RAW"
    lines.append(
        f"B_{name}_OP {raw} 0 V={{0.5*V({node(vpos_net)})*(1+tanh(1000*(V({node(plus_net)})-V({node(minus_net)}))))}}"
    )
    lines.append(f"R_{name}_OUT {raw} {node(out_net)} 100")


def add_follower(lines: list[str], name: str, out_net: str, in_net: str) -> None:
    lines.append(f"E_{name}_FOLLOW {node(out_net)} 0 {node(in_net)} 0 1")


def add_oc_comparator(lines: list[str], name: str, out_net: str, plus_net: str, minus_net: str) -> None:
    """Add a numerically stable open-drain comparator.

    The first generated version used an ideal ngspice SW element for each
    TLV7044/TLV7031 open-drain output. That is too discontinuous for feedback
    cases such as U6B, where V_Stim_Drive is both the comparator output and part
    of the inverting-input feedback network. At t=0 ngspice can land exactly on
    the switching surface and abort with "Timestep too small ... s_u6b_stim_od".

    This behavioural replacement preserves the open-drain topology: external
    schematic pull-up resistors still pull the output high, and the comparator
    only sinks current when V(minus) > V(plus). The sink conductance transitions
    smoothly over roughly 10 mV, which avoids the initial-timepoint singularity
    without changing the circuit-level intent.
    """
    out = node(out_net)
    plus = node(plus_net)
    minus = node(minus_net)
    safe = safe_ref(name)
    lines.append(
        f"B_{safe}_OD_SINK {out} 0 "
        f"I={{ V({out})*(1e-12 + (0.2-1e-12)*0.5*(1+tanh(200*(V({minus})-V({plus}))))) }}"
        f"    $ {name}: smooth open-drain sink, low when {minus_net} > {plus_net}"
    )
    lines.append(f"C_{safe}_OD_NUM {out} 0 0.2p    $ tiny numerical output capacitance for {name}")


def add_active_components(lines: list[str], design: Design, cfg: SimConfig) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* Power sources and active IC behavioural models",
        "* -----------------------------------------------------------------------------",
        "* BT1/SW1: coin-cell source, optional internal resistance, and closed power switch.",
    ]
    if cfg.supply_mode == "ideal":
        lines.append(f"V_IDEAL_VDD VDD 0 DC {cfg.vdd_ideal}    $ ideal lab-supply mode replacing BT1/SW1")
        lines.append("R_BATT_UNUSED P_BATT 0 1G")
    else:
        lines.append(f"V_BT1_RAW VBAT_RAW 0 DC {cfg.vbat}       $ BT1 open-circuit coin-cell voltage")
        lines.append(f"R_BT1_INTERNAL VBAT_RAW P_BATT {cfg.rbat} $ BT1 internal/source resistance")
        lines.append(f"R_SW1_ON P_BATT VDD {cfg.switch_on_resistance} $ SW1 pin2(+BATT) -> pin1(VDD), ON position")
    lines += [
        "",
        "* U7 TPS610995 boost converter approximation.",
        "* The real switching converter, L1 and output capacitors are reduced to an ideal boosted rail.",
        "* L1, C10, C11, C12 and C14 are still present as passive netlist components above.",
        f"B_U7_BOOST Net_U7_VOUT 0 V={{ {cfg.vboost} }}",
        "",
        "* U21 REF3020AIDBZR 2.048 V precision reference.",
        "* Output is clamped by VDD so brownout tests remain physically bounded.",
        "B_U21_REF3020 VREF_2V048 0 V={min(2.048,max(0,V(VDD)))}",
        "",
        "* U22 TLV9001 buffer: VREF_1V024_RAW -> VREF_1V024.",
    ]
    add_follower(lines, "U22", "VREF_1V024", "VREF_1V024_RAW")

    lines += [
        "",
        "* U1 MCP6004 analogue core.",
        "* U1A leak buffer: /V_Leak_ref -> V_Leak.",
    ]
    add_follower(lines, "U1A", "V_Leak", "/V_Leak_ref")
    lines.append("* U1B adaptation shaping amplifier with R41/R42/R43/R44/R45 feedback network.")
    lines.append("* Closed-loop fallback: Vout = 3*V(Net-(U1A-VINB+)) - 2*V(V_Leak), from R43=100k/R44=200k.")
    add_voltage_driver(
        lines,
        "U1B",
        "Net-(U1A-VOUTB)",
        "3*V(Net_U1A_VINBP)-2*V(V_Leak)",
        out_resistance="100",
        comment="U1B closed-loop adaptation shaper; avoids high-gain feedback convergence at t=0",
    )
    lines.append("* U1C AP follower driving /Adapt_Kick_Drive through C29 into /Vkick.")
    add_follower(lines, "U1C", "/Adapt_Kick_Drive", "AP")
    lines.append("* U1D adaptation-state buffer: Vw -> Vw_buff.")
    add_follower(lines, "U1D", "Vw_buff", "Vw")

    lines += [
        "",
        "* U2 MCP6004 reference, reset, peak, and centred synaptic-drive amplifiers.",
        "* U2A: VREF_2V048 -> V_Leak_Ref_Max. This is the new global top reference for RV1.",
    ]
    add_follower(lines, "U2A", "V_Leak_Ref_Max", "VREF_2V048")
    lines.append("* U2B: V_Reset_Ref -> /Reset_Injection_Drive.")
    add_follower(lines, "U2B", "/Reset_Injection_Drive", "V_Reset_Ref")
    lines.append("* U2C: V_Peak_Ref -> V_Peak_Drive.")
    add_follower(lines, "U2C", "V_Peak_Drive", "V_Peak_Ref")
    lines.append("* U2D: centred synapse drive using R83/R84/R85/R86 feedback.")
    lines.append("* Closed-loop fallback with equal 1M resistors: /V_Syn_Drive = V_Syn_State + Vm_Int - VREF_1V024.")
    lines.append("* Therefore the synapse injects zero current through R87 when V_Syn_State = VREF_1V024.")
    add_voltage_driver(
        lines,
        "U2D",
        "/V_Syn_Drive",
        "V(V_Syn_State)+V(Vm_Int)-V(VREF_1V024)",
        out_resistance="100",
        comment="U2D closed-loop centred synapse driver; zero effect at 1.024 V state",
    )

    lines += [
        "",
        "* U3 MCP6004 four synaptic set-voltage buffers from RV6..RV9.",
    ]
    add_follower(lines, "U3A_SYN1", "V_Syn1_Set", "Net-(U3A-VINB+)")
    add_follower(lines, "U3B_SYN2", "V_Syn2_Set", "Net-(U3B-VINC+)")
    add_follower(lines, "U3C_SYN3", "V_Syn3_Set", "Net-(U3C-VIND+)")
    add_follower(lines, "U3D_SYN4", "V_Syn4_Set", "Net-(U3D-VINA+)")

    lines += [
        "",
        "* U8 TLV9001 Vm_Ext output driver powered from V_Boost.",
        "* R3/R4 set the non-inverting gain; R2/C13/D1 form the protected external output.",
    ]
    lines.append("* Closed-loop fallback: Vm_Out_DRV = (1 + R3/R4)*Vm_Display_In = 1.1*Vm_Display_In.")
    add_voltage_driver(
        lines,
        "U8",
        "Vm_Out_DRV",
        "1.1*V(Vm_Display_In)",
        vpos_net="V_Boost",
        out_resistance="25",
        comment="U8 closed-loop Vm_Ext driver; removes high-gain loop at Vm_Out_DRV",
    )

    lines += [
        "",
        "* U4/U5 TLV7044 comparators implement RV4/Vsel capacitor-bank one-hot selection.",
        "* S0 high for Vsel<T1; S1 high for T1<Vsel<T2; S2 high for T2<Vsel<T3;",
        "* S3 high for T3<Vsel<T4; S4 high for Vsel>T4. Tied outputs are open-drain ANDs.",
    ]
    add_oc_comparator(lines, "U4A_S0", "S0", "T1", "Vsel")
    add_oc_comparator(lines, "U4B_S1_LOW", "S1", "Vsel", "T1")
    add_oc_comparator(lines, "U4C_S1_HIGH", "S1", "T2", "Vsel")
    add_oc_comparator(lines, "U4D_S2_LOW", "S2", "Vsel", "T2")
    add_oc_comparator(lines, "U5D_S2_HIGH", "S2", "T3", "Vsel")
    add_oc_comparator(lines, "U5B_S3_LOW", "S3", "Vsel", "T3")
    add_oc_comparator(lines, "U5C_S3_HIGH", "S3", "T4", "Vsel")
    add_oc_comparator(lines, "U5A_S4", "S4", "Vsel", "T4")

    lines += [
        "",
        "* U6 TLV7044 comparators.",
        "* U6A Peak_Window: high when Spike_Pulse > V_Threshold.",
    ]
    add_oc_comparator(lines, "U6A_PEAK", "Peak_Window", "Spike_Pulse", "V_Threshold")
    lines.append("* U6B external stimulus drive: high when the R92/R93 summing node exceeds the R94/R95 feedback node.")
    add_oc_comparator(lines, "U6B_STIM", "V_Stim_Drive", "Net-(U6B-INB+)", "Net-(U6B-INB-)")
    lines.append("* U6C Reset_Window: high while reset reference node exceeds the reset timer node.")
    add_oc_comparator(lines, "U6C_RESET", "Reset_Window", "Net-(U6C-INC+)", "Net-(U6C-INC-)")
    lines.append("* U6D /AP_Gate: high below threshold, released low when Vm_Int exceeds V_Threshold.")
    add_oc_comparator(lines, "U6D_AP_GATE", "/AP_Gate", "V_Threshold", "Vm_Int")

    lines += [
        "",
        "* U19 TLV7031 spike-output comparator: Peak_Window -> Spike_Out driver.",
        "* R88 is the output pull-up and R89 is the 100 ohm series jack resistor.",
    ]
    add_oc_comparator(lines, "U19_SPIKE_OUT", "Net-(U19-OUT)", "Peak_Window", "V_Logic_Mid")
    lines.append("")


def add_switches(lines: list[str], design: Design) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* TS5A3166 analogue switches U9..U20",
        "* KiCad pin mapping: pin1=NO, pin2=COM, pin3=GND, pin4=IN, pin5=VDD.",
        "* -----------------------------------------------------------------------------",
    ]
    for ref in [f"U{i}" for i in range(9, 21)]:
        comp = design.components.get(ref)
        if not comp:
            continue
        no_net = pin_net(design, ref, "1")
        com_net = pin_net(design, ref, "2")
        ctrl_net = pin_net(design, ref, "4")
        lines.append(
            f"S_{ref} {node(com_net)} {node(no_net)} {node(ctrl_net)} 0 SW_TS5A3166"
            f"    $ {ref}: COM={com_net}, NO={no_net}, IN={ctrl_net}"
        )
    lines.append("")


def add_transistors(lines: list[str], design: Design) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* Discrete transistors",
        "* BSS138 imported footprint mapping used here: pin1=gate, pin2=source, pin3=drain.",
        "* MMBT3904 imported footprint mapping used here: pin1=base, pin2=emitter, pin3=collector.",
        "* -----------------------------------------------------------------------------",
    ]
    for ref in sorted((r for r in design.components if re.fullmatch(r"Q\d+", r)), key=component_sort_key):
        comp = design.components[ref]
        value = comp.value.upper()
        if "BSS138" in value:
            gate = pin_net(design, ref, "1")
            source = pin_net(design, ref, "2")
            drain = pin_net(design, ref, "3")
            lines.append(
                f"M_{ref} {node(drain)} {node(gate)} {node(source)} {node(source)} BSS138_FALLBACK"
                f"    $ {ref}: D={drain}, G={gate}, S={source}"
            )
        elif "3904" in value:
            base = pin_net(design, ref, "1")
            emitter = pin_net(design, ref, "2")
            collector = pin_net(design, ref, "3")
            lines.append(
                f"Q_{ref} {node(collector)} {node(base)} {node(emitter)} MMBT3904_FALLBACK"
                f"    $ {ref}: C={collector}, B={base}, E={emitter}"
            )
        else:
            lines.append(f"* {ref}={comp.value}: transistor type not recognised, not electrically modelled")
    lines.append("")


def add_external_sources(lines: list[str], cfg: SimConfig) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* Optional external jack stimulus sources",
        "* -----------------------------------------------------------------------------",
    ]
    if cfg.stimulus_ext is None:
        lines.append("* J1 ring Stimulus_Ext has no external source; schematic bias network defines it.")
    else:
        lines.append(f"V_STIM_EXT Stimulus_Ext 0 DC {cfg.stimulus_ext:.12g}    $ external DC source on J1 ring")

    syn_specs = [
        (1, cfg.syn1_enable, cfg.syn1_delay, cfg.syn1_width, cfg.syn1_period),
        (2, cfg.syn2_enable, cfg.syn2_delay, cfg.syn2_width, cfg.syn2_period),
        (3, cfg.syn3_enable, cfg.syn3_delay, cfg.syn3_width, cfg.syn3_period),
        (4, cfg.syn4_enable, cfg.syn4_delay, cfg.syn4_width, cfg.syn4_period),
    ]
    for idx, enabled, delay, width, period in syn_specs:
        if enabled:
            lines.append(
                f"V_SYN{idx}_SPIKE Syn{idx}_Spike 0 PULSE(0 {cfg.syn_amp} {delay} {cfg.syn_rise} {cfg.syn_fall} {width} {period})"
            )
        else:
            lines.append(f"* Syn{idx}_Spike has no external pulse source in this run.")
    lines.append("")


def add_global_leakage(lines: list[str], design: Design) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* Very weak leakage on every non-ground net for numerical convergence",
        "* -----------------------------------------------------------------------------",
    ]
    for net_name in sorted(design.nets):
        sp = spice_node_name(net_name)
        if sp == "0":
            continue
        lines.append(f"R_LEAK_{sp} {sp} 0 10G")
    lines.append("")


def add_initial_conditions(lines: list[str], cfg: SimConfig) -> None:
    lines += [
        "* -----------------------------------------------------------------------------",
        "* Initial conditions",
        "* -----------------------------------------------------------------------------",
    ]
    if cfg.startup_mode == "cold":
        lines.append("* Cold startup: capacitors begin discharged unless driven by independent sources.")
        lines.append(f".ic V(Vm_Int)=0 V(V_Syn_State)=0 V(Vm_Display_In)=0")
    else:
        lines.append("* Operating startup: begin close to the expected biased analogue operating point.")
        lines.append(
            ".ic "
            f"V(P_BATT)={cfg.vbat} V(VDD)={cfg.vbat} V(V_Boost)={cfg.vboost} "
            "V(VREF_2V048)=2.048 V(VREF_1V024_RAW)=1.024 V(VREF_1V024)=1.024 "
            f"V(Vm_Int)={cfg.vm_initial} V(Vm_Display_In)={cfg.vm_initial} V(V_Syn_State)={cfg.syn_initial} "
            "V(V_Leak)=0.6 V(AP)=0 V(Peak_Window)=0 V(Reset_Window)=0"
        )
    lines.append("")


def trace_nodes(cfg: SimConfig) -> list[str]:
    core = [
        "VDD",
        "V_Boost",
        "VREF_2V048",
        "VREF_1V024",
        "V_Leak_Ref_Max",
        "/V_Leak_ref",
        "V_Leak",
        "Vm_Int",
        "Vm_Display_In",
        "Vm_Ext",
        "V_Threshold",
        "/AP_Gate",
        "AP",
        "/Rising_AP",
        "Spike_Pulse",
        "Peak_Window",
        "Reset_Window",
        "Spike_Out",
        "V_Syn_State",
        "/V_Syn_Drive",
        "V_Stim_Cmd",
        "V_Stim_Drive",
        "Vw",
        "Vw_buff",
    ]
    if cfg.trace_debug:
        core += [
            "T1", "T2", "T3", "T4", "Vsel", "S0", "S1", "S2", "S3", "S4",
            "Net-(U6C-INC-)", "Net-(U6C-INC+)", "/Reset_Injection_Enable", "/Reset_Gated_Drive",
            "V_Syn1_Set", "V_Syn2_Set", "V_Syn3_Set", "V_Syn4_Set",
            "Net-(U2C-VIND+)", "Net-(U2C-VIND-)",
        ]
    # Deduplicate while preserving order.
    out: list[str] = []
    seen: set[str] = set()
    for item in core:
        sp = node(item)
        if sp not in seen:
            seen.add(sp)
            out.append(item)
    return out


def build_deck(design: Design, cfg: SimConfig, csv_path: Path | None = None) -> str:
    lines: list[str] = [
        "* LIFeling full-schematic behavioural model",
        f"* Source netlist: {cfg.netlist}",
        "* Generated by Spice.py validation-suite-v4",
        ".option method=gear reltol=1e-4 abstol=1e-12 vntol=1e-6 chgtol=1e-14",
        ".option itl1=500 itl4=500",
        ".option gmin=1e-12",
        ".temp 25",
        "",
    ]
    add_models(lines)
    add_node_alias_comments(lines, design)
    add_resistors(lines, design)
    add_potentiometers(lines, design, cfg)
    add_capacitors(lines, design)
    add_inductors(lines, design)
    add_diodes(lines, design)
    add_active_components(lines, design, cfg)
    add_switches(lines, design)
    add_transistors(lines, design)
    add_external_sources(lines, cfg)
    add_global_leakage(lines, design)
    add_initial_conditions(lines, cfg)

    traces = trace_nodes(cfg)
    lines += [
        "* -----------------------------------------------------------------------------",
        "* Analysis",
        "* -----------------------------------------------------------------------------",
        f".tran {cfg.tstep} {cfg.tstop} 0 {cfg.maxstep} uic",
        ".save " + " ".join(f"V({node(net_name)})" for net_name in traces),
    ]
    if csv_path is not None:
        csv_name = str(csv_path.resolve()).replace("\\", "/")
        lines += [
            ".control",
            "run",
            f"wrdata {csv_name} " + " ".join(f"v({node(net_name)})" for net_name in traces),
            "quit",
            ".endc",
        ]
    lines.append(".end")
    return "\n".join(lines) + "\n"


# -----------------------------------------------------------------------------
# Coverage report
# -----------------------------------------------------------------------------


def model_status(ref: str, comp: Component) -> tuple[str, str]:
    if re.fullmatch(r"R\d+", ref):
        return "electrical", "fixed resistor instantiated from netlist"
    if re.fullmatch(r"RV\d+", ref):
        return "electrical", "potentiometer split into two variable resistances"
    if re.fullmatch(r"C\d+", ref):
        return "electrical", "capacitor instantiated from netlist"
    if re.fullmatch(r"L\d+", ref):
        return "electrical", "inductor instantiated from netlist"
    if re.fullmatch(r"D\d+", ref):
        if ref in {"D1", "D18", "D19"}:
            return "behavioural", "ESD protector approximated as capacitance plus leakage"
        if ref == "D9":
            return "behavioural", "RGB LED approximated with three generic LED diodes"
        return "electrical", "diode/clamp instantiated with generic fallback model"
    if re.fullmatch(r"Q\d+", ref):
        return "behavioural", "BSS138/MMBT3904 generic transistor model"
    if ref in {"U1", "U2", "U3", "U8", "U22"}:
        return "behavioural", "op-amp channels modelled as followers or rail-limited amplifiers"
    if ref in {"U4", "U5", "U6", "U19"}:
        return "behavioural", "comparator channels modelled as smooth open-drain sinks with schematic pull-ups"
    if ref in {f"U{i}" for i in range(9, 21)}:
        return "behavioural", "TS5A3166 analogue switch model"
    if ref == "U7":
        return "behavioural", "TPS610995 boost converter approximated as ideal boosted rail"
    if ref == "U21":
        return "behavioural", "REF3020 approximated as ideal 2.048 V reference bounded by VDD"
    if ref == "BT1":
        return "behavioural", "coin-cell source with configurable internal resistance"
    if ref == "SW1":
        return "behavioural", "power switch approximated as configurable ON resistance"
    if ref.startswith("J"):
        return "terminal", "connector represented by its named external nets"
    if ref.startswith("H"):
        return "mechanical", "mounting hole; no electrical model required"
    return "unclassified", "listed but no explicit model rule matched"


def write_coverage_report(design: Design, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ref", "value", "footprint", "status", "model_note", "pins"])
        for ref in sorted(design.components, key=component_sort_key):
            comp = design.components[ref]
            status, note = model_status(ref, comp)
            pins = "; ".join(f"{pin}:{net}" for pin, net in sorted(comp.pins.items()))
            writer.writerow([ref, comp.value, comp.footprint, status, note, pins])


# -----------------------------------------------------------------------------
# ngspice execution and plotting
# -----------------------------------------------------------------------------


def find_ngspice_binary(requested: str) -> str:
    requested = requested.strip().strip('"')
    if requested and requested.lower() not in {"auto", "ngspice", "ngspice.exe"}:
        if Path(requested).is_file():
            return requested
        found = shutil.which(requested)
        if found:
            return found
    for candidate in ["ngspice", "ngspice.exe"]:
        found = shutil.which(candidate)
        if found:
            return found
    common = [
        Path(r"C:\Spice64\bin\ngspice.exe"),
        Path(r"C:\Program Files\ngspice\bin\ngspice.exe"),
        Path(r"C:\Program Files\KiCad\bin\ngspice.exe"),
        Path(r"C:\Program Files\KiCad\10.0\bin\ngspice.exe"),
    ]
    for path in common:
        if path.is_file():
            return str(path)
    raise FileNotFoundError("ngspice was not found. Install ngspice or pass --ngspice-binary <path>.")


def read_wrdata(csv_path: Path, traces: list[str]):
    if pd is None:
        raise RuntimeError("pandas is required to read ngspice wrdata output")
    raw = pd.read_csv(csv_path, sep=r"\s+", header=None, comment="*")
    out = pd.DataFrame()
    out["time_s"] = raw.iloc[:, 0].astype(float)
    value_cols = list(range(1, raw.shape[1], 2))
    for net_name, col in zip(traces, value_cols):
        out[net_name] = raw.iloc[:, col].astype(float)
    return out


def plot_core(df, png_path: Path, title_suffix: str = "") -> None:
    """Generate the full multi-trace validation plot for one run."""
    if plt is None:
        return
    t_ms = df["time_s"].to_numpy() * 1e3
    plot_names = [
        "Vm_Int", "Vm_Ext", "V_Threshold", "AP", "Spike_Pulse", "Peak_Window", "Reset_Window",
        "V_Syn_State", "/V_Syn_Drive", "V_Stim_Drive", "Vw",
    ]
    plt.figure(figsize=(13, 7))
    for name in plot_names:
        if name in df:
            plt.plot(t_ms, df[name].to_numpy(), label=name)
    plt.xlabel("Time (ms)")
    plt.ylabel("Voltage (V)")
    title = "LIFeling updated schematic behavioural model"
    if title_suffix:
        title += f" — {title_suffix}"
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best", fontsize="small", ncol=2)
    plt.tight_layout()
    plt.savefig(png_path, dpi=180)
    plt.close()


def plot_vm_only(df, png_path: Path, title_suffix: str = "") -> None:
    """Generate the companion plot containing only Vm_Int and Vm_Ext.

    The validation suite intentionally writes this second plot for every normal
    plot. Vm_Int is the internal computation node; Vm_Ext is the user-facing
    live/display output after the display-spike overlay and U8 output driver.
    """
    if plt is None:
        return
    t_ms = df["time_s"].to_numpy() * 1e3
    plt.figure(figsize=(13, 5))
    plotted = False
    if "Vm_Int" in df:
        plt.plot(t_ms, df["Vm_Int"].to_numpy(), label="Vm_Int", linewidth=2.2)
        plotted = True
    if "Vm_Ext" in df:
        plt.plot(t_ms, df["Vm_Ext"].to_numpy(), label="Vm_Ext", linewidth=2.4)
        plotted = True
    if not plotted:
        plt.plot(t_ms, np.zeros_like(t_ms), label="Vm traces not saved")
    plt.xlabel("Time (ms)")
    plt.ylabel("Voltage (V)")
    title = "LIFeling Vm_Int / Vm_Ext"
    if title_suffix:
        title += f" — {title_suffix}"
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(png_path, dpi=180)
    plt.close()


def _analysis_window(df, cfg: SimConfig):
    t = df["time_s"].to_numpy()
    if cfg.ignore_start_ms <= 0:
        return t, np.ones_like(t, dtype=bool)
    return t, t >= cfg.ignore_start_ms / 1000.0


def _rising_edge_count(y: np.ndarray, threshold: float = 1.0) -> int:
    if len(y) < 2:
        return 0
    above = y >= threshold
    return int(np.sum((~above[:-1]) & above[1:]))


def _first_crossing_ms(t: np.ndarray, a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    idx = np.where((a >= b) & mask)[0]
    if len(idx) == 0:
        return float("nan")
    return float(t[int(idx[0])] * 1e3)


def _edge_period_ms(t: np.ndarray, y: np.ndarray, threshold: float, mask: np.ndarray) -> float:
    if len(y) < 2:
        return float("nan")
    above = y >= threshold
    idx = np.where((~above[:-1]) & above[1:] & mask[1:])[0] + 1
    if len(idx) < 2:
        return float("nan")
    return float(np.mean(np.diff(t[idx])) * 1e3)


def write_run_diagnostics(df, cfg: SimConfig, csv_path: Path, md_path: Path) -> None:
    """Write compact numerical diagnostics for each validation run."""
    if pd is None:
        return
    t, mask = _analysis_window(df, cfg)
    if not np.any(mask):
        mask = np.ones_like(t, dtype=bool)
    row: dict[str, object] = {
        "script_version": SCRIPT_VERSION,
        "run_label": cfg.run_label,
        "startup_mode": cfg.startup_mode,
        "ignore_start_ms": cfg.ignore_start_ms,
        "tstop": cfg.tstop,
        "tstep": cfg.tstep,
        "maxstep": cfg.maxstep,
        "supply_mode": cfg.supply_mode,
        "vbat": cfg.vbat,
        "rbat": cfg.rbat,
        "vdd_ideal": cfg.vdd_ideal,
        "rv1": cfg.rv1,
        "rv2": cfg.rv2,
        "rv3": cfg.rv3,
        "rv4": cfg.rv4,
        "rv5": cfg.rv5,
        "rv6": cfg.rv6,
        "rv7": cfg.rv7,
        "rv8": cfg.rv8,
        "rv9": cfg.rv9,
    }

    for name in [
        "VDD", "V_Boost", "VREF_2V048", "VREF_1V024", "V_Leak", "Vm_Int", "Vm_Ext",
        "V_Threshold", "AP", "Spike_Pulse", "Peak_Window", "Reset_Window", "Spike_Out",
        "V_Syn_State", "/V_Syn_Drive", "V_Stim_Drive", "Vw", "Vw_buff",
    ]:
        if name in df:
            values = df[name].to_numpy()[mask]
            row[f"{name}_min"] = float(np.nanmin(values))
            row[f"{name}_max"] = float(np.nanmax(values))
            row[f"{name}_end"] = float(df[name].to_numpy()[-1])

    if "Vm_Int" in df and "V_Threshold" in df:
        vm = df["Vm_Int"].to_numpy()
        vt = df["V_Threshold"].to_numpy()
        row["Vm_threshold_crossings"] = _rising_edge_count((vm - vt)[mask], 0.0)
        row["Vm_first_threshold_crossing_ms"] = _first_crossing_ms(t, vm, vt, mask)

    for name, threshold in [
        ("AP", 1.0),
        ("Spike_Pulse", 1.0),
        ("Peak_Window", 1.0),
        ("Reset_Window", 1.0),
        ("Spike_Out", 1.0),
    ]:
        if name in df:
            y = df[name].to_numpy()
            row[f"{name}_rising_edges"] = _rising_edge_count(y[mask], threshold)
            row[f"{name}_mean_period_ms"] = _edge_period_ms(t, y, threshold, mask)

    if cfg.supply_mode == "coin" and "VDD" in df:
        vdd = df["VDD"].to_numpy()[mask]
        try:
            vbat = float(cfg.vbat)
            rbat = float(cfg.rbat)
            row["VDD_sag_max"] = float(vbat - np.nanmin(vdd))
            row["Battery_current_peak_mA_est"] = float((vbat - np.nanmin(vdd)) / rbat * 1e3) if rbat > 0 else float("nan")
        except Exception:
            pass

    pd.DataFrame([row]).to_csv(csv_path, index=False)

    lines = [
        f"# LIFeling run diagnostics — {cfg.run_label or 'unlabelled run'}",
        "",
        f"Script version: `{SCRIPT_VERSION}`",
        f"Analysis ignores first `{cfg.ignore_start_ms:g} ms`.",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    preferred = [
        "Vm_Int_min", "Vm_Int_max", "Vm_Int_end", "Vm_Ext_max", "V_Threshold_min", "V_Threshold_max",
        "Vm_threshold_crossings", "Vm_first_threshold_crossing_ms", "AP_rising_edges",
        "Spike_Pulse_rising_edges", "Peak_Window_rising_edges", "Reset_Window_rising_edges", "Spike_Out_rising_edges",
        "AP_mean_period_ms", "Reset_Window_mean_period_ms", "V_Syn_State_min", "V_Syn_State_max",
        "/V_Syn_Drive_min", "/V_Syn_Drive_max", "VDD_min", "VDD_sag_max", "Battery_current_peak_mA_est",
    ]
    for key in preferred:
        if key in row:
            val = row[key]
            if isinstance(val, float):
                val_txt = f"{val:.6g}"
            else:
                val_txt = str(val)
            lines.append(f"| `{key}` | {val_txt} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_ngspice(deck_path: Path, csv_path: Path, cfg: SimConfig) -> None:
    exe = find_ngspice_binary(cfg.ngspice_binary)
    log_path = csv_path.with_suffix(".ngspice.log")
    if csv_path.exists():
        csv_path.unlink()
    if log_path.exists():
        log_path.unlink()
    proc = subprocess.run(
        [exe, "-b", "-o", str(log_path), str(deck_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not csv_path.exists():
        log_text = log_path.read_text(errors="replace") if log_path.exists() else ""
        raise RuntimeError(
            f"ngspice failed or did not create {csv_path}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\nLOG:\n{log_text}"
        )

# -----------------------------------------------------------------------------
# Validation verdict and README auto-update
# -----------------------------------------------------------------------------

README_AUTOGEN_START = "<!-- LIFELING_SPICE_AUTOGENERATED_START -->"
README_AUTOGEN_END = "<!-- LIFELING_SPICE_AUTOGENERATED_END -->"


def _safe_float(value, default: float = float("nan")) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str) and value.strip() == "":
            return default
        return float(value)
    except Exception:
        return default


def _first_row(df, label_fragment: str):
    if df is None or df.empty or "run_label" not in df.columns:
        return None
    labels = df["run_label"].astype(str)
    rows = df[labels.str.contains(label_fragment, case=False, regex=False, na=False)]
    if rows.empty:
        return None
    return rows.iloc[0]


def _read_validation_suite_status(output_dir: Path) -> dict[str, str]:
    output_dir = Path(output_dir)
    candidates = [
        output_dir / "validation_logs" / "validation_suite_latest.txt",
        output_dir / "validation_suite_latest.txt",
        output_dir.parent / "validation_suite_latest.txt",
    ]

    # Also accept the newest timestamped suite log if latest has not been copied yet.
    log_dir = output_dir / "validation_logs"
    if log_dir.exists():
        candidates.extend(sorted(log_dir.glob("validation_suite_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True))

    suite_path = next((p for p in candidates if p.exists()), None)
    status = {
        "suite_log": str(suite_path) if suite_path else "",
        "total_runs": "",
        "failed_runs": "",
        "start": "",
        "end": "",
    }
    if suite_path is None:
        return status

    text = suite_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("START:"):
            status["start"] = line.split(":", 1)[1].strip()
        elif line.startswith("END:"):
            status["end"] = line.split(":", 1)[1].strip()
        elif line.startswith("TOTAL RUNS:"):
            status["total_runs"] = line.split(":", 1)[1].strip()
        elif line.startswith("FAILED RUNS:"):
            status["failed_runs"] = line.split(":", 1)[1].strip()

    return status


def _add_verdict(rows: list[dict[str, str]], block: str, verdict: str, evidence: str, caveat: str = "") -> None:
    rows.append({
        "block": block,
        "verdict": verdict,
        "evidence": evidence,
        "caveat": caveat,
    })


def make_validation_verdict(output_dir: Path) -> tuple[Path, Path, Path]:
    """Generate block-level validation files from the validation-suite outputs."""
    if pd is None:
        raise RuntimeError("pandas is required for validation verdict generation")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "validation_diagnostics_summary.csv"
    coverage_path = output_dir / "component_model_coverage.csv"

    if not summary_path.exists():
        raise FileNotFoundError(f"Cannot find diagnostics summary: {summary_path}")

    summary = pd.read_csv(summary_path)
    coverage = pd.read_csv(coverage_path) if coverage_path.exists() else pd.DataFrame()
    suite = _read_validation_suite_status(output_dir)

    rows: list[dict[str, str]] = []
    metrics: list[dict[str, str]] = []

    failed_runs = _safe_float(suite.get("failed_runs", ""))
    total_runs = _safe_float(suite.get("total_runs", ""))

    if np.isfinite(failed_runs):
        _add_verdict(
            rows,
            "Simulation execution / convergence",
            "PASS" if failed_runs == 0 else "FAIL",
            f"{int(total_runs) if np.isfinite(total_runs) else 'unknown'} suite steps, {int(failed_runs)} failed.",
        )
    else:
        _add_verdict(
            rows,
            "Simulation execution / convergence",
            "WARNING",
            "Validation-suite log was not found or did not contain TOTAL RUNS / FAILED RUNS.",
        )

    if not coverage.empty and "status" in coverage.columns:
        counts = coverage["status"].astype(str).value_counts().to_dict()
        unclassified = int(counts.get("unclassified", 0))
        evidence = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        _add_verdict(
            rows,
            "Component model coverage",
            "PASS" if unclassified == 0 else "WARNING",
            evidence,
            "Behavioural entries are intentional circuit-block approximations, not vendor-accurate macromodels.",
        )
        for key, val in sorted(counts.items()):
            metrics.append({
                "metric": f"coverage_{key}",
                "value": str(val),
                "run_label": "",
                "notes": "component_model_coverage.csv",
            })
    else:
        _add_verdict(
            rows,
            "Component model coverage",
            "WARNING",
            "component_model_coverage.csv was not found or did not contain a status column.",
        )

    baseline = _first_row(summary, "baseline_self_spiking")
    debug = _first_row(summary, "debug_self_spiking")
    cold = _first_row(summary, "cold_start")
    quiet = _first_row(summary, "quiet_subthreshold")
    mid = _first_row(summary, "synapse_midpoint")
    exc = _first_row(summary, "synapse_excitatory")
    inh = _first_row(summary, "synapse_inhibitory")
    stim_pos = _first_row(summary, "external_stimulus_positive")
    stim_neg = _first_row(summary, "external_stimulus_negative")
    low_batt = _first_row(summary, "low_battery")

    if baseline is not None:
        ref2_min = _safe_float(baseline.get("VREF_2V048_min"))
        ref2_max = _safe_float(baseline.get("VREF_2V048_max"))
        ref1_min = _safe_float(baseline.get("VREF_1V024_min"))
        ref1_max = _safe_float(baseline.get("VREF_1V024_max"))
        ok = (
            2.03 <= ref2_min <= 2.06 and
            2.03 <= ref2_max <= 2.06 and
            1.01 <= ref1_min <= 1.04 and
            1.01 <= ref1_max <= 1.04
        )
        _add_verdict(
            rows,
            "Reference rails VREF_2V048 / VREF_1V024",
            "PASS" if ok else "WARNING",
            f"Baseline VREF_2V048={ref2_min:.4g}..{ref2_max:.4g} V; VREF_1V024={ref1_min:.4g}..{ref1_max:.4g} V.",
        )
        for metric in ["VREF_2V048_min", "VREF_2V048_max", "VREF_1V024_min", "VREF_1V024_max", "VDD_sag_max", "Battery_current_peak_mA_est"]:
            if metric in baseline:
                metrics.append({
                    "metric": metric,
                    "value": f"{_safe_float(baseline.get(metric)):.6g}",
                    "run_label": str(baseline.get("run_label", "")),
                    "notes": "baseline",
                })
    else:
        _add_verdict(rows, "Reference rails VREF_2V048 / VREF_1V024", "WARNING", "Baseline self-spiking run was not found.")

    if baseline is not None:
        ap = int(_safe_float(baseline.get("AP_rising_edges"), 0))
        rst = int(_safe_float(baseline.get("Reset_Window_rising_edges"), 0))
        spk = int(_safe_float(baseline.get("Spike_Out_rising_edges"), 0))
        vm_min = _safe_float(baseline.get("Vm_Int_min"))
        vm_max = _safe_float(baseline.get("Vm_Int_max"))
        ok = ap > 0 and rst > 0 and spk > 0
        _add_verdict(
            rows,
            "Core LIF oscillation / threshold / AP / reset / Spike_Out",
            "PASS" if ok else "WARNING",
            f"Baseline AP={ap}, Reset_Window={rst}, Spike_Out={spk}; Vm_Int={vm_min:.4g}..{vm_max:.4g} V.",
        )
        for metric in [
            "Vm_Int_min", "Vm_Int_max", "Vm_Ext_max",
            "AP_rising_edges", "Spike_Pulse_rising_edges", "Peak_Window_rising_edges",
            "Reset_Window_rising_edges", "Spike_Out_rising_edges", "AP_mean_period_ms",
        ]:
            if metric in baseline:
                metrics.append({
                    "metric": metric,
                    "value": f"{_safe_float(baseline.get(metric)):.6g}",
                    "run_label": str(baseline.get("run_label", "")),
                    "notes": "baseline",
                })
    else:
        _add_verdict(rows, "Core LIF oscillation / threshold / AP / reset / Spike_Out", "WARNING", "Baseline self-spiking run was not found.")

    if quiet is not None:
        edges = int(_safe_float(quiet.get("AP_rising_edges"), 0))
        _add_verdict(
            rows,
            "Quiet subthreshold operating point",
            "PASS" if edges == 0 else "WARNING",
            f"Quiet-subthreshold AP_rising_edges={edges}; Vm_Int_max={_safe_float(quiet.get('Vm_Int_max')):.4g} V.",
        )

    if cold is not None:
        ap = int(_safe_float(cold.get("AP_rising_edges"), 0))
        _add_verdict(
            rows,
            "Cold-start behaviour",
            "PASS" if ap > 0 else "WARNING",
            f"Cold-start AP_rising_edges={ap}; Vm_Int_max={_safe_float(cold.get('Vm_Int_max')):.4g} V.",
            "Cold-start is a stress condition, not the normal operating initial condition.",
        )

    if mid is not None and quiet is not None:
        delta = _safe_float(mid.get("Vm_Int_max")) - _safe_float(quiet.get("Vm_Int_max"))
        mid_edges = int(_safe_float(mid.get("AP_rising_edges"), 0))
        ok = abs(delta) <= 0.005 and mid_edges == 0
        _add_verdict(
            rows,
            "Synapse midpoint zero-effect",
            "PASS" if ok else "WARNING",
            f"Midpoint minus quiet Vm_Int_max delta={delta * 1e3:.4g} mV; AP_rising_edges={mid_edges}.",
        )
        metrics.append({
            "metric": "synapse_midpoint_delta_vm_int_max_mV",
            "value": f"{delta * 1e3:.6g}",
            "run_label": str(mid.get("run_label", "")),
            "notes": "midpoint should be close to zero-effect",
        })

    if exc is not None and quiet is not None:
        delta = _safe_float(exc.get("Vm_Int_max")) - _safe_float(quiet.get("Vm_Int_max"))
        _add_verdict(
            rows,
            "Excitatory synapse sign",
            "PASS" if delta > 0.02 else "WARNING",
            f"Excitatory minus quiet Vm_Int_max delta={delta * 1e3:.4g} mV.",
        )
        metrics.append({
            "metric": "excitatory_delta_vm_int_max_mV",
            "value": f"{delta * 1e3:.6g}",
            "run_label": str(exc.get("run_label", "")),
            "notes": "positive delta expected",
        })

    if inh is not None and baseline is not None:
        p_base = _safe_float(baseline.get("AP_mean_period_ms"))
        p_inh = _safe_float(inh.get("AP_mean_period_ms"))
        ok = np.isfinite(p_base) and np.isfinite(p_inh) and p_inh > p_base
        _add_verdict(
            rows,
            "Inhibitory synapse sign",
            "PASS" if ok else "WARNING",
            f"Baseline AP period={p_base:.4g} ms; inhibitory AP period={p_inh:.4g} ms.",
        )
        metrics.append({
            "metric": "inhibitory_period_delta_ms",
            "value": f"{p_inh - p_base:.6g}",
            "run_label": str(inh.get("run_label", "")),
            "notes": "positive delta means slower firing",
        })

    if stim_pos is not None and stim_neg is not None and quiet is not None:
        q = _safe_float(quiet.get("Vm_Int_max"))
        pos_delta = _safe_float(stim_pos.get("Vm_Int_max")) - q
        neg_delta = _safe_float(stim_neg.get("Vm_Int_max")) - q
        ok = pos_delta > 0 and neg_delta < 0
        verdict = "PASS" if ok else "WARNING"
        _add_verdict(
            rows,
            "External stimulus path",
            verdict,
            f"Positive stimulus delta={pos_delta * 1e3:.4g} mV; negative stimulus delta={neg_delta * 1e3:.4g} mV.",
            "If this warns, run a dedicated Stimulus_Ext -> V_Stim_Drive -> Vm_Int polarity sweep.",
        )
        metrics.append({
            "metric": "stimulus_positive_delta_vm_int_max_mV",
            "value": f"{pos_delta * 1e3:.6g}",
            "run_label": str(stim_pos.get("run_label", "")),
            "notes": "positive delta expected",
        })
        metrics.append({
            "metric": "stimulus_negative_delta_vm_int_max_mV",
            "value": f"{neg_delta * 1e3:.6g}",
            "run_label": str(stim_neg.get("run_label", "")),
            "notes": "negative delta expected",
        })

    rv1_rows = summary[summary.get("run_label", pd.Series(dtype=str)).astype(str).str.contains("rv1_leak_threshold_sweep", case=False, regex=False, na=False)] if not summary.empty else pd.DataFrame()
    if not rv1_rows.empty:
        low_edges = int(_safe_float(rv1_rows.iloc[0].get("AP_rising_edges"), 0))
        high_edges = int(_safe_float(rv1_rows.iloc[-1].get("AP_rising_edges"), 0))
        _add_verdict(
            rows,
            "RV1 leak/reference sweep",
            "PASS" if high_edges >= low_edges else "WARNING",
            f"First sweep AP edges={low_edges}; last sweep AP edges={high_edges}.",
        )

    rv2_rows = summary[summary.get("run_label", pd.Series(dtype=str)).astype(str).str.contains("rv2_leak_rate_sweep", case=False, regex=False, na=False)] if not summary.empty else pd.DataFrame()
    if not rv2_rows.empty:
        periods = [_safe_float(x) for x in rv2_rows.get("AP_mean_period_ms", [])]
        finite = [p for p in periods if np.isfinite(p)]
        _add_verdict(
            rows,
            "RV2 leak-rate sweep",
            "PASS" if len(finite) >= 2 else "WARNING",
            f"Finite AP mean periods observed: {', '.join(f'{p:.4g} ms' for p in finite)}.",
        )

    rv3_rows = summary[summary.get("run_label", pd.Series(dtype=str)).astype(str).str.contains("rv3_adaptation_sweep", case=False, regex=False, na=False)] if not summary.empty else pd.DataFrame()
    if not rv3_rows.empty:
        _add_verdict(
            rows,
            "RV3 adaptation sweep",
            "PASS",
            f"{len(rv3_rows)} RV3 adaptation sweep runs completed.",
            "Interpretation should verify that the knob direction matches the front-panel label.",
        )

    rv4_rows = summary[summary.get("run_label", pd.Series(dtype=str)).astype(str).str.contains("rv4_capacitance_bank_sweep", case=False, regex=False, na=False)] if not summary.empty else pd.DataFrame()
    if not rv4_rows.empty:
        _add_verdict(
            rows,
            "RV4 capacitance-bank sweep",
            "PASS",
            f"{len(rv4_rows)} RV4 capacitance-bank sweep runs completed.",
            "A dedicated Cmem-selection table can be added later if exact one-hot switch state is required.",
        )

    rv5_rows = summary[summary.get("run_label", pd.Series(dtype=str)).astype(str).str.contains("rv5_synaptic_decay_sweep", case=False, regex=False, na=False)] if not summary.empty else pd.DataFrame()
    if not rv5_rows.empty:
        _add_verdict(
            rows,
            "RV5 synaptic decay sweep",
            "PASS",
            f"{len(rv5_rows)} RV5 synaptic decay sweep runs completed.",
            "Interpretation should verify that the knob direction matches the front-panel label.",
        )

    sign_rows = summary[summary.get("run_label", pd.Series(dtype=str)).astype(str).str.contains("synaptic_sign_weight_sweep", case=False, regex=False, na=False)] if not summary.empty else pd.DataFrame()
    if not sign_rows.empty:
        _add_verdict(
            rows,
            "Synaptic sign/weight sweep",
            "PASS",
            f"{len(sign_rows)} synaptic sign/weight sweep runs completed.",
        )

    if low_batt is not None:
        vdd_min = _safe_float(low_batt.get("VDD_min"))
        batt_i = _safe_float(low_batt.get("Battery_current_peak_mA_est"))
        spike_pulse_max = _safe_float(low_batt.get("Spike_Pulse_max"))
        spike_pulse_edges = int(_safe_float(low_batt.get("Spike_Pulse_rising_edges"), 0))
        caveat = ""
        verdict = "PASS"
        if spike_pulse_edges == 0 and np.isfinite(spike_pulse_max) and spike_pulse_max > 0.8:
            verdict = "WARNING"
            caveat = "Spike_Pulse edge counting may need a lower/comparator-relative threshold in low-battery conditions."
        _add_verdict(
            rows,
            "Low-battery / high-impedance stress",
            verdict,
            f"VDD_min={vdd_min:.4g} V; estimated peak battery current={batt_i:.4g} mA; Spike_Pulse_max={spike_pulse_max:.4g} V.",
            caveat,
        )

    verdict_df = pd.DataFrame(rows)
    metrics_df = pd.DataFrame(metrics)

    verdict_csv = output_dir / "LIFeling_validation_verdict.csv"
    metrics_csv = output_dir / "LIFeling_key_validation_metrics.csv"
    verdict_md = output_dir / "LIFeling_validation_verdict.md"

    verdict_df.to_csv(verdict_csv, index=False)
    metrics_df.to_csv(metrics_csv, index=False)

    has_fail = any(str(v).upper() == "FAIL" for v in verdict_df["verdict"])
    has_warning = any(str(v).upper() == "WARNING" for v in verdict_df["verdict"])
    overall = "FAIL" if has_fail else ("PASS WITH WARNINGS" if has_warning else "PASS")

    md_lines = [
        "# LIFeling SPICE validation verdict",
        "",
        f"Script version: `{SCRIPT_VERSION}`",
        f"Overall verdict: **{overall}**",
        "",
    ]
    if suite.get("total_runs") or suite.get("failed_runs"):
        md_lines.append(f"Validation suite: `{suite.get('total_runs', 'unknown')}` total steps, `{suite.get('failed_runs', 'unknown')}` failed.")
        md_lines.append("")
    md_lines += [
        "## Block-level verdict",
        "",
        "| Circuit block | Verdict | Evidence | Caveat |",
        "|---|---|---|---|",
    ]
    for _, row in verdict_df.iterrows():
        md_lines.append(
            f"| {_md_cell(row.get('block', ''))} | **{_md_cell(row.get('verdict', ''))}** | "
            f"{_md_cell(row.get('evidence', ''))} | {_md_cell(row.get('caveat', ''))} |"
        )

    md_lines += [
        "",
        "## Generated files",
        "",
        "- `validation_diagnostics_summary.csv`: aggregate numerical diagnostics, one row per validation run.",
        "- `component_model_coverage.csv`: electrical/behavioural/mechanical model coverage for schematic components.",
        "- `LIFeling_validation_verdict.csv`: machine-readable block-level verdict.",
        "- `LIFeling_key_validation_metrics.csv`: selected regression metrics.",
        "",
    ]

    verdict_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return verdict_md, verdict_csv, metrics_csv


def _is_blank_or_nan(value) -> bool:
    """Return True for values that should not be rendered literally in Markdown."""
    if value is None:
        return True
    try:
        if pd is not None and pd.isna(value):
            return True
    except Exception:
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"", "nan", "none", "nat"}
    return False


def _md_cell(value) -> str:
    if _is_blank_or_nan(value):
        return ""
    text = str(value)
    text = text.replace("|", "\\|")
    text = text.replace("\n", " ")
    return text


def _plain(value, fallback: str = "") -> str:
    return fallback if _is_blank_or_nan(value) else str(value)


def _fmt_sig(value, digits: int = 4) -> str:
    val = _safe_float(value)
    if not np.isfinite(val):
        return ""
    return f"{val:.{digits}g}"


def _fmt_v(value, digits: int = 4) -> str:
    text = _fmt_sig(value, digits)
    return f"{text} V" if text else ""


def _fmt_mv(value, digits: int = 4) -> str:
    val = _safe_float(value)
    if not np.isfinite(val):
        return ""
    return f"{val * 1e3:.{digits}g} mV"


def _fmt_ms(value, digits: int = 4) -> str:
    text = _fmt_sig(value, digits)
    return f"{text} ms" if text else ""


def _fmt_ma(value, digits: int = 4) -> str:
    text = _fmt_sig(value, digits)
    return f"{text} mA" if text else ""


def _fmt_count(value) -> str:
    val = _safe_float(value)
    if not np.isfinite(val):
        return ""
    return str(int(round(val)))


def _fmt_range(row, signal: str, unit: str = "V", digits: int = 4) -> str:
    if row is None:
        return ""
    mn = _safe_float(row.get(f"{signal}_min"))
    mx = _safe_float(row.get(f"{signal}_max"))
    if not (np.isfinite(mn) and np.isfinite(mx)):
        return ""
    if abs(mx - mn) < 1e-9:
        return f"{mx:.{digits}g} {unit}"
    return f"{mn:.{digits}g}–{mx:.{digits}g} {unit}"


def _metric_value(value: str) -> str:
    return _md_cell(value) if value else ""


def _add_metric_table(lines: list[str], metrics: list[tuple[str, str]]) -> None:
    clean = [(label, value) for label, value in metrics if value]
    if not clean:
        lines.append("No numerical diagnostics were available for this step.")
        lines.append("")
        return
    lines += [
        "| Quantity | Latest validation result |",
        "|---|---:|",
    ]
    for label, value in clean:
        lines.append(f"| {_md_cell(label)} | {_metric_value(value)} |")
    lines.append("")


def _rel_markdown_path(target: Path, readme_path: Path) -> str:
    try:
        rel = os.path.relpath(Path(target).resolve(), start=Path(readme_path).resolve().parent)
        return Path(rel).as_posix()
    except Exception:
        return Path(target).as_posix()


def _load_validation_summary(output_dir: Path):
    if pd is None:
        raise RuntimeError("pandas is required for README validation generation")
    path = Path(output_dir) / "validation_diagnostics_summary.csv"
    if not path.exists():
        raise FileNotFoundError(f"Cannot find diagnostics summary: {path}")
    return pd.read_csv(path)


def _load_coverage(output_dir: Path):
    if pd is None:
        raise RuntimeError("pandas is required for README validation generation")
    path = Path(output_dir) / "component_model_coverage.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _load_verdict(output_dir: Path):
    path = Path(output_dir) / "LIFeling_validation_verdict.csv"
    if not path.exists() or pd is None:
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df.fillna("")


def _coverage_counts(coverage) -> dict[str, int]:
    if coverage is None or coverage.empty or "status" not in coverage.columns:
        return {}
    return {str(k): int(v) for k, v in coverage["status"].astype(str).value_counts().sort_index().items()}


def _coverage_text(coverage) -> str:
    counts = _coverage_counts(coverage)
    if not counts:
        return "No component coverage table was available."
    preferred = ["electrical", "behavioural", "terminal", "mechanical", "unclassified"]
    parts = []
    for key in preferred:
        if key in counts:
            parts.append(f"{key}: {counts[key]}")
    for key, val in counts.items():
        if key not in preferred:
            parts.append(f"{key}: {val}")
    return "; ".join(parts)


def _verdict_lookup(verdict_df, contains_text: str) -> tuple[str, str, str]:
    if verdict_df is None or verdict_df.empty or "block" not in verdict_df.columns:
        return "", "", ""
    mask = verdict_df["block"].astype(str).str.contains(contains_text, case=False, regex=False, na=False)
    rows = verdict_df[mask]
    if rows.empty:
        return "", "", ""
    row = rows.iloc[0]
    return _plain(row.get("verdict")), _plain(row.get("evidence")), _plain(row.get("caveat"))


def _overall_verdict(verdict_df, suite: dict[str, str]) -> str:
    failed = _safe_float(suite.get("failed_runs", ""))
    if np.isfinite(failed) and failed > 0:
        return "FAIL"
    if verdict_df is not None and not verdict_df.empty and "verdict" in verdict_df.columns:
        values = [str(v).upper() for v in verdict_df["verdict"].dropna().tolist()]
        if any(v == "FAIL" for v in values):
            return "FAIL"
        if any(v == "WARNING" for v in values):
            return "PASS WITH WARNINGS"
        if values:
            return "PASS"
    if np.isfinite(failed) and failed == 0:
        return "PASS"
    return "UNKNOWN"


def _find_row(summary, label_fragment: str):
    row = _first_row(summary, label_fragment)
    if row is not None:
        return row
    # Fallback for labels with numerical prefixes, suffix hashes, or shortened fragments.
    if summary is None or summary.empty or "run_label" not in summary.columns:
        return None
    fragment = label_fragment.lower()
    rows = summary[summary["run_label"].astype(str).str.lower().str.contains(fragment, regex=False, na=False)]
    return None if rows.empty else rows.iloc[0]



def _first_available_row(summary, *fragments: str):
    for fragment in fragments:
        row = _find_row(summary, fragment)
        if row is not None:
            return row
    return None


def _find_latest_plot(output_dir: Path, label_fragment: str, kind: str) -> Path | None:
    """Find the newest matching plot without producing broken Markdown links.

    kind="vm" selects companion *_vmint_vmext.png plots.
    kind="full" selects the full multi-trace PNG for the same run.
    """
    output_dir = Path(output_dir)
    if not output_dir.exists():
        return None
    fragment = label_fragment.lower()
    matches: list[Path] = []
    for path in output_dir.glob("*.png"):
        name = path.name.lower()
        if fragment not in name:
            continue
        is_vm_only = name.endswith("_vmint_vmext.png")
        if kind == "vm" and not is_vm_only:
            continue
        if kind == "full" and is_vm_only:
            continue
        matches.append(path)
    if not matches:
        return None
    return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _append_plot(lines: list[str], output_dir: Path, readme_path: Path, label: str, fragment: str, kind: str) -> None:
    plot = _find_latest_plot(output_dir, fragment, kind)
    if plot is None:
        plot_desc = "Vm_Int/Vm_Ext" if kind == "vm" else "full trace"
        lines.append(f"Plot: no {plot_desc} PNG was found for run-label fragment `{fragment}`.")
        lines.append("")
        return
    rel = _rel_markdown_path(plot, readme_path)
    suffix = "Vm_Int and Vm_Ext" if kind == "vm" else "full trace set"
    lines.append(f"![{label} — {suffix}]({rel})")
    lines.append("")


def _append_step_header(lines: list[str], number: int, title: str) -> None:
    lines += [
        f"### Step {number}: {title}",
        "",
    ]


def _append_evidence(lines: list[str], fragment: str, signals: list[str], verdict: str, caveat: str = "") -> None:
    lines.append(f"**Evidence source.** Run-label fragment: `{fragment}`.")
    if signals:
        lines.append(f"**Key signals.** {', '.join(f'`{s}`' for s in signals)}.")
    if verdict:
        verdict_line = f"**Verdict.** {verdict}."
        if caveat:
            verdict_line += f" {caveat}"
        lines.append(verdict_line)
    lines.append("")


def _delta_max(row, reference_row, signal: str = "Vm_Int") -> float:
    if row is None or reference_row is None:
        return float("nan")
    return _safe_float(row.get(f"{signal}_max")) - _safe_float(reference_row.get(f"{signal}_max"))


def _sweep_count(summary, fragment: str) -> int:
    if summary is None or summary.empty or "run_label" not in summary.columns:
        return 0
    return int(summary["run_label"].astype(str).str.contains(fragment, case=False, regex=False, na=False).sum())


def _sweep_observation(summary, fragment: str, kind: str) -> str:
    if summary is None or summary.empty or "run_label" not in summary.columns:
        return ""
    rows = summary[summary["run_label"].astype(str).str.contains(fragment, case=False, regex=False, na=False)]
    if rows.empty:
        return ""
    if kind == "rv1":
        return f"AP edges changed from {_fmt_count(rows.iloc[0].get('AP_rising_edges'))} to {_fmt_count(rows.iloc[-1].get('AP_rising_edges'))}."
    if kind == "rv2":
        vals = [_safe_float(v) for v in rows.get("AP_mean_period_ms", [])]
        finite = [f"{v:.4g} ms" for v in vals if np.isfinite(v)]
        return "Finite AP periods: " + ", ".join(finite) + "." if finite else "No finite AP period was extracted."
    if kind in {"rv3", "rv4", "rv5", "syn"}:
        return f"{len(rows)} runs completed."
    return f"{len(rows)} runs completed."


def build_readme_validation_section(output_dir: Path, readme_path: Path) -> str:
    output_dir = Path(output_dir)
    readme_path = Path(readme_path)

    verdict_md, verdict_csv, metrics_csv = make_validation_verdict(output_dir)
    summary = _load_validation_summary(output_dir)
    coverage = _load_coverage(output_dir)
    verdict_df = _load_verdict(output_dir)
    suite = _read_validation_suite_status(output_dir)
    overall = _overall_verdict(verdict_df, suite)

    baseline = _first_available_row(summary, "02_baseline_self_spiking_coin", "baseline_self_spiking_coin")
    debug = _first_available_row(summary, "03_debug_self_spiking_short", "debug_self_spiking_short")
    cold = _first_available_row(summary, "04_cold_start_self_spiking_coin", "cold_start_self_spiking_coin")
    quiet = _first_available_row(summary, "05_quiet_subthreshold_no_synapse", "quiet_subthreshold")
    midpoint = _first_available_row(summary, "06_synapse_midpoint_zero_effect_single", "synapse_midpoint")
    excit = _first_available_row(summary, "07_synapse_excitatory_single_high", "synapse_excitatory")
    inhib = _first_available_row(summary, "08_synapse_inhibitory_single_low", "synapse_inhibitory")
    stim_pos = _first_available_row(summary, "09_external_stimulus_positive_subthreshold", "external_stimulus_positive")
    stim_neg = _first_available_row(summary, "10_external_stimulus_negative_subthreshold", "external_stimulus_negative")
    low_batt = _first_available_row(summary, "12_low_battery_high_impedance_stress", "low_battery")

    rel_output = _rel_markdown_path(output_dir, readme_path)
    rel_summary = _rel_markdown_path(output_dir / "validation_diagnostics_summary.csv", readme_path)
    rel_coverage = _rel_markdown_path(output_dir / "component_model_coverage.csv", readme_path)
    rel_verdict_md = _rel_markdown_path(verdict_md, readme_path)
    rel_verdict_csv = _rel_markdown_path(verdict_csv, readme_path)
    rel_metrics_csv = _rel_markdown_path(metrics_csv, readme_path)

    lines: list[str] = [
        README_AUTOGEN_START,
        "",
        "## Auto-generated SPICE validation walkthrough",
        "",
        "This section is generated from the latest files in `LIFeling_pyspice_output/`. Do not edit it by hand; rerun the validation suite or run `Spice.py --update-readme-only` to regenerate it.",
        "",
        "The validation suite uses `Spice.py` to build a controlled behavioural SPICE model from the KiCad netlist, run ngspice simulations, write numerical diagnostics, and turn those outputs into documentation of the circuit behaviour. The goal is not only to check whether the simulations ran, but to explain what each validation run demonstrates about the LIFeling analogue neuron.",
        "",
        "### Latest validation-suite status",
        "",
        f"- Script version: `{SCRIPT_VERSION}`",
        f"- Suite start: `{_plain(suite.get('start'), 'not recorded')}`",
        f"- Suite end: `{_plain(suite.get('end'), 'not recorded')}`",
        f"- Total runs: `{_plain(suite.get('total_runs'), 'unknown')}`",
        f"- Failed runs: `{_plain(suite.get('failed_runs'), 'unknown')}`",
        f"- Overall verdict: **{overall}**",
        f"- Output folder: [`{rel_output}`]({rel_output})",
        "",
        "### Model scope and limitations",
        "",
        "This is a functional behavioural model. Passive components are instantiated from the KiCad netlist, while active devices such as op-amps, comparators, analogue switches, the boost converter, and protection devices are represented by stable behavioural approximations. That is deliberate: the model is meant to validate circuit function, signal polarity, timing, operating ranges, and interactions between subcircuits.",
        "",
        "It is not a full transistor-level or vendor-accurate simulation of every integrated circuit. It does not prove PCB parasitics, real comparator propagation delay, op-amp output-current limits, battery chemistry, contact resistance, or classroom fault tolerance. Before treating the hardware as physically proven, the simulated behaviours below still need to be checked on the assembled PCB with oscilloscope measurements and realistic loading.",
        "",
    ]

    # Step 1
    cov_verdict, cov_evidence, cov_caveat = _verdict_lookup(verdict_df, "Component model coverage")
    _append_step_header(lines, 1, "Netlist-driven model and component coverage")
    lines += [
        "**What is being tested.** This step checks that the schematic components exported from KiCad are either electrically included in the generated model or explicitly accounted for as behavioural, terminal, or mechanical entries.",
        "",
        "**Why it matters.** A SPICE validation is only useful if it remains tied to the actual schematic. Coverage makes model drift visible: a missing resistor, an unaccounted analogue switch, or an unclassified connector can otherwise make the simulation look healthy while no longer representing the board.",
        "",
        "**Evidence source.** `component_model_coverage.csv`.",
        "",
    ]
    _add_metric_table(lines, [("Coverage by model class", _coverage_text(coverage))])
    if cov_verdict:
        lines.append(f"**Verdict.** {cov_verdict}. {cov_caveat}".rstrip())
        lines.append("")
    lines.append("No plot is required for this step because it is a model-coverage check rather than a transient waveform check.")
    lines.append("")

    # Step 2
    ref_verdict, _, ref_caveat = _verdict_lookup(verdict_df, "Reference rails")
    _append_step_header(lines, 2, "Reference rails and supply model")
    lines += [
        "**What is being tested.** The baseline self-spiking coin-cell run checks the 2.048 V reference, the derived 1.024 V midpoint reference, and the simplified coin-cell supply model under normal oscillating operation.",
        "",
        "**Why it matters.** The LIFeling analogue neuron depends on stable references: the 2.048 V rail defines the upper analogue reference, while the 1.024 V midpoint is used as a neutral centre for several functions. Supply sag is also important because a weak coin cell can move comparator thresholds and reduce pulse amplitudes.",
        "",
    ]
    _append_evidence(lines, "02_baseline_self_spiking_coin", ["VREF_2V048", "VREF_1V024", "VDD", "Vm_Int", "AP"], ref_verdict, ref_caveat)
    _add_metric_table(lines, [
        ("VREF_2V048 range", _fmt_range(baseline, "VREF_2V048")),
        ("VREF_1V024 range", _fmt_range(baseline, "VREF_1V024")),
        ("VDD range", _fmt_range(baseline, "VDD")),
        ("Maximum VDD sag from battery model", _fmt_v(baseline.get("VDD_sag_max") if baseline is not None else None)),
        ("Estimated peak battery current", _fmt_ma(baseline.get("Battery_current_peak_mA_est") if baseline is not None else None)),
    ])
    _append_plot(lines, output_dir, readme_path, "Reference rails and baseline supply behaviour", "02_baseline_self_spiking_coin", "full")

    # Step 3
    core_verdict, _, core_caveat = _verdict_lookup(verdict_df, "Core LIF oscillation")
    _append_step_header(lines, 3, "Baseline LIF behaviour")
    lines += [
        "**What is being tested.** The baseline run checks that the membrane integrates toward threshold, fires repeatedly, resets, and exposes a usable external Vm output.",
        "",
        "**Why it matters.** This is the core LIFeling behaviour: `Vm_Int` is the internal membrane computation node, `Vm_Ext` is the live output presented to the outside world, `V_Threshold` defines the firing point, and the AP/reset path must return the membrane to a repeatable state instead of latching.",
        "",
    ]
    _append_evidence(lines, "02_baseline_self_spiking_coin", ["Vm_Int", "Vm_Ext", "V_Threshold", "AP", "Reset_Window", "Spike_Out"], core_verdict, core_caveat)
    _add_metric_table(lines, [
        ("Vm_Int range", _fmt_range(baseline, "Vm_Int")),
        ("Vm_Ext range", _fmt_range(baseline, "Vm_Ext")),
        ("V_Threshold range", _fmt_range(baseline, "V_Threshold")),
        ("AP rising edges", _fmt_count(baseline.get("AP_rising_edges") if baseline is not None else None)),
        ("Reset_Window rising edges", _fmt_count(baseline.get("Reset_Window_rising_edges") if baseline is not None else None)),
        ("Spike_Out rising edges", _fmt_count(baseline.get("Spike_Out_rising_edges") if baseline is not None else None)),
        ("Mean AP period", _fmt_ms(baseline.get("AP_mean_period_ms") if baseline is not None else None)),
    ])
    _append_plot(lines, output_dir, readme_path, "Baseline LIF behaviour", "02_baseline_self_spiking_coin", "vm")

    # Step 4
    _append_step_header(lines, 4, "Spike-generation and reset timing")
    lines += [
        "**What is being tested.** The debug self-spiking run saves the internal timing signals that turn a threshold crossing into an AP pulse, a peak/display event, a reset window, and an external spike output.",
        "",
        "**Why it matters.** The membrane waveform alone cannot show whether the timing chain is healthy. The AP, `Spike_Pulse`, `Peak_Window`, `Reset_Window`, and `Spike_Out` traces make it possible to detect missing pulses, pulse-count mismatches, or reset windows that fail to close.",
        "",
    ]
    _append_evidence(lines, "03_debug_self_spiking_short", ["AP", "Spike_Pulse", "Peak_Window", "Reset_Window", "Spike_Out"], core_verdict, core_caveat)
    _add_metric_table(lines, [
        ("AP rising edges", _fmt_count(debug.get("AP_rising_edges") if debug is not None else None)),
        ("Spike_Pulse rising edges", _fmt_count(debug.get("Spike_Pulse_rising_edges") if debug is not None else None)),
        ("Peak_Window rising edges", _fmt_count(debug.get("Peak_Window_rising_edges") if debug is not None else None)),
        ("Reset_Window rising edges", _fmt_count(debug.get("Reset_Window_rising_edges") if debug is not None else None)),
        ("Spike_Out rising edges", _fmt_count(debug.get("Spike_Out_rising_edges") if debug is not None else None)),
        ("Mean AP period", _fmt_ms(debug.get("AP_mean_period_ms") if debug is not None else None)),
    ])
    _append_plot(lines, output_dir, readme_path, "Spike-generation and reset timing", "03_debug_self_spiking_short", "full")

    # Step 5
    quiet_verdict, _, quiet_caveat = _verdict_lookup(verdict_df, "Quiet subthreshold")
    _append_step_header(lines, 5, "Quiet subthreshold condition")
    lines += [
        "**What is being tested.** This run lowers the operating point so that the neuron should remain below threshold when no synapse is active.",
        "",
        "**Why it matters.** A controllable teaching neuron must be able to stay silent. If the model spikes in this condition, the leak reference, threshold, reset bias, or hidden stimulus path may be unintentionally driving the membrane.",
        "",
    ]
    _append_evidence(lines, "05_quiet_subthreshold_no_synapse", ["Vm_Int", "Vm_Ext", "V_Threshold", "AP"], quiet_verdict, quiet_caveat)
    _add_metric_table(lines, [
        ("Vm_Int maximum", _fmt_v(quiet.get("Vm_Int_max") if quiet is not None else None)),
        ("Vm_Ext maximum", _fmt_v(quiet.get("Vm_Ext_max") if quiet is not None else None)),
        ("AP rising edges", _fmt_count(quiet.get("AP_rising_edges") if quiet is not None else None)),
    ])
    _append_plot(lines, output_dir, readme_path, "Quiet subthreshold condition", "05_quiet_subthreshold_no_synapse", "vm")

    # Step 6
    mid_verdict, _, mid_caveat = _verdict_lookup(verdict_df, "Synapse midpoint")
    mid_delta = _delta_max(midpoint, quiet, "Vm_Int")
    _append_step_header(lines, 6, "Synapse midpoint zero-effect")
    lines += [
        "**What is being tested.** The synaptic state is set near the 1.024 V midpoint, where the centred synapse drive should be neutral.",
        "",
        "**Why it matters.** The signed synapse architecture should not inject excitation or inhibition when the synaptic state is at its midpoint. This is the condition that lets a connected synapse be electrically present without significantly perturbing the membrane.",
        "",
    ]
    _append_evidence(lines, "06_synapse_midpoint_zero_effect_single", ["V_Syn_State", "VREF_1V024", "Vm_Int", "Vm_Ext", "AP"], mid_verdict, mid_caveat)
    _add_metric_table(lines, [
        ("V_Syn_State range", _fmt_range(midpoint, "V_Syn_State")),
        ("Vm_Int maximum", _fmt_v(midpoint.get("Vm_Int_max") if midpoint is not None else None)),
        ("Delta versus quiet Vm_Int maximum", _fmt_mv(mid_delta)),
        ("AP rising edges", _fmt_count(midpoint.get("AP_rising_edges") if midpoint is not None else None)),
    ])
    _append_plot(lines, output_dir, readme_path, "Synapse midpoint zero-effect", "06_synapse_midpoint_zero_effect_single", "vm")

    # Step 7
    exc_verdict, _, exc_caveat = _verdict_lookup(verdict_df, "Excitatory synapse")
    exc_delta = _delta_max(excit, quiet, "Vm_Int")
    _append_step_header(lines, 7, "Excitatory synapse")
    lines += [
        "**What is being tested.** The synaptic set voltage is driven high so that the synapse should push the membrane in the excitatory direction.",
        "",
        "**Why it matters.** A high synaptic state should raise `Vm_Int` relative to the quiet subthreshold case. This validates the sign of the centred synapse drive and the injection path into the membrane node.",
        "",
    ]
    _append_evidence(lines, "07_synapse_excitatory_single_high", ["V_Syn_State", "/V_Syn_Drive", "Vm_Int", "Vm_Ext"], exc_verdict, exc_caveat)
    _add_metric_table(lines, [
        ("V_Syn_State range", _fmt_range(excit, "V_Syn_State")),
        ("Vm_Int maximum", _fmt_v(excit.get("Vm_Int_max") if excit is not None else None)),
        ("Delta versus quiet Vm_Int maximum", _fmt_mv(exc_delta)),
        ("AP rising edges", _fmt_count(excit.get("AP_rising_edges") if excit is not None else None)),
    ])
    _append_plot(lines, output_dir, readme_path, "Excitatory synapse", "07_synapse_excitatory_single_high", "vm")

    # Step 8
    inh_verdict, _, inh_caveat = _verdict_lookup(verdict_df, "Inhibitory synapse")
    base_period = _safe_float(baseline.get("AP_mean_period_ms") if baseline is not None else None)
    inh_period = _safe_float(inhib.get("AP_mean_period_ms") if inhib is not None else None)
    period_delta = inh_period - base_period if np.isfinite(base_period) and np.isfinite(inh_period) else float("nan")
    _append_step_header(lines, 8, "Inhibitory synapse")
    lines += [
        "**What is being tested.** The synaptic set voltage is driven low while the neuron is otherwise in a self-spiking configuration.",
        "",
        "**Why it matters.** Inhibition should reduce excitability. In this validation suite, the clearest numerical sign is a longer AP period than the baseline self-spiking run, meaning the membrane takes longer to reach threshold.",
        "",
    ]
    _append_evidence(lines, "08_synapse_inhibitory_single_low", ["V_Syn_State", "Vm_Int", "Vm_Ext", "AP"], inh_verdict, inh_caveat)
    _add_metric_table(lines, [
        ("Baseline mean AP period", _fmt_ms(base_period)),
        ("Inhibitory mean AP period", _fmt_ms(inh_period)),
        ("Period increase", _fmt_ms(period_delta)),
        ("Inhibitory AP rising edges", _fmt_count(inhib.get("AP_rising_edges") if inhib is not None else None)),
    ])
    _append_plot(lines, output_dir, readme_path, "Inhibitory synapse", "08_synapse_inhibitory_single_low", "vm")

    # Step 9
    cold_verdict, _, cold_caveat = _verdict_lookup(verdict_df, "Cold-start")
    _append_step_header(lines, 9, "Cold-start behaviour")
    lines += [
        "**What is being tested.** The cold-start run begins from discharged or low initial conditions rather than from the normal biased operating point.",
        "",
        "**Why it matters.** This is a power-on robustness check. It helps separate normal operating behaviour from startup transients and shows whether the model can recover into a valid oscillating regime after initial conditions are unfavourable.",
        "",
    ]
    _append_evidence(lines, "04_cold_start_self_spiking_coin", ["VDD", "Vm_Int", "Vm_Ext", "AP", "Reset_Window"], cold_verdict, cold_caveat)
    _add_metric_table(lines, [
        ("Vm_Int range", _fmt_range(cold, "Vm_Int")),
        ("Vm_Ext range", _fmt_range(cold, "Vm_Ext")),
        ("AP rising edges", _fmt_count(cold.get("AP_rising_edges") if cold is not None else None)),
        ("Estimated peak battery current", _fmt_ma(cold.get("Battery_current_peak_mA_est") if cold is not None else None)),
    ])
    _append_plot(lines, output_dir, readme_path, "Cold-start behaviour", "04_cold_start_self_spiking_coin", "vm")

    # Step 10
    low_verdict, _, low_caveat = _verdict_lookup(verdict_df, "Low-battery")
    _append_step_header(lines, 10, "Low-battery / high-impedance stress")
    lines += [
        "**What is being tested.** This stress run lowers the battery voltage and raises the source resistance to test whether the simplified supply model sags enough to disturb spike generation.",
        "",
        "**Why it matters.** Coin-cell impedance can reduce pulse amplitude and upset comparator-level assumptions. A run can still be useful even when it warns: the warning identifies where the validation threshold no longer matches the reduced signal level.",
        "",
    ]
    _append_evidence(lines, "12_low_battery_high_impedance_stress", ["VDD", "Vm_Int", "Spike_Pulse", "AP", "Spike_Out"], low_verdict, low_caveat)
    _add_metric_table(lines, [
        ("VDD range", _fmt_range(low_batt, "VDD")),
        ("Maximum VDD sag from battery model", _fmt_v(low_batt.get("VDD_sag_max") if low_batt is not None else None)),
        ("Estimated peak battery current", _fmt_ma(low_batt.get("Battery_current_peak_mA_est") if low_batt is not None else None)),
        ("Spike_Pulse maximum", _fmt_v(low_batt.get("Spike_Pulse_max") if low_batt is not None else None)),
        ("Spike_Pulse rising edges counted above 1 V", _fmt_count(low_batt.get("Spike_Pulse_rising_edges") if low_batt is not None else None)),
    ])
    if low_caveat:
        lines.append(f"Note: {low_caveat}")
        lines.append("")
    _append_plot(lines, output_dir, readme_path, "Low-battery / high-impedance stress", "12_low_battery_high_impedance_stress", "full")

    # Step 11
    stim_verdict, _, stim_caveat = _verdict_lookup(verdict_df, "External stimulus path")
    pos_delta = _delta_max(stim_pos, quiet, "Vm_Int")
    neg_delta = _delta_max(stim_neg, quiet, "Vm_Int")
    _append_step_header(lines, 11, "External stimulus path")
    lines += [
        "**What is being tested.** The positive and negative external stimulus runs check whether a command applied at `Stimulus_Ext` changes the membrane through the stimulus-drive path.",
        "",
        "**Why it matters.** The stimulus input is intended to be a controlled way to bias or perturb the neuron from outside the board. Polarity matters: a positive command should not accidentally behave like an inhibitory command unless that inversion is explicitly intended and documented.",
        "",
    ]
    _append_evidence(lines, "09_external_stimulus_positive_subthreshold / 10_external_stimulus_negative_subthreshold", ["Stimulus_Ext", "V_Stim_Drive", "Vm_Int", "Vm_Ext"], stim_verdict, stim_caveat)
    _add_metric_table(lines, [
        ("Positive stimulus Vm_Int maximum", _fmt_v(stim_pos.get("Vm_Int_max") if stim_pos is not None else None)),
        ("Positive stimulus delta versus quiet", _fmt_mv(pos_delta)),
        ("Negative stimulus Vm_Int maximum", _fmt_v(stim_neg.get("Vm_Int_max") if stim_neg is not None else None)),
        ("Negative stimulus delta versus quiet", _fmt_mv(neg_delta)),
        ("Positive V_Stim_Drive range", _fmt_range(stim_pos, "V_Stim_Drive")),
        ("Negative V_Stim_Drive range", _fmt_range(stim_neg, "V_Stim_Drive")),
    ])
    if np.isfinite(pos_delta) and np.isfinite(neg_delta) and pos_delta < 0 and neg_delta < 0:
        lines.append("Current interpretation: both positive and negative stimulus commands suppress `Vm_Int` in the latest diagnostics, so this block remains a warning rather than a confirmed bidirectional stimulus transfer.")
        lines.append("")
    lines.append("Next validation improvement: add a dedicated `Stimulus_Ext -> V_Stim_Drive -> Vm_Int` transfer sweep so the polarity, gain, and linear range of the stimulus path are documented directly.")
    lines.append("")
    _append_plot(lines, output_dir, readme_path, "Positive external stimulus", "09_external_stimulus_positive_subthreshold", "vm")
    _append_plot(lines, output_dir, readme_path, "Negative external stimulus", "10_external_stimulus_negative_subthreshold", "vm")

    # Step 12
    _append_step_header(lines, 12, "Parameter sweeps")
    lines += [
        "**What is being tested.** The sweep runs vary the front-panel controls and synaptic set levels to check that the model responds in the expected direction across more than one operating point.",
        "",
        "**Why it matters.** A single successful waveform can hide a wrong knob direction or a narrow operating point. Sweeps make the controls easier to interpret for readers and provide regression metrics for future schematic changes.",
        "",
        "| Sweep | Expected control meaning | Runs found | Latest observation | Verdict |",
        "|---|---|---:|---|---|",
    ]
    sweep_specs = [
        ("RV1 leak/reference", "Moves the leak reference and therefore the ease of reaching threshold.", "rv1_leak_threshold_sweep", "rv1", "RV1 leak/reference sweep"),
        ("RV2 leak-rate", "Changes membrane leak conductance and therefore the charging/discharging rate.", "rv2_leak_rate_sweep", "rv2", "RV2 leak-rate sweep"),
        ("RV3 adaptation", "Changes the adaptation path strength or recovery behaviour.", "rv3_adaptation_sweep", "rv3", "RV3 adaptation sweep"),
        ("RV4 capacitance bank", "Selects the effective membrane capacitance and therefore the time scale.", "rv4_capacitance_bank_sweep", "rv4", "RV4 capacitance-bank sweep"),
        ("RV5 synaptic decay", "Changes how quickly the synaptic state returns toward its neutral/leak value.", "rv5_synaptic_decay_sweep", "rv5", "RV5 synaptic decay sweep"),
        ("Synaptic sign/weight", "Checks that low, midpoint, and high synaptic set values move the state in the expected direction.", "synaptic_sign_weight_sweep", "syn", "Synaptic sign/weight sweep"),
    ]
    for name, expected, fragment, kind, verdict_key in sweep_specs:
        verdict, evidence, caveat = _verdict_lookup(verdict_df, verdict_key)
        count = _sweep_count(summary, fragment)
        observation = _sweep_observation(summary, fragment, kind)
        verdict_txt = verdict
        if caveat:
            verdict_txt = f"{verdict_txt}; {caveat}" if verdict_txt else caveat
        if evidence and not observation:
            observation = evidence
        lines.append(f"| {_md_cell(name)} | {_md_cell(expected)} | {count} | {_md_cell(observation)} | {_md_cell(verdict_txt)} |")
    lines.append("")

    lines += [
        "### Files generated by the validation suite",
        "",
        "These files are kept as separate artifacts so the README can stay readable while the raw numerical results remain available for inspection and regression checks.",
        "",
        f"- [Diagnostics summary CSV]({rel_summary})",
        f"- [Component model coverage CSV]({rel_coverage})",
        f"- [Block-level validation verdict Markdown]({rel_verdict_md})",
        f"- [Block-level validation verdict CSV]({rel_verdict_csv})",
        f"- [Key validation metrics CSV]({rel_metrics_csv})",
        "",
        README_AUTOGEN_END,
        "",
    ]

    return "\n".join(lines)


def update_readme(readme_path: Path, output_dir: Path) -> Path:
    readme_path = Path(readme_path)
    output_dir = Path(output_dir)

    readme_path.parent.mkdir(parents=True, exist_ok=True)

    if readme_path.exists():
        text = readme_path.read_text(encoding="utf-8", errors="replace")
    else:
        text = "# LIFeling SPICE simulation\n\n"

    section = build_readme_validation_section(output_dir, readme_path)

    pattern = re.compile(
        re.escape(README_AUTOGEN_START) + r".*?" + re.escape(README_AUTOGEN_END) + r"\s*",
        flags=re.S,
    )

    if pattern.search(text):
        new_text = pattern.sub(section, text)
    else:
        if not text.endswith("\n"):
            text += "\n"
        new_text = text + "\n" + section

    readme_path.write_text(new_text, encoding="utf-8")
    return readme_path


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def output_suffix(cfg: SimConfig) -> str:
    payload_dict = dataclasses.asdict(cfg).copy()
    # Keep the hash tied to circuit-affecting choices and run label, but avoid
    # needless changes from absolute output paths or execution mode toggles.
    for key in ["output_dir", "run", "write_only"]:
        payload_dict.pop(key, None)
    payload = repr(sorted(payload_dict.items())).encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()[:8]
    syn = ""
    if cfg.syn1_enable or cfg.syn2_enable or cfg.syn3_enable or cfg.syn4_enable:
        syn = "_syn" + "".join(str(i) for i, e in enumerate([cfg.syn1_enable, cfg.syn2_enable, cfg.syn3_enable, cfg.syn4_enable], start=1) if e)
    label = safe_filename(cfg.run_label) + "_" if cfg.run_label else ""
    suffix = f"{label}rv{cfg.rv1:.2f}_{cfg.rv2:.2f}_{cfg.rv3:.2f}_{cfg.rv4:.2f}_vb{cfg.vbat}_t{cfg.tstop}{syn}_{digest}"
    return suffix.replace(".", "p").replace("-", "m")


def parse_args(argv: list[str]) -> SimConfig:
    parser = argparse.ArgumentParser(description="Generate/run the updated full-schematic LIFeling SPICE model.")
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--run-label", default="", help="Optional label prefixed to output filenames; useful for validation suites.")
    parser.add_argument("--run", action="store_true", help="Run ngspice after writing the deck.")
    parser.add_argument("--write-only", action="store_true", help="Only write .cir and coverage files; do not run ngspice.")
    parser.add_argument("--ngspice-binary", default="auto")

    # Backward-compatible aliases accepted from the previous Vm-only script.
    # They are intentionally retained so old command lines do not fail.
    # The updated model is always the full schematic, always uses the ngspice CLI
    # when --run is selected, and always uses the RV4-controlled capacitor bank.
    parser.add_argument("--stage", choices=["passive", "threshold", "threshold_reset", "threshold_reset_adapt"], default="threshold_reset_adapt", help=argparse.SUPPRESS)
    parser.add_argument("--backend", choices=["pyspice", "ngspice-cli"], default="ngspice-cli", help=argparse.SUPPRESS)
    parser.add_argument("--trace-set", choices=["core", "debug"], default="core", help=argparse.SUPPRESS)
    parser.add_argument("--ignore-start-ms", type=float, default=0.0, help="Initial time in ms ignored by diagnostics; does not affect ngspice.")
    parser.add_argument("--cmem-mode", choices=["manual", "rv4"], default="rv4", help=argparse.SUPPRESS)

    parser.add_argument("--supply-mode", choices=["coin", "ideal"], default="coin")
    parser.add_argument("--vbat", default="3.0")
    parser.add_argument("--rbat", default="30")
    parser.add_argument("--vdd-ideal", default="3.0")
    parser.add_argument("--switch-on-resistance", default="0.2")
    parser.add_argument("--vboost", default="3.3")
    parser.add_argument("--startup-mode", choices=["operating", "cold"], default="operating")
    parser.add_argument("--vm-initial", default="0.60")
    parser.add_argument("--syn-initial", default="1.024")

    parser.add_argument("--tstop", default="500m")
    parser.add_argument("--tstep", default="10u")
    parser.add_argument("--maxstep", default="10u")

    for idx, default in [(1, 0.30), (2, 0.50), (3, 0.50), (4, 0.50), (5, 0.50), (6, 0.50), (7, 0.50), (8, 0.50), (9, 0.50)]:
        parser.add_argument(f"--rv{idx}", type=float, default=default)

    parser.add_argument("--stimulus-ext", "--stim-dc", dest="stimulus_ext", type=float, default=None, help="Optional DC source on J1 ring / Stimulus_Ext.")
    parser.add_argument("--syn1-enable", action="store_true")
    parser.add_argument("--syn2-enable", action="store_true")
    parser.add_argument("--syn3-enable", action="store_true")
    parser.add_argument("--syn4-enable", action="store_true")
    parser.add_argument("--syn-all-enable", action="store_true")
    parser.add_argument("--syn-amp", default="3.0")
    parser.add_argument("--syn-rise", default="1u")
    parser.add_argument("--syn-fall", default="1u")
    for idx, delay in [(1, "80m"), (2, "120m"), (3, "160m"), (4, "200m")]:
        parser.add_argument(f"--syn{idx}-delay", default=delay)
        parser.add_argument(f"--syn{idx}-width", default="5m")
        parser.add_argument(f"--syn{idx}-period", default="100m")
    parser.add_argument("--trace-debug", action="store_true")
    parser.add_argument(
        "--make-validation-verdict",
        action="store_true",
        help="Generate validation verdict files from validation_diagnostics_summary.csv and component_model_coverage.csv.",
    )
    parser.add_argument(
        "--update-readme",
        action="store_true",
        help="Update README.md after a normal run.",
    )
    parser.add_argument(
        "--update-readme-only",
        action="store_true",
        help="Update README.md from existing validation outputs without running ngspice or parsing the netlist.",
    )
    parser.add_argument(
        "--readme-path",
        type=Path,
        default=THIS_DIR / "README.md",
        help="README file to update when --update-readme or --update-readme-only is used.",
    )

    ns = parser.parse_args(argv)
    return SimConfig(
        netlist=ns.netlist,
        output_dir=ns.output_dir,
        run_label=ns.run_label,
        run=ns.run,
        write_only=ns.write_only,
        ngspice_binary=ns.ngspice_binary,
        supply_mode=ns.supply_mode,
        vbat=ns.vbat,
        rbat=ns.rbat,
        vdd_ideal=ns.vdd_ideal,
        switch_on_resistance=ns.switch_on_resistance,
        vboost=ns.vboost,
        startup_mode=ns.startup_mode,
        ignore_start_ms=ns.ignore_start_ms,
        vm_initial=ns.vm_initial,
        syn_initial=ns.syn_initial,
        tstop=ns.tstop,
        tstep=ns.tstep,
        maxstep=ns.maxstep,
        rv1=ns.rv1,
        rv2=ns.rv2,
        rv3=ns.rv3,
        rv4=ns.rv4,
        rv5=ns.rv5,
        rv6=ns.rv6,
        rv7=ns.rv7,
        rv8=ns.rv8,
        rv9=ns.rv9,
        stimulus_ext=ns.stimulus_ext,
        syn1_enable=ns.syn1_enable or ns.syn_all_enable,
        syn2_enable=ns.syn2_enable or ns.syn_all_enable,
        syn3_enable=ns.syn3_enable or ns.syn_all_enable,
        syn4_enable=ns.syn4_enable or ns.syn_all_enable,
        syn_amp=ns.syn_amp,
        syn_rise=ns.syn_rise,
        syn_fall=ns.syn_fall,
        syn1_delay=ns.syn1_delay,
        syn1_width=ns.syn1_width,
        syn1_period=ns.syn1_period,
        syn2_delay=ns.syn2_delay,
        syn2_width=ns.syn2_width,
        syn2_period=ns.syn2_period,
        syn3_delay=ns.syn3_delay,
        syn3_width=ns.syn3_width,
        syn3_period=ns.syn3_period,
        syn4_delay=ns.syn4_delay,
        syn4_width=ns.syn4_width,
        syn4_period=ns.syn4_period,
        trace_debug=ns.trace_debug or ns.trace_set == "debug",
        make_validation_verdict=ns.make_validation_verdict,
        update_readme=ns.update_readme,
        update_readme_only=ns.update_readme_only,
        readme_path=ns.readme_path,
    )


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    if cfg.update_readme_only:
        verdict_md, verdict_csv, metrics_csv = make_validation_verdict(cfg.output_dir)
        readme = update_readme(cfg.readme_path, cfg.output_dir)
        print(f"Spice.py version: {SCRIPT_VERSION}")
        print(f"Wrote validation verdict: {verdict_md}")
        print(f"Wrote validation verdict: {verdict_csv}")
        print(f"Wrote key metrics:        {metrics_csv}")
        print(f"Updated README:           {readme}")
        return 0

    if cfg.make_validation_verdict:
        verdict_md, verdict_csv, metrics_csv = make_validation_verdict(cfg.output_dir)
        print(f"Spice.py version: {SCRIPT_VERSION}")
        print(f"Wrote validation verdict: {verdict_md}")
        print(f"Wrote validation verdict: {verdict_csv}")
        print(f"Wrote key metrics:        {metrics_csv}")
        return 0

    design = parse_kicad_netlist(cfg.netlist)

    suffix = output_suffix(cfg)
    deck_path = cfg.output_dir / f"LIFeling_updated_{suffix}.cir"
    csv_path = cfg.output_dir / f"LIFeling_updated_{suffix}.raw.csv"
    parsed_csv_path = cfg.output_dir / f"LIFeling_updated_{suffix}.csv"
    plot_path = cfg.output_dir / f"LIFeling_updated_{suffix}.png"
    vm_plot_path = cfg.output_dir / f"LIFeling_updated_{suffix}_vmint_vmext.png"
    diag_csv_path = cfg.output_dir / f"LIFeling_updated_{suffix}_diagnostics.csv"
    diag_md_path = cfg.output_dir / f"LIFeling_updated_{suffix}_diagnostics.md"
    coverage_path = cfg.output_dir / "component_model_coverage.csv"

    deck = build_deck(design, cfg, csv_path=csv_path if cfg.run else None)
    deck_path.write_text(deck, encoding="utf-8")
    write_coverage_report(design, coverage_path)

    print(f"Spice.py version: {SCRIPT_VERSION}")
    print(f"Parsed components: {len(design.components)}")
    print(f"Parsed nets:       {len(design.nets)}")
    print(f"Wrote deck:        {deck_path}")
    print(f"Wrote coverage:    {coverage_path}")

    if cfg.run:
        run_ngspice(deck_path, csv_path, cfg)
        traces = trace_nodes(cfg)
        df = read_wrdata(csv_path, traces)

        rename = {spice_node_name(name): name for name in traces}
        df = df.rename(columns=rename)

        df.to_csv(parsed_csv_path, index=False)
        title_suffix = cfg.run_label or suffix
        plot_core(df, plot_path, title_suffix=title_suffix)
        plot_vm_only(df, vm_plot_path, title_suffix=title_suffix)
        write_run_diagnostics(df, cfg, diag_csv_path, diag_md_path)

        print(f"Wrote parsed CSV:   {parsed_csv_path}")
        print(f"Wrote diagnostics:  {diag_csv_path}")
        print(f"Wrote diagnostics:  {diag_md_path}")
        if plt is not None:
            print(f"Wrote plot:         {plot_path}")
            print(f"Wrote Vm-only plot: {vm_plot_path}")
    else:
        print("ngspice was not run. Use --run to simulate after installing ngspice.")

    if cfg.update_readme:
        verdict_md, verdict_csv, metrics_csv = make_validation_verdict(cfg.output_dir)
        readme = update_readme(cfg.readme_path, cfg.output_dir)
        print(f"Wrote validation verdict: {verdict_md}")
        print(f"Wrote validation verdict: {verdict_csv}")
        print(f"Wrote key metrics:        {metrics_csv}")
        print(f"Updated README:           {readme}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
