"""Static source, connectivity, pin-map, and coverage audits."""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .design import Component, Design
from .models import FamilyResolution, family_for_component, sha256_file


@dataclasses.dataclass
class AuditFinding:
    identifier: str
    severity: str
    passed: bool
    summary: str
    evidence: str


TLV7044_PIN_FUNCTIONS = {
    "1": "OUTA", "2": "INA-", "3": "INA+", "4": "VDD",
    "5": "INB+", "6": "INB-", "7": "OUTB", "8": "OUTC",
    "9": "INC-", "10": "INC+", "11": "GND", "12": "IND+",
    "13": "IND-", "14": "OUTD",
}


def file_manifest(paths: list[tuple], *, repository_commit: str, simulation_date: str, ngspice_version: str = "not executed") -> list[dict[str, Any]]:
    """Build a provenance manifest.

    Each input is ``(path, source_type)`` or ``(path, source_type, original_name)``.
    The optional original name preserves the user's uploaded filename even when a
    source was renamed inside the reconstruction package to avoid clashing with
    the newly generated implementation.
    """
    rows: list[dict[str, Any]] = []
    for item in paths:
        if len(item) == 2:
            path, source_type = item
            original_name = Path(path).name
        elif len(item) == 3:
            path, source_type, original_name = item
        else:
            raise ValueError(f"Invalid manifest source tuple: {item!r}")
        path = Path(path)
        stat = path.stat()
        rows.append({
            "file_name": str(original_name),
            "packaged_path": str(path),
            "path": str(path),
            "sha256": sha256_file(path),
            "size_bytes": stat.st_size,
            "source_type": source_type,
            "export_date": "",
            "repository_commit": repository_commit,
            "model_version": __version__,
            "simulation_date": simulation_date,
            "ngspice_version": ngspice_version,
            "python_version": platform.python_version(),
            "operating_system": platform.platform(),
            "mtime_utc": __import__("datetime").datetime.fromtimestamp(stat.st_mtime, tz=__import__("datetime").timezone.utc).isoformat(),
        })
    return rows


def _pin_function_ok(component: Component, pin: str, expected: str) -> bool:
    actual = component.pins.get(pin)
    if actual is None:
        return False
    normalized = actual.function.upper().replace("−", "-").replace("_", "")
    expected_n = expected.upper().replace("−", "-").replace("_", "")
    aliases = {
        "VDD": ("VDD", "VCC", "V+"),
        "GND": ("GND", "VEE", "VSS", "V-"),
    }.get(expected_n, (expected_n,))
    return any(normalized.startswith(alias) for alias in aliases)


def _net_nodes(design: Design, net: str) -> set[tuple[str, str]]:
    output: set[tuple[str, str]] = set()
    for reference, component in design.components.items():
        for pin, connection in component.pins.items():
            if connection.net == net:
                output.add((reference, pin))
    return output


def _connected_between(component: Component, net_a: str, net_b: str) -> bool:
    nets = {pin.net for pin in component.pins.values()}
    return {net_a, net_b}.issubset(nets)


def run_topology_audit(design: Design) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    # TLV7044 package pins.
    for ref in ("U4", "U5", "U6"):
        component = design.require_component(ref)
        failed = [f"{pin}:{expected}" for pin, expected in TLV7044_PIN_FUNCTIONS.items() if not _pin_function_ok(component, pin, expected)]
        findings.append(AuditFinding(
            f"pinmap.{ref}.tlv7044", "error", not failed,
            f"{ref} uses the corrected TLV7044 PW-14 physical pin order.",
            "All 14 physical pin functions match." if not failed else "Mismatches: " + ", ".join(failed),
        ))

    # Package-level physical pin maps for every other modelled IC family.
    package_maps = [
        ("mcp6004", ("U1", "U2", "U3"), {"1":"VOUTA","2":"VINA-","3":"VINA+","4":"VDD","5":"VINB+","6":"VINB-","7":"VOUTB","8":"VOUTC","9":"VINC-","10":"VINC+","11":"GND","12":"VIND+","13":"VIND-","14":"VOUTD"}),
        ("tlv9001", ("U8", "U22"), {"1":"OUT","2":"GND","3":"IN+","4":"IN-","5":"VDD"}),
        ("tlv9041", ("U23",), {"1":"OUT","2":"GND","3":"IN+","4":"IN-","5":"VDD"}),
        ("tlv7031", ("U19",), {"1":"OUT","2":"GND","3":"IN+","4":"IN-","5":"VDD"}),
        ("ts5a3166", tuple(f"U{i}" for i in range(9,19)) + ("U20",), {"1":"NO","2":"COM","3":"GND","4":"IN","5":"VDD"}),
        ("tps610995", ("U7",), {"1":"GND","2":"VOUT","3":"FB","4":"EN","5":"SW","6":"VIN","7":"POWERPAD"}),
    ]
    for family, refs, expected_map in package_maps:
        failed = []
        for ref in refs:
            component = design.require_component(ref)
            for pin, expected in expected_map.items():
                if not _pin_function_ok(component, pin, expected):
                    actual = component.pins.get(pin).function if pin in component.pins else "missing"
                    failed.append(f"{ref}.{pin}: expected {expected}, found {actual}")
        findings.append(AuditFinding(
            f"pinmap.family.{family}", "error", not failed,
            f"{family.upper()} physical package pins match the approved package map for {', '.join(refs)}.",
            "All physical pin functions match." if not failed else "; ".join(failed),
        ))

    # RV4 selector truth table, explicitly derived from physical comparator pins/nets.
    expected_channels = {
        "U4A": ("S0", "T1", "Vsel"),
        "U4B": ("S1", "Vsel", "T1"),
        "U4C": ("S1", "T2", "Vsel"),
        "U4D": ("S4", "Vsel", "T4"),
        "U5A": ("S2", "Vsel", "T2"),
        "U5B": ("S2", "T3", "Vsel"),
        "U5C": ("S3", "Vsel", "T3"),
        "U5D": ("S3", "T4", "Vsel"),
    }
    channel_pins = {
        "A": ("1", "3", "2"), "B": ("7", "5", "6"),
        "C": ("8", "10", "9"), "D": ("14", "12", "13"),
    }
    failures: list[str] = []
    for name, (out_net, plus_net, minus_net) in expected_channels.items():
        ref, channel = name[:2], name[-1]
        out_pin, plus_pin, minus_pin = channel_pins[channel]
        comp = design.require_component(ref)
        actual = (comp.net(out_pin), comp.net(plus_pin), comp.net(minus_pin))
        if actual != (out_net, plus_net, minus_net):
            failures.append(f"{name} expected {(out_net, plus_net, minus_net)}, got {actual}")
    findings.append(AuditFinding(
        "topology.rv4.comparators", "error", not failures,
        "RV4 selector comparator polarity is derived from physical pins and forms the intended five windows.",
        "Physical comparator channels match the one-hot window equations." if not failures else "; ".join(failures),
    ))

    capacitor_expectation = [
        ("U9", "S0", "C18", "470nF"), ("U10", "S1", "C20", "1uF"),
        ("U11", "S2", "C22", "2.2uF"), ("U12", "S3", "C24", "4.7uF"),
        ("U13", "S4", "C26", "10uF"),
    ]
    cap_failures: list[str] = []
    for switch_ref, control, cap_ref, value in capacitor_expectation:
        switch = design.require_component(switch_ref)
        capacitor = design.require_component(cap_ref)
        if switch.net("4") != control or switch.net("2") != "Vm_Int" or switch.net("1") not in {pin.net for pin in capacitor.pins.values()} or capacitor.value != value:
            cap_failures.append(f"{switch_ref}/{cap_ref}")
    findings.append(AuditFinding(
        "topology.rv4.capacitors", "error", not cap_failures,
        "RV4 selects 470 nF, 1 µF, 2.2 µF, 4.7 µF, then 10 µF through U9–U13.",
        "Monotonic physical switch/capacitor chain confirmed." if not cap_failures else "Failed pairs: " + ", ".join(cap_failures),
    ))

    # Peak window active high.
    u6 = design.require_component("U6")
    r51 = design.require_component("R51")
    controls = {(ref, pin) for ref in ("U14", "U20") for pin in ("4",) if design.require_component(ref).net(pin) == "Peak_Window"}
    u19 = design.require_component("U19")
    peak_ok = (
        u6.net("1") == "Peak_Window" and u6.net("3") == "Spike_Pulse" and u6.net("2") == "V_Threshold"
        and _connected_between(r51, "VDD", "Peak_Window")
        and controls == {("U14", "4"), ("U20", "4")}
        and u19.net("3") == "Peak_Window" and u19.net("4") == "V_Logic_Mid"
    )
    findings.append(AuditFinding(
        "topology.peak_window.active_high", "error", peak_ok,
        "Peak_Window is an active-high event pulse generated by U6A and pulled up by R51.",
        f"U6A pins: OUT={u6.net('1')}, IN+={u6.net('3')}, IN-={u6.net('2')}; R51={sorted(pin.net for pin in r51.pins.values())}; U14/U20 controls={sorted(controls)}.",
    ))

    # U23 physical stimulus amplifier.
    u23 = design.require_component("U23")
    expected_u23 = {"1": "V_Stim_Drive", "2": "GNDREF", "3": "Net-(U23-IN+)", "4": "Net-(U23-IN-)", "5": "VDD"}
    u23_fail = [f"pin {pin}: {u23.net(pin)}" for pin, net in expected_u23.items() if u23.net(pin) != net]
    resistor_rules = {
        "R92": ("Vm_Int", "Net-(U23-IN+)", "100kΩ"),
        "R93": ("V_Stim_Cmd", "Net-(U23-IN+)", "200kΩ"),
        "R94": ("VREF_1V024", "Net-(U23-IN-)", "200kΩ"),
        "R95": ("V_Stim_Drive", "Net-(U23-IN-)", "100kΩ"),
    }
    for ref, (a, b, value) in resistor_rules.items():
        component = design.require_component(ref)
        if not _connected_between(component, a, b) or component.value != value:
            u23_fail.append(f"{ref} expected {a}<->{b} {value}")
    output_injection_refs = [ref for ref, c in design.components.items() if re.fullmatch(r"R\d+", ref) and _connected_between(c, "V_Stim_Drive", "Vm_Int")]
    if output_injection_refs != ["R96"]:
        u23_fail.append(f"output-to-Vm resistor refs={output_injection_refs}")
    findings.append(AuditFinding(
        "topology.stimulus.u23", "error", not u23_fail,
        "U23 is the physical TLV9041 stimulus amplifier and all four gain-setting resistors are present.",
        "Electrical topology matches the intended transfer; the output-to-Vm resistor is physically R96, not R97." if not u23_fail else "; ".join(u23_fail),
    ))
    findings.append(AuditFinding(
        "naming.stimulus.r96_r97", "warning", False,
        "The latest electrical topology uses R96 between V_Stim_Drive and Vm_Int, while the requested design note calls this resistor R97.",
        "R97 is absent. R96 is 100 kΩ between V_Stim_Drive and Vm_Int; there is no VDD pull-up on V_Stim_Drive.",
    ))

    # U6B unused state.
    unused_ok = u6.net("5") == "VDD" and u6.net("6") == "GNDREF" and u6.net("7").startswith("unconnected-")
    findings.append(AuditFinding(
        "topology.u6b.unused", "error", unused_ok,
        "U6B is unused and forced into a deterministic state.",
        f"INB+={u6.net('5')}, INB-={u6.net('6')}, OUTB={u6.net('7')}",
    ))

    # Exact fixed-output boost variant. TI defines TPS610995 as 3.6 V; TPS610994 is 3.3 V.
    u7 = design.require_component("U7")
    boost_exact = u7.value == "TPS610995DRVR"
    findings.append(AuditFinding(
        "power.boost.tps610995_fixed_output", "warning", False,
        "The fitted TPS610995DRVR is the fixed 3.6 V variant, not the 3.3 V TPS610994 variant.",
        f"Netlist U7 value={u7.value}. Portable switching model VSET is locked to 3.6 V; previous 3.3 V behavioural assumptions are rejected.",
    ))

    # REF3020 DBZ physical package order is IN=1, OUT=2, GND=3.
    u21 = design.require_component("U21")
    ref_pin_ok = u21.net("1") == "VDD" and u21.net("2") == "VREF_2V048" and u21.net("3") == "GNDREF"
    findings.append(AuditFinding(
        "pinmap.u21.ref3020_physical", "error", ref_pin_ok,
        "REF3020AIDBZR physical DBZ package pins match the official IN=1, OUT=2, GND=3 order.",
        f"KiCad mapping: pin1={u21.net('1')}, pin2={u21.net('2')}, pin3={u21.net('3')}.",
    ))
    findings.append(AuditFinding(
        "model.u21.ref3020_vendor_terminal_order", "warning", False,
        "The official REF3020 TINA macro-model terminal declaration remains an explicit vendor-profile gate.",
        "The physical package order is verified, but the downloaded model's actual .SUBCKT terminal order must still be inspected and wrapped before vendor instantiation.",
    ))
    return findings


def component_category(component: Component, registry: dict[str, Any]) -> tuple[str, str, str]:
    ref = component.reference
    if re.fullmatch(r"R\d+", ref):
        return "ordinary passive instantiated directly", "direct resistor with tolerance support", "high"
    if re.fullmatch(r"RV\d+", ref):
        return "ordinary passive instantiated directly", "three-terminal potentiometer split at physical wiper", "high"
    if re.fullmatch(r"C\d+", ref):
        return "ordinary passive instantiated directly", "capacitor with ESR, leakage, ESL and optional DC-bias derating", "medium"
    if re.fullmatch(r"L\d+", ref):
        return "datasheet-derived electrical model", "inductance plus DCR/parasitic capacitance; saturation checked numerically", "medium"
    if ref.startswith("J"):
        return "connector or external terminal", "physical pins retained as external nets", "high"
    if ref.startswith("H"):
        return "mechanical-only", "mounting hole; deliberately omitted electrically", "high"
    if ref == "BT1":
        return "datasheet-derived electrical model", "CR2032 fixed-source or dynamic equivalent; exact cell manufacturer unresolved", "medium"
    if ref == "SW1":
        return "datasheet-derived electrical model", "power switch contact resistance and selectable state", "medium"
    family = family_for_component(component.value, registry)
    if family:
        return family.get("category", "unresolved"), family.get("portable_model", ""), "high" if family.get("category", "").startswith("official") else "medium"
    return "unresolved", "no model rule", "none"


def functional_block(component: Component) -> str:
    ref = component.reference
    nets = {pin.net for pin in component.pins.values()}
    if ref in {"BT1", "SW1", "U7", "L1", "U21", "U22"} or any(net in nets for net in {"+BATT", "V_Boost", "VREF_2V048", "VREF_1V024"}):
        return "power and precision references"
    if ref in {"U9", "U10", "U11", "U12", "U13", "RV4", "C18", "C20", "C22", "C24", "C26"} or any(net in nets for net in {"S0", "S1", "S2", "S3", "S4", "T1", "T2", "T3", "T4", "Vsel"}):
        return "membrane capacitance selector"
    if ref in {"U23", "R92", "R93", "R94", "R95", "R96", "C39"} or any(net in nets for net in {"V_Stim_Cmd", "V_Stim_Drive", "Stimulus_Ext"}):
        return "external stimulus"
    if any("Syn" in net for net in nets) or ref in {"U15", "U16", "U17", "U18", "RV5", "RV6", "RV7", "RV8", "RV9"}:
        return "signed synapses"
    if any(net in nets for net in {"Peak_Window", "Reset_Window", "Spike_Pulse", "AP", "/AP_Gate", "Spike_Out"}):
        return "threshold, AP, peak, reset and spike output"
    if any(net in nets for net in {"Vw", "Vw_buff", "/Adapt", "/Vkick", "/Adapt_Kick_Drive"}):
        return "adaptation"
    if any(net in nets for net in {"Vm_Int", "V_Leak", "/V_Leak_ref", "V_Threshold"}):
        return "membrane leak and integration"
    if any(net in nets for net in {"Vm_Ext", "Vm_Display_In", "Vm_Out_DRV", "Vm_FB"}):
        return "external membrane display/output"
    if nets <= {"VDD", "GNDREF"}:
        return "local decoupling"
    if ref.startswith("J"):
        return "external interfaces"
    if ref.startswith("H"):
        return "mechanical"
    return "miscellaneous schematic support"



def pin_model_rows(design: Design, resolution_by_value: dict[str, FamilyResolution]) -> list[dict[str, str]]:
    """Map every active/discrete physical pin to wrapper and model terminals."""
    rows: list[dict[str, str]] = []

    def add(component: Component, instance: str, pin: str, wrapper_role: str, model_name: str, model_index: str, model_role: str, note: str = "") -> None:
        connection = component.pins.get(pin)
        if connection is None:
            return
        resolution = resolution_by_value.get(component.value)
        rows.append({
            "reference": component.reference,
            "instance": instance,
            "value": component.value,
            "physical_pin": pin,
            "pin_function": connection.function,
            "connected_net": connection.net,
            "wrapper_terminal": wrapper_role,
            "model_name": model_name,
            "model_terminal_index_or_token": model_index,
            "model_terminal_role": model_role,
            "model_file": (resolution.selected_path if component.value == "MCP6004T-I/ST" and resolution and resolution.selected_path
                           else "models/portable/lifeling_portable_models.lib"),
            "mapping_note": note,
        })

    for reference in design.refs(""):
        c = design.components[reference]
        if c.value == "MCP6004T-I/ST":
            channel_map = {
                "A": {"3": ("IN+", "1", "IN+"), "2": ("IN-", "2", "IN-"), "1": ("OUT", "5", "OUT")},
                "B": {"5": ("IN+", "1", "IN+"), "6": ("IN-", "2", "IN-"), "7": ("OUT", "5", "OUT")},
                "C": {"10": ("IN+", "1", "IN+"), "9": ("IN-", "2", "IN-"), "8": ("OUT", "5", "OUT")},
                "D": {"12": ("IN+", "1", "IN+"), "13": ("IN-", "2", "IN-"), "14": ("OUT", "5", "OUT")},
            }
            for channel, mapping in channel_map.items():
                for pin, (role, index, model_role) in mapping.items():
                    add(c, f"{reference}{channel}", pin, role, "MCP6001", index, model_role, "MCP6004 package split into four official MCP6001 family instances")
                add(c, f"{reference}{channel}", "4", "V+", "MCP6001", "3", "V+")
                add(c, f"{reference}{channel}", "11", "V-", "MCP6001", "4", "V-")
        elif c.value == "TLV7044PWR":
            channel_map = {
                "A": {"1": "OUT", "3": "IN+", "2": "IN-"},
                "B": {"7": "OUT", "5": "IN+", "6": "IN-"},
                "C": {"8": "OUT", "10": "IN+", "9": "IN-"},
                "D": {"14": "OUT", "12": "IN+", "13": "IN-"},
            }
            order = {"OUT": "1", "V-": "2", "IN+": "3", "IN-": "4", "V+": "5"}
            for channel, mapping in channel_map.items():
                for pin, role in mapping.items():
                    add(c, f"{reference}{channel}", pin, role, "LIF_TLV7041_OD", order[role], role)
                add(c, f"{reference}{channel}", "11", "V-", "LIF_TLV7041_OD", "2", "V-")
                add(c, f"{reference}{channel}", "4", "V+", "LIF_TLV7041_OD", "5", "V+")
        elif c.value == "TLV7031DCKR":
            mapping = {"1": ("OUT", "1"), "2": ("V-", "2"), "3": ("IN+", "3"), "4": ("IN-", "4"), "5": ("V+", "5")}
            for pin, (role, index) in mapping.items(): add(c, reference, pin, role, "LIF_TLV7031_PP", index, role)
        elif c.value in {"TLV9001IDBVR", "TLV9041IDBVR"}:
            model = "LIF_TLV9001" if c.value.startswith("TLV9001") else "LIF_TLV9041"
            mapping = {"3": ("IN+", "1"), "4": ("IN-", "2"), "5": ("V+", "3"), "2": ("V-", "4"), "1": ("OUT", "5")}
            for pin, (role, index) in mapping.items(): add(c, reference, pin, role, model, index, role)
        elif c.value == "TS5A3166DCKR":
            mapping = {"1": ("NO", "1"), "2": ("COM", "2"), "3": ("GND", "3"), "4": ("IN", "4"), "5": ("V+", "5")}
            for pin, (role, index) in mapping.items(): add(c, reference, pin, role, "LIF_TS5A3166", index, role)
        elif c.value == "TPS610995DRVR":
            mapping = {"1": ("GND", "1"), "2": ("VOUT", "2"), "3": ("FB", "3"), "4": ("EN", "4"), "5": ("SW", "5"), "6": ("VIN", "6"), "7": ("PowerPad", "package-only")}
            for pin, (role, index) in mapping.items(): add(c, reference, pin, role, "LIF_TPS610995_SWITCHING", index, role, "Pad 7 is tied to package ground outside the six-terminal wrapper" if pin == "7" else "")
        elif c.value == "REF3020AIDBZR":
            mapping = {"1": ("VIN", "1"), "2": ("VOUT", "2"), "3": ("GND", "3")}
            for pin, (role, index) in mapping.items(): add(c, reference, pin, role, "LIF_REF3020", index, role, "Vendor TINA declaration remains gated")
        elif c.value == "TPD1E05U06DPYT":
            for pin, role, index in (("1", "IO", "1"), ("2", "GND", "2")): add(c, reference, pin, role, "LIF_TPD1E05U06", index, role)
        elif c.value in {"BAT54WS L9", "1N4148WS", "RB521S30T1G"}:
            model = {"BAT54WS L9":"LIF_BAT54WS", "1N4148WS":"LIF_1N4148WS", "RB521S30T1G":"LIF_RB521S30"}[c.value]
            add(c, reference, "2", "A", model, "A", "anode")
            add(c, reference, "1", "K", model, "K", "cathode")
        elif c.value == "19-237/R6GHBHC-A01/2T":
            add(c, f"{reference}_R", "4", "A", "LIF_LED_RED", "A", "anode")
            add(c, f"{reference}_R", "1", "K", "LIF_LED_RED", "K", "red cathode")
            add(c, f"{reference}_G", "4", "A", "LIF_LED_GREEN", "A", "anode")
            add(c, f"{reference}_G", "2", "K", "LIF_LED_GREEN", "K", "green cathode")
            add(c, f"{reference}_B", "4", "A", "LIF_LED_BLUE", "A", "anode")
            add(c, f"{reference}_B", "3", "K", "LIF_LED_BLUE", "K", "blue cathode")
        elif c.value == "BSS138":
            mapping = {"3": ("D", "D"), "1": ("G", "G"), "2": ("S", "S")}
            for pin, (role,index) in mapping.items(): add(c, reference, pin, role, "LIF_BSS138", index, role)
            add(c, reference, "2", "B", "LIF_BSS138", "B", "body tied to source")
        elif c.value == "MMBT3904":
            mapping = {"3": ("C", "C"), "1": ("B", "B"), "2": ("E", "E")}
            for pin, (role,index) in mapping.items(): add(c, reference, pin, role, "LIF_MMBT3904", index, role)
        elif reference == "BT1":
            add(c, reference, "1", "P", "LIF_CR2032_DYNAMIC or fixed source", "1", "positive")
            add(c, reference, "2", "N", "LIF_CR2032_DYNAMIC or fixed source", "2", "negative")
        elif reference == "SW1":
            add(c, reference, "1", "contact A", "RSW1", "1", "contact")
            add(c, reference, "2", "contact B", "RSW1", "2", "contact")
            add(c, reference, "3", "unused", "R_SW1_UNUSED", "1", "floating pad")
    return rows


def write_audit_outputs(design: Design, registry: dict[str, Any], resolutions: list[FamilyResolution], findings: list[AuditFinding], output_dir: Path) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    resolution_by_value = {item.value: item for item in resolutions}

    pin_mapping_csv = output_dir / "pin_model_mapping.csv"
    mapping_rows = pin_model_rows(design, resolution_by_value)
    with pin_mapping_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        fields = list(mapping_rows[0]) if mapping_rows else ["reference"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(mapping_rows)

    inventory_csv = output_dir / "netlist_inventory.csv"
    with inventory_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["reference", "value", "footprint", "manufacturer", "manufacturer_part", "supplier_number", "physical_pin", "pin_function", "pin_type", "connected_net", "functional_block", "model_category", "model_file", "model_subcircuit", "model_terminal_order", "model_confidence", "simulation_status"])
        for reference in design.refs(""):
            component = design.components[reference]
            category, note, confidence = component_category(component, registry)
            resolution = resolution_by_value.get(component.value)
            pins = component.pins or {"": None}
            for pin, connection in sorted(pins.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 999):
                writer.writerow([
                    reference, component.value, component.footprint, component.manufacturer, component.manufacturer_part,
                    component.supplier_number, pin,
                    connection.function if connection else "", connection.pin_type if connection else "", connection.net if connection else "",
                    functional_block(component), category,
                    (resolution.selected_path if component.value == "MCP6004T-I/ST" and resolution and resolution.selected_path
                     else "models/portable/lifeling_portable_models.lib" if resolution else ""),
                    resolution.subcircuit_name if resolution else "",
                    " ".join(resolution.subcircuit_terminals) if resolution else "", resolution.confidence if resolution else confidence,
                    resolution.model_status if resolution else note,
                ])

    coverage_csv = output_dir / "component_model_coverage.csv"
    unresolved: list[str] = []
    with coverage_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["reference", "value", "category", "model_note", "model_confidence", "simulation_status", "functional_block"])
        for reference in design.refs(""):
            component = design.components[reference]
            category, note, confidence = component_category(component, registry)
            resolution = resolution_by_value.get(component.value)
            status = resolution.model_status if resolution else note
            if category == "unresolved" or status == "unresolved":
                unresolved.append(reference)
            writer.writerow([reference, component.value, category, note, resolution.confidence if resolution else confidence, status, functional_block(component)])

    model_json = output_dir / "model_manifest.json"
    model_json.write_text(json.dumps([dataclasses.asdict(item) for item in resolutions], indent=2, ensure_ascii=False), encoding="utf-8")
    model_csv = output_dir / "model_manifest.csv"
    with model_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(dataclasses.asdict(resolutions[0]).keys()) if resolutions else ["value"])
        writer.writeheader()
        for item in resolutions:
            row = dataclasses.asdict(item)
            row["references"] = ";".join(row["references"])
            row["subcircuit_terminals"] = " ".join(row["subcircuit_terminals"])
            writer.writerow(row)

    findings_json = output_dir / "connectivity_audit.json"
    findings_json.write_text(json.dumps([dataclasses.asdict(item) for item in findings], indent=2, ensure_ascii=False), encoding="utf-8")
    findings_md = output_dir / "connectivity_audit.md"
    lines = ["# LIFeling connectivity and pin-map audit", "", f"Netlist: `{design.path.name}`", f"Export: `{design.metadata.export_date}` using `{design.metadata.tool}`", "", "| Check | Severity | Result | Evidence |", "|---|---|---|---|",]
    for item in findings:
        result = "PASS" if item.passed else ("WARNING" if item.severity == "warning" else "FAIL")
        lines.append(f"| `{item.identifier}` | {item.severity} | **{result}** | {item.evidence.replace('|', chr(92)+'|')} |")
    if unresolved:
        lines += ["", "## Unresolved references", "", ", ".join(f"`{ref}`" for ref in unresolved)]
    findings_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"inventory": inventory_csv, "coverage": coverage_csv, "pin_mapping": pin_mapping_csv, "model_json": model_json, "model_csv": model_csv, "audit_json": findings_json, "audit_md": findings_md}
