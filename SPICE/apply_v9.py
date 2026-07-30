#!/usr/bin/env python3
"""Apply LIFeling SPICE cold-start separation patch v9.

Run from the SPICE directory:
    python -B .\apply_v9.py

The full-board cold-start case is changed from the multi-timescale dynamic-SOC
battery model to a fixed-SOC Thevenin equivalent with a controlled voltage
ramp.  The dynamic CR2032 subcircuit is retained for later battery-only
validation; it is not suitable for inclusion in a 1 MHz full-board switching
startup deck.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path.cwd()


def read(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"Missing required file: {path}")
    return path.read_text(encoding="utf-8")


def write_changed(path: Path, old: str, new: str, label: str) -> None:
    if new == old:
        print(f"SKIP  {label}: already correct")
        return
    backup = path.with_suffix(path.suffix + ".v9.bak")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(new, encoding="utf-8")
    print(f"PATCH {label}: {path}")


# 1. Add an optional supply ramp to DeckConfig and coin_fixed generation.
deck = ROOT / "lifeling_spice" / "deck.py"
text = read(deck)
old = text
if "battery_rise_time:" not in text:
    marker = "    battery_soc: float = 1.0\n"
    if marker not in text:
        raise SystemExit("Cannot locate battery_soc in lifeling_spice/deck.py")
    text = text.replace(marker, marker + "    battery_rise_time: str | None = None\n", 1)

plain = '        lines.append(f"VBT1_OC N_BT1_OC {minus} DC {cfg.battery_voltage:.9g}")\n        lines.append(f"RBT1_INT N_BT1_OC {plus} {cfg.battery_resistance:.9g}")'
ramped = '''        if cfg.battery_rise_time:
            lines.append(
                f"VBT1_OC N_BT1_OC {minus} PWL(0 0 {cfg.battery_rise_time} {cfg.battery_voltage:.9g})"
            )
        else:
            lines.append(f"VBT1_OC N_BT1_OC {minus} DC {cfg.battery_voltage:.9g}")
        lines.append(f"RBT1_INT N_BT1_OC {plus} {cfg.battery_resistance:.9g}")'''
if "PWL(0 0 {cfg.battery_rise_time}" not in text:
    if plain not in text:
        raise SystemExit("Cannot locate coin_fixed source generation in lifeling_spice/deck.py")
    text = text.replace(plain, ramped, 1)
write_changed(deck, old, text, "add optional fixed-battery startup ramp")


# 2. Convert N06 to a fixed-SOC Thevenin cold-start case.
spice = ROOT / "Spice.py"
text = read(spice)
old = text
pattern = re.compile(
    r'DeckConfig\(\s*test_name\s*=\s*["\'](?:N_)?06_cold_start_dynamic_battery["\'](?P<body>.*?)\),',
    re.DOTALL,
)
match = pattern.search(text)
if not match:
    nearby = [line for line in text.splitlines() if "06_cold_start_dynamic_battery" in line]
    raise SystemExit("Cannot locate N06 DeckConfig in Spice.py:\n" + "\n".join(nearby[:10]))
block = match.group(0)
new = block
new = re.sub(r'supply_mode\s*=\s*["\']coin_dynamic["\']', 'supply_mode="coin_fixed"', new, count=1)
new = re.sub(r'battery_voltage\s*=\s*3(?:\.0+)?', 'battery_voltage=2.92125', new, count=1)
new = re.sub(r'\s*battery_soc\s*=\s*0\.75\s*,?', '', new, count=1)
if "battery_rise_time=" not in new:
    anchor = re.search(r'battery_resistance\s*=\s*35(?:\.0+)?\s*,', new)
    if not anchor:
        raise SystemExit("Cannot locate N06 battery_resistance argument")
    new = new[:anchor.end()] + ' battery_rise_time="1m",' + new[anchor.end():]
if 'supply_mode="coin_fixed"' not in new:
    raise SystemExit("N06 supply mode was not converted to coin_fixed")
if 'battery_voltage=2.92125' not in new:
    raise SystemExit("N06 equivalent OCV was not installed")
text = text[:match.start()] + new + text[match.end():]
write_changed(spice, old, text, "separate full-board cold start from dynamic SOC model")


# 3. Update the runtime regression to describe the new scope accurately.
test_runtime = ROOT / "tests" / "test_dynamic_battery_runtime.py"
text = read(test_runtime)
old = text
text = text.replace('self.assertEqual(cfg.supply_mode, "coin_dynamic")', 'self.assertEqual(cfg.supply_mode, "coin_fixed")')
if 'self.assertEqual(cfg.battery_voltage, 2.92125)' not in text:
    target = '        self.assertEqual(cfg.supply_mode, "coin_fixed")\n'
    if target not in text:
        raise SystemExit("Cannot locate updated N06 supply-mode assertion")
    text = text.replace(
        target,
        target
        + '        self.assertAlmostEqual(cfg.battery_voltage, 2.92125, places=6)\n'
        + '        self.assertEqual(cfg.battery_resistance, 35.0)\n'
        + '        self.assertEqual(cfg.battery_rise_time, "1m")\n',
        1,
    )
write_changed(test_runtime, old, text, "update cold-start runtime regression")


# 4. Add a deck-level regression proving N06 uses the ramped Thevenin source.
new_test = ROOT / "tests" / "test_cold_start_thevenin.py"
new_text = '''from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Spice
from lifeling_spice.deck import build_deck
from lifeling_spice.design import parse_netlist


class ColdStartTheveninRegression(unittest.TestCase):
    def test_n06_uses_ramped_fixed_soc_thevenin_source(self):
        design = parse_netlist(ROOT / "sources" / "LIFeling.net")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = next(
                c for c in Spice.test_configs(Path(tmp), "hybrid")
                if c.test_name == "06_cold_start_dynamic_battery"
            )
            deck, _ = build_deck(design, cfg, ROOT, "manifest-test")
        self.assertIn("VBT1_OC N_BT1_OC 0 PWL(0 0 1m 2.92125)", deck)
        self.assertIn("RBT1_INT N_BT1_OC P_BATT 35", deck)
        self.assertNotIn("XBT1 P_BATT 0 LIF_CR2032_DYNAMIC", deck)


if __name__ == "__main__":
    unittest.main()
'''
previous = new_test.read_text(encoding="utf-8") if new_test.exists() else ""
write_changed(new_test, previous, new_text, "install N06 Thevenin deck regression")

print("\nPatch v9 applied successfully.")
print("The dynamic CR2032 model remains packaged, but N06 now tests full-board startup at fixed SOC.")
print("Next: python -B -m unittest discover -s .\\tests -v")
