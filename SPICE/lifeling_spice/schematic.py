"""Placed-symbol cross-checks against the attached KiCad schematic."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .design import Design
from .sexpr import iter_blocks


def _placed_symbols(path: Path) -> dict[str, dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    symbols: dict[str, dict[str, str]] = {}
    for block in iter_blocks(text, "symbol"):
        # Library definitions use `(symbol "name" ...)`; placed symbols carry a lib_id.
        if not re.search(r"\(lib_id\s+\"", block):
            continue
        # KiCad strings may contain escaped quotes, notably Sim.Params values such as
        # `type=\"R\" model=\"Battery_Cell\"`.  A plain `[^"]*` regex
        # truncates those values and creates false source-drift warnings.
        quoted = r'((?:\\.|[^"\\])*)'

        def unescape_kicad_string(value: str) -> str:
            # KiCad uses conventional backslash escapes in quoted S-expressions.
            # JSON decoding gives us an exact, compact decoder for those strings.
            try:
                return json.loads(f'"{value}"')
            except json.JSONDecodeError:
                return value.replace(r'\"', '"').replace(r'\\', '\\')

        properties = {
            unescape_kicad_string(name): unescape_kicad_string(value)
            for name, value in re.findall(
                rf'\(property\s+"{quoted}"\s+"{quoted}"', block
            )
        }
        reference = properties.get("Reference", "")
        if reference:
            symbols[reference] = {
                "reference": reference,
                "value": properties.get("Value", ""),
                "footprint": properties.get("Footprint", ""),
                "datasheet": properties.get("Datasheet", ""),
                "lib_id": (re.search(r"\(lib_id\s+\"([^\"]+)\"", block).group(1)
                           if re.search(r"\(lib_id\s+\"([^\"]+)\"", block) else ""),
            }
    return symbols


def _footprint_tail(value: str) -> str:
    return value.split(":", 1)[-1]


def write_schematic_crosscheck(path: Path, design: Design, report_dir: Path) -> dict[str, Any]:
    path = Path(path)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    placed = _placed_symbols(path)
    missing = sorted(set(design.components) - set(placed))
    value_mismatches = []
    footprint_mismatches = []
    for reference, component in design.components.items():
        symbol = placed.get(reference)
        if not symbol:
            continue
        # BT1's exported netlist value is overwritten by a Sim.Params expression; retain this visibly.
        if component.value != symbol["value"]:
            value_mismatches.append({
                "reference": reference,
                "netlist_value": component.value,
                "schematic_value": symbol["value"],
                "known_sim_value_override": reference == "BT1" and "model=\"Battery_Cell\"" in component.value,
            })
        if _footprint_tail(component.footprint) != _footprint_tail(symbol["footprint"]):
            footprint_mismatches.append({
                "reference": reference,
                "netlist_footprint": component.footprint,
                "schematic_footprint": symbol["footprint"],
            })
    # Power symbols and power flags are placed schematic symbols but are not
    # ordinary BOM/netlist components.  Excluding them keeps this list focused
    # on genuinely unexpected functional references.
    unexpected = sorted(
        reference
        for reference in set(placed) - set(design.components)
        if not reference.startswith(("#PWR", "#FLG"))
    )
    result = {
        "schematic": str(path),
        "placed_symbol_count": len(placed),
        "netlist_component_count": len(design.components),
        "missing_netlist_references_in_schematic": missing,
        "unexpected_schematic_references_not_in_netlist": unexpected,
        "value_mismatches": value_mismatches,
        "footprint_mismatches": footprint_mismatches,
        "blocking_failures": len(missing) + len(footprint_mismatches),
        "warnings": len(value_mismatches),
    }
    json_path = report_dir / "schematic_crosscheck.json"
    md_path = report_dir / "schematic_crosscheck.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# KiCad schematic / exported-netlist cross-check", "",
        f"Placed schematic symbols: **{len(placed)}**; exported netlist components: **{len(design.components)}**.", "",
        f"Blocking cross-check failures: **{result['blocking_failures']}**; metadata warnings: **{result['warnings']}**.", "",
    ]
    if missing:
        lines += ["## Missing references", "", ", ".join(f"`{ref}`" for ref in missing), ""]
    if footprint_mismatches:
        lines += ["## Footprint mismatches", "", "| Reference | Netlist | Schematic |", "|---|---|---|"]
        for row in footprint_mismatches:
            lines.append(f"| `{row['reference']}` | `{row['netlist_footprint']}` | `{row['schematic_footprint']}` |")
        lines.append("")
    if value_mismatches:
        lines += ["## Value metadata mismatches", "", "| Reference | Netlist value | Schematic value | Interpretation |", "|---|---|---|---|"]
        for row in value_mismatches:
            interpretation = "Known KiCad simulation-value override; electrically modelled as CR2032 from reference, symbol and footprint metadata." if row["known_sim_value_override"] else "Review required."
            lines.append(f"| `{row['reference']}` | `{row['netlist_value'].replace('|','\\|')}` | `{row['schematic_value'].replace('|','\\|')}` | {interpretation} |")
        lines.append("")
    if not missing and not footprint_mismatches:
        lines += ["Every exported reference is present as a placed schematic symbol and all exported footprints match the placed-symbol footprints after library-prefix normalization.", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {**result, "json": str(json_path), "markdown": str(md_path)}
