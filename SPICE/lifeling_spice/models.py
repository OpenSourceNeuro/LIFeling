"""Model registry loading, source inspection, and strict coverage checks."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .design import Design


MODEL_EXTENSIONS = {".lib", ".cir", ".mod", ".model", ".sp", ".spi", ".txt", ".tsm"}


@dataclasses.dataclass(frozen=True)
class SubcircuitDeclaration:
    name: str
    terminals: tuple[str, ...]
    path: Path
    line: int


@dataclasses.dataclass(frozen=True)
class ModelCardDeclaration:
    name: str
    device_type: str
    path: Path
    line: int


@dataclasses.dataclass
class FamilyResolution:
    value: str
    references: list[str]
    category: str
    manufacturer: str
    exact_part: str
    selected_path: str
    selected_sha256: str
    subcircuit_name: str
    subcircuit_terminals: list[str]
    model_status: str
    confidence: str
    notes: str
    source_page: str
    package_name: str
    model_version_date: str
    wrapper_required: str
    simulator: str
    encrypted: Any
    ngspice_compatibility: str
    redistribution: str


def load_registry(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_model_files(root: Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in MODEL_EXTENSIONS)


def inspect_subcircuits(path: Path) -> list[SubcircuitDeclaration]:
    declarations: list[SubcircuitDeclaration] = []
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    logical: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("+") and logical:
            prior_number, prior = logical[-1]
            logical[-1] = (prior_number, prior + " " + line.lstrip()[1:].strip())
        else:
            logical.append((number, line.strip()))
    for number, line in logical:
        match = re.match(r"(?i)^\.subckt\s+(\S+)\s*(.*)$", line)
        if not match:
            continue
        name = match.group(1)
        tail = match.group(2)
        tail = re.split(r"(?i)\bparams?\s*:", tail, maxsplit=1)[0]
        terminals = tuple(token for token in tail.split() if token and not token.startswith("*"))
        declarations.append(SubcircuitDeclaration(name=name, terminals=terminals, path=Path(path), line=number))
    return declarations


def inspect_model_cards(path: Path) -> list[ModelCardDeclaration]:
    declarations: list[ModelCardDeclaration] = []
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"(?i)^\s*\.model\s+(\S+)\s+(\S+)", line)
        if match:
            declarations.append(ModelCardDeclaration(match.group(1), match.group(2).lstrip("(").upper(), Path(path), number))
    return declarations


def _candidate_paths(project_root: Path, family: dict[str, Any]) -> list[Path]:
    output: list[Path] = []
    for candidate in family.get("local_candidates", []):
        path = project_root / candidate
        output.extend(discover_model_files(path))
    return list(dict.fromkeys(path.resolve() for path in output))


def resolve_families(design: Design, registry: dict[str, Any], project_root: Path, profile: str) -> list[FamilyResolution]:
    families = registry["families"]
    present_values: dict[str, list[str]] = {}
    for reference, component in design.components.items():
        present_values.setdefault(component.value, []).append(reference)

    results: list[FamilyResolution] = []
    for value, family in families.items():
        references = sorted(present_values.get(value, []))
        if not references and value not in {"CR2032", "ANR3015T2R2M"}:
            continue
        if value == "CR2032":
            references = ["BT1"] if "BT1" in design.components else []
        if value == "ANR3015T2R2M":
            references = ["L1"] if "L1" in design.components else []
        candidates = _candidate_paths(project_root, family)
        declarations: list[SubcircuitDeclaration] = []
        model_cards: list[ModelCardDeclaration] = []
        selected: Path | None = None
        selected_decl: SubcircuitDeclaration | None = None
        selected_model: ModelCardDeclaration | None = None
        names = {name.upper() for name in family.get("subcircuit_candidates", [])}
        model_names = {name.upper() for name in family.get("model_card_candidates", family.get("subcircuit_candidates", []))}
        for path in candidates:
            for declaration in inspect_subcircuits(path):
                declarations.append(declaration)
                if declaration.name.upper() in names and selected_decl is None and selected_model is None:
                    selected = path
                    selected_decl = declaration
            for declaration in inspect_model_cards(path):
                model_cards.append(declaration)
                if declaration.name.upper() in model_names and selected_decl is None and selected_model is None:
                    selected = path
                    selected_model = declaration
        portable = str(family.get("portable_model", ""))
        exact_mismatch = value in {"MMBT3904", "1N4148WS"} and selected is not None and "provided" in selected.parts

        if selected_decl:
            status = "installed vendor/model source"
            confidence = "high" if not exact_mismatch else "medium"
            note = f"Inspected .SUBCKT at {selected_decl.path.name}:{selected_decl.line}."
            if exact_mismatch:
                status = "installed comparison model; portable fallback selected"
                note += " The supplied model manufacturer does not match the ordered/netlist manufacturer and is not instantiated by the hybrid deck."
        elif selected_model:
            status = "installed vendor/model card"
            confidence = "high" if not exact_mismatch else "medium"
            note = f"Inspected .MODEL {selected_model.name} ({selected_model.device_type}) at {selected_model.path.name}:{selected_model.line}."
            if exact_mismatch:
                status = "installed comparison model; portable fallback selected"
                note += " The supplied model manufacturer does not match the ordered/netlist manufacturer and is not instantiated by the hybrid deck."
        elif candidates and not names and not model_names:
            selected = candidates[0]
            status = "installed model card or non-subcircuit source"
            confidence = "medium"
            note = "Installed model file found; no named .SUBCKT was required or declared."
        else:
            status = "portable fallback"
            confidence = "medium" if portable else "unresolved"
            note = "Official package is not installed/verified; using documented portable model." if portable else "No usable source found."

        approved_order = family.get("declared_terminal_order")
        if selected_decl is not None and approved_order is not None and len(selected_decl.terminals) != len(approved_order):
            status = "unresolved"
            confidence = "none"
            note = f"Terminal-count mismatch: inspected {len(selected_decl.terminals)} terminals but approved wrapper expects {len(approved_order)}."

        if profile == "vendor":
            if selected is None:
                status = "unresolved"
                confidence = "none"
                note = "Strict vendor profile requires an installed official/exact model."
            elif family.get("declared_terminal_order") is None and selected_decl is not None:
                status = "unresolved"
                confidence = "none"
                note = "Actual .SUBCKT was found but no approved adapter terminal order is locked in model_registry.json."
            elif exact_mismatch:
                status = "unresolved"
                confidence = "none"
                note = "Strict vendor profile rejects supplied cross-manufacturer model."

        results.append(
            FamilyResolution(
                value=value,
                references=references,
                category=family.get("category", "unresolved"),
                manufacturer=family.get("manufacturer", ""),
                exact_part=family.get("exact_part", value),
                selected_path=str(selected.relative_to(project_root)) if selected else "",
                selected_sha256=sha256_file(selected) if selected else "",
                subcircuit_name=selected_decl.name if selected_decl else "",
                subcircuit_terminals=list(selected_decl.terminals) if selected_decl else [],
                model_status=status,
                confidence=confidence,
                notes=note,
                source_page=family.get("model_source_page", family.get("product_page", "")),
                package_name=family.get("package_name", ""),
                model_version_date=family.get("model_version_date", "not established"),
                wrapper_required=family.get("wrapper", ""),
                simulator=family.get("simulator", ""),
                encrypted=family.get("encrypted"),
                ngspice_compatibility=family.get("ngspice_compatibility", ""),
                redistribution=family.get("redistribution", ""),
            )
        )
    return results




VENDOR_REQUIRED_SUBCIRCUITS = {
    "LIF_TLV7041_OD", "LIF_TLV7031_PP", "LIF_TLV9001", "LIF_TLV9041",
    "LIF_TS5A3166", "LIF_REF3020", "LIF_TPD1E05U06",
    "LIF_CR2032_DYNAMIC", "LIF_TPS610995_SWITCHING",
}
VENDOR_REQUIRED_MODEL_CARDS = {
    "LIF_MMBT3904", "LIF_BSS138", "LIF_BAT54WS", "LIF_RB521S30",
    "LIF_1N4148WS", "LIF_LED_RED", "LIF_LED_GREEN", "LIF_LED_BLUE",
}

def validate_vendor_adapter_library(path: Path) -> tuple[set[str], set[str]]:
    """Return missing wrapper subcircuits and model cards in the strict vendor adapter library."""
    path = Path(path)
    if not path.is_file():
        return set(VENDOR_REQUIRED_SUBCIRCUITS), set(VENDOR_REQUIRED_MODEL_CARDS)
    subcircuits = {item.name.upper() for item in inspect_subcircuits(path)}
    text = path.read_text(encoding="utf-8", errors="replace")
    models = {match.group(1).upper() for match in re.finditer(r"(?im)^\s*\.model\s+(\S+)", text)}
    return ({name for name in VENDOR_REQUIRED_SUBCIRCUITS if name.upper() not in subcircuits},
            {name for name in VENDOR_REQUIRED_MODEL_CARDS if name.upper() not in models})

def family_for_component(component_value: str, registry: dict[str, Any]) -> dict[str, Any] | None:
    return registry.get("families", {}).get(component_value)
