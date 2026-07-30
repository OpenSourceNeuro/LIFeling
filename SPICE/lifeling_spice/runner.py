"""ngspice execution, data conversion, and numerical regression diagnostics."""
from __future__ import annotations

import csv
import dataclasses
import json
import math
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .deck import DeckConfig, node, safe_name


@dataclasses.dataclass
class RunResult:
    test_name: str
    status: str
    source_lock_sha256: str
    deck: str
    log: str
    wrdata: str
    parsed_csv: str
    diagnostics_json: str
    plot_png: str
    ngspice_version: str
    return_code: int | None
    message: str


def _prefer_console_binary(path_value: str | Path) -> str:
    """Prefer the Windows console executable when a GUI ngspice launcher is selected.

    Official Windows ngspice packages commonly install both ``ngspice.exe``
    (GUI) and ``ngspice_con.exe`` (console/batch).  Launching the GUI binary
    from a subprocess can display an "Information during setup" dialog and
    block unattended validation.
    """
    path = Path(path_value)
    if platform.system().lower().startswith("win") and path.name.lower() == "ngspice.exe":
        console = path.with_name("ngspice_con.exe")
        if console.is_file():
            return str(console)
    return str(path)


def find_ngspice(requested: str = "auto") -> str | None:
    if requested and requested.lower() != "auto":
        path = Path(requested)
        if path.is_file():
            return _prefer_console_binary(path)
        found = shutil.which(requested)
        if found:
            return _prefer_console_binary(found)
        raise FileNotFoundError(
            f"The explicitly requested ngspice executable does not exist: {requested}"
        )
    env = os.environ.get("NGSPICE_BINARY", "")
    if env and Path(env).is_file():
        return _prefer_console_binary(env)
    # On Windows, ngspice_con.exe is the batch/console program.  It must be
    # preferred over the GUI launcher ngspice.exe.
    for candidate in ("ngspice_con", "ngspice_con.exe", "ngspice", "ngspice.exe"):
        found = shutil.which(candidate)
        if found:
            return _prefer_console_binary(found)
    for candidate in (
        Path(r"C:\Spice64\bin\ngspice_con.exe"),
        Path(r"C:\Spice64\bin\ngspice.exe"),
        Path(r"C:\Program Files\ngspice\bin\ngspice_con.exe"),
        Path(r"C:\Program Files\ngspice\bin\ngspice.exe"),
        Path(r"C:\Program Files\KiCad\10.0\bin\ngspice_con.exe"),
        Path(r"C:\Program Files\KiCad\10.0\bin\ngspice.exe"),
        Path(r"C:\Program Files\KiCad\bin\ngspice_con.exe"),
        Path(r"C:\Program Files\KiCad\bin\ngspice.exe"),
    ):
        if candidate.is_file():
            return _prefer_console_binary(candidate)
    return None


def ngspice_version(executable: str) -> str:
    try:
        completed = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=20, check=False)
        lines = (completed.stdout or completed.stderr).strip().splitlines()
        for line in lines:
            if "ngspice-" in line.lower():
                return line.strip("* \t")
        return lines[0].strip("* \t") if lines else "unknown"
    except Exception as exc:
        return f"unavailable: {exc}"


def _read_wrdata(path: Path, trace_names: list[str]) -> dict[str, list[float]]:
    rows: list[list[float]] = []
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("*"):
                continue
            try:
                rows.append([float(token) for token in stripped.split()])
            except ValueError:
                continue
    if not rows:
        raise RuntimeError(f"No numeric rows in {path}")
    width = len(rows[0])
    # wrdata normally writes x,y pairs for every vector; tolerate a single shared x column.
    if width >= 2 * len(trace_names):
        time = [row[0] for row in rows]
        series = {name: [row[2 * index + 1] for row in rows] for index, name in enumerate(trace_names)}
    elif width >= len(trace_names) + 1:
        time = [row[0] for row in rows]
        series = {name: [row[index + 1] for row in rows] for index, name in enumerate(trace_names)}
    else:
        raise RuntimeError(f"Unexpected wrdata column count {width}; expected at least {len(trace_names)+1}")
    return {"time_s": time, **series}


def _rising_edges(values: list[float], threshold: float) -> int:
    return sum(1 for a, b in zip(values, values[1:]) if a < threshold <= b)


def _crossing_times(time: list[float], values: list[float], threshold: float) -> list[float]:
    return [time[index] for index, (a, b) in enumerate(zip(values, values[1:]), start=1) if a < threshold <= b]


def diagnostics(data: dict[str, list[float]], cfg: DeckConfig, source_lock_sha: str, deck_sha: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "test_name": cfg.test_name,
        "source_lock_sha256": source_lock_sha,
        "deck_sha256": deck_sha,
        "temperature_c": cfg.temperature_c,
        "profile": cfg.profile,
        "supply_mode": cfg.supply_mode,
        "pot_positions": cfg.pot_positions,
    }
    for name, values in data.items():
        if name == "time_s" or not values:
            continue
        row[name] = {"min": min(values), "max": max(values), "end": values[-1]}
    time = data.get("time_s", [])
    for signal in ("AP", "Peak_Window", "Reset_Window", "Spike_Out", "Spike_Pulse"):
        if signal in data:
            supply = max(data.get("VDD", [3.0]))
            threshold = 0.5 * supply
            edges = _crossing_times(time, data[signal], threshold)
            row[f"{signal}_rising_edges"] = len(edges)
            row[f"{signal}_mean_period_s"] = (sum(b-a for a,b in zip(edges, edges[1:]))/(len(edges)-1)) if len(edges)>1 else None
    if "Vm_Int" in data and "V_Threshold" in data:
        crossings = sum(1 for vm0, vm1, vt0, vt1 in zip(data["Vm_Int"], data["Vm_Int"][1:], data["V_Threshold"], data["V_Threshold"][1:]) if vm0 < vt0 and vm1 >= vt1)
        row["Vm_threshold_crossings"] = crossings
    if "V_Stim_Cmd" in data and "V_Stim_Drive" in data and "Vm_Int" in data and "VREF_1V024" in data:
        vdd = data.get("VDD", [3.0] * len(data["V_Stim_Drive"]))
        samples = []
        for drive, vm, cmd, ref, supply in zip(data["V_Stim_Drive"], data["Vm_Int"], data["V_Stim_Cmd"], data["VREF_1V024"], vdd):
            # Evaluate the resistor-derived closed-loop equation only away from output clipping.
            if 0.05 < drive < max(0.05, supply - 0.05):
                samples.append(drive - (vm + 0.5 * (cmd - ref)))
        row["stimulus_transfer_linear_points"] = len(samples)
        row["stimulus_transfer_error_linear_max_abs_v"] = max((abs(x) for x in samples), default=None)
    return row



def _plot_run(data: dict[str, list[float]], cfg: DeckConfig, path: Path) -> str:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    time_ms = [value * 1000 for value in data.get("time_s", [])]
    if not time_ms:
        return ""
    selected = [name for name in ("Vm_Int", "Vm_Ext", "V_Threshold", "AP", "Peak_Window", "Reset_Window", "Spike_Out", "V_Stim_Drive", "V_Syn_State") if name in data]
    fig = plt.figure(figsize=(13, 7))
    for name in selected:
        plt.plot(time_ms, data[name], label=name)
    plt.xlabel("Time (ms)")
    plt.ylabel("Voltage (V)")
    plt.title(f"LIFeling SPICE — {cfg.test_name}")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best", fontsize="small", ncol=2)
    plt.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path)


def _flatten_diagnostic(value: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            if set(item).issubset({"min", "max", "end"}):
                for subkey, subvalue in item.items():
                    row[f"{key}_{subkey}"] = subvalue
            else:
                row[key] = json.dumps(item, sort_keys=True)
        else:
            row[key] = item
    return row


def write_suite_reports(execution: list[dict[str, Any]], report_dir: Path) -> tuple[Path, Path, Path]:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for item in execution:
        row = dict(item)
        diag_path = item.get("diagnostics_json")
        if item.get("status") == "passed" and diag_path and Path(diag_path).exists():
            row.update(_flatten_diagnostic(json.loads(Path(diag_path).read_text(encoding="utf-8"))))
        rows.append(row)
    all_keys = sorted({key for row in rows for key in row})
    summary_csv = report_dir / "validation_diagnostics_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=all_keys)
        writer.writeheader(); writer.writerows(rows)

    by_name = {row.get("test_name", ""): row for row in rows}
    verdicts: list[dict[str, str]] = []
    source_locks = sorted({str(row.get("source_lock_sha256", "")) for row in rows if row.get("source_lock_sha256")})
    source_lock = source_locks[0] if len(source_locks) == 1 else ("multiple" if source_locks else "not recorded")
    def add(block: str, status: str, evidence: str, limitation: str = "") -> None:
        verdicts.append({"source_lock_sha256": source_lock, "block": block, "status": status, "evidence": evidence, "limitation": limitation})
    not_executed = sum(row.get("status") == "not_executed" for row in rows)
    failed = sum(row.get("status") == "failed" for row in rows)
    add("Simulation execution", "FAIL" if failed else ("INCOMPLETE" if not_executed else "PASS"), f"{len(rows)} decks; {failed} failed; {not_executed} not executed.")

    baseline = by_name.get("01_full_operating")
    if baseline and baseline.get("status") == "passed":
        boost = baseline.get("V_Boost_end")
        ref2 = baseline.get("VREF_2V048_end")
        ref1 = baseline.get("VREF_1V024_end")
        ok = all(isinstance(x, (int,float)) for x in (boost,ref2,ref1)) and 3.4 <= boost <= 3.8 and 2.02 <= ref2 <= 2.08 and 0.99 <= ref1 <= 1.06
        add("Power and reference rails", "PASS" if ok else "WARNING", f"V_Boost={boost}; VREF_2V048={ref2}; VREF_1V024={ref1}.", "Portable models are not production sign-off models.")
        edges = baseline.get("AP_rising_edges", 0)
        add("Core LIF activity", "PASS" if isinstance(edges,(int,float)) and edges > 0 else "WARNING", f"AP rising edges={edges}; Vm threshold crossings={baseline.get('Vm_threshold_crossings')}.")
    else:
        add("Power and reference rails", "NOT EVALUATED", "Baseline was not executed successfully.")
        add("Core LIF activity", "NOT EVALUATED", "Baseline was not executed successfully.")

    peak = by_name.get("02_peak_window_active_high")
    if peak and peak.get("status") == "passed":
        pe = peak.get("Peak_Window_rising_edges", 0); se = peak.get("Spike_Out_rising_edges", 0)
        add("Active-high Peak_Window and Spike_Out", "PASS" if pe and se else "WARNING", f"Peak_Window edges={pe}; Spike_Out edges={se}.")
    else:
        add("Active-high Peak_Window and Spike_Out", "NOT EVALUATED", "Event deck was not executed successfully.")

    stimulus_rows = [row for name,row in by_name.items() if "stimulus_transfer" in name and row.get("status") == "passed"]
    if stimulus_rows:
        errors = [row.get("stimulus_transfer_error_linear_max_abs_v") for row in stimulus_rows if isinstance(row.get("stimulus_transfer_error_linear_max_abs_v"),(int,float))]
        add("U23 closed-loop stimulus transfer", "PASS" if errors and max(errors) < 0.1 else "WARNING", f"Maximum linear-equation residual={max(errors) if errors else 'unavailable'} V.", "Residual is interpreted only while U23 is not clipping.")
    else:
        add("U23 closed-loop stimulus transfer", "NOT EVALUATED", "Stimulus decks were not executed successfully.")

    selector = [row for name,row in sorted(by_name.items()) if "rv4_selector_region" in name and row.get("status") == "passed"]
    if selector:
        one_hot = []
        for row in selector:
            vdd = row.get("VDD_end", 3.0)
            highs = [name for name in ("S0","S1","S2","S3","S4") if isinstance(row.get(f"{name}_end"),(int,float)) and row[f"{name}_end"] > 0.5*vdd]
            one_hot.append(highs)
        expected = [["S0"],["S1"],["S2"],["S3"],["S4"]]
        add("RV4 one-hot monotonic selector", "PASS" if one_hot == expected else "WARNING", f"Observed high outputs={one_hot}.")
    else:
        add("RV4 one-hot monotonic selector", "NOT EVALUATED", "Selector sweep was not executed successfully.")

    off = by_name.get("09_power_switch_off")
    if off and off.get("status") == "passed":
        end = off.get("VDD_end")
        add("Power-off state", "PASS" if isinstance(end,(int,float)) and end < 0.1 else "WARNING", f"VDD_end={end} V.")
    else:
        add("Power-off state", "NOT EVALUATED", "Power-off deck was not executed successfully.")

    cold = by_name.get("06_cold_start_dynamic_battery")
    low_battery = by_name.get("07_low_battery_high_impedance")
    power_rows = [row for row in (cold, low_battery) if row and row.get("status") == "passed"]
    if len(power_rows) == 2:
        evidence = "; ".join(
            f"{row.get('test_name')}: VDD={row.get('VDD_min')}..{row.get('VDD_max')} V, "
            f"VREF2={row.get('VREF_2V048_end')} V" for row in power_rows
        )
        valid = all(isinstance(row.get("VDD_end"),(int,float)) and row.get("VDD_end") > 1.8 for row in power_rows)
        add("Cold-start and low-battery operation", "PASS" if valid else "WARNING", evidence, "Battery chemistry and converter fallback remain approximate.")
    else:
        add("Cold-start and low-battery operation", "NOT EVALUATED", "Cold-start and low-battery decks were not both executed successfully.")

    vm_load = by_name.get("10_vm_ext_loaded_10k")
    spike_load = by_name.get("11_spike_out_loaded_10k")
    if baseline and baseline.get("status") == "passed" and vm_load and vm_load.get("status") == "passed" and spike_load and spike_load.get("status") == "passed":
        vm_drop = None
        if isinstance(baseline.get("Vm_Ext_max"),(int,float)) and isinstance(vm_load.get("Vm_Ext_max"),(int,float)):
            vm_drop = baseline.get("Vm_Ext_max") - vm_load.get("Vm_Ext_max")
        spike_edges = spike_load.get("Spike_Out_rising_edges", 0)
        ok = (vm_drop is None or vm_drop < 0.25) and isinstance(spike_edges,(int,float)) and spike_edges > 0
        add("External output loading", "PASS" if ok else "WARNING", f"10 kOhm Vm_Ext peak reduction={vm_drop} V; loaded Spike_Out edges={spike_edges}.")
    else:
        add("External output loading", "NOT EVALUATED", "Vm_Ext and Spike_Out load decks were not executed successfully.")

    def completed_rows(fragment: str) -> list[dict[str, Any]]:
        return [row for name, row in sorted(by_name.items()) if fragment in name and row.get("status") == "passed"]

    rv1 = completed_rows("30_rv1_leak_")
    if len(rv1) == 3:
        values = [row.get("V_Leak_end") for row in rv1 if isinstance(row.get("V_Leak_end"),(int,float))]
        add("RV1 leak-reference control", "PASS" if len(values)==3 and max(values)-min(values)>0.05 else "WARNING", f"V_Leak end values={values}.")
    else:
        add("RV1 leak-reference control", "NOT EVALUATED", "RV1 sweep was not fully executed.")

    rv2 = completed_rows("31_rv2_leak_rate_")
    if len(rv2) == 3:
        periods = [row.get("AP_mean_period_s") for row in rv2 if isinstance(row.get("AP_mean_period_s"),(int,float))]
        extrema = [row.get("Vm_Int_max") for row in rv2 if isinstance(row.get("Vm_Int_max"),(int,float))]
        responds = (len(periods)>=2 and max(periods)-min(periods)>1e-4) or (len(extrema)==3 and max(extrema)-min(extrema)>0.01)
        add("RV2 membrane-leak-rate control", "PASS" if responds else "WARNING", f"AP periods={periods}; Vm_Int maxima={extrema}.")
    else:
        add("RV2 membrane-leak-rate control", "NOT EVALUATED", "RV2 sweep was not fully executed.")

    rv3 = completed_rows("32_rv3_adaptation_")
    if len(rv3) == 3:
        vw = [row.get("Vw_max") for row in rv3 if isinstance(row.get("Vw_max"),(int,float))]
        periods = [row.get("AP_mean_period_s") for row in rv3 if isinstance(row.get("AP_mean_period_s"),(int,float))]
        responds = (len(vw)==3 and max(vw)-min(vw)>0.01) or (len(periods)>=2 and max(periods)-min(periods)>1e-4)
        add("RV3 adaptation control", "PASS" if responds else "WARNING", f"Vw maxima={vw}; AP periods={periods}.")
    else:
        add("RV3 adaptation control", "NOT EVALUATED", "RV3 sweep was not fully executed.")

    rv5 = completed_rows("33_rv5_synapse_decay_")
    if len(rv5) == 3:
        states = [row.get("V_Syn_State_end") for row in rv5 if isinstance(row.get("V_Syn_State_end"),(int,float))]
        responds = len(states)==3 and max(states)-min(states)>0.005
        add("RV5 synaptic-decay control", "PASS" if responds else "WARNING", f"V_Syn_State end values={states}.")
    else:
        add("RV5 synaptic-decay control", "NOT EVALUATED", "RV5 sweep was not fully executed.")

    synapse_ok = True
    synapse_evidence = []
    synapse_complete = True
    for channel in range(1,5):
        pot = channel + 5
        trio = [by_name.get(f"40_rv{pot}_syn{channel}_{level}") for level in ("low","mid","high")]
        if not all(row and row.get("status") == "passed" for row in trio):
            synapse_complete = False
            continue
        maxima = [row.get("Vm_Int_max") for row in trio]
        states = [row.get("V_Syn_State_max") for row in trio]
        monotonic = all(isinstance(x,(int,float)) for x in maxima) and maxima[0] <= maxima[1] <= maxima[2]
        synapse_ok = synapse_ok and monotonic
        synapse_evidence.append(f"Syn{channel} Vm_Int max low/mid/high={maxima}; state max={states}")
    if synapse_complete:
        add("Synaptic sign, midpoint and RV6-RV9 weight controls", "PASS" if synapse_ok else "WARNING", "; ".join(synapse_evidence), "Direction is checked at the physical membrane response; exact biological equivalence is not claimed.")
    else:
        add("Synaptic sign, midpoint and RV6-RV9 weight controls", "NOT EVALUATED", "All four low/mid/high synaptic control triplets were not executed successfully.")

    temperature_rows = completed_rows("50_temperature_")
    if len(temperature_rows) == 3:
        valid = all(isinstance(row.get("VDD_end"),(int,float)) and row.get("VDD_end") > 1.8 for row in temperature_rows)
        add("Temperature sweep", "PASS" if valid else "WARNING", "; ".join(f"{row.get('test_name')}: VDD_end={row.get('VDD_end')}, AP={row.get('AP_rising_edges')}" for row in temperature_rows), "Portable model temperature laws are incomplete.")
    else:
        add("Temperature sweep", "NOT EVALUATED", "All temperature decks were not executed successfully.")

    tolerance_rows = completed_rows("60_tolerance_seed_")
    if len(tolerance_rows) == 5:
        failed_function = [row.get("test_name") for row in tolerance_rows if not isinstance(row.get("VDD_end"),(int,float)) or row.get("VDD_end") < 1.8]
        add("Component-tolerance seeds", "PASS" if not failed_function else "WARNING", f"Five deterministic seeds executed; rail-level failures={failed_function}.", "Five seeds are a regression screen, not a production-yield Monte Carlo study.")
    else:
        add("Component-tolerance seeds", "NOT EVALUATED", "All deterministic tolerance seeds were not executed successfully.")

    add("ESD and sustained external-fault survival", "NOT CLAIMED", "Protection devices are represented only for normal-signal loading and limited clamp-transient exploration.", "No SPICE result from this suite constitutes IEC ESD qualification or sustained-overvoltage survival proof.")

    verdict_csv = report_dir / "validation_verdict.csv"
    with verdict_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_lock_sha256","block","status","evidence","limitation"])
        writer.writeheader(); writer.writerows(verdicts)
    verdict_md = report_dir / "validation_verdict.md"
    lines = ["# LIFeling SPICE validation verdict", "", f"Source lock SHA-256: `{source_lock}`", "", "| Block | Status | Evidence | Limitation |", "|---|---|---|---|"]
    for row in verdicts:
        lines.append(f"| {row['block']} | **{row['status']}** | {row['evidence'].replace('|','\\|')} | {row['limitation'].replace('|','\\|')} |")
    verdict_md.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return summary_csv, verdict_csv, verdict_md


def run_deck(
    deck_path: Path,
    cfg: DeckConfig,
    source_lock_sha: str,
    executable: str = "auto",
    timeout_seconds: float | None = 180.0,
) -> RunResult:
    deck_path = Path(deck_path)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = cfg.output_dir / f"{safe_name(cfg.test_name)}.ngspice.log"
    wrdata_path = cfg.output_dir / f"{safe_name(cfg.test_name)}.wrdata.txt"
    parsed_path = cfg.output_dir / f"{safe_name(cfg.test_name)}.csv"
    diag_path = cfg.output_dir / f"{safe_name(cfg.test_name)}.diagnostics.json"
    plot_path = cfg.output_dir / f"{safe_name(cfg.test_name)}.png"
    binary = find_ngspice(executable)
    if binary is None:
        result = RunResult(cfg.test_name, "not_executed", source_lock_sha, str(deck_path), str(log_path), str(wrdata_path), str(parsed_path), str(diag_path), str(plot_path), "not installed", None, "ngspice binary was not found")
        diag_path.write_text(json.dumps(dataclasses.asdict(result), indent=2), encoding="utf-8")
        return result
    version = ngspice_version(binary)

    # A new run must never inherit diagnostics or plots from an earlier suite.
    # Stale files previously made interrupted runs appear more complete than
    # they actually were.
    for stale_path in (log_path, wrdata_path, parsed_path, diag_path, plot_path):
        if stale_path.exists():
            stale_path.unlink()

    command = [binary, "-b", "-o", str(log_path.resolve()), str(deck_path.resolve())]
    try:
        completed = subprocess.run(
            command,
            cwd=deck_path.parent,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        log_tail = ""
        if log_path.exists():
            log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        message = (
            f"ngspice timed out after {timeout_seconds:g} s; "
            f"command={command!r}; log_tail={log_tail!r}"
        )
        result = RunResult(
            cfg.test_name, "failed", source_lock_sha, str(deck_path), str(log_path),
            str(wrdata_path), str(parsed_path), str(diag_path), str(plot_path),
            version, None, message,
        )
        diag_path.write_text(json.dumps(dataclasses.asdict(result), indent=2), encoding="utf-8")
        return result

    if completed.returncode != 0 or not wrdata_path.exists():
        message = f"ngspice returned {completed.returncode}; stdout={completed.stdout[-1000:]}; stderr={completed.stderr[-1000:]}"
        result = RunResult(cfg.test_name, "failed", source_lock_sha, str(deck_path), str(log_path), str(wrdata_path), str(parsed_path), str(diag_path), str(plot_path), version, completed.returncode, message)
        diag_path.write_text(json.dumps(dataclasses.asdict(result), indent=2), encoding="utf-8")
        return result

    try:
        trace_names = [name for name in cfg.save_nets]
        data = _read_wrdata(wrdata_path, trace_names)
        with parsed_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            keys = list(data)
            writer.writerow(keys)
            writer.writerows(zip(*(data[key] for key in keys)))
        import hashlib
        deck_sha = hashlib.sha256(deck_path.read_bytes()).hexdigest()
        diag = diagnostics(data, cfg, source_lock_sha, deck_sha)
        diag.update({"status": "passed", "ngspice_version": version, "python_version": platform.python_version(), "operating_system": platform.platform()})
        diag_path.write_text(json.dumps(diag, indent=2), encoding="utf-8")
        plot = _plot_run(data, cfg, plot_path)
    except Exception as exc:
        result = RunResult(
            cfg.test_name, "failed", source_lock_sha, str(deck_path), str(log_path),
            str(wrdata_path), str(parsed_path), str(diag_path), str(plot_path),
            version, completed.returncode, f"post-processing failed: {exc}",
        )
        diag_path.write_text(json.dumps(dataclasses.asdict(result), indent=2), encoding="utf-8")
        return result

    return RunResult(cfg.test_name, "passed", source_lock_sha, str(deck_path), str(log_path), str(wrdata_path), str(parsed_path), str(diag_path), plot, version, completed.returncode, "completed")
