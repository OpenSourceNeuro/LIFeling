"""Reader-facing validation report construction."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .design import Design
from .audit import AuditFinding
from .models import FamilyResolution


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def build_report(
    design: Design,
    source_manifest: list[dict[str, Any]],
    repository_snapshot: dict[str, Any],
    findings: list[AuditFinding],
    resolutions: list[FamilyResolution],
    execution_status: list[dict[str, Any]],
    output_path: Path,
    static_test_summary: dict[str, Any] | None = None,
) -> Path:
    output_path = Path(output_path)
    source_lock_path = output_path.parent / "source_lock.json"
    source_lock_sha = hashlib.sha256(source_lock_path.read_bytes()).hexdigest() if source_lock_path.is_file() else "not recorded"
    source_manifest_path = output_path.parent / "source_manifest.json"
    source_manifest_sha = hashlib.sha256(source_manifest_path.read_bytes()).hexdigest() if source_manifest_path.is_file() else "not recorded"
    attached_newer = repository_snapshot.get("attached_files_newer", True)
    schematic_crosscheck = _read_json(output_path.parent / "schematic_crosscheck.json", {})
    failures = [item for item in findings if not item.passed and item.severity == "error"]
    warnings = [item for item in findings if not item.passed and item.severity == "warning"]
    executed = [item for item in execution_status if item.get("status") == "passed"]
    failed_runs = [item for item in execution_status if item.get("status") == "failed"]
    not_run = [item for item in execution_status if item.get("status") == "not_executed"]
    static_test_summary = static_test_summary or {}
    static_count = int(static_test_summary.get("tests_run", 0) or 0)
    static_failures = int(static_test_summary.get("failures", 0) or 0)
    static_errors = int(static_test_summary.get("errors", 0) or 0)
    static_status = static_test_summary.get("status", "not recorded")

    lines = [
        "# LIFeling SPICE reconstruction and validation report",
        "",
        "## Executive conclusion",
        "",
        f"The electrical model was reconstructed from the attached KiCad export dated **{design.metadata.export_date}**, produced by **{design.metadata.tool}**. The export contains **{len(design.components)} components** and **{len(design.nets)} nets**. Connectivity in generated decks is derived from physical pins in that export; intended equations and previous behavioural mappings are not used as connectivity sources.",
        "",
        f"The static topology audit has **{len(failures)} blocking failures** and **{len(warnings)} explicit warnings**. " + ("No blocking topology failure remains." if not failures else "Blocking failures must be corrected before simulation results are accepted."),
        "",
        f"Transient execution status: **{len(executed)} passed**, **{len(failed_runs)} failed**, **{len(not_run)} not executed**. A non-executed run is not reported as electrical validation.",
        "",
        f"Static reconstruction tests: **{max(0, static_count - static_failures - static_errors)} passed, {static_failures} failures, {static_errors} errors** ({static_status}).",
        "",
        "> This system validates a SPICE representation. It does not constitute hardware validation, ESD qualification, battery-life certification, sustained-fault survival proof, PCB-parasitic validation, or production test evidence.",
        "",
        "## 1. Source and version lock",
        "",
        f"- Authoritative netlist SHA-256: `{design.metadata.sha256}`",
        f"- Stable source-lock SHA-256: `{source_lock_sha}`",
        f"- Full run-manifest SHA-256: `{source_manifest_sha}`",
        f"- KiCad source recorded in export: `{design.metadata.source}`",
        f"- Export date: `{design.metadata.export_date}`",
        f"- KiCad tool: `{design.metadata.tool}`",
        f"- Repository comparison commit: `{repository_snapshot.get('commit_sha','not recorded')}`",
        f"- Repository commit date: `{repository_snapshot.get('commit_date','not recorded')}`",
        f"- Attached files newer than repository comparison: **{'yes' if attached_newer else 'no'}**",
        "",
        "When attached and repository files differ, the attached netlist controls electrical connectivity. The schematic is a visual cross-check. The earlier Python implementation and historical outputs are comparison material only.",
        "",
        f"Schematic cross-check: **{schematic_crosscheck.get('placed_symbol_count','unknown')} placed symbols**, **{schematic_crosscheck.get('blocking_failures','unknown')} blocking mismatches**, **{schematic_crosscheck.get('warnings','unknown')} metadata warnings**. Escaped KiCad property strings are decoded before comparison, so the BT1 simulation-parameter value is compared exactly rather than truncated.",
        "",
        "### Source hashes",
        "",
        "| File | Type | Bytes | SHA-256 |",
        "|---|---|---:|---|",
    ]
    for row in source_manifest:
        lines.append(f"| `{row['file_name']}` | {row['source_type']} | {row['size_bytes']} | `{row['sha256']}` |")

    lines += [
        "",
        "## 2. Verified hardware corrections",
        "",
    ]
    for item in findings:
        if item.identifier.startswith(("pinmap.", "topology.rv4", "topology.peak_window", "topology.stimulus", "topology.u6b", "naming.stimulus", "power.boost")):
            result = "PASS" if item.passed else ("WARNING" if item.severity == "warning" else "FAIL")
            lines += [f"### {item.summary}", "", f"**{result}.** {item.evidence}", ""]

    lines += [
        "## 3. Important netlist findings",
        "",
        "1. The TLV7044 channel-A correction is present on U4, U5 and U6 and the full physical PW-14 mapping is audited before channel instances are emitted.",
        "2. RV4’s five comparator windows and TS5A3166/capacitor mapping are generated from physical comparator inputs and switch pins. The intended monotonic sequence is confirmed by topology, not hard-coded as a selector outcome.",
        "3. `Peak_Window` is physically active-high: U6A compares `Spike_Pulse` at IN+ against `V_Threshold` at IN−, R51 pulls up the open-drain output, and U14/U20 use that node as an active-high control.",
        "4. U23 is a physical TLV9041 stage with R92–R95 forming the closed-loop network. The transfer is not replaced by a behavioural voltage source.",
        "5. The output-to-`Vm_Int` resistor is **R96 = 100 kΩ** in the attached export. **R97 is absent.** Electrically this is the intended injection resistor, but the designator differs from the requested description.",
        "6. U6B is unused: INB+ is tied to VDD, INB− to GNDREF, and OUTB is unconnected.",
        "7. U7 is `TPS610995DRVR`, which is the fixed 3.6 V member. The prior hard-coded 3.3 V boost assumption is rejected; 3.3 V would correspond to TPS610994.",
        "8. REF3020 KiCad physical pins are pin 1 input, pin 2 output and pin 3 ground. A downloaded TINA macro-model is never instantiated until its actual terminal declaration is inspected and wrapped.",
        "",
        "## 4. Model coverage and hierarchy",
        "",
        "The default `hybrid` profile uses the supplied official Microchip MCP6001/2/4 family macro-model for all twelve MCP6004 channels and documented portable models for devices whose official packages are not yet installed and smoke-tested. `pin_model_mapping.csv` records every active/discrete physical pin, connected net, wrapper terminal and model terminal. The `vendor` profile is intentionally strict: it fails rather than silently substituting an unapproved model or guessed terminal order.",
        "",
        "| Family | References | Selected status | Model/subcircuit | Confidence | Known limitation |",
        "|---|---|---|---|---|---|",
    ]
    for item in resolutions:
        refs = ", ".join(item.references)
        model = item.subcircuit_name or item.selected_path or "portable rule"
        note = item.notes.replace("|", "\\|")
        lines.append(f"| `{item.value}` | {refs} | {item.model_status} | `{model}` | {item.confidence} | {note} |")

    lines += [
        "",
        "### Explicit approximations remaining in the portable/hybrid profile",
        "",
        "- TLV7044 and TLV7031: rail-aware comparator wrappers include open-drain/push-pull topology, quiescent current, finite output resistance, input loading, hysteresis and a propagation-delay pole. They are not substitutes for the official TI model’s complete overdrive and supply dependence.",
        "- TLV9001 and TLV9041: finite open-loop gain, dominant pole, rail clipping, output resistance and quiescent current are represented. Input offset, detailed output-current limiting and every datasheet corner are not fully reproduced.",
        "- TS5A3166: active-high supply-referenced logic, on-resistance, leakage and capacitance are represented. Charge injection, exact powered-off isolation and process corners remain approximate.",
        "- TPS610995: the fallback is a 3.6 V switching macro-model using the physical L1 and output capacitors. It is not an official efficiency or control-loop sign-off model. The official unencrypted transient package should be smoke-tested separately before replacing it.",
        "- REF3020: startup, dropout, finite source resistance, source-only behaviour and quiescent current are approximated. Noise and complete line/load-regulation surfaces are not sign-off quality.",
        "- TPD1E05U06: capacitance, leakage, breakdown and dynamic resistance are datasheet-derived. This cannot prove IEC ESD robustness or sustained overvoltage survival.",
        "- CR2032: the actual cell manufacturer is unspecified; both fixed source-resistance sweeps and a dynamic equivalent are supported, but battery-life predictions are provisional.",
        "- L1 and MLCCs: DCR/ESR/ESL, tolerance, leakage and conservative DC-bias derating are included. Exact vendor nonlinear curves are not embedded unless supplied.",
        "- BSS138, MMBT3904, BAT54WS, 1N4148WS, RB521S30 and the RGB LED use explicit vendor-mismatch or datasheet-derived models where an exact ordered-part model was unavailable.",
        "",
        "## 5. Validation test matrix",
        "",
        "| Test | Purpose | Acceptance evidence | Hardware claim allowed? |",
        "|---|---|---|---|",
        "| Full operating transient | Integrate, threshold, AP, peak, reset, adaptation, synapse, outputs | Numeric edge counts, rail ranges, periods and trace CSV | No; functional SPICE correlation only |",
        "| RV4 selector sweep | Confirm one-hot physical comparator/switch selection over five regions | S0–S4 states and effective membrane transient ordering | No |",
        "| U23 stimulus transfer sweep | Confirm gain, polarity, clipping, settling and injection current emerge from U23/R92–R96 | `V_Stim_Drive - [Vm_Int + 0.5(V_Stim_Cmd−VREF)]` error inside linear region | No |",
        "| Peak-window event | Confirm active-high `Peak_Window`, U14/U20 closure and positive external pulse | event timing and polarity | No |",
        "| Cold and low-battery startup | Check reference, comparator and boost startup under source impedance | startup time, rail sag, failure mode | No battery-life or safety claim |",
        "| Synapse sign and decay sweeps | Confirm midpoint neutrality, excitatory/inhibitory polarity and RV5 decay | differential Vm response and state decay | No |",
        "| Tolerance/temperature Monte Carlo | Identify functional margins and fragile parameter combinations | percentile distributions and failing seeds | No production yield claim without measured distributions |",
        "",
        "## 6. Execution record",
        "",
    ]
    if not execution_status:
        lines.append("No execution record was supplied.")
    else:
        lines += ["| Test | Status | ngspice | Message |", "|---|---|---|---|"]
        for item in execution_status:
            lines.append(f"| `{item.get('test_name','')}` | **{item.get('status','')}** | {item.get('ngspice_version','')} | {str(item.get('message','')).replace('|','\\|')} |")

    lines += [
        "",
        "## 7. Build gates",
        "",
        "The build fails when any new active component lacks a registry rule, any functional reference/net is absent, any required installed model is missing in strict-vendor mode, a named subcircuit cannot be found, a locked terminal count/order disagrees, or any exported reference is neither instantiated nor deliberately classified as terminal/mechanical.",
        "",
        "## 8. Required bench correlation before production",
        "",
        "The final PCB should be correlated at minimum for VDD/boost startup, 2.048 V and 1.024 V references, RV4 one-hot selection, U23 gain/clipping, AP/Peak/Reset timing, Spike_Out levels into representative loads, synaptic midpoint neutrality, quiescent current, CR2032 pulse sag, output protection under realistic classroom faults, and temperature/tolerance extremes. Those measurements should be stored beside the SPICE CSVs with board serial number, instruments, probe points and firmware/test conditions.",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
