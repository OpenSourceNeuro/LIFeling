"""Download official model packages and inspect actual declarations without assuming pin order."""
from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from .models import discover_model_files, inspect_model_cards, inspect_subcircuits, sha256_file


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if destination not in target.parents and target != destination:
            raise RuntimeError(f"Unsafe archive member: {member.filename}")
    archive.extractall(destination)


def fetch_vendor_models(registry: dict[str, Any], project_root: Path, *, overwrite: bool = False) -> Path:
    root = Path(project_root)
    download_root = root / "models" / "downloads"
    vendor_root = root / "models" / "vendor"
    download_root.mkdir(parents=True, exist_ok=True)
    vendor_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for value, family in registry.get("families", {}).items():
        url = family.get("download_url")
        if not url:
            continue
        package_name = family.get("package_name", value)
        extension = ".zip" if ".ZIP" in package_name.upper() or "/zip/" in url else Path(url).suffix or ".bin"
        filename = value.replace("/", "_").replace(" ", "_") + extension
        destination = download_root / filename
        record: dict[str, Any] = {"value": value, "url": url, "package_name": package_name, "downloaded_file": str(destination.relative_to(root)), "status": ""}
        try:
            if overwrite or not destination.exists():
                request = urllib.request.Request(url, headers={"User-Agent": "LIFeling-SPICE-model-audit/2026.07"})
                with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
            record["sha256"] = sha256_file(destination)
            record["size_bytes"] = destination.stat().st_size
            extraction = vendor_root / value.replace("/", "_").replace(" ", "_")
            if zipfile.is_zipfile(destination):
                extraction.mkdir(parents=True, exist_ok=True)
                _safe_extract(zipfile.ZipFile(destination), extraction)
            else:
                extraction.parent.mkdir(parents=True, exist_ok=True)
                target = extraction.with_suffix(destination.suffix)
                shutil.copy2(destination, target)
                extraction = target
            declarations = []
            model_cards = []
            for model_file in discover_model_files(extraction):
                for declaration in inspect_subcircuits(model_file):
                    declarations.append({
                        "file": str(model_file.relative_to(root)),
                        "sha256": sha256_file(model_file),
                        "line": declaration.line,
                        "subcircuit": declaration.name,
                        "terminal_order": list(declaration.terminals),
                    })
                for declaration in inspect_model_cards(model_file):
                    model_cards.append({
                        "file": str(model_file.relative_to(root)),
                        "sha256": sha256_file(model_file),
                        "line": declaration.line,
                        "model_card": declaration.name,
                        "device_type": declaration.device_type,
                    })
            record["declarations"] = declarations
            record["model_cards"] = model_cards
            record["status"] = "downloaded_and_inspected"
            record["compatibility_gate"] = "unapproved until a smoke test passes and terminal order is locked in model_registry.json"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
        records.append(record)
    output = root / "reports" / "vendor_model_download_inspection.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return output
