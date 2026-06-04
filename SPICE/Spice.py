#!/usr/bin/env python3
"""
Spiky_Lui2 Vm simulation with Python + ngspice/PySpice.

This version is aligned to the current KiCad schematic/netlist naming for the
Vm-relevant LIF circuit:

    passive               : V_Leak reference, RV2 leakage path, Vm_Int capacitance
    threshold             : U6B TLV7044, Q1, AP, Rising_AP, Spike_Pulse
    threshold_reset       : U6A/U6C TLV7044, Q3-Q6, Peak_Window, Reset_Window
    threshold_reset_adapt : U1C/U1D, D4/D5/D7, Vw adaptation path, Q2

Important simplifications
-------------------------
This is still a simulation model, not a full KiCad-generated netlist. It models
only the Vm-relevant subcircuit and keeps explicit comments tying each SPICE-safe
node name back to the KiCad net name. Some SPICE node names omit KiCad's leading
slash because ngspice-safe names are easier to parse and plot.

The plotting, .save list, CSV parsing, and printed diagnostics all use the same
trace list returned by traces_for_config(). Therefore, every node printed in the
console is also present in the plotted output.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# -----------------------------------------------------------------------------
# User-editable vendor model configuration
# -----------------------------------------------------------------------------

THIS_DIR = Path(__file__).resolve().parent
MODEL_DIR = THIS_DIR / "models"
OUTPUT_DIR = THIS_DIR / "spiky_pyspice_output"

# Op-amp: schematic U1/U2/U19 = MCP6004T-I/ST.
# The Microchip MCP6001/2/4 macromodel is often distributed as a family model.
MCP6004_LIB = MODEL_DIR / "MCP6001.txt"
MCP6004_SUBCKT_NAME = "MCP6001"

# Comparator: schematic U6 = TLV7044PWR.
# Update these to match the exact TI model file/subcircuit name you download.
TLV7044_LIB = MODEL_DIR / "TLV7044.lib"
TLV7044_SUBCKT_NAME = "TLV7044"

# MOSFET: schematic Q1/Q3/Q4/Q5/Q6/Q7 = BSS138.
BSS138_LIB = MODEL_DIR / "BSS138.lib"
BSS138_MODEL_NAME = "BSS138"

# BJT: schematic Q2 = MMBT3904.
MMBT3904_LIB = MODEL_DIR / "MMBT3904.spice.txt"
MMBT3904_MODEL_NAME = "DI_MMBT3904"

# Signal diodes: schematic D4/D5/D7 = 1N4148WS.
DIODE_1N4148_LIB = MODEL_DIR / "1n4148_spice.lib"
DIODE_1N4148_NAME = "1N4148"
DIODE_1N4148_IS_SUBCKT = True

# Spike diode: schematic D8 = RB521S30T1G Schottky.
RB521S30_LIB = MODEL_DIR / "RB521S30.lib"
RB521S30_NAME = "RB521S30"
RB521S30_IS_SUBCKT = False

NumberLike = str | float | int


# -----------------------------------------------------------------------------
# KiCad-net aliases used by this SPICE deck
# -----------------------------------------------------------------------------

# KiCad GNDREF is mapped directly to ngspice ground 0.
GND = "0"
VDD = "VDD"

# Passive / references.
V_LEAK_REF_MAX = "V_Leak_Ref_Max"        # KiCad: V_Leak_Ref_Max
V_LEAK_REF = "V_Leak_ref"                # KiCad: /V_Leak_ref
V_LEAK = "V_Leak"                        # KiCad: V_Leak
VM = "Vm_Int"                            # KiCad: Vm_Int
RV2_PIN1 = "RV2_pin1"                    # KiCad: Net-(R32-Pad1)
V_RESET_REF = "V_Reset_Ref"              # KiCad: V_Reset_Ref
RESET_INJ = "Reset_Injection_Drive"      # KiCad: /Reset_Injection_Drive

# Threshold / AP / spike.
V_THRESHOLD = "V_Threshold"              # KiCad: V_Threshold
Q1_GATE = "Q1_G"                         # KiCad: Net-(Q1-G)
AP = "AP"                                # KiCad: AP
RISING_AP = "Rising_AP"                  # KiCad: /Rising_AP
SPIKE_PULSE = "Spike_Pulse"              # KiCad: Spike_Pulse

# Peak/reset windows.
PEAK_WINDOW = "Peak_Window"              # KiCad: Peak_Window
RESET_WINDOW = "Reset_Window"            # KiCad: Reset_Window
U6C_PLUS = "U6C_INC_plus"                # KiCad: Net-(U6C-INC+)
U6C_MINUS = "U6C_INC_minus"              # KiCad: Net-(U6C-INC-)
Q3_D = "Q3_D"                            # KiCad: Net-(Q3-D)
Q4_D = "Q4_D"                            # KiCad: Net-(Q4-D)
Q5_D = "Q5_D"                            # KiCad: Net-(Q5-D)
Q6_D = "Q6_D"                            # KiCad: Net-(Q6-D)

# Adaptation.
U1C_OUT = "U1C_OUT"                      # KiCad: Net-(U1B-VINC-), U1C output/follower node
VKICK = "Vkick"                          # KiCad: /Vkick
VW = "Vw"                                # KiCad: Vw
RV3_BOTTOM = "RV3_bottom"                # KiCad: Net-(R42-Pad1)
VW_BUFF = "Vw_buff"                      # KiCad: Vw_buff
Q2_B = "Q2_B"                            # KiCad: Net-(Q2-Pad1)
Q2_C = "Q2_C"                            # KiCad: Net-(Q2-Pad3)

# Optional external stimulus input.
STIMULUS_EXT = "Stimulus_Ext"            # KiCad: Stimulus_Ext
V_STIM_CMD = "V_Stim_Cmd"                # KiCad: V_Stim_Cmd
V_STIM_DRIVE = "V_Stim_Drive"            # KiCad: V_Stim_Drive


@dataclasses.dataclass(frozen=True)
class Trace:
    """One saved/plotted/printed voltage trace."""

    key: str              # DataFrame column and diagnostic name
    node: str             # SPICE node name
    label: str            # Plot label, usually the KiCad net name


BASE_TRACES = [
    Trace("VM", VM, "Vm_Int"),
    Trace("VLEAK", V_LEAK, "V_Leak"),
    Trace("VLEAK_REF", V_LEAK_REF, "/V_Leak_ref"),
    Trace("VLEAK_REF_MAX", V_LEAK_REF_MAX, "V_Leak_Ref_Max"),
    Trace("V_RESET_REF", V_RESET_REF, "V_Reset_Ref"),
    Trace("RESET_INJ", RESET_INJ, "/Reset_Injection_Drive"),
]

THRESHOLD_TRACES = [
    Trace("VTHRESH", V_THRESHOLD, "V_Threshold"),
    Trace("Q1_GATE", Q1_GATE, "Net-(Q1-G)"),
    Trace("AP", AP, "AP"),
    Trace("RISING_AP", RISING_AP, "/Rising_AP"),
    Trace("SPIKE_PULSE", SPIKE_PULSE, "Spike_Pulse"),
]

RESET_TRACES = [
    Trace("PEAK_WINDOW", PEAK_WINDOW, "Peak_Window"),
    Trace("RESET_WINDOW", RESET_WINDOW, "Reset_Window"),
    Trace("U6C_PLUS", U6C_PLUS, "Net-(U6C-INC+)"),
    Trace("U6C_MINUS", U6C_MINUS, "Net-(U6C-INC-)"),
    Trace("Q3_D", Q3_D, "Net-(Q3-D)"),
    Trace("Q4_D", Q4_D, "Net-(Q4-D)"),
    Trace("Q5_D", Q5_D, "Net-(Q5-D)"),
    Trace("Q6_D", Q6_D, "Net-(Q6-D)"),
]

ADAPT_TRACES = [
    Trace("U1C_OUT", U1C_OUT, "U1C output / Net-(U1B-VINC-)"),
    Trace("VKICK", VKICK, "/Vkick"),
    Trace("VW", VW, "Vw"),
    Trace("VW_BUFF", VW_BUFF, "Vw_buff"),
    Trace("Q2_B", Q2_B, "Net-(Q2-Pad1)"),
    Trace("Q2_C", Q2_C, "Net-(Q2-Pad3)"),
]

STIM_TRACES = [
    Trace("STIMULUS_EXT", STIMULUS_EXT, "Stimulus_Ext"),
    Trace("V_STIM_CMD", V_STIM_CMD, "V_Stim_Cmd"),
    Trace("V_STIM_DRIVE", V_STIM_DRIVE, "V_Stim_Drive"),
]


@dataclasses.dataclass
class SimConfig:
    stage: Literal["passive", "threshold", "threshold_reset", "threshold_reset_adapt"] = "passive"
    strict_vendor: bool = False
    vdd: str = "3"
    rv1_fraction: float = 0.5
    rv2_fraction: float = 0.5
    rv3_fraction: float = 0.5
    cmem: str = "2.2u"
    vm_initial: str = "0.385"
    tstop: str = "1"
    tstep: str = "10u"
    maxstep: str = "10u"
    probe: Literal["ideal", "scope10m", "probe1m"] = "ideal"
    stim_dc: float | None = None
    backend: Literal["pyspice", "ngspice-cli"] = "ngspice-cli"
    ngspice_binary: str = "auto"

    @property
    def bss138_model(self) -> str:
        return BSS138_MODEL_NAME if self.strict_vendor else "BSS138_FALLBACK"

    @property
    def npn_model(self) -> str:
        return MMBT3904_MODEL_NAME if self.strict_vendor else "MMBT3904_FALLBACK"

    @property
    def signal_diode_name(self) -> str:
        return DIODE_1N4148_NAME if self.strict_vendor else "D1N4148_FALLBACK"

    @property
    def spike_diode_name(self) -> str:
        return RB521S30_NAME if self.strict_vendor else "RB521S30_FALLBACK"


def traces_for_config(cfg: SimConfig) -> list[Trace]:
    """Single source of truth for .save, CSV parsing, plotting, and printing."""
    traces = list(BASE_TRACES)
    if cfg.stage in {"threshold", "threshold_reset", "threshold_reset_adapt"}:
        traces += THRESHOLD_TRACES
    if cfg.stage in {"threshold_reset", "threshold_reset_adapt"}:
        traces += RESET_TRACES
    if cfg.stage == "threshold_reset_adapt":
        traces += ADAPT_TRACES
    if cfg.stim_dc is not None:
        traces += STIM_TRACES
    return traces


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def _to_float_suffix(value: str) -> float:
    """Convert a simple SPICE value string to float, for derived values only."""
    value = value.strip().replace("Ω", "").replace("ohm", "")
    match = re.fullmatch(r"([0-9]*\.?[0-9]+)\s*([a-zA-Zµu]*)", value)
    if not match:
        raise ValueError(f"Cannot parse SPICE value: {value!r}")
    base = float(match.group(1))
    suffix = match.group(2).lower().replace("µ", "u")
    multipliers = {
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
    if suffix not in multipliers:
        raise ValueError(f"Unsupported suffix {suffix!r} in {value!r}")
    return base * multipliers[suffix]


def split_pot(total: str, fraction: float) -> tuple[str, str]:
    """Return lower and upper resistances for a three-terminal pot.

    fraction = 0.0 means wiper at pin 1 / low end.
    fraction = 1.0 means wiper at pin 3 / high end.
    """
    total_ohm = _to_float_suffix(total)
    fraction = float(np.clip(fraction, 1e-6, 1 - 1e-6))
    lower = total_ohm * fraction
    upper = total_ohm * (1.0 - fraction)
    return f"{lower:.12g}", f"{upper:.12g}"


def pot_upper_segment(total: str, fraction: float) -> str:
    """Resistance between wiper and pin 3/high end."""
    _, upper = split_pot(total, fraction)
    return upper


def detect_model_statement(path: Path, name: str) -> str | None:
    """Return '.model' or '.subckt' if a model/subckt name is found in a file."""
    if not path.exists():
        return None
    text = path.read_text(errors="ignore")
    pattern_model = re.compile(rf"^\s*\.model\s+{re.escape(name)}\b", re.I | re.M)
    pattern_subckt = re.compile(rf"^\s*\.subckt\s+{re.escape(name)}\b", re.I | re.M)
    if pattern_model.search(text):
        return ".model"
    if pattern_subckt.search(text):
        return ".subckt"
    return None


def include_line(path: Path) -> str:
    p = str(path.resolve()).replace("\\", "/")
    return f'.include "{p}"'


def patched_mcp6001_model_for_ngspice(original_path: Path) -> Path:
    """Create an ngspice-compatible patched copy of the Microchip MCP6001 model."""
    if not original_path.exists():
        raise FileNotFoundError(f"Cannot find MCP6001/MCP6004 model file: {original_path}")

    patched_dir = OUTPUT_DIR / "patched_models"
    patched_dir.mkdir(parents=True, exist_ok=True)
    patched_path = patched_dir / "MCP6001_ngspice.lib"

    text = original_path.read_text(errors="replace")
    text = re.sub(
        r"(?im)^(\s*r\S+\s+\S+\s+\S+\s+\S+)\s+tc\s+(\S+)\s+(\S+)\s*$",
        r"\1 TC=\2,\3",
        text,
    )
    patched_path.write_text(text)
    return patched_path


def find_ngspice_binary(requested: str) -> str:
    """Find ngspice.exe robustly on Windows/PyCharm."""
    requested = (requested or "").strip().strip('"')

    if requested and requested.lower() not in {"auto", "ngspice", "ngspice.exe"}:
        p = Path(requested)
        if p.is_file():
            return str(p)
        found = shutil.which(requested)
        if found:
            return found

    env_value = os.environ.get("NGSPICE_BINARY", "").strip().strip('"')
    if env_value:
        p = Path(env_value)
        if p.is_file():
            return str(p)
        found = shutil.which(env_value)
        if found:
            return found

    for name in ("ngspice", "ngspice.exe"):
        found = shutil.which(name)
        if found:
            return found

    common_paths = [
        Path(r"C:\Spice64\bin\ngspice.exe"),
        Path(r"C:\Spice64_d\bin\ngspice.exe"),
        Path(r"C:\Program Files\ngspice\bin\ngspice.exe"),
        Path(r"C:\Program Files (x86)\ngspice\bin\ngspice.exe"),
        Path(r"C:\Program Files\KiCad\bin\ngspice.exe"),
        Path(r"C:\Program Files\KiCad\10.0\bin\ngspice.exe"),
        Path(r"C:\Program Files\KiCad\9.0\bin\ngspice.exe"),
        Path(r"C:\Program Files\KiCad\8.0\bin\ngspice.exe"),
    ]

    for p in common_paths:
        if p.is_file():
            return str(p)

    searched = "\n".join(f"  - {p}" for p in common_paths)
    raise FileNotFoundError(
        "Could not find ngspice.exe.\n\n"
        "Fix options:\n"
        "  1. Install ngspice for Windows.\n"
        "  2. Add the folder containing ngspice.exe to your Windows PATH.\n"
        "  3. Or pass the exact path, for example:\n\n"
        r'     --ngspice-binary "C:\Spice64\bin\ngspice.exe"' + "\n\n"
        "The script also checked these common locations:\n"
        f"{searched}\n"
    )


# -----------------------------------------------------------------------------
# SPICE model includes, wrappers, and primitive helpers
# -----------------------------------------------------------------------------


def build_vendor_includes(cfg: SimConfig) -> list[str]:
    """Return .include lines or fallback model definitions."""
    lines: list[str] = []

    if cfg.strict_vendor:
        mcp6004_include = patched_mcp6001_model_for_ngspice(MCP6004_LIB)

        required: list[tuple[Path, str, str]] = [(mcp6004_include, MCP6004_SUBCKT_NAME, ".subckt")]
        include_paths: list[Path] = [mcp6004_include]

        if cfg.stage in {"threshold", "threshold_reset", "threshold_reset_adapt"}:
            required += [
                (TLV7044_LIB, TLV7044_SUBCKT_NAME, ".subckt"),
                (BSS138_LIB, BSS138_MODEL_NAME, ".model"),
            ]
            include_paths += [TLV7044_LIB, BSS138_LIB]

            if RB521S30_IS_SUBCKT:
                required.append((RB521S30_LIB, RB521S30_NAME, ".subckt"))
            else:
                required.append((RB521S30_LIB, RB521S30_NAME, ".model"))
            include_paths.append(RB521S30_LIB)

        if cfg.stage == "threshold_reset_adapt":
            required += [(MMBT3904_LIB, MMBT3904_MODEL_NAME, ".model")]
            include_paths.append(MMBT3904_LIB)

            if DIODE_1N4148_IS_SUBCKT:
                required.append((DIODE_1N4148_LIB, DIODE_1N4148_NAME, ".subckt"))
            else:
                required.append((DIODE_1N4148_LIB, DIODE_1N4148_NAME, ".model"))
            include_paths.append(DIODE_1N4148_LIB)

        missing: list[str] = []
        for path, name, expected_kind in required:
            kind = detect_model_statement(path, name)
            if kind != expected_kind:
                missing.append(f"{path} must contain {expected_kind} {name}")

        if missing:
            raise FileNotFoundError(
                "Strict vendor mode requested, but these models were not found:\n"
                + "\n".join(f"  - {m}" for m in missing)
                + "\n\nPut the vendor model files in ./models/ and edit the *_LIB/*_NAME constants."
            )

        for path in dict.fromkeys(include_paths):
            lines.append(include_line(path))
    else:
        lines += [
            "* ---- Fallback models: replace with vendor models for final analysis ----",
            ".model D1N4148_FALLBACK D(Is=2.52n Rs=0.568 N=1.752 Cjo=2p M=0.4 Eg=1.11 Tt=4n)",
            ".model RB521S30_FALLBACK D(Is=5u Rs=1 N=1.05 Cjo=10p Eg=0.69 Bv=30 Ibv=10u)",
            ".model MMBT3904_FALLBACK NPN(Is=6.7f Bf=250 Vaf=100 Ikf=0.1 Xtb=1.5 Br=6 Cjc=4p Cje=8p Tf=300p Tr=50n)",
            ".model BSS138_FALLBACK NMOS(Level=1 Vto=1.2 Kp=2m Lambda=0.02 Rd=2 Rs=2 Cgd=20p Cgs=20p)",
            ".model SW_OC SW(Ron=10 Roff=1e12 Vt=0 Vh=1m)",
        ]

    return lines


def build_vendor_wrappers(cfg: SimConfig) -> list[str]:
    """Return wrappers for op-amp and comparator subcircuits.

    Local wrapper APIs used by this deck:
      MCP6004_UNIT OUT MINUS PLUS VDD VSS
      TLV7044_UNIT OUT MINUS PLUS VDD VSS

    The internal X... pin order may need adjustment to match the exact vendor
    .SUBCKT line in your downloaded model file.
    """
    if not cfg.strict_vendor:
        return []

    lines = [
        "* ---- Local wrappers around vendor macromodels ----",
        "* MCP6004_UNIT wrapper API: OUT MINUS PLUS VDD VSS",
        ".subckt MCP6004_UNIT OUT MINUS PLUS VDD VSS",
        "* Common Microchip MCP6001 family order assumed here: PLUS MINUS VDD VSS OUT",
        f"XAMP PLUS MINUS VDD VSS OUT {MCP6004_SUBCKT_NAME}",
        ".ends MCP6004_UNIT",
    ]

    if cfg.stage in {"threshold", "threshold_reset", "threshold_reset_adapt"}:
        lines += [
            "",
            "* TLV7044_UNIT wrapper API: OUT MINUS PLUS VDD VSS",
            ".subckt TLV7044_UNIT OUT MINUS PLUS VDD VSS",
            "* Adjust the order below if the TI model .SUBCKT uses another pin order.",
            f"XCMP PLUS MINUS VDD VSS OUT {TLV7044_SUBCKT_NAME}",
            ".ends TLV7044_UNIT",
        ]

    return lines


def opamp_follower(lines: list[str], name: str, out: str, inp: str, cfg: SimConfig) -> None:
    """Add an op-amp voltage follower."""
    if cfg.strict_vendor:
        lines.append(f"X{name} {out} {out} {inp} {VDD} {GND} MCP6004_UNIT")
    else:
        lines.append(f"E{name} {out} {GND} {inp} {GND} 1")


def tlv7044_oc(lines: list[str], name: str, out: str, minus: str, plus: str, cfg: SimConfig) -> None:
    """Add a TLV7044 comparator model.

    Fallback mode models the output as open-drain: OUT is pulled to ground when
    V(minus) > V(plus). Pull-up resistors are external, matching the schematic.
    """
    if cfg.strict_vendor:
        lines.append(f"X{name} {out} {minus} {plus} {VDD} {GND} TLV7044_UNIT")
    else:
        lines.append(f"S{name} {out} {GND} {minus} {plus} SW_OC")


def add_model_or_subckt_diode(
    lines: list[str],
    name: str,
    anode: str,
    cathode: str,
    model_or_subckt: str,
    is_subckt: bool,
) -> None:
    """Add a diode. SPICE order is anode, cathode."""
    if is_subckt:
        lines.append(f"X{name} {anode} {cathode} {model_or_subckt}")
    else:
        lines.append(f"D{name} {anode} {cathode} {model_or_subckt}")


def add_signal_diode(lines: list[str], name: str, anode: str, cathode: str, cfg: SimConfig) -> None:
    add_model_or_subckt_diode(
        lines,
        name,
        anode,
        cathode,
        cfg.signal_diode_name,
        DIODE_1N4148_IS_SUBCKT if cfg.strict_vendor else False,
    )


def add_spike_schottky(lines: list[str], name: str, anode: str, cathode: str, cfg: SimConfig) -> None:
    add_model_or_subckt_diode(
        lines,
        name,
        anode,
        cathode,
        cfg.spike_diode_name,
        RB521S30_IS_SUBCKT if cfg.strict_vendor else False,
    )


# -----------------------------------------------------------------------------
# Netlist generation
# -----------------------------------------------------------------------------


def add_header(cfg: SimConfig) -> list[str]:
    lines = [
        f"* Spiky_Lui2 Vm simulation: stage={cfg.stage}",
        "* Generated by spiky_lui2_vm_groundtruth.py",
        "* KiCad GNDREF is mapped to ngspice ground node 0.",
        ".option method=gear reltol=1e-4 abstol=1e-12 vntol=1e-6 chgtol=1e-14",
        ".option itl1=500 itl4=500",
        ".temp 25",
        "",
    ]
    lines += build_vendor_includes(cfg)
    lines += [""]
    lines += build_vendor_wrappers(cfg)
    lines += [""]
    return lines


def add_references_and_passive_vm(lines: list[str], cfg: SimConfig) -> None:
    rv1_low, rv1_high = split_pot("50k", cfg.rv1_fraction)
    rv2_low, rv2_high = split_pot("50k", cfg.rv2_fraction)

    lines += [
        "* ---- Supply and reference dividers ----",
        f"VDD {VDD} {GND} DC {cfg.vdd}",
        f"CDEC1 {VDD} {GND} 100n",
        f"CDEC2 {VDD} {GND} 10u",
        "",
        "* Ground-truth divider: R4=49.9k VDD->V_Leak_Ref_Max, R5=100k V_Leak_Ref_Max->GNDREF",
        f"R4 {VDD} {V_LEAK_REF_MAX} 49.9k",
        f"R5 {V_LEAK_REF_MAX} {GND} 100k",
        "",
        f"* RV1=50k: pin1=GNDREF, pin2=/V_Leak_ref, pin3=V_Leak_Ref_Max; fraction={cfg.rv1_fraction:.3f}",
        f"RV1_LOW {V_LEAK_REF} {GND} {rv1_low}",
        f"RV1_HIGH {V_LEAK_REF_MAX} {V_LEAK_REF} {rv1_high}",
    ]
    opamp_follower(lines, "U1A", V_LEAK, V_LEAK_REF, cfg)

    lines += [
        "",
        "* Reset injection reference: R10=69.8k VDD->V_Reset_Ref, R11=10k V_Reset_Ref->GNDREF",
        f"R10 {VDD} {V_RESET_REF} 69.8k",
        f"R11 {V_RESET_REF} {GND} 10k",
    ]
    opamp_follower(lines, "U2B", RESET_INJ, V_RESET_REF, cfg)

    lines += [
        "",
        "* ---- Passive membrane core ----",
        "* RV2 ground truth: pin1=Net-(R32-Pad1), pin2=Vm_Int, pin3=V_Leak, R32=1k pin1->Vm_Int.",
        f"RV2_LOWER {RV2_PIN1} {VM} {rv2_low}",
        f"R32 {RV2_PIN1} {VM} 1k",
        f"RV2_UPPER {V_LEAK} {VM} {rv2_high}",
        f"CMEM_SELECTED {VM} {GND} {cfg.cmem} IC={cfg.vm_initial}",
        f"C26 {VM} {GND} 100p",
    ]

    if cfg.probe == "scope10m":
        lines += [
            "* 10x oscilloscope probe approximation",
            f"RPROBE {VM} {GND} 10Meg",
            f"CPROBE {VM} {GND} 15p",
        ]
    elif cfg.probe == "probe1m":
        lines += [
            "* 1 MOhm probe load",
            f"RPROBE {VM} {GND} 1Meg",
        ]

    if cfg.stim_dc is not None:
        add_external_stimulus(lines, cfg)


def add_external_stimulus(lines: list[str], cfg: SimConfig) -> None:
    lines += [
        "",
        "* ---- Optional external stimulus path ----",
        "* Ground truth: J1 pin2=Stimulus_Ext -> R83=1k -> V_Stim_Cmd; C37=100pF; U19B buffer; R88=47k -> Vm_Int.",
        f"VSTIM {STIMULUS_EXT} {GND} DC {cfg.stim_dc:.12g}",
        f"R83 {STIMULUS_EXT} {V_STIM_CMD} 1k",
        f"C37 {V_STIM_CMD} {GND} 100p",
    ]
    opamp_follower(lines, "U19B", V_STIM_DRIVE, V_STIM_CMD, cfg)
    lines.append(f"R88 {V_STIM_DRIVE} {VM} 47k")


def add_threshold(lines: list[str], cfg: SimConfig) -> None:
    lines += [
        "",
        "* ---- Threshold comparator U6B and AP/spike generation ----",
        "* Ground truth: R6=24.3k VDD->V_Threshold, R7=10k V_Threshold->GNDREF.",
        f"R6 {VDD} {V_THRESHOLD} 24.3k",
        f"R7 {V_THRESHOLD} {GND} 10k",
        "* U6B: INB+=V_Threshold, INB-=Vm_Int, OUTB=Net-(Q1-G).",
        f"R33 {V_THRESHOLD} {Q1_GATE} 220k",
        f"R34 {VDD} {Q1_GATE} 10k",
    ]
    tlv7044_oc(lines, "U6B", Q1_GATE, VM, V_THRESHOLD, cfg)

    lines += [
        "* Q1=BSS138: D=AP, G=Net-(Q1-G), S=GNDREF.",
        f"R35 {VDD} {AP} 22k",
        f"MQ1 {AP} {Q1_GATE} {GND} {GND} {cfg.bss138_model}",
        "* C29=10nF AP->/Rising_AP, R46=100k /Rising_AP->GNDREF, D8=RB521S30T1G to Spike_Pulse.",
        f"C29 {AP} {RISING_AP} 10n",
        f"R46 {RISING_AP} {GND} 100k",
    ]
    # KiCad D8 pin 2 = /Rising_AP and pin 1 = Spike_Pulse. For this diode symbol,
    # pin 2 is anode and pin 1 is cathode, so SPICE order is /Rising_AP -> Spike_Pulse.
    add_spike_schottky(lines, "D8", RISING_AP, SPIKE_PULSE, cfg)
    lines.append(f"R47 {SPIKE_PULSE} {GND} 1Meg")

    lines += [
        "* Approximate TLV7044 input clamp on Spike_Pulse input.",
        "* TLV7044 inputs are diode-clamped to VEE; this prevents unrealistic large negative input swing.",
        "DCLAMP_SPIKE_GND 0 Spike_Pulse D_TLV_INPUT_CLAMP",
    ]


def add_peak_and_reset(lines: list[str], cfg: SimConfig) -> None:
    lines += [
        "",
        "* ---- Peak and reset windows: U6A/U6C and Q3-Q6 ----",
        "* U6A: INA+=Spike_Pulse, INA-=V_Threshold, OUTA=Peak_Window; R48 pull-up.",
        "* Fallback open-drain comparator pulls OUT low when V(-) > V(+).",
        "* Therefore Peak_Window is low when Spike_Pulse < V_Threshold, and releases high when Spike_Pulse > V_Threshold.",
        f"R48 {VDD} {PEAK_WINDOW} 100k",
    ]
    tlv7044_oc(lines, "U6A", PEAK_WINDOW, V_THRESHOLD, SPIKE_PULSE, cfg)

    lines += [
        "",
        "* Reset-window timing node: R50=22k VDD->Net-(U6C-INC-), C31=1uF to GNDREF.",
        f"R50 {VDD} {U6C_MINUS} 22k",
        f"C31 {U6C_MINUS} {GND} 1u IC={cfg.vdd}",
        "* Q3=BSS138: D=Net-(Q3-D), G=AP, S=GNDREF; R51=100R from Q3_D to U6C_MINUS.",
        f"MQ3 {Q3_D} {AP} {GND} {GND} {cfg.bss138_model}",
        f"R51 {Q3_D} {U6C_MINUS} 100",
        "",
        "* U6C plus input network and reset-window pull-up.",
        f"R53 {U6C_PLUS} {VDD} 27k",
        f"R54 {U6C_PLUS} {RESET_WINDOW} 100k",
        f"R55 {U6C_PLUS} {GND} 22k",
        f"R52 {VDD} {RESET_WINDOW} 100k",
    ]
    tlv7044_oc(lines, "U6C", RESET_WINDOW, U6C_MINUS, U6C_PLUS, cfg)

    lines += [
        "",
        "* Reset-current gate chain Q4/Q5/Q6.",
        "* Q4=BSS138: D=Net-(Q4-D), G=Peak_Window, S=GNDREF; R56 pull-up.",
        f"R56 {VDD} {Q4_D} 100k",
        f"MQ4 {Q4_D} {PEAK_WINDOW} {GND} {GND} {cfg.bss138_model}",
        "* Q5=BSS138: G=Net-(Q4-D), S=/Reset_Injection_Drive, D=Net-(Q5-D).",
        f"MQ5 {Q5_D} {Q4_D} {RESET_INJ} {RESET_INJ} {cfg.bss138_model}",
        "* Q6=BSS138: G=Reset_Window, S=Net-(Q5-D), D=Net-(Q6-D); R57=10k to Vm_Int.",
        f"MQ6 {Q6_D} {RESET_WINDOW} {Q5_D} {Q5_D} {cfg.bss138_model}",
        f"R57 {Q6_D} {VM} 10k",
    ]


def add_adaptation(lines: list[str], cfg: SimConfig) -> None:
    rv3_low, rv3_high = split_pot("100k", cfg.rv3_fraction)

    lines += [
        "",
        "* ---- Adaptation path /Vw ----",
        "* U1C is a follower driven from AP: U1C+=AP, U1C-/OUT=Net-(U1B-VINC-).",
    ]
    opamp_follower(lines, "U1C", U1C_OUT, AP, cfg)

    lines += [
        "* C27=1uF between U1C output and /Vkick; R36=22k /Vkick->GNDREF.",
        f"C27 {VKICK} {U1C_OUT} 1u",
        f"R36 {VKICK} {GND} 22k",
        "* Diode orientation from KiCad pins: D4 GNDREF->/Vkick, D5 /Vkick->Vw, D7 GNDREF->Vw.",
    ]
    add_signal_diode(lines, "D4", GND, VKICK, cfg)
    add_signal_diode(lines, "D5", VKICK, VW, cfg)
    add_signal_diode(lines, "D7", GND, VW, cfg)

    lines += [
        f"C28 {VW} {GND} 10u IC=0",
        f"* RV3=100k: pins 1/2=Vw, pin3=Net-(R42-Pad1); fraction={cfg.rv3_fraction:.3f}.",
        f"RV3_LOWER {VW} {VW} {rv3_low}",
        f"RV3_UPPER {VW} {RV3_BOTTOM} {rv3_high}",
        f"R42 {RV3_BOTTOM} {GND} 100",
    ]
    opamp_follower(lines, "U1D", VW_BUFF, VW, cfg)

    lines += [
        "* Q2=MMBT3904 adaptation current path: R44/R45 base divider, R43 collector to Vm_Int.",
        f"R44 {VW_BUFF} {Q2_B} 22k",
        f"R45 {Q2_B} {GND} 100k",
        f"Q2 {Q2_C} {Q2_B} {GND} {cfg.npn_model}",
        f"R43 {VM} {Q2_C} 10k",
    ]


def build_spice_deck(cfg: SimConfig, *, for_cli: bool = False, csv_path: Path | None = None) -> str:
    lines = add_header(cfg)
    add_references_and_passive_vm(lines, cfg)

    if cfg.stage in {"threshold", "threshold_reset", "threshold_reset_adapt"}:
        add_threshold(lines, cfg)
    if cfg.stage in {"threshold_reset", "threshold_reset_adapt"}:
        add_peak_and_reset(lines, cfg)
    if cfg.stage == "threshold_reset_adapt":
        add_adaptation(lines, cfg)

    traces = traces_for_config(cfg)
    lines += [
        "",
        "* ---- Analysis ----",
        f".tran {cfg.tstep} {cfg.tstop} 0 {cfg.maxstep} uic",
        ".save " + " ".join(f"V({trace.node})" for trace in traces),
    ]

    if for_cli:
        assert csv_path is not None
        csv = str(csv_path.resolve()).replace("\\", "/")
        vector_expr = " ".join(f"v({trace.node})" for trace in traces)
        lines += [
            ".control",
            "run",
            f"wrdata {csv} {vector_expr}",
            "quit",
            ".endc",
        ]

    lines.append(".end")
    return "\n".join(lines) + "\n"


# -----------------------------------------------------------------------------
# Simulation runners
# -----------------------------------------------------------------------------


def run_with_pyspice(deck_path: Path, cfg: SimConfig) -> pd.DataFrame:
    """Run using PySpice/ngspice and return selected traces as a DataFrame."""
    try:
        import PySpice.Logging.Logging as Logging
        from PySpice.Spice import Simulation
        from PySpice.Spice.Parser import SpiceParser
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "PySpice is not importable. Install it with `pip install PySpice`, "
            "or rerun with --backend ngspice-cli."
        ) from exc

    Logging.setup_logging()
    Simulation.CircuitSimulator.DEFAULT_SIMULATOR = "ngspice-subprocess"

    parser = SpiceParser(path=str(deck_path))
    circuit = parser.build_circuit(ground=0)
    simulator = circuit.simulator(temperature=25, nominal_temperature=25)

    analysis = simulator.transient(
        step_time=_to_float_suffix(cfg.tstep),
        end_time=_to_float_suffix(cfg.tstop),
    )

    data = {"time_s": np.array(analysis.time, dtype=float)}
    for trace in traces_for_config(cfg):
        try:
            data[trace.key] = np.array(analysis.nodes[trace.node.lower()], dtype=float)
        except Exception:
            data[trace.key] = np.full_like(data["time_s"], np.nan, dtype=float)
    return pd.DataFrame(data)


def run_with_ngspice_cli(deck_path: Path, csv_path: Path, cfg: SimConfig) -> pd.DataFrame:
    ngspice_exe = find_ngspice_binary(cfg.ngspice_binary)
    log_path = csv_path.with_suffix(".ngspice.log")

    print(f"Using ngspice binary: {ngspice_exe}")
    print(f"ngspice log file:     {log_path}")

    if csv_path.exists():
        csv_path.unlink()
    if log_path.exists():
        log_path.unlink()

    proc = subprocess.run(
        [ngspice_exe, "-b", "-o", str(log_path), str(deck_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    stdout_text = proc.stdout or ""
    stderr_text = proc.stderr or ""
    log_text = log_path.read_text(errors="replace") if log_path.exists() else ""

    if proc.returncode != 0:
        raise RuntimeError(
            f"ngspice failed with exit code {proc.returncode}\n\n"
            f"Command:\n  {ngspice_exe} -b -o {log_path} {deck_path}\n\n"
            f"STDOUT:\n{stdout_text}\n\nSTDERR:\n{stderr_text}\n\nNGSPICE LOG:\n{log_text}\n\n"
            f"SPICE deck was:\n{deck_path}"
        )

    if not csv_path.exists():
        raise FileNotFoundError(
            f"ngspice ran but did not create the expected output file:\n{csv_path}\n\n"
            f"Command:\n  {ngspice_exe} -b -o {log_path} {deck_path}\n\n"
            f"STDOUT:\n{stdout_text}\n\nSTDERR:\n{stderr_text}\n\nNGSPICE LOG:\n{log_text}"
        )

    raw = pd.read_csv(csv_path, sep=r"\s+", header=None, comment="*")
    traces = traces_for_config(cfg)

    out = pd.DataFrame()
    out["time_s"] = raw.iloc[:, 0].astype(float)

    value_cols = list(range(1, raw.shape[1], 2))
    if len(value_cols) < len(traces):
        raise ValueError(
            f"ngspice output has {len(value_cols)} value columns, but {len(traces)} traces were requested."
        )

    for trace, col in zip(traces, value_cols[: len(traces)]):
        out[trace.key] = raw.iloc[:, col].astype(float)

    return out


# -----------------------------------------------------------------------------
# Plotting and diagnostics
# -----------------------------------------------------------------------------


def plot_results(df: pd.DataFrame, cfg: SimConfig, png_path: Path) -> None:
    """Plot every trace that will also be printed by print_diagnostics()."""
    traces = traces_for_config(cfg)
    t_ms = df["time_s"].to_numpy() * 1e3

    plt.figure(figsize=(13, 7))

    for trace in traces:
        if trace.key not in df or df[trace.key].isna().all():
            continue
        linewidth = 2.4 if trace.key == "VM" else 1.2
        alpha = 1.0 if trace.key == "VM" else 0.82
        plt.plot(t_ms, df[trace.key].to_numpy(), label=trace.label, linewidth=linewidth, alpha=alpha)

    plt.xlabel("Time (ms)")
    plt.ylabel("Voltage (V)")
    plt.title(f"Spiky_Lui2 Vm simulation — {cfg.stage}, probe={cfg.probe}")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best", fontsize="small", ncol=2)
    plt.tight_layout()
    plt.savefig(png_path, dpi=180)
    plt.close()


def print_node_summary(df: pd.DataFrame, key: str, display_name: str, t: np.ndarray) -> None:
    if key not in df or df[key].isna().all():
        return

    y = df[key].to_numpy()
    print(f"{display_name} start = {y[0]:.6g} V")
    print(f"{display_name} end   = {y[-1]:.6g} V")
    print(f"{display_name} min   = {np.nanmin(y):.6g} V")
    print(f"{display_name} max   = {np.nanmax(y):.6g} V")

    dy = np.abs(np.diff(y))
    if len(dy) > 0 and np.nanmax(dy) > 0.1:
        i = int(np.nanargmax(dy)) + 1
        print(f"Largest {display_name} transition near t = {t[i] * 1e3:.6g} ms")


def print_diagnostics(df: pd.DataFrame, cfg: SimConfig) -> None:
    """Print diagnostics for exactly the same traces that are plotted."""
    traces = traces_for_config(cfg)
    t = df["time_s"].to_numpy()

    for trace in traces:
        print_node_summary(df, trace.key, trace.label, t)

    if "VM" in df and "VTHRESH" in df and not df["VTHRESH"].isna().all():
        vm = df["VM"].to_numpy()
        vth = df["VTHRESH"].to_numpy()
        crossed = np.where(vm >= vth)[0]
        if len(crossed) > 0:
            i = crossed[0]
            print(f"First Vm_Int >= V_Threshold at t = {t[i] * 1e3:.6g} ms")
            print(f"Vm_Int at crossing       = {vm[i]:.6g} V")
            print(f"V_Threshold at crossing  = {vth[i]:.6g} V")
        else:
            print("Vm_Int never crossed V_Threshold.")


# -----------------------------------------------------------------------------
# Command line
# -----------------------------------------------------------------------------


def parse_args(argv: list[str]) -> SimConfig:
    p = argparse.ArgumentParser(description="Simulate the Spiky_Lui2 Vm-relevant circuit with ngspice/PySpice.")
    p.add_argument("--stage", choices=["passive", "threshold", "threshold_reset", "threshold_reset_adapt"], default="passive")
    p.add_argument("--strict-vendor", action="store_true", help="Require external vendor model files in ./models/.")
    p.add_argument("--backend", choices=["pyspice", "ngspice-cli"], default="ngspice-cli")
    p.add_argument("--ngspice-binary", default="auto", help="Path to ngspice.exe, or 'auto' to search PATH/common Windows locations.")
    p.add_argument("--vdd", default="3", help="Supply voltage, e.g. 3 or 2.7")
    p.add_argument("--rv1", type=float, default=0.5, help="RV1 wiper fraction, 0..1; pin1=GNDREF, pin3=V_Leak_Ref_Max")
    p.add_argument("--rv2", type=float, default=0.5, help="RV2 wiper fraction, 0..1; pin1=R32 node, pin2=Vm_Int, pin3=V_Leak")
    p.add_argument("--rv3", type=float, default=0.5, help="RV3 wiper fraction, 0..1; pins1/2=Vw, pin3=R42 node")
    p.add_argument("--cmem", default="2.2u", help="Selected membrane capacitor, e.g. 470n, 1u, 2.2u, 4.7u, 10u")
    p.add_argument("--vm-initial", default="0.385")
    p.add_argument("--tstop", default="1", help="Transient stop time, seconds by default")
    p.add_argument("--tstep", default="10u")
    p.add_argument("--maxstep", default="10u")
    p.add_argument("--probe", choices=["ideal", "scope10m", "probe1m"], default="ideal")
    p.add_argument("--stim-dc", type=float, default=None, help="Optional DC source at J1 pin2 / Stimulus_Ext")

    ns = p.parse_args(argv)
    return SimConfig(
        stage=ns.stage,
        strict_vendor=ns.strict_vendor,
        vdd=ns.vdd,
        rv1_fraction=ns.rv1,
        rv2_fraction=ns.rv2,
        rv3_fraction=ns.rv3,
        cmem=ns.cmem,
        vm_initial=ns.vm_initial,
        tstop=ns.tstop,
        tstep=ns.tstep,
        maxstep=ns.maxstep,
        probe=ns.probe,
        stim_dc=ns.stim_dc,
        backend=ns.backend,
        ngspice_binary=ns.ngspice_binary,
    )


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    suffix = f"{cfg.stage}_{cfg.probe}"
    if cfg.stim_dc is not None:
        suffix += "_stim"
    if cfg.strict_vendor:
        suffix += "_vendor"

    deck_path = OUTPUT_DIR / f"spiky_vm_{suffix}.cir"
    csv_path = OUTPUT_DIR / f"spiky_vm_{suffix}.csv"
    png_path = OUTPUT_DIR / f"spiky_vm_{suffix}.png"

    deck = build_spice_deck(cfg, for_cli=(cfg.backend == "ngspice-cli"), csv_path=csv_path)
    deck_path.write_text(deck)

    print(f"Wrote SPICE deck: {deck_path}")
    print(f"Stage:          {cfg.stage}")
    print(f"Backend:        {cfg.backend}")
    print(f"Strict vendor:  {cfg.strict_vendor}")
    print("Saved/plotted/printed traces:")
    for trace in traces_for_config(cfg):
        print(f"  - {trace.key}: {trace.label} [{trace.node}]")

    if cfg.backend == "pyspice":
        df = run_with_pyspice(deck_path, cfg)
    else:
        df = run_with_ngspice_cli(deck_path, csv_path, cfg)

    df.to_csv(csv_path, index=False)
    plot_results(df, cfg, png_path)

    print(f"Wrote CSV:  {csv_path}")
    print(f"Wrote plot: {png_path}")
    print_diagnostics(df, cfg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
