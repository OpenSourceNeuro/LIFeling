#!/usr/bin/env python3
"""
LIFeling Vm simulation with Python + ngspice/PySpice.

This script models the Vm-relevant LIF subcircuit of the current KiCad design:

    passive               : raw/buffered V_Leak_Ref_Max, V_Leak reference, RV2 leak path, RV4/Cm selection, Vm_Int
    threshold             : U6B TLV7044, Q1, AP, /Rising_AP, Spike_Pulse, D20 clamp
    threshold_reset       : U6A/U6C TLV7044, peak/reset windows, reset injection path,
                            Vm peak injection through U14/R49, display-spike synthesis through
                            U20/R90/R91/C38, Vm_Ext output buffer, Spike_Out driver
    threshold_reset_adapt : U1B/U1C/U1D, /Vkick, Vw adaptation shaping, Q2

This is not a complete KiCad-generated netlist. It is a controlled behavioural
SPICE model using KiCad-aligned component names and SPICE-safe node aliases.

Default plotting uses a compact "core" trace set: user-level diagnostic nodes
only. Use --trace-set debug to include internal transistor/MOSFET nodes.

Power-up handling is split into two explicit modes:

    --startup-mode operating : VDD decoupling and reset timer start precharged;
                               use for normal behaviour, sweeps, and synapse tests.
    --startup-mode cold      : VDD decoupling, reset timer, and Vm start discharged;
                               use for power-on/startup stress tests.
"""


from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
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
OUTPUT_DIR = THIS_DIR / "LIFeling_pyspice_output"

# Op-amp: schematic U1/U2/U19 = MCP6004T-I/ST.
MCP6004_LIB = MODEL_DIR / "MCP6001.txt"
MCP6004_SUBCKT_NAME = "MCP6001"

# Comparator: schematic U4/U5/U6 = TLV7044PWR.
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

# Spike diode and new explicit negative clamp: schematic D8 and D20 = RB521S30T1G.
RB521S30_LIB = MODEL_DIR / "RB521S30.lib"
RB521S30_NAME = "RB521S30"
RB521S30_IS_SUBCKT = False

# -----------------------------------------------------------------------------
# SPICE-safe aliases for KiCad nets
# -----------------------------------------------------------------------------

GND = "0"          # KiCad: GNDREF
VDD = "VDD"        # KiCad: local circuit rail after optional battery impedance
VBAT_RAW = "VBAT_RAW"  # Ideal source side of the optional coin-cell model

# Passive / references.
V_LEAK_REF_MAX_RAW = "V_Leak_Ref_Max_Raw"  # KiCad: R4/R5 raw divider node before U2A buffer
V_LEAK_REF_MAX = "V_Leak_Ref_Max"          # KiCad: U2A buffered output feeding RV1 and RV6..RV9
V_LEAK_REF = "V_Leak_ref"                  # KiCad: /V_Leak_ref
V_LEAK = "V_Leak"                        # KiCad: V_Leak
VM = "Vm_Int"                            # KiCad: Vm_Int
RV2_PIN1 = "RV2_pin1"                    # KiCad: Net-(R32-Pad1)
V_RESET_REF = "V_Reset_Ref"              # KiCad: V_Reset_Ref
RESET_INJ = "Reset_Injection_Drive"      # KiCad: /Reset_Injection_Drive
V_PEAK_REF = "V_Peak_Ref"                # KiCad: V_Peak_Ref, R8/R9 divider
V_PEAK_DRIVE = "V_Peak_Drive"            # KiCad: Net-(U2C-VINC-), U2C buffered V_Peak_Ref
PEAK_INJECT_NO = "Peak_Injection_NO"     # KiCad: Net-(U14-NO), between U14 NO and R49

# Vm external/live-plot output driver and display-spike synthesis.
VM_DISPLAY_IN = "Vm_Display_In"          # KiCad: display-synthesised Vm input to U8 IN+
DISPLAY_SPIKE_NO = "Display_Spike_NO"    # KiCad: Net-(U20-NO), V_Peak_Drive side of display switch
VM_DRV = "Vm_DRV"                        # KiCad: Vm_DRV, U8 output before R1
VM_FB = "Vm_FB"                          # KiCad: Vm_FB, U8 inverting input
VM_EXT = "Vm_Ext"                        # KiCad: Vm_Ext, external/live analog Vm output

# Threshold / AP / spike.
V_THRESHOLD = "V_Threshold"              # KiCad: V_Threshold
THRESHOLD_COMP_OUT = "Threshold_Comparator_Out"  # KiCad: /Threshold_Comparator_Out
AP = "AP"                                # KiCad: AP
RISING_AP = "Rising_AP"                  # KiCad: /Rising_AP
SPIKE_PULSE = "Spike_Pulse"              # KiCad: Spike_Pulse
U6D_OUT = "U6D_Out"                      # KiCad: Net-(U6D-OUTD), Spike_Out comparator output
SPIKE_OUT = "Spike_Out"                  # KiCad: Spike_Out jack node
V_LOGIC_MID = "V_Logic_Mid"              # KiCad: V_Logic_Mid, reused by U6D output driver

# Peak/reset windows.
PEAK_WINDOW = "Peak_Window"              # KiCad: Peak_Window
RESET_WINDOW = "Reset_Window"            # KiCad: Reset_Window
U6C_PLUS = "U6C_INC_plus"                # KiCad: Net-(U6C-INC+)
U6C_MINUS = "U6C_INC_minus"              # KiCad: Net-(U6C-INC-)
RESET_TIMER_DISCHARGE = "Reset_Timer_Discharge"    # KiCad: Reset_Timer_Discharge
RESET_INJECTION_ENABLE = "Reset_Injection_Enable"  # KiCad: /Reset_Injection_Enable
RESET_REF_GATED = "Reset_Ref_Gated"                # KiCad: Reset_Ref_Gated
RESET_CURRENT_NODE = "Reset_Current_Node"          # KiCad: Reset_Current_Node

# Adaptation.
ADAPT_KICK_DRIVE = "Adapt_Kick_Drive"      # KiCad: Adapt_Kick_Drive
VKICK = "Vkick"                          # KiCad: /Vkick
VW = "Vw"                                # KiCad: Vw
RV3_BOTTOM = "RV3_bottom"                # KiCad: Net-(R42-Pad1)
VW_BUFF = "Vw_buff"                      # KiCad: Vw_buff
ADAPT_BASE = "Adapt_Base"                  # KiCad: Adapt_Base
ADAPT_CURRENT_SINK = "Adapt_Current_Sink"  # KiCad: Adapt_Current_Sink
ADAPT_U1B_PLUS = "Adapt_U1B_plus"          # KiCad: Net-(U1B-VINB+), Vm/Vkick sensing node
ADAPT_U1B_MINUS = "Adapt_U1B_minus"        # KiCad: Net-(U1B-VINB-), V_Leak/output feedback node
ADAPT_U1B_OUT = "Adapt_U1B_out"            # KiCad: Net-(U1B-VOUTB)
ADAPT_U1B_DIODE_A = "Adapt_U1B_diode_A"    # KiCad: Net-(D6-A), anode side of D6

# Optional external stimulus input.
STIMULUS_EXT = "Stimulus_Ext"            # KiCad: Stimulus_Ext
V_STIM_CMD = "V_Stim_Cmd"                # KiCad: V_Stim_Cmd
V_STIM_DRIVE = "V_Stim_Drive"            # KiCad: V_Stim_Drive
V_STIM_PLUS = "V_Stim_plus"               # KiCad: Net-(U19B-VINB+), R84/R85 summing node
V_STIM_MINUS = "V_Stim_minus"             # KiCad: Net-(U19B-VINB-), R86/R87 feedback node

# Synaptic input/state circuit.
SYN1_SPIKE = "Syn1_Spike"
SYN2_SPIKE = "Syn2_Spike"
SYN3_SPIKE = "Syn3_Spike"
SYN4_SPIKE = "Syn4_Spike"

SYN1_IN = "Syn1_Input"                  # KiCad: Net-(D10-A), after R66/R65/D10/D11 clamp
SYN2_IN = "Syn2_Input"                  # KiCad: Net-(D12-A)
SYN3_IN = "Syn3_Input"                  # KiCad: Net-(D14-A)
SYN4_IN = "Syn4_Input"                  # KiCad: Net-(D16-A)

U15_IN = "U15_IN"                       # KiCad: Net-(U15-IN)
U16_IN = "U16_IN"                       # KiCad: Net-(U16-IN)
U17_IN = "U17_IN"                       # KiCad: Net-(U17-IN)
U18_IN = "U18_IN"                       # KiCad: Net-(U18-IN)

SYN1_SET_RAW = "Syn1_Set_raw"           # KiCad: Net-(U3A-VINB+) / RV6 wiper
SYN2_SET_RAW = "Syn2_Set_raw"           # KiCad: Net-(U3B-VINC+) / RV7 wiper
SYN3_SET_RAW = "Syn3_Set_raw"           # KiCad: Net-(U3C-VIND+) / RV8 wiper
SYN4_SET_RAW = "Syn4_Set_raw"           # KiCad: Net-(U3D-VINA+) / RV9 wiper

V_SYN1_SET = "V_Syn1_Set"
V_SYN2_SET = "V_Syn2_Set"
V_SYN3_SET = "V_Syn3_Set"
V_SYN4_SET = "V_Syn4_Set"

SYN1_NO = "Syn1_NO"                     # KiCad: Net-(U15-NO)
SYN2_NO = "Syn2_NO"                     # KiCad: Net-(U16-NO)
SYN3_NO = "Syn3_NO"                     # KiCad: Net-(U17-NO)
SYN4_NO = "Syn4_NO"                     # KiCad: Net-(U18-NO)

V_SYN_STATE = "V_Syn_State"
RV5_DECAY = "RV5_decay"                 # KiCad: Net-(R79-Pad2), RV5 pins 1/2
V_SYN_DRIVE = "V_Syn_Drive"             # Behavioural alias for KiCad Net-(U2C-VIND-) / U2D output feeding R80


@dataclasses.dataclass(frozen=True)
class Trace:
    """One saved/plotted/printed voltage trace."""

    key: str
    node: str
    label: str


# Compact trace set: intended for normal circuit interpretation and CSV export.
# The CSV is deliberately kept focused on live-plot/visualisation signals rather
# than every internal debug node. The results text file still contains the run
# header and validation diagnostics for the same saved traces.
CORE_BASE_TRACES = [
    Trace("VM_EXT", VM_EXT, "Vm_Ext"),
    Trace("VM", VM, "Vm_Int"),
    Trace("VLEAK", V_LEAK, "V_Leak"),
]

CORE_SUPPLY_TRACES = [
    Trace("VDD", VDD, "VDD"),
]

DEBUG_SUPPLY_TRACES = [
    Trace("VBAT_RAW", VBAT_RAW, "Vbat raw"),
]

CORE_THRESHOLD_TRACES = [
    Trace("VTHRESH", V_THRESHOLD, "V_Threshold"),
    Trace("AP", AP, "AP"),
    Trace("SPIKE_PULSE", SPIKE_PULSE, "Spike_Pulse"),
]

CORE_RESET_TRACES = [
    Trace("SPIKE_OUT", SPIKE_OUT, "Spike_Out"),
    Trace("PEAK_WINDOW", PEAK_WINDOW, "Peak_Window"),
    Trace("RESET_WINDOW", RESET_WINDOW, "Reset_Window"),
]

CORE_ADAPT_TRACES = [
    Trace("VW", VW, "Vw"),
    Trace("VW_BUFF", VW_BUFF, "Vw_buff"),
]

CORE_STIM_TRACES = [
    Trace("STIMULUS_EXT", STIMULUS_EXT, "Stimulus_Ext"),
    Trace("V_STIM_DRIVE", V_STIM_DRIVE, "V_Stim_Drive"),
]

# Debug/validation traces are intentionally compact: enough to validate the
# important blocks without bloating every CSV with all switch and transistor nets.
DEBUG_BASE_TRACES = [
    Trace("VM_DISPLAY_IN", VM_DISPLAY_IN, "Vm_Display_In"),
    Trace("VLEAK_REF_MAX_RAW", V_LEAK_REF_MAX_RAW, "V_Leak_Ref_Max_Raw"),
    Trace("VLEAK_REF_MAX", V_LEAK_REF_MAX, "V_Leak_Ref_Max buffered"),
    Trace("V_PEAK_REF", V_PEAK_REF, "V_Peak_Ref"),
    Trace("V_PEAK_DRIVE", V_PEAK_DRIVE, "V_Peak_Drive"),
    Trace("PEAK_INJECT_NO", PEAK_INJECT_NO, "Peak injection switch NO"),
    Trace("V_RESET_REF", V_RESET_REF, "V_Reset_Ref"),
]

DEBUG_THRESHOLD_TRACES = [
    Trace("THRESHOLD_COMP_OUT", THRESHOLD_COMP_OUT, "/Threshold_Comparator_Out"),
]

DEBUG_RESET_TRACES = [
    Trace("DISPLAY_SPIKE_NO", DISPLAY_SPIKE_NO, "Display spike switch NO"),
    Trace("U6D_OUT", U6D_OUT, "U6D spike-output driver"),
    Trace("RESET_TIMER", U6C_MINUS, "Reset timer / U6C-"),
    Trace("RESET_REF_NODE", U6C_PLUS, "Reset comparator ref / U6C+"),
    Trace("RESET_INJECTION_ENABLE", RESET_INJECTION_ENABLE, "/Reset_Injection_Enable"),
    Trace("RESET_REF_GATED", RESET_REF_GATED, "Reset_Ref_Gated"),
]

DEBUG_ADAPT_TRACES = [
    Trace("ADAPT_U1B_OUT", ADAPT_U1B_OUT, "U1B adaptation shaper output"),
    Trace("ADAPT_KICK_DRIVE", ADAPT_KICK_DRIVE, "Adapt_Kick_Drive"),
    Trace("ADAPT_BASE", ADAPT_BASE, "Adapt_Base"),
    Trace("ADAPT_CURRENT_SINK", ADAPT_CURRENT_SINK, "Adapt_Current_Sink"),
]

DEBUG_STIM_TRACES = [
    Trace("V_STIM_CMD", V_STIM_CMD, "V_Stim_Cmd"),
    Trace("V_STIM_PLUS", V_STIM_PLUS, "U19B stimulus plus input"),
    Trace("V_STIM_MINUS", V_STIM_MINUS, "U19B stimulus minus input"),
]

CORE_SYNAPSE_TRACES = [
    Trace("V_SYN_STATE", V_SYN_STATE, "V_Syn_State"),
]

CORE_SYNAPSE1_TRACES = [
    Trace("SYN1_SPIKE", SYN1_SPIKE, "Syn1_Spike"),
    Trace("V_SYN1_SET", V_SYN1_SET, "V_Syn1_Set"),
]
CORE_SYNAPSE2_TRACES = [
    Trace("SYN2_SPIKE", SYN2_SPIKE, "Syn2_Spike"),
    Trace("V_SYN2_SET", V_SYN2_SET, "V_Syn2_Set"),
]
CORE_SYNAPSE3_TRACES = [
    Trace("SYN3_SPIKE", SYN3_SPIKE, "Syn3_Spike"),
    Trace("V_SYN3_SET", V_SYN3_SET, "V_Syn3_Set"),
]
CORE_SYNAPSE4_TRACES = [
    Trace("SYN4_SPIKE", SYN4_SPIKE, "Syn4_Spike"),
    Trace("V_SYN4_SET", V_SYN4_SET, "V_Syn4_Set"),
]

DEBUG_SYNAPSE_COMMON_TRACES = [
    Trace("V_SYN_DRIVE", V_SYN_DRIVE, "V_Syn_Drive"),
    Trace("RV5_DECAY", RV5_DECAY, "Net-(R79-Pad2) / RV5 pins 1/2"),
]

# These full per-channel switch internals are intentionally no longer saved by
# default. Add them temporarily here if you need TS5A3166-level characterisation.
DEBUG_SYNAPSE1_TRACES: list[Trace] = []
DEBUG_SYNAPSE2_TRACES: list[Trace] = []
DEBUG_SYNAPSE3_TRACES: list[Trace] = []
DEBUG_SYNAPSE4_TRACES: list[Trace] = []


@dataclasses.dataclass
class SimConfig:
    stage: Literal["passive", "threshold", "threshold_reset", "threshold_reset_adapt"] = "passive"
    strict_vendor: bool = False
    vdd: str = "3"

    # Supply / power-integrity model.
    # ideal: VDD is driven by an ideal voltage source.
    # coin:  VBAT_RAW -> Rbat -> VDD, with local decoupling on VDD.
    supply_mode: Literal["ideal", "coin"] = "ideal"
    vbat: str = "3"
    rbat: str = "30"
    cdec_local: str = "100n"
    cdec_bulk: str = "10u"
    cdec_reservoir: str = "47u"
    cdec_esr: str = "0.2"

    # Initial-condition policy.
    # operating: model an already-powered circuit, with VDD reservoirs and reset timer precharged.
    # cold:      model power-on from discharged VDD reservoirs/reset timer/Vm.
    startup_mode: Literal["operating", "cold"] = "operating"
    ignore_start_ms: float = 0.0
    cold_vm_initial: str = "0"

    # Component tolerance model. Nominal mode preserves exact schematic values.
    # Random mode applies deterministic per-component uniform variation using tol_seed.
    tol_mode: Literal["nominal", "random"] = "nominal"
    tol_seed: int = 1
    res_tol_pct: float = 0.0
    cap_tol_pct: float = 0.0
    pot_tol_pct: float = 0.0

    rv1_fraction: float = 0.5
    rv2_fraction: float = 0.5
    rv3_fraction: float = 0.5
    rv4_fraction: float = 0.5

    cmem_mode: Literal["manual", "rv4"] = "manual"
    cmem: str = "2.2u"
    vm_initial: str = "0.385"

    tstop: str = "1"
    tstep: str = "10u"
    maxstep: str = "10u"

    probe: Literal["ideal", "scope10m", "probe1m"] = "ideal"
    trace_set: Literal["core", "debug"] = "core"

    stim_dc: float | None = None

    # Synaptic circuit model. Disabled by default so existing LIF validation is unchanged.
    # schematic/buffered = current KiCad connectivity: R4/R5 -> V_Leak_Ref_Max_Raw -> U2A buffer
    #                      -> V_Leak_Ref_Max, which feeds RV1 and RV6..RV9 pin 3.
    # legacy_direct      = old comparison mode: RV6..RV9 use the raw divider node directly.
    syn_ref_mode: Literal["schematic", "legacy_direct", "buffered"] = "schematic"
    syn1_enable: bool = False
    syn2_enable: bool = False
    syn3_enable: bool = False
    syn4_enable: bool = False

    # RV5 controls V_Syn_State decay back toward V_Leak.
    # RV6..RV9 control the set voltages for synapses 1..4.
    rv5_fraction: float = 0.5
    rv6_fraction: float = 0.5
    rv7_fraction: float = 0.5
    rv8_fraction: float = 0.5
    rv9_fraction: float = 0.5

    # Pulse sources injected at Syn*_Spike jack nets for simulation.
    syn_amp: str = "3"
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

    backend: Literal["pyspice", "ngspice-cli"] = "ngspice-cli"
    ngspice_binary: str = "auto"

    sweep: bool = False
    sweep_rv1: str = "0.3,0.5,0.7,1.0"
    sweep_rv2: str = "0.2,0.5,0.8"
    sweep_rv3: str = "0.2,0.5,0.8"
    sweep_rv4: str = ""
    sweep_vbat: str = ""
    sweep_rbat: str = ""

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

    @property
    def syn_diode_name(self) -> str:
        # Synaptic input clamps are BAT54WS in the KiCad netlist. We use a
        # compact Schottky fallback unless/until a BAT54 vendor model is added.
        return "BAT54_FALLBACK"


# -----------------------------------------------------------------------------
# Selection / naming helpers
# -----------------------------------------------------------------------------


def cmem_from_rv4(rv4: float) -> str:
    """Idealised RV4 one-hot capacitance selector."""
    rv4 = float(np.clip(rv4, 0.0, 1.0))
    if rv4 < 0.2:
        return "470n"
    if rv4 < 0.4:
        return "1u"
    if rv4 < 0.6:
        return "2.2u"
    if rv4 < 0.8:
        return "4.7u"
    return "10u"


def selected_cmem_nominal(cfg: SimConfig) -> str:
    """Selected membrane capacitor using the requested RV4 setting."""
    return cmem_from_rv4(cfg.rv4_fraction) if cfg.cmem_mode == "rv4" else cfg.cmem


def selected_cmem(cfg: SimConfig) -> str:
    """Selected membrane capacitor after optional RV4 setting tolerance."""
    if cfg.cmem_mode != "rv4":
        return cfg.cmem
    return cmem_from_rv4(effective_pot_fraction(cfg, "RV4", cfg.rv4_fraction))


def synapse_enabled(cfg: SimConfig) -> bool:
    return cfg.syn1_enable or cfg.syn2_enable or cfg.syn3_enable or cfg.syn4_enable


def syn_state_initial_voltage(cfg: SimConfig) -> str:
    # In operating mode, start V_Syn_State close to the membrane IC to avoid an
    # artificial synaptic startup kick. In cold mode, keep it discharged.
    # The state will then relax toward V_Leak through R79/RV5.
    return cfg.vm_initial if cfg.startup_mode == "operating" else cfg.cold_vm_initial


def synapse_pulse(delay: str, width: str, period: str, amp: str, rise: str, fall: str) -> str:
    return f"PULSE(0 {amp} {delay} {rise} {fall} {width} {period})"


def safe_tag(text: str) -> str:
    """Make a short value safe for filenames."""
    return (
        str(text)
        .strip()
        .replace(" ", "")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(".", "p")
        .replace("-", "m")
        .replace("+", "p")
    )


def float_tag(value: float) -> str:
    return f"{value:.3f}".replace(".", "p")


def short_num(value: float | int | str) -> str:
    """Compact filename-safe number token for sweep output paths.

    This intentionally produces much shorter tokens than output_suffix(), because
    long Windows paths can make ngspice fail before it writes a useful log file.
    Examples:
        1.0  -> "1"
        0.5  -> "0p5"
        3.2  -> "3p2"
        -0.1 -> "m0p1"
    """
    try:
        text = f"{float(value):g}"
    except Exception:
        text = str(value)

    return (
        text.strip()
        .replace("-", "m")
        .replace(".", "p")
        .replace("+", "")
        .replace(" ", "")
        .replace("µ", "u")
    )


def stage_tag(stage: str) -> str:
    """Short filename-safe stage tag."""
    return {
        "passive": "pass",
        "threshold": "th",
        "threshold_reset": "tr",
        "threshold_reset_adapt": "tra",
    }.get(stage, safe_tag(stage))


def enabled_synapse_tag(cfg: SimConfig) -> str:
    """Return compact enabled-synapse channel token, e.g. '1' or '1234'."""
    return "".join(
        str(i)
        for i, enabled in enumerate(
            [cfg.syn1_enable, cfg.syn2_enable, cfg.syn3_enable, cfg.syn4_enable],
            start=1,
        )
        if enabled
    )


def enabled_synapse_timing(cfg: SimConfig) -> list[tuple[int, str, str, str]]:
    """Return per-enabled-synapse pulse timing as (channel, delay, width, period)."""
    channels = [
        (1, cfg.syn1_enable, cfg.syn1_delay, cfg.syn1_width, cfg.syn1_period),
        (2, cfg.syn2_enable, cfg.syn2_delay, cfg.syn2_width, cfg.syn2_period),
        (3, cfg.syn3_enable, cfg.syn3_delay, cfg.syn3_width, cfg.syn3_period),
        (4, cfg.syn4_enable, cfg.syn4_delay, cfg.syn4_width, cfg.syn4_period),
    ]
    return [(idx, delay, width, period) for idx, enabled, delay, width, period in channels if enabled]


def _all_equal(values: list[str]) -> bool:
    return len(set(values)) <= 1


def trace_tag(trace_set: str) -> str:
    """Very short filename token for the selected trace set."""
    return {"core": "c", "debug": "d"}.get(trace_set, safe_tag(trace_set)[:1] or "x")


def startup_tag(startup_mode: str) -> str:
    """Very short filename token for startup mode."""
    return {"operating": "op", "cold": "cd"}.get(startup_mode, safe_tag(startup_mode)[:2])


def value_list_tag(values: list[float | int | str]) -> str:
    """Compact filename-safe token for a list of numeric/string values."""
    return "-".join(short_num(value) for value in values)


def timing_value_tag(value: str) -> str:
    """Compact SPICE-time token for filenames.

    SPICE uses m for milli and u for micro. For filename readability we keep
    the suffix letter but remove repeated channel prefixes. Examples:
        150m -> 150m
        5m   -> 5m
        1u   -> 1u
    """
    return short_num(value)


def synapse_timing_tag(cfg: SimConfig) -> str:
    """Short filename tag for enabled synaptic pulse timing.

    The detailed timing is still printed in the run header. Filenames only need
    enough human-readable information for quick recognition because the final
    hash uniquely protects against collisions.
    """
    timing = enabled_synapse_timing(cfg)
    if not timing:
        return ""

    delays = [delay for _, delay, _, _ in timing]
    widths = [width for _, _, width, _ in timing]
    periods = [period for _, _, _, period in timing]

    parts: list[str] = []

    # Delays are the most useful timing values to see in the filename. For
    # staggered diagnostics, use d150m-180m-210m-240m instead of the previous
    # d1150m_d2180m_d3210m_d4240m form.
    if _all_equal(delays):
        parts.append(f"d{timing_value_tag(delays[0])}")
    else:
        parts.append("d" + "-".join(timing_value_tag(delay) for delay in delays))

    # Width is usually common across channels and diagnostically important.
    if _all_equal(widths):
        parts.append(f"w{timing_value_tag(widths[0])}")
    else:
        parts.append("w" + "-".join(timing_value_tag(width) for width in widths))

    # Period is normally the default 100m. Omit it in that common case; the
    # config hash still distinguishes non-obvious differences. Include it only
    # when it is not the default or when channels differ.
    if not _all_equal(periods) or periods[0] != "100m":
        if _all_equal(periods):
            parts.append(f"p{timing_value_tag(periods[0])}")
        else:
            parts.append("p" + "-".join(timing_value_tag(period) for period in periods))

    return "_" + "_".join(parts)


def run_identity_hash(cfg: SimConfig) -> str:
    """Short stable hash of simulation-affecting options for filename safety.

    The human-readable suffix intentionally remains compact, so this hash acts
    as a final guard against accidental overwrites when two configurations differ
    in a parameter not explicitly shown in the suffix. Backend/path/sweep fields
    are excluded because they do not change the generated circuit behaviour.
    """
    data = dataclasses.asdict(cfg)
    for key in (
        "backend",
        "ngspice_binary",
        "sweep",
        "sweep_rv1",
        "sweep_rv2",
        "sweep_rv3",
        "sweep_rv4",
        "sweep_vbat",
        "sweep_rbat",
    ):
        data.pop(key, None)
    payload = repr(sorted(data.items())).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:8]


def output_suffix(cfg: SimConfig) -> str:
    """Short but collision-resistant output suffix for normal runs.

    Earlier filenames encoded almost every synapse channel and timing parameter,
    which pushed Windows paths over ngspice's comfort zone. This version keeps a
    compact human-readable summary plus an 8-character configuration hash.
    The printed header and generated .cir file remain the authoritative detailed
    record of the run configuration.
    """
    cmem_value = selected_cmem(cfg)

    suffix = (
        f"{stage_tag(cfg.stage)}{trace_tag(cfg.trace_set)}"
        f"_r{value_list_tag([cfg.rv1_fraction, cfg.rv2_fraction, cfg.rv3_fraction])}"
    )

    if cfg.cmem_mode == "rv4":
        suffix += f"_m{short_num(cfg.rv4_fraction)}c{safe_tag(cmem_value)}"
    else:
        suffix += f"_c{safe_tag(cmem_value)}"

    if cfg.supply_mode == "coin":
        suffix += f"_b{short_num(cfg.vbat)}r{short_num(cfg.rbat)}"
    else:
        suffix += f"_v{short_num(cfg.vdd)}"

    suffix += f"_{startup_tag(cfg.startup_mode)}"

    if cfg.ignore_start_ms > 0:
        suffix += f"_i{short_num(cfg.ignore_start_ms)}"

    if cfg.tol_mode == "random":
        suffix += (
            f"_tol{cfg.tol_seed}"
            f"r{short_num(cfg.res_tol_pct)}"
            f"c{short_num(cfg.cap_tol_pct)}"
            f"p{short_num(cfg.pot_tol_pct)}"
        )

    if cfg.stim_dc is not None:
        suffix += f"_u{short_num(cfg.stim_dc)}"

    if synapse_enabled(cfg):
        syn_tag = enabled_synapse_tag(cfg)
        suffix += f"_s{syn_tag}k{short_num(cfg.rv5_fraction)}"

        if cfg.syn_ref_mode == "legacy_direct":
            suffix += "R"
        elif cfg.syn_ref_mode == "buffered":
            suffix += "B"

        syn_fracs: list[float] = []
        if cfg.syn1_enable:
            syn_fracs.append(cfg.rv6_fraction)
        if cfg.syn2_enable:
            syn_fracs.append(cfg.rv7_fraction)
        if cfg.syn3_enable:
            syn_fracs.append(cfg.rv8_fraction)
        if cfg.syn4_enable:
            syn_fracs.append(cfg.rv9_fraction)

        if syn_fracs:
            if len(set(round(float(v), 9) for v in syn_fracs)) == 1:
                suffix += f"g{short_num(syn_fracs[0])}"
            else:
                suffix += f"g{value_list_tag(syn_fracs)}"

        suffix += synapse_timing_tag(cfg)

    suffix += f"_t{short_num(cfg.tstop)}"

    if cfg.strict_vendor:
        suffix += "_vend"

    suffix += f"_h{run_identity_hash(cfg)}"

    return suffix


def dedupe_traces(traces: list[Trace]) -> list[Trace]:
    """Keep first occurrence of each trace key/node pair to avoid duplicate .save/wrdata vectors."""
    out: list[Trace] = []
    seen: set[tuple[str, str]] = set()
    for trace in traces:
        sig = (trace.key, trace.node)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(trace)
    return out

def traces_for_config(cfg: SimConfig) -> list[Trace]:
    """Single source of truth for .save, CSV parsing, plotting, and printing."""
    traces = list(CORE_BASE_TRACES)
    if cfg.supply_mode == "coin" or cfg.trace_set == "debug":
        traces += CORE_SUPPLY_TRACES

    if cfg.stage in {"threshold", "threshold_reset", "threshold_reset_adapt"}:
        traces += CORE_THRESHOLD_TRACES
    if cfg.stage in {"threshold_reset", "threshold_reset_adapt"}:
        traces += CORE_RESET_TRACES
    if cfg.stage == "threshold_reset_adapt":
        traces += CORE_ADAPT_TRACES
    if cfg.stim_dc is not None:
        traces += CORE_STIM_TRACES

    if synapse_enabled(cfg):
        traces += CORE_SYNAPSE_TRACES
        if cfg.syn1_enable:
            traces += CORE_SYNAPSE1_TRACES
        if cfg.syn2_enable:
            traces += CORE_SYNAPSE2_TRACES
        if cfg.syn3_enable:
            traces += CORE_SYNAPSE3_TRACES
        if cfg.syn4_enable:
            traces += CORE_SYNAPSE4_TRACES

    if cfg.trace_set == "debug":
        # VBAT_RAW exists only when the optional coin-cell source-impedance
        # model is active. In ideal-supply mode the generated deck contains
        # VDD_SRC directly on VDD and no VBAT_RAW node, so do not ask ngspice
        # to save/write V(VBAT_RAW) in that mode.
        if cfg.supply_mode == "coin":
            traces += DEBUG_SUPPLY_TRACES
        traces += DEBUG_BASE_TRACES
        if cfg.stage in {"threshold", "threshold_reset", "threshold_reset_adapt"}:
            traces += DEBUG_THRESHOLD_TRACES
        if cfg.stage in {"threshold_reset", "threshold_reset_adapt"}:
            traces += DEBUG_RESET_TRACES
        if cfg.stage == "threshold_reset_adapt":
            traces += DEBUG_ADAPT_TRACES
        traces += DEBUG_STIM_TRACES
        if synapse_enabled(cfg):
            traces += DEBUG_SYNAPSE_COMMON_TRACES
            if cfg.syn1_enable:
                traces += DEBUG_SYNAPSE1_TRACES
            if cfg.syn2_enable:
                traces += DEBUG_SYNAPSE2_TRACES
            if cfg.syn3_enable:
                traces += DEBUG_SYNAPSE3_TRACES
            if cfg.syn4_enable:
                traces += DEBUG_SYNAPSE4_TRACES

    return dedupe_traces(traces)


# -----------------------------------------------------------------------------
# Generic utilities
# -----------------------------------------------------------------------------


def _to_float_suffix(value: str) -> float:
    """Convert a simple SPICE value string to float, for derived values only."""
    value = value.strip().replace("ohm", "").replace("ohm", "")
    match = re.fullmatch(r"([0-9]*\.?[0-9]+)\s*([a-zA-Zuu]*)", value)
    if not match:
        raise ValueError(f"Cannot parse SPICE value: {value!r}")

    base = float(match.group(1))
    suffix = match.group(2).lower().replace("u", "u")
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




def format_spice_number(value: float) -> str:
    """Return a compact numeric SPICE value string."""
    if value == 0:
        return "0"
    return f"{value:.12g}"


def _stable_unit_interval(seed: int, key: str) -> float:
    payload = f"{seed}:{key}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    integer = int.from_bytes(digest[:8], "big")
    return integer / float(2**64 - 1)


def tolerance_factor(cfg: SimConfig, key: str, pct: float) -> float:
    """Deterministic uniform tolerance factor for a named component."""
    if cfg.tol_mode != "random" or pct <= 0:
        return 1.0
    u = _stable_unit_interval(cfg.tol_seed, key)
    delta = (2.0 * u - 1.0) * pct / 100.0
    return 1.0 + delta


def toleranced_value(cfg: SimConfig, key: str, nominal: str, pct: float) -> str:
    value = _to_float_suffix(nominal) * tolerance_factor(cfg, key, pct)
    return format_spice_number(value)


def r_value(cfg: SimConfig, key: str, nominal: str) -> str:
    return toleranced_value(cfg, key, nominal, cfg.res_tol_pct)


def c_value(cfg: SimConfig, key: str, nominal: str) -> str:
    return toleranced_value(cfg, key, nominal, cfg.cap_tol_pct)


def effective_pot_fraction(cfg: SimConfig, key: str, nominal_fraction: float) -> float:
    """Effective control fraction after optional knob/wiper tolerance.

    pot_tol_pct is interpreted as percent of full-scale travel. For example,
    pot_tol_pct=5 gives a deterministic random offset in [-0.05, +0.05].
    """
    frac = float(nominal_fraction)
    if cfg.tol_mode == "random" and cfg.pot_tol_pct > 0:
        u = _stable_unit_interval(cfg.tol_seed, f"{key}_fraction")
        frac += (2.0 * u - 1.0) * cfg.pot_tol_pct / 100.0
    return float(np.clip(frac, 1e-6, 1 - 1e-6))


def split_pot_toleranced(cfg: SimConfig, key: str, total: str, fraction: float) -> tuple[str, str]:
    total_ohm = _to_float_suffix(total) * tolerance_factor(cfg, f"{key}_total", cfg.pot_tol_pct)
    frac = effective_pot_fraction(cfg, key, fraction)
    lower = total_ohm * frac
    upper = total_ohm * (1.0 - frac)
    return format_spice_number(lower), format_spice_number(upper)

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
    """Resistance between pot wiper/pin1 side and pin3/high end."""
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
        Path(r"C:\Users\mzimm\Documents\Spice64\bin\ngspice.exe"),
        Path(r"C:\Users\mjyzi\Documents\Spice64\bin\ngspice.exe"),
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
            ".model BAT54_FALLBACK D(Is=2u Rs=1 N=1.05 Cjo=10p Eg=0.69 Bv=30 Ibv=10u)",
            ".model MMBT3904_FALLBACK NPN(Is=6.7f Bf=250 Vaf=100 Ikf=0.1 Xtb=1.5 Br=6 Cjc=4p Cje=8p Tf=300p Tr=50n)",
            ".model BSS138_FALLBACK NMOS(Level=1 Vto=1.2 Kp=2m Lambda=0.02 Rd=2 Rs=2)",
            ".model SW_OC SW(Ron=10 Roff=1e12 Vt=0 Vh=1m)",
            ".model SW_TS5A3166 SW(Ron=0.9 Roff=1e12 Vt=1.5 Vh=0.05)",
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


def opamp_unit(
    lines: list[str],
    name: str,
    out: str,
    minus: str,
    plus: str,
    cfg: SimConfig,
    *,
    vpos: str = VDD,
    out_res: str = "100",
    vendor_ok: bool = True,
) -> None:
    """Add a generic rail-limited fallback op-amp stage.

    Strict-vendor mode uses the MCP6004 wrapper where appropriate. Fallback mode
    uses a smooth behavioural source followed by a small output resistance.

    Important ngspice details:
      * The PSpice-style limit(x, lo, hi) expression was not reliable in this
        deck and previously allowed impossible tens-of-kilovolts outputs.
      * Hard min(max(...)) clipping fixed the overvoltage but created a
        convergence failure at t=0 when used inside unity-gain follower loops
        such as U2A.
      * The fallback below uses a differentiable tanh rail limiter. For true
        followers, opamp_follower() uses a simple unity VCVS because the follower
        input nodes are already kept within the analogue rails by the surrounding
        circuit.
    """
    if cfg.strict_vendor and vendor_ok and vpos == VDD:
        lines.append(f"X{name} {out} {minus} {plus} {VDD} {GND} MCP6004_UNIT")
    else:
        raw = f"{name}_raw"
        gain = "1e3"
        # Smooth 0..V(vpos) limiting:
        #   Vraw = Vrail/2 * (1 + tanh(gain * (V+ - V-)))
        # This is less ideal than a real macromodel, but it is bounded and much
        # easier for ngspice to converge than a hard discontinuous clip.
        lines.append(
            f"B{name}_OP {raw} {GND} "
            f"V={{0.5*V({vpos})*(1+tanh({gain}*(V({plus})-V({minus}))))}}"
        )
        lines.append(f"R{name}_OUT {raw} {out} {out_res}")


def opamp_follower(lines: list[str], name: str, out: str, inp: str, cfg: SimConfig) -> None:
    """Add a stable unity-gain follower approximation.

    The buffered reference and state followers are low-risk unity buffers whose
    inputs are produced by resistor dividers or bounded state nodes. A simple
    unity VCVS is more robust than solving a high-gain behavioural feedback loop
    at the initial timestep. Non-follower op-amp stages still use opamp_unit(),
    which is explicitly rail-limited.
    """
    if cfg.strict_vendor:
        lines.append(f"X{name} {out} {out} {inp} {VDD} {GND} MCP6004_UNIT")
    else:
        lines.append(f"E{name} {out} {GND} {inp} {GND} 1")


def clamp_expr_to_vdd(expr: str, *, rail: str = VDD) -> str:
    """Return an ngspice expression clipped to the local analogue rail.

    This is used only for closed-loop equivalent output drivers, not inside
    high-gain feedback loops. It keeps behavioural outputs within the physical
    supply range while avoiding the convergence failures caused by explicitly
    solving ideal op-amp feedback at t=0.
    """
    return f"min(max(({expr}),0),V({rail}))"


def add_closed_loop_driver(
    lines: list[str],
    name: str,
    out: str,
    expr: str,
    cfg: SimConfig,
    *,
    rail: str = VDD,
    out_res: str = "25",
) -> None:
    """Add a bounded closed-loop behavioural op-amp output approximation."""
    raw = f"{name}_raw"
    lines.append(f"B{name} {raw} {GND} V={{ {clamp_expr_to_vdd(expr, rail=rail)} }}")
    lines.append(f"R{name}_OUT {raw} {out} {out_res}")



def add_esd_cap(lines: list[str], name: str, node: str, cfg: SimConfig) -> None:
    """Approximate one-pin ESD/TVS devices as small capacitance plus leakage.

    TPD1E05U06-style protection parts are not modelled as hard diodes here,
    because clamping a normal 0-3 V signal to ground would be unrealistic for
    this behavioural model. The capacitance/leakage approximation preserves the
    small load relevant for transient visualisation.
    """
    lines.append(f"C{name}_ESD {node} {GND} {c_value(cfg, name + '_CESD', '1p')}")
    lines.append(f"R{name}_LEAK {node} {GND} 1G")


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
        f"* LIFeling Vm simulation: stage={cfg.stage}",
        "* Generated by Spice.py",
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


def add_cap_to_ground(
    lines: list[str],
    name: str,
    node: str,
    nominal_cap: str,
    cfg: SimConfig,
    *,
    esr: str | None = None,
    ic: str | None = None,
) -> None:
    """Add a capacitor to ground, optionally through a small ESR resistor."""
    cap = c_value(cfg, name, nominal_cap)
    if esr is not None and _to_float_suffix(esr) > 0:
        cap_node = f"{name}_esr_node"
        lines.append(f"R{name}_ESR {node} {cap_node} {esr}")
        suffix = f" IC={ic}" if ic is not None else ""
        lines.append(f"C{name} {cap_node} {GND} {cap}{suffix}")
    else:
        suffix = f" IC={ic}" if ic is not None else ""
        lines.append(f"C{name} {node} {GND} {cap}{suffix}")


def initial_supply_voltage(cfg: SimConfig) -> str:
    """Nominal final supply voltage used for operating initial conditions."""
    return cfg.vbat if cfg.supply_mode == "coin" else cfg.vdd


def vdd_cap_initial_voltage(cfg: SimConfig) -> str:
    """Initial voltage across local VDD decoupling capacitors."""
    return initial_supply_voltage(cfg) if cfg.startup_mode == "operating" else "0"


def reset_timer_initial_voltage(cfg: SimConfig) -> str:
    """Initial voltage for C31 / U6C reset-timer node."""
    return initial_supply_voltage(cfg) if cfg.startup_mode == "operating" else "0"


def vm_initial_voltage(cfg: SimConfig) -> str:
    """Initial voltage for the membrane capacitor."""
    return cfg.vm_initial if cfg.startup_mode == "operating" else cfg.cold_vm_initial


def add_supply_and_decoupling(lines: list[str], cfg: SimConfig) -> None:
    """Add either an ideal VDD source or a coin-cell source impedance model."""
    if cfg.supply_mode == "coin":
        lines += [
            "* ---- Non-ideal coin-cell supply model ----",
            f"VBAT {VBAT_RAW} {GND} DC {cfg.vbat}",
            f"RBAT {VBAT_RAW} {VDD} {cfg.rbat}",
            "* Local VDD decoupling after the battery/internal-resistance node.",
        ]
    else:
        lines += [
            "* ---- Ideal supply model ----",
            f"VDD_SRC {VDD} {GND} DC {cfg.vdd}",
            "* Local VDD decoupling on ideal supply rail.",
        ]

    # A compact local-decoupling approximation. The three capacitors represent
    # small IC bypass, board bulk, and optional reservoir storage respectively.
    # In operating mode they start charged, avoiding artificial startup crossings.
    # In cold mode they start discharged, letting us inspect power-on behaviour.
    vdd_ic = vdd_cap_initial_voltage(cfg)
    add_cap_to_ground(lines, "CDEC_LOCAL", VDD, cfg.cdec_local, cfg, esr=cfg.cdec_esr, ic=vdd_ic)
    add_cap_to_ground(lines, "CDEC_BULK", VDD, cfg.cdec_bulk, cfg, esr=cfg.cdec_esr, ic=vdd_ic)
    add_cap_to_ground(lines, "CDEC_RESERVOIR", VDD, cfg.cdec_reservoir, cfg, esr=cfg.cdec_esr, ic=vdd_ic)


def add_references_and_passive_vm(lines: list[str], cfg: SimConfig) -> None:
    rv1_low, rv1_high = split_pot_toleranced(cfg, "RV1", "50k", cfg.rv1_fraction)
    rv2_low, rv2_high = split_pot_toleranced(cfg, "RV2", "50k", cfg.rv2_fraction)
    cmem_value_nominal = selected_cmem(cfg)
    cmem_value = c_value(cfg, "CMEM_SELECTED", cmem_value_nominal)

    lines += ["* ---- Supply and reference dividers ----"]
    add_supply_and_decoupling(lines, cfg)

    lines += [
        "",
        "* Raw divider and global V_Leak_Ref_Max buffer.",
        "* KiCad 2026-06-10: R4/R5 create V_Leak_Ref_Max_Raw; U2A buffers it to V_Leak_Ref_Max.",
        "* V_Leak_Ref_Max then feeds every downstream use: RV1 pin3 and RV6..RV9 pin3.",
        f"R4 {VDD} {V_LEAK_REF_MAX_RAW} {r_value(cfg, 'R4', '49.9k')}",
        f"R5 {V_LEAK_REF_MAX_RAW} {GND} {r_value(cfg, 'R5', '100k')}",
    ]
    opamp_follower(lines, "U2A_LEAK_REF_MAX", V_LEAK_REF_MAX, V_LEAK_REF_MAX_RAW, cfg)

    lines += [
        "",
        f"* RV1=50k: pin1=GNDREF, pin2=/V_Leak_ref, pin3=buffered V_Leak_Ref_Max; requested fraction={cfg.rv1_fraction:.3f}, effective fraction={effective_pot_fraction(cfg, 'RV1', cfg.rv1_fraction):.3f}",
        f"RV1_LOW {V_LEAK_REF} {GND} {rv1_low}",
        f"RV1_HIGH {V_LEAK_REF_MAX} {V_LEAK_REF} {rv1_high}",
    ]
    opamp_follower(lines, "U1A", V_LEAK, V_LEAK_REF, cfg)

    lines += [
        "",
        "* Reset injection reference: R10=69.8k VDD->V_Reset_Ref, R11=10k V_Reset_Ref->GNDREF",
        f"R10 {VDD} {V_RESET_REF} {r_value(cfg, 'R10', '69.8k')}",
        f"R11 {V_RESET_REF} {GND} {r_value(cfg, 'R11', '10k')}",
    ]
    opamp_follower(lines, "U2B", RESET_INJ, V_RESET_REF, cfg)

    lines += [
        "",
        "* Peak injection reference: R8=10k VDD->V_Peak_Ref, R9=100k V_Peak_Ref->GNDREF.",
        "* U2C buffers V_Peak_Ref; U14/R49 later inject it into Vm_Int during Peak_Window.",
        f"R8 {VDD} {V_PEAK_REF} {r_value(cfg, 'R8', '10k')}",
        f"R9 {V_PEAK_REF} {GND} {r_value(cfg, 'R9', '100k')}",
    ]
    opamp_follower(lines, "U2C_PEAK", V_PEAK_DRIVE, V_PEAK_REF, cfg)

    lines += [
        "",
        "* ---- Passive membrane core ----",
        "* RV2 ground truth: pin1=Net-(R32-Pad1), pin2=Vm_Int, pin3=V_Leak, R32=1k pin1->Vm_Int.",
        f"* RV2 requested fraction={cfg.rv2_fraction:.3f}, effective fraction={effective_pot_fraction(cfg, 'RV2', cfg.rv2_fraction):.3f}",
        f"RV2_LOWER {RV2_PIN1} {VM} {rv2_low}",
        f"R32 {RV2_PIN1} {VM} {r_value(cfg, 'R32', '1k')}",
        f"RV2_UPPER {V_LEAK} {VM} {rv2_high}",
        f"* Membrane capacitance selected by {'RV4' if cfg.cmem_mode == 'rv4' else '--cmem'}: nominal={cmem_value_nominal}, actual={cmem_value}",
        f"CMEM_SELECTED {VM} {GND} {cmem_value} IC={vm_initial_voltage(cfg)}",
        f"C26 {VM} {GND} {c_value(cfg, 'C26', '100p')}",
        "* Vm_Int Schottky clamps from schematic: D2 to VDD and D3 to GNDREF.",
    ]
    add_model_or_subckt_diode(lines, "D2_VM_HIGH", VM, VDD, cfg.syn_diode_name, False)
    add_model_or_subckt_diode(lines, "D3_VM_LOW", GND, VM, cfg.syn_diode_name, False)


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

    add_external_stimulus(lines, cfg)

def add_external_stimulus(lines: list[str], cfg: SimConfig) -> None:
    """Add a robust closed-loop equivalent of the U19B stimulus amplifier.

    Schematic topology retained:
      Stimulus_Ext -> R83 -> V_Stim_Cmd, C37 to ground
      Vm_Int/V_Stim_Cmd -> R84/R85 -> U19B+
      V_Leak/V_Stim_Drive -> R86/R87 -> U19B-
      U19B output V_Stim_Drive -> R88 -> Vm_Int

    The ideal op-amp feedback loop is not solved explicitly in fallback mode,
    because it can make ngspice fail at the initial timestep. Instead we keep
    the resistor network as loading and drive V_Stim_Drive from the closed-loop
    ideal-op-amp equation:

        Vout = (1 + R87/R86) * Vplus - (R87/R86) * V_Leak

    The result is clipped to 0..VDD because the real amplifier cannot exceed its
    local supply rails.
    """
    r86_value = r_value(cfg, 'R86', '200k')
    r87_value = r_value(cfg, 'R87', '100k')
    ratio = _to_float_suffix(r87_value) / _to_float_suffix(r86_value)
    gain_plus = 1.0 + ratio

    lines += [
        "",
        "* ---- External stimulus path: U19B closed-loop equivalent ----",
    ]
    if cfg.stim_dc is None:
        lines += [
            "* No external stimulus source requested; jack node is biased weakly only for SPICE convergence.",
            f"RSTIM_EXT_BIAS {STIMULUS_EXT} {GND} 1G",
        ]
    else:
        lines.append(f"VSTIM {STIMULUS_EXT} {GND} DC {cfg.stim_dc:.12g}")

    lines += [
        f"R83 {STIMULUS_EXT} {V_STIM_CMD} {r_value(cfg, 'R83', '1k')}",
        f"C37 {V_STIM_CMD} {GND} {c_value(cfg, 'C37', '100p')}",
        f"R84 {VM} {V_STIM_PLUS} {r_value(cfg, 'R84', '100k')}",
        f"R85 {V_STIM_CMD} {V_STIM_PLUS} {r_value(cfg, 'R85', '200k')}",
        f"R86 {V_LEAK} {V_STIM_MINUS} {r86_value}",
        f"R87 {V_STIM_DRIVE} {V_STIM_MINUS} {r87_value}",
    ]
    add_closed_loop_driver(
        lines,
        "U19B_STIM_CL",
        V_STIM_DRIVE,
        f"{gain_plus:.12g}*V({V_STIM_PLUS})-{ratio:.12g}*V({V_LEAK})",
        cfg,
        out_res="100",
    )
    lines.append(f"R88 {V_STIM_DRIVE} {VM} {r_value(cfg, 'R88', '47k')}")
    add_esd_cap(lines, "D19", STIMULUS_EXT, cfg)


def add_threshold(lines: list[str], cfg: SimConfig) -> None:
    lines += [
        "",
        "* ---- Threshold comparator U6B and AP/spike generation ----",
        "* Ground truth: R6=24.3k VDD->V_Threshold, R7=10k V_Threshold->GNDREF.",
        f"R6 {VDD} {V_THRESHOLD} {r_value(cfg, 'R6', '24.3k')}",
        f"R7 {V_THRESHOLD} {GND} {r_value(cfg, 'R7', '10k')}",
        "* U6B: INB+=V_Threshold, INB-=Vm_Int, OUTB=/Threshold_Comparator_Out.",
        f"R33 {V_THRESHOLD} {THRESHOLD_COMP_OUT} {r_value(cfg, 'R33', '220k')}",
        f"R34 {VDD} {THRESHOLD_COMP_OUT} {r_value(cfg, 'R34', '10k')}",
    ]
    tlv7044_oc(lines, "U6B", THRESHOLD_COMP_OUT, VM, V_THRESHOLD, cfg)

    lines += [
        "* Q1=BSS138: D=AP, G=/Threshold_Comparator_Out, S=GNDREF.",
        f"R35 {VDD} {AP} {r_value(cfg, 'R35', '22k')}",
        f"MQ1 {AP} {THRESHOLD_COMP_OUT} {GND} {GND} {cfg.bss138_model}",
        "* C29=10nF AP->/Rising_AP, R46=100k /Rising_AP->GNDREF, D8=RB521S30T1G to Spike_Pulse.",
        f"C29 {AP} {RISING_AP} {c_value(cfg, 'C29', '10n')}",
        f"R46 {RISING_AP} {GND} {r_value(cfg, 'R46', '100k')}",
    ]

    # KiCad D8 pin 2 = /Rising_AP and pin 1 = Spike_Pulse. For this diode symbol,
    # pin 2 is anode and pin 1 is cathode, so SPICE order is /Rising_AP -> Spike_Pulse.
    add_spike_schottky(lines, "D8", RISING_AP, SPIKE_PULSE, cfg)
    lines.append(f"R47 {SPIKE_PULSE} {GND} {r_value(cfg, 'R47', '1Meg')}")

    lines += [
        "* D20 external Schottky clamp added to schematic: anode=GNDREF, cathode=Spike_Pulse.",
        "* It conducts when Spike_Pulse goes below GNDREF and protects U6A INA+.",
        f"DD20 {GND} {SPIKE_PULSE} {cfg.spike_diode_name}",
    ]


def add_peak_and_reset(lines: list[str], cfg: SimConfig) -> None:
    lines += [
        "",
        "* ---- Peak and reset windows: U6A/U6C and Q3-Q6 ----",
        "* U6A: INA+=Spike_Pulse, INA-=V_Threshold, OUTA=Peak_Window; R48 pull-up.",
        "* Fallback open-drain comparator pulls OUT low when V(-) > V(+).",
        f"R48 {VDD} {PEAK_WINDOW} {r_value(cfg, 'R48', '100k')}",
    ]
    tlv7044_oc(lines, "U6A", PEAK_WINDOW, V_THRESHOLD, SPIKE_PULSE, cfg)

    lines += [
        "",
        "* Vm peak-injection path: U14 closes when Peak_Window is high.",
        "* Hardware: U2C buffered V_Peak_Ref -> R49 -> U14 NO/COM -> Vm_Int.",
        f"R49 {V_PEAK_DRIVE} {PEAK_INJECT_NO} {r_value(cfg, 'R49', '10k')}",
        f"SU14_PEAK {VM} {PEAK_INJECT_NO} {PEAK_WINDOW} {GND} SW_TS5A3166",
        "",
        "* Reset-window timing node: R50=22k VDD->Net-(U6C-INC-), C31=1uF to GNDREF.",
        f"R50 {VDD} {U6C_MINUS} {r_value(cfg, 'R50', '22k')}",
        f"C31 {U6C_MINUS} {GND} {c_value(cfg, 'C31', '1u')} IC={reset_timer_initial_voltage(cfg)}",
        "* Q3=BSS138: D=Reset_Timer_Discharge, G=AP, S=GNDREF; R51=100R from RESET_TIMER_DISCHARGE to U6C_MINUS.",
        f"MQ3 {RESET_TIMER_DISCHARGE} {AP} {GND} {GND} {cfg.bss138_model}",
        f"R51 {RESET_TIMER_DISCHARGE} {U6C_MINUS} {r_value(cfg, 'R51', '100')}",
        "",
        "* U6C plus input network and reset-window pull-up.",
        f"R53 {U6C_PLUS} {VDD} {r_value(cfg, 'R53', '27k')}",
        f"R54 {U6C_PLUS} {RESET_WINDOW} {r_value(cfg, 'R54', '100k')}",
        f"R55 {U6C_PLUS} {GND} {r_value(cfg, 'R55', '22k')}",
        f"R52 {VDD} {RESET_WINDOW} {r_value(cfg, 'R52', '100k')}",
    ]
    tlv7044_oc(lines, "U6C", RESET_WINDOW, U6C_MINUS, U6C_PLUS, cfg)

    lines += [
        "",
        "* Reset-current gate chain Q4/Q5/Q6.",
        "* Q4=BSS138: D=/Reset_Injection_Enable, G=Peak_Window, S=GNDREF; R56 pull-up.",
        f"R56 {VDD} {RESET_INJECTION_ENABLE} {r_value(cfg, 'R56', '100k')}",
        f"MQ4 {RESET_INJECTION_ENABLE} {PEAK_WINDOW} {GND} {GND} {cfg.bss138_model}",
        "* Q5=BSS138: G=/Reset_Injection_Enable, S=/Reset_Injection_Drive, D=Reset_Ref_Gated.",
        f"MQ5 {RESET_REF_GATED} {RESET_INJECTION_ENABLE} {RESET_INJ} {RESET_INJ} {cfg.bss138_model}",
        "* Q6=BSS138: G=Reset_Window, S=Reset_Ref_Gated, D=Reset_Current_Node; R57=10k to Vm_Int.",
        f"MQ6 {RESET_CURRENT_NODE} {RESET_WINDOW} {RESET_REF_GATED} {RESET_REF_GATED} {cfg.bss138_model}",
        f"R57 {RESET_CURRENT_NODE} {VM} {r_value(cfg, 'R57', '10k')}",
        "",
        "* Spike_Out driver: U6D compares Peak_Window against V_Logic_Mid; R81 pull-up and R82 series output.",
        "* V_Logic_Mid is approximated with the schematic divider R12/R13 already used by U6D.",
        f"R12_LOGIC {VDD} {V_LOGIC_MID} {r_value(cfg, 'R12', '100k')}",
        f"R13_LOGIC {V_LOGIC_MID} {GND} {r_value(cfg, 'R13', '100k')}",
        f"R81 {VDD} {U6D_OUT} {r_value(cfg, 'R81', '100k')}",
    ]
    tlv7044_oc(lines, "U6D_SPIKE_OUT", U6D_OUT, V_LOGIC_MID, PEAK_WINDOW, cfg)
    lines += [
        f"R82 {U6D_OUT} {SPIKE_OUT} {r_value(cfg, 'R82', '100')}",
    ]
    add_esd_cap(lines, "D18", SPIKE_OUT, cfg)


def add_adaptation(lines: list[str], cfg: SimConfig) -> None:
    rv3_low, rv3_high = split_pot_toleranced(cfg, "RV3", "100k", cfg.rv3_fraction)
    u1c_ideal_out = "U1C_ideal_out"

    r39_value = r_value(cfg, 'R39', '100k')
    r40_value = r_value(cfg, 'R40', '200k')
    u1b_ratio = _to_float_suffix(r40_value) / _to_float_suffix(r39_value)
    u1b_gain_plus = 1.0 + u1b_ratio

    lines += [
        "",
        "* ---- Adaptation path /Vw ----",
        "* U1B adaptation-shaping amplifier from schematic, implemented as a closed-loop equivalent.",
        "* This keeps the R37/R38/R39/R40 loading while avoiding an ideal op-amp feedback loop at t=0.",
        f"R37 {VKICK} {ADAPT_U1B_PLUS} {r_value(cfg, 'R37', '200k')}",
        f"R38 {ADAPT_U1B_PLUS} {VM} {r_value(cfg, 'R38', '100k')}",
        f"R39 {V_LEAK} {ADAPT_U1B_MINUS} {r39_value}",
        f"R40 {ADAPT_U1B_MINUS} {ADAPT_U1B_OUT} {r40_value}",
    ]
    add_closed_loop_driver(
        lines,
        "U1B_ADAPT_CL",
        ADAPT_U1B_OUT,
        f"{u1b_gain_plus:.12g}*V({ADAPT_U1B_PLUS})-{u1b_ratio:.12g}*V({V_LEAK})",
        cfg,
        out_res="100",
    )
    lines += [
        f"R41 {ADAPT_U1B_OUT} {ADAPT_U1B_DIODE_A} {r_value(cfg, 'R41', '330k')}",
    ]
    add_spike_schottky(lines, "D6", ADAPT_U1B_DIODE_A, VW, cfg)

    lines += [
        "* U1C is a follower driven from AP: U1C+=AP, U1C-/OUT=Adapt_Kick_Drive.",
    ]
    opamp_follower(lines, "U1C", u1c_ideal_out, AP, cfg)

    lines += [
        "* Model-only U1C output resistance/current-limiting approximation.",
        "* This prevents the ideal fallback op-amp from injecting unrealistic current into C27.",
        f"RU1C_OUT {u1c_ideal_out} {ADAPT_KICK_DRIVE} {r_value(cfg, 'RU1C_OUT', '100')}",
        "* C27=1uF between U1C output and /Vkick; R36=22k /Vkick->GNDREF.",
        f"C27 {VKICK} {ADAPT_KICK_DRIVE} {c_value(cfg, 'C27', '1u')}",
        f"R36 {VKICK} {GND} {r_value(cfg, 'R36', '22k')}",
        "* Diode orientation from KiCad pins: D4 GNDREF->/Vkick, D5 /Vkick->Vw, D7 GNDREF->Vw.",
    ]
    add_signal_diode(lines, "D4", GND, VKICK, cfg)
    add_signal_diode(lines, "D5", VKICK, VW, cfg)
    add_signal_diode(lines, "D7", GND, VW, cfg)

    lines += [
        f"C28 {VW} {GND} {c_value(cfg, 'C28', '10u')} IC=0",
        f"* RV3=100k: pins 1/2=Vw, pin3=Net-(R42-Pad1); requested fraction={cfg.rv3_fraction:.3f}, effective fraction={effective_pot_fraction(cfg, 'RV3', cfg.rv3_fraction):.3f}.",
        f"RV3_LOWER {VW} {VW} {rv3_low}",
        f"RV3_UPPER {VW} {RV3_BOTTOM} {rv3_high}",
        f"R42 {RV3_BOTTOM} {GND} {r_value(cfg, 'R42', '100')}",
    ]
    opamp_follower(lines, "U1D", VW_BUFF, VW, cfg)

    lines += [
        "* Q2=MMBT3904 adaptation current path: R44/R45 base divider, R43 collector to Vm_Int.",
        f"R44 {VW_BUFF} {ADAPT_BASE} {r_value(cfg, 'R44', '22k')}",
        f"R45 {ADAPT_BASE} {GND} {r_value(cfg, 'R45', '100k')}",
        f"Q2 {ADAPT_CURRENT_SINK} {ADAPT_BASE} {GND} {cfg.npn_model}",
        f"R43 {VM} {ADAPT_CURRENT_SINK} {r_value(cfg, 'R43', '10k')}",
    ]




def add_synapse_input(
    lines: list[str],
    idx: int,
    spike_node: str,
    input_node: str,
    switch_ctrl: str,
    delay: str,
    width: str,
    period: str,
    cfg: SimConfig,
) -> None:
    """Add one Syn*_Spike jack input, clamp, and TS5A3166 control node."""
    r_spike = {1: "R66", 2: "R70", 3: "R74", 4: "R78"}[idx]
    r_ctrl = {1: "R64", 2: "R68", 3: "R72", 4: "R76"}[idx]
    r_pull = {1: "R65", 2: "R69", 3: "R73", 4: "R77"}[idx]
    d_hi = {1: "D10", 2: "D12", 3: "D14", 4: "D16"}[idx]
    d_lo = {1: "D11", 2: "D13", 3: "D15", 4: "D17"}[idx]

    lines += [
        f"* Syn{idx} spike input: jack net -> 22k -> clamp node -> 1k -> TS5A3166 IN.",
        f"VSYN{idx} {spike_node} {GND} {synapse_pulse(delay, width, period, cfg.syn_amp, cfg.syn_rise, cfg.syn_fall)}",
        f"{r_spike} {spike_node} {input_node} {r_value(cfg, r_spike, '22k')}",
        f"{r_pull} {input_node} {GND} {r_value(cfg, r_pull, '100k')}",
    ]
    # BAT54 input clamps from the KiCad netlist:
    # D10/D12/D14/D16: anode=input node, cathode=VDD.
    # D11/D13/D15/D17: anode=GNDREF, cathode=input node.
    add_model_or_subckt_diode(lines, d_hi, input_node, VDD, cfg.syn_diode_name, False)
    add_model_or_subckt_diode(lines, d_lo, GND, input_node, cfg.syn_diode_name, False)
    lines.append(f"{r_ctrl} {input_node} {switch_ctrl} {r_value(cfg, r_ctrl, '1k')}")


def add_synapse_set_voltage(
    lines: list[str],
    idx: int,
    rv_ref: str,
    raw_node: str,
    set_node: str,
    fraction: float,
    cfg: SimConfig,
) -> None:
    """Add RV6..RV9 set-voltage pot and U3 follower."""
    low, high = split_pot_toleranced(cfg, rv_ref, "100k", fraction)
    top_node = V_LEAK_REF_MAX_RAW if cfg.syn_ref_mode == "legacy_direct" else V_LEAK_REF_MAX
    u3_name = {1: "U3B", 2: "U3C", 3: "U3D", 4: "U3A"}[idx]
    lines += [
        f"* {rv_ref}=100k: pin1=GNDREF, pin2=Syn{idx} set wiper, pin3={top_node}.",
        f"* Syn{idx} set requested fraction={fraction:.3f}, effective fraction={effective_pot_fraction(cfg, rv_ref, fraction):.3f}",
        f"{rv_ref}_LOW {raw_node} {GND} {low}",
        f"{rv_ref}_HIGH {top_node} {raw_node} {high}",
    ]
    opamp_follower(lines, u3_name, set_node, raw_node, cfg)


def add_synapse_switch_path(
    lines: list[str],
    idx: int,
    set_node: str,
    no_node: str,
    switch_ctrl: str,
    cfg: SimConfig,
) -> None:
    """Add TS5A3166 ideal switch and 22k injection resistor to V_Syn_State."""
    uref = {1: "U15", 2: "U16", 3: "U17", 4: "U18"}[idx]
    r_inject = {1: "R63", 2: "R67", 3: "R71", 4: "R75"}[idx]
    lines += [
        f"* {uref}=TS5A3166: COM=V_Syn{idx}_Set, NO=Net-({uref}-NO), IN=Syn{idx} control.",
        f"S{uref} {set_node} {no_node} {switch_ctrl} {GND} SW_TS5A3166",
        f"{r_inject} {no_node} {V_SYN_STATE} {r_value(cfg, r_inject, '22k')}",
    ]


def add_synaptic_circuits(lines: list[str], cfg: SimConfig) -> None:
    """Add the synaptic state circuit and enabled Syn1..Syn4 spike-gated set paths.

    This models the intended functional path from the KiCad netlist:
      V_Leak_Ref_Max_Raw -> U2A buffer -> V_Leak_Ref_Max -> RV1/RV6..RV9 pin 3
      Syn*_Spike -> clamp/filter -> TS5A3166 -> V_Syn*_Set -> 22k -> V_Syn_State
      V_Syn_State -> U2D state buffer -> R80 -> Vm_Int

    The updated netlist has no separate V_Syn_Ref node. U2A output/inverting
    pins are the global V_Leak_Ref_Max rail, and the raw divider node is named
    V_Leak_Ref_Max_Raw. The state-buffer net around U2 pins 12/13/14 is still
    kept in the previously intended follower direction V_Syn_State -> V_Syn_Drive
    -> R80 -> Vm_Int, because the exported netlist still appears to tie
    output/inverting together and V_Syn_State to the non-inverting input.
    """
    if not synapse_enabled(cfg):
        return

    rv5_to_vleak = pot_upper_segment("100k", effective_pot_fraction(cfg, "RV5", cfg.rv5_fraction))
    rv5_to_vleak = format_spice_number(_to_float_suffix(rv5_to_vleak) * tolerance_factor(cfg, "RV5_total", cfg.pot_tol_pct))

    lines += [
        "",
        "* ---- Synaptic state and spike-gated input circuit ----",
        "* C36/R79/RV5 form the synaptic state memory/decay path.",
        f"C36 {V_SYN_STATE} {GND} {c_value(cfg, 'C36', '220n')} IC={syn_state_initial_voltage(cfg)}",
        f"R79 {V_SYN_STATE} {RV5_DECAY} {r_value(cfg, 'R79', '10k')}",
        f"RV5_DECAY_RES {RV5_DECAY} {V_LEAK} {rv5_to_vleak}",
        "* Intended U2D follower: V_Syn_State -> V_Syn_Drive; R80 injects into Vm_Int.",
    ]
    opamp_follower(lines, "U2D_SYN", V_SYN_DRIVE, V_SYN_STATE, cfg)
    lines.append(f"R80 {V_SYN_DRIVE} {VM} {r_value(cfg, 'R80', '47k')}")

    if cfg.syn_ref_mode == "legacy_direct":
        lines += [
            "",
            "* LEGACY/COMPARISON ONLY: RV6..RV9 pin 3 use the raw divider node directly.",
            "* This bypasses U2A and does not match the 2026-06-10 KiCad netlist.",
        ]
    else:
        lines += [
            "",
            "* Current KiCad reference connectivity already modeled in the passive/reference block:",
            "* R4/R5 -> V_Leak_Ref_Max_Raw -> U2A buffer -> V_Leak_Ref_Max.",
            "* RV6, RV7, RV8 and RV9 pin 3 are connected to buffered V_Leak_Ref_Max.",
        ]

    # Set-voltage buffers exist for all four channels because RV6..RV9 load the buffered reference rail.
    add_synapse_set_voltage(lines, 1, "RV6", SYN1_SET_RAW, V_SYN1_SET, cfg.rv6_fraction, cfg)
    add_synapse_set_voltage(lines, 2, "RV7", SYN2_SET_RAW, V_SYN2_SET, cfg.rv7_fraction, cfg)
    add_synapse_set_voltage(lines, 3, "RV8", SYN3_SET_RAW, V_SYN3_SET, cfg.rv8_fraction, cfg)
    add_synapse_set_voltage(lines, 4, "RV9", SYN4_SET_RAW, V_SYN4_SET, cfg.rv9_fraction, cfg)

    if cfg.syn1_enable:
        add_synapse_input(lines, 1, SYN1_SPIKE, SYN1_IN, U15_IN, cfg.syn1_delay, cfg.syn1_width, cfg.syn1_period, cfg)
        add_synapse_switch_path(lines, 1, V_SYN1_SET, SYN1_NO, U15_IN, cfg)
    if cfg.syn2_enable:
        add_synapse_input(lines, 2, SYN2_SPIKE, SYN2_IN, U16_IN, cfg.syn2_delay, cfg.syn2_width, cfg.syn2_period, cfg)
        add_synapse_switch_path(lines, 2, V_SYN2_SET, SYN2_NO, U16_IN, cfg)
    if cfg.syn3_enable:
        add_synapse_input(lines, 3, SYN3_SPIKE, SYN3_IN, U17_IN, cfg.syn3_delay, cfg.syn3_width, cfg.syn3_period, cfg)
        add_synapse_switch_path(lines, 3, V_SYN3_SET, SYN3_NO, U17_IN, cfg)
    if cfg.syn4_enable:
        add_synapse_input(lines, 4, SYN4_SPIKE, SYN4_IN, U18_IN, cfg.syn4_delay, cfg.syn4_width, cfg.syn4_period, cfg)
        add_synapse_switch_path(lines, 4, V_SYN4_SET, SYN4_NO, U18_IN, cfg)

def add_vm_external_output(lines: list[str], cfg: SimConfig) -> None:
    """Add U8/TLV9001 Vm_Ext output buffer with display-spike synthesis.

    Latest KiCad display path:
      Vm_Int -> R90=100k -> Vm_Display_In
      Vm_Display_In -> C38=22n -> GNDREF
      V_Peak_Drive -> R91=10k -> U20 NO
      U20 COM -> Vm_Display_In
      U20 IN  -> Peak_Window
      D21 clamps Vm_Display_In to VDD, D22 clamps Vm_Display_In to GNDREF
      Vm_Display_In -> U8 non-inverting input -> R1/C14 -> Vm_Ext

    The key modelling intention is that Vm_Int remains the internal LIF
    computation node, while Vm_Ext becomes a user-facing/display trace that
    follows Vm_Int and receives an additional short spike-shaped pulse.

    U8 is still represented as a bounded closed-loop equivalent rather than an
    explicit ideal op-amp feedback loop, which keeps ngspice robust.
    """
    r2_value = r_value(cfg, 'R2', '10k')
    r3_value = r_value(cfg, 'R3', '100k')
    vmext_gain = 1.0 + _to_float_suffix(r2_value) / _to_float_suffix(r3_value)

    lines += [
        "",
        "* ---- Vm_Ext display-spike synthesis and live-output driver ----",
        "* New hardware: Vm_Int no longer drives U8 IN+ directly.",
        "* R90 lets Vm_Display_In follow the internal membrane node without strongly loading Vm_Int.",
        f"R90 {VM_DISPLAY_IN} {VM} {r_value(cfg, 'R90', '100k')}",
        f"C38 {VM_DISPLAY_IN} {GND} {c_value(cfg, 'C38', '22n')} IC={vm_initial_voltage(cfg)}",
        "* Display-node BAT54WS clamps: D21 high clamp to VDD, D22 low clamp to GNDREF.",
    ]
    add_model_or_subckt_diode(lines, "D21_DISPLAY_HIGH", VM_DISPLAY_IN, VDD, cfg.syn_diode_name, False)
    add_model_or_subckt_diode(lines, "D22_DISPLAY_LOW", GND, VM_DISPLAY_IN, cfg.syn_diode_name, False)

    if cfg.stage in {"threshold_reset", "threshold_reset_adapt"}:
        lines += [
            "* U20 display-spike switch: Peak_Window controls a short charge from buffered V_Peak_Drive.",
            "* Peak_Window is used only as the switch control; V_Peak_Drive supplies the display-spike energy.",
            f"R91 {V_PEAK_DRIVE} {DISPLAY_SPIKE_NO} {r_value(cfg, 'R91', '10k')}",
            f"SU20_DISPLAY_SPIKE {VM_DISPLAY_IN} {DISPLAY_SPIKE_NO} {PEAK_WINDOW} {GND} SW_TS5A3166",
        ]
    else:
        lines += [
            "* Display-spike switch U20 is omitted in passive/threshold-only stages because Peak_Window",
            "* is not instantiated in those reduced models. Vm_Display_In still follows Vm_Int through R90/C38.",
        ]

    lines += [
        "",
        "* U8 TLV9001 live-output buffer, closed-loop equivalent.",
        "* Real U8 V+ is V_Boost; behavioural model powers it from VDD because boost is out of scope.",
        f"R2 {VM_FB} {VM_DRV} {r2_value}",
        f"R3 {GND} {VM_FB} {r3_value}",
    ]
    add_closed_loop_driver(
        lines,
        "U8_VM_EXT_CL",
        VM_DRV,
        f"{vmext_gain:.12g}*V({VM_DISPLAY_IN})",
        cfg,
        out_res="25",
    )
    lines += [
        f"R1 {VM_DRV} {VM_EXT} {r_value(cfg, 'R1', '220')}",
        f"C14 {VM_EXT} {GND} {c_value(cfg, 'C14', '100p')}",
    ]
    add_esd_cap(lines, "D1", VM_EXT, cfg)



def build_spice_deck(cfg: SimConfig, *, for_cli: bool = False, csv_path: Path | None = None) -> str:
    lines = add_header(cfg)
    add_references_and_passive_vm(lines, cfg)
    add_vm_external_output(lines, cfg)

    if cfg.stage in {"threshold", "threshold_reset", "threshold_reset_adapt"}:
        add_threshold(lines, cfg)
    if cfg.stage in {"threshold_reset", "threshold_reset_adapt"}:
        add_peak_and_reset(lines, cfg)
    if cfg.stage == "threshold_reset_adapt":
        add_adaptation(lines, cfg)
    if synapse_enabled(cfg):
        add_synaptic_circuits(lines, cfg)

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
        linewidth = 2.6 if trace.key in {"VM_EXT", "VM"} else 1.2
        alpha = 1.0 if trace.key in {"VM_EXT", "VM"} else 0.85
        plt.plot(t_ms, df[trace.key].to_numpy(), label=trace.label, linewidth=linewidth, alpha=alpha)

    plt.xlabel("Time (ms)")
    plt.ylabel("Voltage (V)")
    supply_label = f"{cfg.supply_mode}, {cfg.startup_mode}"
    plt.title(
        f"LIFeling Vm - {cfg.stage}, {selected_cmem(cfg)}, "
        f"RV1={cfg.rv1_fraction:.2f}, RV2={cfg.rv2_fraction:.2f}, RV3={cfg.rv3_fraction:.2f}, "
        f"{supply_label}"
    )
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best", fontsize="small", ncol=2)
    plt.tight_layout()
    plt.savefig(png_path, dpi=180)
    plt.close()

def plot_vm_only(df: pd.DataFrame, cfg: SimConfig, png_path: Path) -> None:
    """Generate a clean comparison plot with both Vm_Int and Vm_Ext.

    Vm_Int is the internal LIF computation node. Vm_Ext is the physical live
    output after the display-spike synthesis and U8 output stage. Plotting both
    together makes it clear how much of the visible spike is part of the
    user-facing display overlay versus the internal membrane computation.
    """
    t_ms = df["time_s"].to_numpy() * 1e3

    plt.figure(figsize=(13, 5))

    plotted = False
    if "VM" in df and not df["VM"].isna().all():
        plt.plot(t_ms, df["VM"].to_numpy(), label="Vm_Int", linewidth=2.2, alpha=0.95)
        plotted = True
    if "VM_EXT" in df and not df["VM_EXT"].isna().all():
        plt.plot(t_ms, df["VM_EXT"].to_numpy(), label="Vm_Ext", linewidth=2.8, alpha=0.95)
        plotted = True

    if not plotted:
        plt.plot(t_ms, np.zeros_like(t_ms), label="No Vm trace available", linewidth=2.0)

    plt.xlabel("Time (ms)")
    plt.ylabel("Voltage (V)")
    tol_label = ""
    if cfg.tol_mode == "random":
        tol_label = f", tol seed={cfg.tol_seed}"

    if cfg.supply_mode == "coin":
        supply_label = f", coin {cfg.vbat}V/{cfg.rbat}ohm, {cfg.startup_mode}"
    else:
        supply_label = f", ideal {cfg.vdd}V, {cfg.startup_mode}"

    plt.title(
        f"LIFeling Vm comparison (Vm_Int and Vm_Ext) - {cfg.stage}, {selected_cmem(cfg)}, "
        f"RV1={cfg.rv1_fraction:.2f}, RV2={cfg.rv2_fraction:.2f}, RV3={cfg.rv3_fraction:.2f}"
        f"{supply_label}{tol_label}"
    )

    # Fixed display range for easy comparison between simulations.
    plt.ylim(0, 3)
    plt.yticks(np.arange(0, 3.1, 0.5))

    plt.grid(True, alpha=0.3)
    plt.legend(loc="best")
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


def count_rising_edges(y: np.ndarray, threshold: float) -> int:
    if len(y) < 2:
        return 0
    above = y >= threshold
    return int(np.sum((~above[:-1]) & above[1:]))


def analysis_mask(t: np.ndarray, cfg: SimConfig) -> np.ndarray:
    """Mask for diagnostics after the requested startup-ignore interval."""
    if cfg.ignore_start_ms <= 0:
        return np.ones_like(t, dtype=bool)
    return t >= cfg.ignore_start_ms / 1000.0


def first_crossing_index(y: np.ndarray, ref: np.ndarray, mask: np.ndarray | None = None) -> int | None:
    if mask is None:
        idx = np.where(y >= ref)[0]
    else:
        idx = np.where((y >= ref) & mask)[0]
    if len(idx) == 0:
        return None
    return int(idx[0])


def crossing_count_after_mask(t: np.ndarray, y: np.ndarray, ref: np.ndarray, cfg: SimConfig) -> int:
    mask = analysis_mask(t, cfg)
    if not np.any(mask):
        return 0
    diff = y[mask] - ref[mask]
    return count_rising_edges(diff, 0.0)


def edge_count_after_mask(t: np.ndarray, y: np.ndarray, threshold: float, cfg: SimConfig) -> int:
    mask = analysis_mask(t, cfg)
    if not np.any(mask):
        return 0
    return count_rising_edges(y[mask], threshold)


def _fmt_optional_ms(value_s: float | None) -> str:
    """Format an optional time value in milliseconds for console output."""
    if value_s is None or not np.isfinite(value_s):
        return "n/a"
    return f"{value_s * 1e3:.6g} ms"


def _interp_threshold_time(t0: float, t1: float, y0: float, y1: float, threshold: float) -> float:
    """Linearly interpolate the threshold-crossing time between two samples."""
    if y1 == y0 or not np.isfinite(y0) or not np.isfinite(y1):
        return float(t1)
    frac = (threshold - y0) / (y1 - y0)
    if not np.isfinite(frac):
        return float(t1)
    frac = float(np.clip(frac, 0.0, 1.0))
    return float(t0 + frac * (t1 - t0))


def digital_pulse_timing_stats(
    t: np.ndarray,
    y: np.ndarray,
    cfg: SimConfig,
    *,
    threshold: float = 1.0,
) -> dict[str, object]:
    """Return timing statistics for a logic-like waveform after ignore_start_ms.

    This is intended for comparator/window signals such as Reset_Window. It avoids
    over-interpreting the final sample of a transient by reporting duty cycle,
    last edge times, closed pulse widths, and whether the last pulse is still
    open at the simulation endpoint.
    """
    mask = analysis_mask(t, cfg)
    idx = np.flatnonzero(mask)

    empty = {
        "threshold": threshold,
        "analysis_start_s": None,
        "analysis_end_s": None,
        "duration_s": 0.0,
        "high_at_start": False,
        "high_at_end": False,
        "state_at_end": "UNKNOWN",
        "rise_count": 0,
        "fall_count": 0,
        "last_rise_s": None,
        "last_fall_s": None,
        "open_high_duration_s": None,
        "low_duration_since_last_fall_s": None,
        "duty_cycle": float("nan"),
        "closed_pulse_count": 0,
        "pulse_width_mean_s": float("nan"),
        "pulse_width_median_s": float("nan"),
        "pulse_width_max_s": float("nan"),
        "pulse_width_min_s": float("nan"),
    }

    if len(idx) < 2:
        return empty

    tw = np.asarray(t[idx], dtype=float)
    yw = np.asarray(y[idx], dtype=float)
    valid = np.isfinite(tw) & np.isfinite(yw)
    tw = tw[valid]
    yw = yw[valid]
    if len(tw) < 2:
        return empty

    above = yw >= threshold
    rise_locs = np.where((~above[:-1]) & above[1:])[0] + 1
    fall_locs = np.where(above[:-1] & (~above[1:]))[0] + 1

    rise_times = np.array(
        [
            _interp_threshold_time(tw[i - 1], tw[i], yw[i - 1], yw[i], threshold)
            for i in rise_locs
        ],
        dtype=float,
    )
    fall_times = np.array(
        [
            _interp_threshold_time(tw[i - 1], tw[i], yw[i - 1], yw[i], threshold)
            for i in fall_locs
        ],
        dtype=float,
    )

    total_time = float(tw[-1] - tw[0])
    if total_time > 0:
        interval_dt = np.diff(tw)
        high_time = float(np.sum(interval_dt[above[:-1]]))
        duty_cycle = high_time / total_time
    else:
        duty_cycle = float("nan")

    closed_widths: list[float] = []
    fall_cursor = 0
    for r_loc, r_time in zip(rise_locs, rise_times):
        while fall_cursor < len(fall_locs) and fall_locs[fall_cursor] <= r_loc:
            fall_cursor += 1
        if fall_cursor >= len(fall_locs):
            break
        width = float(fall_times[fall_cursor] - r_time)
        if width >= 0:
            closed_widths.append(width)
        fall_cursor += 1

    high_at_start = bool(above[0])
    high_at_end = bool(above[-1])
    if high_at_end:
        if len(rise_locs):
            open_start = float(rise_times[-1])
        elif high_at_start:
            open_start = float(tw[0])
        else:
            open_start = float("nan")
        open_duration = float(tw[-1] - open_start) if np.isfinite(open_start) else None
        low_since_fall = None
    else:
        open_duration = None
        if len(fall_times):
            low_since_fall = float(tw[-1] - fall_times[-1])
        elif not high_at_start:
            low_since_fall = total_time
        else:
            low_since_fall = None

    widths = np.asarray(closed_widths, dtype=float)
    if len(widths):
        width_mean = float(np.mean(widths))
        width_median = float(np.median(widths))
        width_max = float(np.max(widths))
        width_min = float(np.min(widths))
    else:
        width_mean = width_median = width_max = width_min = float("nan")

    return {
        "threshold": threshold,
        "analysis_start_s": float(tw[0]),
        "analysis_end_s": float(tw[-1]),
        "duration_s": total_time,
        "high_at_start": high_at_start,
        "high_at_end": high_at_end,
        "state_at_end": "HIGH" if high_at_end else "LOW",
        "rise_count": int(len(rise_times)),
        "fall_count": int(len(fall_times)),
        "last_rise_s": float(rise_times[-1]) if len(rise_times) else None,
        "last_fall_s": float(fall_times[-1]) if len(fall_times) else None,
        "open_high_duration_s": open_duration,
        "low_duration_since_last_fall_s": low_since_fall,
        "duty_cycle": duty_cycle,
        "closed_pulse_count": int(len(widths)),
        "pulse_width_mean_s": width_mean,
        "pulse_width_median_s": width_median,
        "pulse_width_max_s": width_max,
        "pulse_width_min_s": width_min,
    }


def print_reset_window_timing_summary(df: pd.DataFrame, cfg: SimConfig) -> None:
    """Print reset-window timing diagnostics independent of endpoint phase."""
    if "RESET_WINDOW" not in df or df["RESET_WINDOW"].isna().all():
        return

    t = df["time_s"].to_numpy()
    reset = df["RESET_WINDOW"].to_numpy()
    stats = digital_pulse_timing_stats(t, reset, cfg, threshold=1.0)

    print("Reset_Window timing analysis >1 V after ignore:")
    print(f"  State at end = {stats['state_at_end']}")
    duty = stats["duty_cycle"]
    if isinstance(duty, float) and np.isfinite(duty):
        print(f"  Duty cycle after ignore = {100.0 * duty:.6g} %")
    else:
        print("  Duty cycle after ignore = n/a")
    print(f"  Rising edges after ignore = {stats['rise_count']}")
    print(f"  Falling edges after ignore = {stats['fall_count']}")
    print(f"  Last rising edge after ignore = {_fmt_optional_ms(stats['last_rise_s'])}")
    print(f"  Last falling edge after ignore = {_fmt_optional_ms(stats['last_fall_s'])}")

    if stats["high_at_end"]:
        print(f"  Open high pulse at end duration = {_fmt_optional_ms(stats['open_high_duration_s'])}")
    else:
        print(f"  Low time since last falling edge = {_fmt_optional_ms(stats['low_duration_since_last_fall_s'])}")

    if stats["closed_pulse_count"]:
        print(f"  Closed reset pulse count = {stats['closed_pulse_count']}")
        print(f"  Reset pulse width median = {_fmt_optional_ms(stats['pulse_width_median_s'])}")
        print(f"  Reset pulse width mean   = {_fmt_optional_ms(stats['pulse_width_mean_s'])}")
        print(f"  Reset pulse width min    = {_fmt_optional_ms(stats['pulse_width_min_s'])}")
        print(f"  Reset pulse width max    = {_fmt_optional_ms(stats['pulse_width_max_s'])}")
    else:
        print("  Closed reset pulse count = 0")


def print_vdd_power_summary(df: pd.DataFrame, cfg: SimConfig) -> None:
    """Report VDD sag and approximate battery current after startup-ignore."""
    if cfg.supply_mode != "coin" or "VDD" not in df:
        return

    t = df["time_s"].to_numpy()
    mask = analysis_mask(t, cfg)
    if not np.any(mask):
        return

    vdd = df["VDD"].to_numpy()
    vdd_window = vdd[mask]
    vbat = _to_float_suffix(cfg.vbat)
    rbat = _to_float_suffix(cfg.rbat)

    vdd_min = float(np.nanmin(vdd_window))
    vdd_max = float(np.nanmax(vdd_window))
    vdd_end = float(vdd[-1])
    sag = vbat - vdd_min
    i_peak = sag / rbat if rbat > 0 else float("nan")

    print(f"VDD analysis window starts at t = {cfg.ignore_start_ms:g} ms")
    print(f"VDD min after ignore = {vdd_min:.6g} V")
    print(f"VDD max after ignore = {vdd_max:.6g} V")
    print(f"VDD end              = {vdd_end:.6g} V")
    print(f"VDD sag from Vbat    = {sag:.6g} V")
    print(f"Approx peak battery current after ignore = {i_peak * 1e3:.6g} mA")


def print_event_summary(df: pd.DataFrame, cfg: SimConfig) -> None:
    t = df["time_s"].to_numpy()
    mask = analysis_mask(t, cfg)

    if cfg.ignore_start_ms > 0:
        print(f"Event analysis ignores t < {cfg.ignore_start_ms:g} ms.")

    if "VM" in df and "VTHRESH" in df and not df["VTHRESH"].isna().all():
        vm = df["VM"].to_numpy()
        vth = df["VTHRESH"].to_numpy()

        raw_count = count_rising_edges(vm - vth, 0.0)
        filtered_count = crossing_count_after_mask(t, vm, vth, cfg)
        print(f"Raw threshold crossing count = {raw_count}")
        print(f"Threshold crossing count after ignore = {filtered_count}")

        raw_i = first_crossing_index(vm, vth)
        filtered_i = first_crossing_index(vm, vth, mask)

        if raw_i is not None:
            print(f"Raw first Vm_Int >= V_Threshold at t = {t[raw_i] * 1e3:.6g} ms")
            print(f"Raw Vm_Int at crossing       = {vm[raw_i]:.6g} V")
            print(f"Raw V_Threshold at crossing  = {vth[raw_i]:.6g} V")
        else:
            print("Raw Vm_Int never crossed V_Threshold.")

        if cfg.ignore_start_ms > 0:
            if filtered_i is not None:
                print(f"First Vm_Int >= V_Threshold after ignore at t = {t[filtered_i] * 1e3:.6g} ms")
                print(f"Vm_Int at crossing after ignore       = {vm[filtered_i]:.6g} V")
                print(f"V_Threshold at crossing after ignore  = {vth[filtered_i]:.6g} V")
            else:
                print("Vm_Int never crossed V_Threshold after ignore.")

    if "SPIKE_PULSE" in df:
        spike = df["SPIKE_PULSE"].to_numpy()
        print(f"Raw Spike_Pulse rising-edge count >1 V = {count_rising_edges(spike, 1.0)}")
        print(f"Spike_Pulse rising-edge count >1 V after ignore = {edge_count_after_mask(t, spike, 1.0, cfg)}")

    if "RESET_WINDOW" in df:
        reset = df["RESET_WINDOW"].to_numpy()
        print(f"Raw Reset_Window rising-edge count >1 V = {count_rising_edges(reset, 1.0)}")
        print(f"Reset_Window rising-edge count >1 V after ignore = {edge_count_after_mask(t, reset, 1.0, cfg)}")
        print_reset_window_timing_summary(df, cfg)

    print_vdd_power_summary(df, cfg)


def print_diagnostics(df: pd.DataFrame, cfg: SimConfig) -> None:
    """Print diagnostics for exactly the same traces that are plotted."""
    traces = traces_for_config(cfg)
    t = df["time_s"].to_numpy()

    for trace in traces:
        print_node_summary(df, trace.key, trace.label, t)

    print_event_summary(df, cfg)


# -----------------------------------------------------------------------------
# Sweep helpers
# -----------------------------------------------------------------------------


def parse_float_list(text: str) -> list[float]:
    values = []
    for item in text.split(","):
        item = item.strip()
        if item:
            values.append(float(item))
    if not values:
        raise ValueError(f"Empty sweep list: {text!r}")
    return values


def parse_string_list(text: str) -> list[str]:
    values = [item.strip() for item in text.split(",") if item.strip()]
    if not values:
        raise ValueError(f"Empty sweep list: {text!r}")
    return values


def summarise_run(df: pd.DataFrame, cfg: SimConfig, run_index: int, csv_path: Path, png_path: Path) -> dict[str, object]:
    t = df["time_s"].to_numpy()
    mask = analysis_mask(t, cfg)

    vm = df["VM"].to_numpy() if "VM" in df else np.array([])
    vm_ext = df["VM_EXT"].to_numpy() if "VM_EXT" in df else np.array([])
    vth = df["VTHRESH"].to_numpy() if "VTHRESH" in df else np.full_like(t, np.nan)
    spike = df["SPIKE_PULSE"].to_numpy() if "SPIKE_PULSE" in df else np.full_like(t, np.nan)
    reset = df["RESET_WINDOW"].to_numpy() if "RESET_WINDOW" in df else np.full_like(t, np.nan)
    vw = df["VW"].to_numpy() if "VW" in df else np.full_like(t, np.nan)
    vdd = df["VDD"].to_numpy() if "VDD" in df else np.full_like(t, np.nan)

    raw_crossing_count = count_rising_edges(vm - vth, 0.0) if len(vm) and len(vth) else 0
    filtered_crossing_count = crossing_count_after_mask(t, vm, vth, cfg) if len(vm) and len(vth) else 0

    raw_i = first_crossing_index(vm, vth) if len(vm) and len(vth) else None
    filtered_i = first_crossing_index(vm, vth, mask) if len(vm) and len(vth) else None

    raw_crossing_ms = float(t[raw_i] * 1e3) if raw_i is not None else float("nan")
    filtered_crossing_ms = float(t[filtered_i] * 1e3) if filtered_i is not None else float("nan")

    if len(vdd) and np.any(mask) and not np.all(np.isnan(vdd)):
        vdd_window = vdd[mask]
        vdd_min_after_ignore = float(np.nanmin(vdd_window))
        vdd_max_after_ignore = float(np.nanmax(vdd_window))
        if cfg.supply_mode == "coin":
            vbat = _to_float_suffix(cfg.vbat)
            rbat = _to_float_suffix(cfg.rbat)
            vdd_sag_after_ignore = vbat - vdd_min_after_ignore
            approx_i_mA_after_ignore = (vdd_sag_after_ignore / rbat * 1e3) if rbat > 0 else np.nan
        else:
            vdd_sag_after_ignore = np.nan
            approx_i_mA_after_ignore = np.nan
    else:
        vdd_min_after_ignore = np.nan
        vdd_max_after_ignore = np.nan
        vdd_sag_after_ignore = np.nan
        approx_i_mA_after_ignore = np.nan

    if len(reset) and not np.all(np.isnan(reset)):
        reset_stats = digital_pulse_timing_stats(t, reset, cfg, threshold=1.0)
    else:
        reset_stats = digital_pulse_timing_stats(t, np.full_like(t, np.nan), cfg, threshold=1.0)

    return {
        "run": run_index,
        "stage": cfg.stage,
        "startup_mode": cfg.startup_mode,
        "ignore_start_ms": cfg.ignore_start_ms,
        "rv1": cfg.rv1_fraction,
        "rv2": cfg.rv2_fraction,
        "rv3": cfg.rv3_fraction,
        "rv4": cfg.rv4_fraction,
        "cmem_mode": cfg.cmem_mode,
        "selected_cmem": selected_cmem(cfg),
        "vdd": cfg.vdd,
        "supply_mode": cfg.supply_mode,
        "vbat": cfg.vbat,
        "rbat": cfg.rbat,
        "tol_mode": cfg.tol_mode,
        "tol_seed": cfg.tol_seed,
        "res_tol_pct": cfg.res_tol_pct,
        "cap_tol_pct": cfg.cap_tol_pct,
        "pot_tol_pct": cfg.pot_tol_pct,
        "raw_first_cross_ms": raw_crossing_ms,
        "first_cross_ms_after_ignore": filtered_crossing_ms,
        "raw_crossing_count": raw_crossing_count,
        "crossing_count_after_ignore": filtered_crossing_count,
        "raw_spike_count_gt_1v": count_rising_edges(spike, 1.0) if len(spike) else 0,
        "spike_count_gt_1v_after_ignore": edge_count_after_mask(t, spike, 1.0, cfg) if len(spike) else 0,
        "raw_reset_count_gt_1v": count_rising_edges(reset, 1.0) if len(reset) else 0,
        "reset_count_gt_1v_after_ignore": edge_count_after_mask(t, reset, 1.0, cfg) if len(reset) else 0,
        "vm_int_min": float(np.nanmin(vm)) if len(vm) else np.nan,
        "vm_int_max": float(np.nanmax(vm)) if len(vm) else np.nan,
        "vm_int_end": float(vm[-1]) if len(vm) else np.nan,
        "vm_ext_min": float(np.nanmin(vm_ext)) if len(vm_ext) else np.nan,
        "vm_ext_max": float(np.nanmax(vm_ext)) if len(vm_ext) else np.nan,
        "vm_ext_end": float(vm_ext[-1]) if len(vm_ext) else np.nan,
        "vthreshold_min": float(np.nanmin(vth)) if len(vth) else np.nan,
        "vthreshold_max": float(np.nanmax(vth)) if len(vth) else np.nan,
        "spike_pulse_min": float(np.nanmin(spike)) if len(spike) else np.nan,
        "spike_pulse_max": float(np.nanmax(spike)) if len(spike) else np.nan,
        "reset_window_max": float(np.nanmax(reset)) if len(reset) else np.nan,
        "reset_window_end_high_gt_1v": bool(reset_stats["high_at_end"]),
        "reset_window_duty_cycle_after_ignore": reset_stats["duty_cycle"],
        "reset_window_last_rise_ms_after_ignore": (
            float(reset_stats["last_rise_s"] * 1e3) if reset_stats["last_rise_s"] is not None else np.nan
        ),
        "reset_window_last_fall_ms_after_ignore": (
            float(reset_stats["last_fall_s"] * 1e3) if reset_stats["last_fall_s"] is not None else np.nan
        ),
        "reset_window_open_high_duration_ms_at_end": (
            float(reset_stats["open_high_duration_s"] * 1e3)
            if reset_stats["open_high_duration_s"] is not None
            else np.nan
        ),
        "reset_window_low_duration_ms_since_last_fall": (
            float(reset_stats["low_duration_since_last_fall_s"] * 1e3)
            if reset_stats["low_duration_since_last_fall_s"] is not None
            else np.nan
        ),
        "reset_window_closed_pulse_count_after_ignore": reset_stats["closed_pulse_count"],
        "reset_window_pulse_width_median_ms_after_ignore": reset_stats["pulse_width_median_s"] * 1e3,
        "reset_window_pulse_width_mean_ms_after_ignore": reset_stats["pulse_width_mean_s"] * 1e3,
        "reset_window_pulse_width_max_ms_after_ignore": reset_stats["pulse_width_max_s"] * 1e3,
        "reset_window_pulse_width_min_ms_after_ignore": reset_stats["pulse_width_min_s"] * 1e3,
        "vw_max": float(np.nanmax(vw)) if len(vw) else np.nan,
        "vdd_min_after_ignore": vdd_min_after_ignore,
        "vdd_max_after_ignore": vdd_max_after_ignore,
        "vdd_sag_after_ignore": vdd_sag_after_ignore,
        "approx_peak_battery_current_mA_after_ignore": approx_i_mA_after_ignore,
        "plot": str(png_path),
        "csv": str(csv_path),
    }


def run_sweep(cfg: SimConfig) -> int:
    rv1_values = parse_float_list(cfg.sweep_rv1)
    rv2_values = parse_float_list(cfg.sweep_rv2)
    rv3_values = parse_float_list(cfg.sweep_rv3)
    rv4_values = parse_float_list(cfg.sweep_rv4) if cfg.sweep_rv4.strip() else [cfg.rv4_fraction]
    vbat_values = parse_string_list(cfg.sweep_vbat) if cfg.sweep_vbat.strip() else [cfg.vbat]
    rbat_values = parse_string_list(cfg.sweep_rbat) if cfg.sweep_rbat.strip() else [cfg.rbat]

    # Keep sweep paths short. Long Windows paths can make ngspice fail before it
    # writes a useful log file, especially when the run name repeats every
    # parameter value. The detailed per-run metadata is still stored in
    # sweep_summary.csv.
    if cfg.supply_mode == "coin":
        sweep_dir = OUTPUT_DIR / "sweep" / f"{cfg.stage}_{cfg.trace_set}_{cfg.startup_mode}_coin"
    else:
        sweep_dir = OUTPUT_DIR / "sweep" / f"{cfg.stage}_{cfg.trace_set}_{cfg.startup_mode}_ideal"

    if cfg.tol_mode == "random":
        sweep_dir = sweep_dir / f"tol{cfg.tol_seed}"

    sweep_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []
    all_rows: list[pd.DataFrame] = []
    run_index = 0

    for rv1 in rv1_values:
        for rv2 in rv2_values:
            for rv3 in rv3_values:
                for rv4 in rv4_values:
                    for vbat in vbat_values:
                        for rbat in rbat_values:
                            run_index += 1
                            run_cfg = dataclasses.replace(
                                cfg,
                                sweep=False,
                                rv1_fraction=rv1,
                                rv2_fraction=rv2,
                                rv3_fraction=rv3,
                                rv4_fraction=rv4,
                                vbat=vbat,
                                rbat=rbat,
                            )

                            run_name = (
                                f"r{run_index:03d}"
                                f"_r1{short_num(rv1)}"
                                f"_r2{short_num(rv2)}"
                                f"_r3{short_num(rv3)}"
                                f"_r4{short_num(rv4)}"
                            )
                            if run_cfg.supply_mode == "coin":
                                run_name += f"_vb{short_num(run_cfg.vbat)}_rb{short_num(run_cfg.rbat)}"
                            else:
                                run_name += f"_vdd{short_num(run_cfg.vdd)}"
                            if run_cfg.tol_mode == "random":
                                run_name += f"_tol{run_cfg.tol_seed}"
                            run_name += f"_c{safe_tag(selected_cmem(run_cfg))}"

                            deck_path = sweep_dir / f"{run_name}.cir"
                            csv_path = sweep_dir / f"{run_name}.csv"
                            png_path = sweep_dir / f"{run_name}.png"
                            vm_png_path = sweep_dir / f"{run_name}_vmint_vmext.png"

                            for path in (deck_path, csv_path, png_path, vm_png_path):
                                if len(str(path)) > 240:
                                    print(f"WARNING: long path may fail on Windows/ngspice: {len(str(path))} chars")
                                    print(path)

                            print("")
                            print("=" * 80)
                            print(
                                f"Sweep run {run_index}: "
                                f"RV1={rv1:.3f}, RV2={rv2:.3f}, RV3={rv3:.3f}, RV4={rv4:.3f}, "
                                f"Cmem={selected_cmem(run_cfg)}, supply={run_cfg.supply_mode}, "
                                f"Vbat={vbat}, Rbat={rbat}"
                            )
                            print("=" * 80)

                            deck = build_spice_deck(
                                run_cfg,
                                for_cli=(run_cfg.backend == "ngspice-cli"),
                                csv_path=csv_path,
                            )
                            deck_path.write_text(deck)

                            if run_cfg.backend == "pyspice":
                                df = run_with_pyspice(deck_path, run_cfg)
                            else:
                                df = run_with_ngspice_cli(deck_path, csv_path, run_cfg)

                            df.to_csv(csv_path, index=False)
                            plot_results(df, run_cfg, png_path)
                            plot_vm_only(df, run_cfg, vm_png_path)

                            df_meta = df.copy()
                            df_meta.insert(0, "run", run_index)
                            df_meta.insert(1, "rv1", rv1)
                            df_meta.insert(2, "rv2", rv2)
                            df_meta.insert(3, "rv3", rv3)
                            df_meta.insert(4, "rv4", rv4)
                            df_meta.insert(5, "selected_cmem", selected_cmem(run_cfg))
                            df_meta.insert(6, "startup_mode", run_cfg.startup_mode)
                            df_meta.insert(7, "ignore_start_ms", run_cfg.ignore_start_ms)
                            df_meta.insert(8, "vbat", vbat)
                            df_meta.insert(9, "rbat", rbat)
                            all_rows.append(df_meta)

                            summary_row = summarise_run(df, run_cfg, run_index, csv_path, png_path)
                            summary_row["vm_only_plot"] = str(vm_png_path)
                            summary_rows.append(summary_row)

    summary = pd.DataFrame(summary_rows)
    summary_path = sweep_dir / "sweep_summary.csv"
    summary.to_csv(summary_path, index=False)

    combined_path = sweep_dir / "sweep_all_traces.csv"
    pd.concat(all_rows, ignore_index=True).to_csv(combined_path, index=False)

    print("")
    print("=" * 80)
    print("Sweep complete")
    print(f"Summary CSV:       {summary_path}")
    print(f"Combined traces:   {combined_path}")
    print("=" * 80)

    return 0


# -----------------------------------------------------------------------------
# Results text logging
# -----------------------------------------------------------------------------


class TeeTextIO:
    """Write text to multiple streams."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


@contextlib.contextmanager
def tee_stdout(path: Path):
    """Duplicate stdout to a results text file for reproducible validation logs."""
    old_stdout = sys.stdout
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        sys.stdout = TeeTextIO(old_stdout, handle)
        try:
            yield
        finally:
            sys.stdout = old_stdout


# -----------------------------------------------------------------------------
# Command line
# -----------------------------------------------------------------------------


def parse_args(argv: list[str]) -> SimConfig:
    p = argparse.ArgumentParser(description="Simulate the LIFeling Vm-relevant circuit with ngspice/PySpice.")

    p.add_argument("--stage", choices=["passive", "threshold", "threshold_reset", "threshold_reset_adapt"], default="passive")
    p.add_argument("--strict-vendor", action="store_true", help="Require external vendor model files in ./models/.")
    p.add_argument("--backend", choices=["pyspice", "ngspice-cli"], default="ngspice-cli")
    p.add_argument("--ngspice-binary", default="auto", help="Path to ngspice.exe, or 'auto' to search PATH/common Windows locations.")

    p.add_argument("--vdd", default="3", help="Ideal-supply voltage, e.g. 3, 3.3, or 2.7")
    p.add_argument("--supply-mode", choices=["ideal", "coin"], default="ideal", help="ideal = ideal VDD source; coin = VBAT -> Rbat -> VDD with local decoupling")
    p.add_argument("--vbat", default="3", help="Coin-cell open-circuit/source voltage used with --supply-mode coin")
    p.add_argument("--rbat", default="30", help="Coin-cell series/internal resistance in ohms used with --supply-mode coin")
    p.add_argument("--cdec-local", default="100n", help="Local IC bypass capacitance on VDD")
    p.add_argument("--cdec-bulk", default="10u", help="Board-level bulk capacitance on VDD")
    p.add_argument("--cdec-reservoir", default="47u", help="Optional reservoir capacitance on VDD")
    p.add_argument("--cdec-esr", default="0.2", help="Series ESR applied to each VDD decoupling capacitor")
    p.add_argument(
        "--startup-mode",
        choices=["operating", "cold"],
        default="operating",
        help="operating = precharged VDD/reset timer for normal behaviour; cold = discharged startup test",
    )
    p.add_argument(
        "--ignore-start-ms",
        type=float,
        default=0.0,
        help="Ignore this initial time window when reporting event counts/crossings and VDD sag.",
    )
    p.add_argument(
        "--cold-vm-initial",
        default="0",
        help="Vm_Int initial condition used only with --startup-mode cold.",
    )

    p.add_argument("--tol-mode", choices=["nominal", "random"], default="nominal", help="Apply deterministic random component tolerances")
    p.add_argument("--tol-seed", type=int, default=1, help="Seed for deterministic random tolerance factors")
    p.add_argument("--res-tol-pct", type=float, default=0.0, help="Uniform resistor tolerance, +/-percent")
    p.add_argument("--cap-tol-pct", type=float, default=0.0, help="Uniform capacitor tolerance, +/-percent")
    p.add_argument("--pot-tol-pct", type=float, default=0.0, help="Pot total/wiper tolerance, +/-percent of value/full-scale travel")
    p.add_argument("--rv1", type=float, default=0.5, help="RV1 wiper fraction, 0..1; pin1=GNDREF, pin3=V_Leak_Ref_Max")
    p.add_argument("--rv2", type=float, default=0.5, help="RV2 wiper fraction, 0..1; pin1=R32 node, pin2=Vm_Int, pin3=V_Leak")
    p.add_argument("--rv3", type=float, default=0.5, help="RV3 wiper fraction, 0..1; pins1/2=Vw, pin3=R42 node")
    p.add_argument("--rv4", type=float, default=0.5, help="RV4 Cm selector fraction, 0..1")

    p.add_argument("--cmem-mode", choices=["manual", "rv4"], default="manual")
    p.add_argument("--cmem", default="2.2u", help="Manual membrane capacitor, e.g. 470n, 1u, 2.2u, 4.7u, 10u")
    p.add_argument("--vm-initial", default="0.385")

    p.add_argument("--tstop", default="1", help="Transient stop time, seconds by default")
    p.add_argument("--tstep", default="10u")
    p.add_argument("--maxstep", default="10u")

    p.add_argument("--probe", choices=["ideal", "scope10m", "probe1m"], default="ideal")
    p.add_argument("--trace-set", choices=["core", "debug"], default="core", help="core = readable circuit traces; debug = include internal transistor/MOSFET nodes")
    p.add_argument("--stim-dc", type=float, default=None, help="Optional DC source at J1 pin2 / Stimulus_Ext")

    p.add_argument("--syn1-enable", action="store_true", help="Enable Syn1 spike-gated synaptic input model.")
    p.add_argument("--syn2-enable", action="store_true", help="Enable Syn2 spike-gated synaptic input model.")
    p.add_argument("--syn3-enable", action="store_true", help="Enable Syn3 spike-gated synaptic input model.")
    p.add_argument("--syn4-enable", action="store_true", help="Enable Syn4 spike-gated synaptic input model.")
    p.add_argument("--syn-all-enable", action="store_true", help="Enable all four synaptic input models.")
    p.add_argument(
        "--syn-ref-mode",
        choices=["schematic", "legacy_direct", "buffered"],
        default="schematic",
        help="schematic = current KiCad R4/R5 raw node -> U2A buffer -> V_Leak_Ref_Max -> RV1/RV6-RV9; legacy_direct = old raw-node comparison; buffered = deprecated alias of schematic",
    )
    p.add_argument("--rv5", type=float, default=0.5, help="RV5 synaptic-state decay fraction, 0..1; pins1/2=decay node, pin3=V_Leak")
    p.add_argument("--rv6", type=float, default=0.5, help="RV6 Syn1 set-voltage fraction, 0..1")
    p.add_argument("--rv7", type=float, default=0.5, help="RV7 Syn2 set-voltage fraction, 0..1")
    p.add_argument("--rv8", type=float, default=0.5, help="RV8 Syn3 set-voltage fraction, 0..1")
    p.add_argument("--rv9", type=float, default=0.5, help="RV9 Syn4 set-voltage fraction, 0..1")
    p.add_argument("--syn-amp", default="3", help="Synaptic input pulse high voltage")
    p.add_argument("--syn-rise", default="1u", help="Synaptic input pulse rise time")
    p.add_argument("--syn-fall", default="1u", help="Synaptic input pulse fall time")
    p.add_argument("--syn1-delay", default="80m")
    p.add_argument("--syn1-width", default="5m")
    p.add_argument("--syn1-period", default="100m")
    p.add_argument("--syn2-delay", default="120m")
    p.add_argument("--syn2-width", default="5m")
    p.add_argument("--syn2-period", default="100m")
    p.add_argument("--syn3-delay", default="160m")
    p.add_argument("--syn3-width", default="5m")
    p.add_argument("--syn3-period", default="100m")
    p.add_argument("--syn4-delay", default="200m")
    p.add_argument("--syn4-width", default="5m")
    p.add_argument("--syn4-period", default="100m")

    p.add_argument("--sweep", action="store_true", help="Run an RV parameter sweep.")
    p.add_argument("--sweep-rv1", default="0.3,0.5,0.7,1.0")
    p.add_argument("--sweep-rv2", default="0.2,0.5,0.8")
    p.add_argument("--sweep-rv3", default="0.2,0.5,0.8")
    p.add_argument("--sweep-rv4", default="", help="Optional RV4 sweep list. Empty means use --rv4 only.")
    p.add_argument("--sweep-vbat", default="", help="Optional coin-cell voltage sweep list. Empty means use --vbat only.")
    p.add_argument("--sweep-rbat", default="", help="Optional coin-cell resistance sweep list. Empty means use --rbat only.")

    ns = p.parse_args(argv)
    return SimConfig(
        stage=ns.stage,
        strict_vendor=ns.strict_vendor,
        vdd=ns.vdd,
        supply_mode=ns.supply_mode,
        vbat=ns.vbat,
        rbat=ns.rbat,
        cdec_local=ns.cdec_local,
        cdec_bulk=ns.cdec_bulk,
        cdec_reservoir=ns.cdec_reservoir,
        cdec_esr=ns.cdec_esr,
        startup_mode=ns.startup_mode,
        ignore_start_ms=ns.ignore_start_ms,
        cold_vm_initial=ns.cold_vm_initial,
        tol_mode=ns.tol_mode,
        tol_seed=ns.tol_seed,
        res_tol_pct=ns.res_tol_pct,
        cap_tol_pct=ns.cap_tol_pct,
        pot_tol_pct=ns.pot_tol_pct,
        rv1_fraction=ns.rv1,
        rv2_fraction=ns.rv2,
        rv3_fraction=ns.rv3,
        rv4_fraction=ns.rv4,
        cmem_mode=ns.cmem_mode,
        cmem=ns.cmem,
        vm_initial=ns.vm_initial,
        tstop=ns.tstop,
        tstep=ns.tstep,
        maxstep=ns.maxstep,
        probe=ns.probe,
        trace_set=ns.trace_set,
        stim_dc=ns.stim_dc,
        syn_ref_mode=ns.syn_ref_mode,
        syn1_enable=ns.syn1_enable or ns.syn_all_enable,
        syn2_enable=ns.syn2_enable or ns.syn_all_enable,
        syn3_enable=ns.syn3_enable or ns.syn_all_enable,
        syn4_enable=ns.syn4_enable or ns.syn_all_enable,
        rv5_fraction=ns.rv5,
        rv6_fraction=ns.rv6,
        rv7_fraction=ns.rv7,
        rv8_fraction=ns.rv8,
        rv9_fraction=ns.rv9,
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
        backend=ns.backend,
        ngspice_binary=ns.ngspice_binary,
        sweep=ns.sweep,
        sweep_rv1=ns.sweep_rv1,
        sweep_rv2=ns.sweep_rv2,
        sweep_rv3=ns.sweep_rv3,
        sweep_rv4=ns.sweep_rv4,
        sweep_vbat=ns.sweep_vbat,
        sweep_rbat=ns.sweep_rbat,
    )


def print_run_header(cfg: SimConfig, deck_path: Path) -> None:
    print(f"Wrote SPICE deck: {deck_path}")
    print(f"Stage:          {cfg.stage}")
    print(f"Backend:        {cfg.backend}")
    print(f"Strict vendor:  {cfg.strict_vendor}")
    print(f"Trace set:      {cfg.trace_set}")
    print(f"Supply mode:    {cfg.supply_mode}")
    if cfg.supply_mode == "coin":
        print(f"Vbat/Rbat:      {cfg.vbat} V / {cfg.rbat} ohm")
        print(f"VDD decoupling: {cfg.cdec_local} + {cfg.cdec_bulk} + {cfg.cdec_reservoir}, ESR={cfg.cdec_esr} ohm")
    else:
        print(f"Ideal VDD:      {cfg.vdd} V")
    print(f"Startup mode:   {cfg.startup_mode}")
    print(f"Ignore start:   {cfg.ignore_start_ms:g} ms")
    if cfg.startup_mode == "cold":
        print(f"Cold Vm IC:      {cfg.cold_vm_initial} V")
    print(f"Tolerance mode: {cfg.tol_mode}")
    if cfg.tol_mode == "random":
        print(f"Tolerance seed: {cfg.tol_seed}")
        print(f"Tolerances:     R=+/-{cfg.res_tol_pct}% C=+/-{cfg.cap_tol_pct}% pot=+/-{cfg.pot_tol_pct}%")
        print(
            f"Effective RVs:  RV1={effective_pot_fraction(cfg, 'RV1', cfg.rv1_fraction):.3f} / "
            f"RV2={effective_pot_fraction(cfg, 'RV2', cfg.rv2_fraction):.3f} / "
            f"RV3={effective_pot_fraction(cfg, 'RV3', cfg.rv3_fraction):.3f} / "
            f"RV4={effective_pot_fraction(cfg, 'RV4', cfg.rv4_fraction):.3f}"
        )
    print(f"RV1/RV2/RV3:    {cfg.rv1_fraction:.3f} / {cfg.rv2_fraction:.3f} / {cfg.rv3_fraction:.3f}")
    print(f"Cmem mode:      {cfg.cmem_mode}")
    print("Leak ref path:  R4/R5 -> V_Leak_Ref_Max_Raw -> U2A buffer -> V_Leak_Ref_Max")
    print("Peak path:      R8/R9 -> V_Peak_Ref -> U2C buffer -> R49/U14 -> Vm_Int")
    print("Live Vm output: Vm_Int -> R90/C38 Vm_Display_In + V_Peak_Drive/R91/U20 display spike -> U8/R1/C14 -> Vm_Ext")
    if synapse_enabled(cfg):
        print(f"Syn ref mode:   {cfg.syn_ref_mode}")
        if cfg.syn_ref_mode == "legacy_direct":
            print("Syn set refs:   RV6/RV7/RV8/RV9 pin3 use raw V_Leak_Ref_Max_Raw (comparison mode)")
        else:
            print("Syn set refs:   RV6/RV7/RV8/RV9 pin3 use buffered V_Leak_Ref_Max")
        print("Syn state path: U2D follower model V_Syn_State -> V_Syn_Drive -> R80 -> Vm_Int")
        print("Syn timing:")
        for idx, delay, width, period in enabled_synapse_timing(cfg):
            print(f"  - Syn{idx}: delay={delay}, width={width}, period={period}")
        print("KiCad check:    U2D is now consistent: pin12=+, pins13/14=feedback/output")
    print(f"RV4 fraction:   {cfg.rv4_fraction:.3f}")
    print(f"Selected Cmem:  {selected_cmem(cfg)}")
    print("Saved/plotted/printed compact visualisation traces:")
    for trace in traces_for_config(cfg):
        print(f"  - {trace.key}: {trace.label} [{trace.node}]")


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if cfg.sweep:
        return run_sweep(cfg)

    suffix = output_suffix(cfg)
    deck_path = OUTPUT_DIR / f"LIFeling_vm_{suffix}.cir"
    csv_path = OUTPUT_DIR / f"LIFeling_vm_{suffix}.csv"
    png_path = OUTPUT_DIR / f"LIFeling_vm_{suffix}.png"
    vm_png_path = OUTPUT_DIR / f"LIFeling_vm_{suffix}_vmint_vmext.png"
    results_path = OUTPUT_DIR / f"LIFeling_vm_{suffix}_results.txt"

    for path in (deck_path, csv_path, png_path, vm_png_path, results_path):
        if len(str(path)) > 240:
            print(f"WARNING: long path may fail on Windows/ngspice: {len(str(path))} chars")
            print(path)

    deck = build_spice_deck(cfg, for_cli=(cfg.backend == "ngspice-cli"), csv_path=csv_path)
    deck_path.write_text(deck)

    with tee_stdout(results_path):
        print(f"Results text file: {results_path}")
        print_run_header(cfg, deck_path)

        if cfg.backend == "pyspice":
            df = run_with_pyspice(deck_path, cfg)
        else:
            df = run_with_ngspice_cli(deck_path, csv_path, cfg)

        # Save the same compact visualisation/validation traces that are plotted
        # and printed. The detailed debug narrative is kept in *_results.txt.
        df.to_csv(csv_path, index=False)
        plot_results(df, cfg, png_path)
        plot_vm_only(df, cfg, vm_png_path)

        print(f"Wrote CSV:              {csv_path}")
        print(f"Wrote multi-trace plot: {png_path}")
        print(f"Wrote Vm_Int/Vm_Ext plot: {vm_png_path}")
        print(f"Wrote results text:     {results_path}")
        print_diagnostics(df, cfg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
