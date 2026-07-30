#!/usr/bin/env python3
"""Resume/repair the partially applied LIFeling SPICE runtime patch v8.

Run from the SPICE directory:
    python -B .\apply_v8_1.py

This script is intentionally idempotent. It accepts the partial state left by
apply_v8.py, patches the specialised N06 suite configuration using structural
matching, updates the old static assertion, and adds the single-suite-case CLI.
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


def write_changed(path: Path, old_text: str, new_text: str, label: str) -> None:
    if new_text == old_text:
        print(f"SKIP  {label}: already correct")
        return
    backup = path.with_suffix(path.suffix + ".v8_1.bak")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(new_text, encoding="utf-8")
    print(f"PATCH {label}: {path}")


# 1. Verify/finish the dynamic-battery model changes.
model = ROOT / "models" / "portable" / "lifeling_portable_models.lib"
text = read(model)
original = text
text = text.replace(
    "BOCV NOCV N V={2.55+0.50*max(0,min(1,V(NSOC,N)))-0.06*(1-max(0,min(1,V(NSOC,N))))^2}",
    "BOCV NOCV N V={2.55+0.50*V(NSOC,N)-0.06*(1-V(NSOC,N))^2}",
)
text = text.replace("BSOC NSOC N I={I(VSENSE)}", "FSOC NSOC N VSENSE 1")
if "BOCV NOCV N V={2.55+0.50*V(NSOC,N)-0.06*(1-V(NSOC,N))^2}" not in text:
    raise SystemExit("Could not verify the simplified BOCV line in the dynamic battery model.")
if "FSOC NSOC N VSENSE 1" not in text:
    raise SystemExit("Could not verify the FSOC controlled source in the dynamic battery model.")
write_changed(model, original, text, "finish dynamic-battery model optimisation")


# 2. Patch N06 structurally, regardless of one-line/multiline formatting.
spice = ROOT / "Spice.py"
text = read(spice)
original = text
pattern = re.compile(
    r'DeckConfig\(\s*test_name\s*=\s*["\'](?:N_)?06_cold_start_dynamic_battery["\'](?P<body>.*?)\),',
    re.DOTALL,
)
match = pattern.search(text)
if not match:
    # Fallback: show nearby source to make any future mismatch actionable.
    nearby = [line for line in text.splitlines() if "cold_start_dynamic_battery" in line]
    raise SystemExit(
        "Cannot locate the N06 DeckConfig structurally in Spice.py. Matching lines:\n"
        + "\n".join(nearby[:10])
    )
block = match.group(0)
new_block = re.sub(r'tstop\s*=\s*["\'][^"\']+["\']', 'tstop="50m"', block, count=1)
if new_block == block and 'tstop="50m"' not in block and "tstop='50m'" not in block:
    raise SystemExit("Located N06, but could not identify its tstop argument.")
if "save_nets=" not in new_block:
    insertion = 'save_nets=["VDD", "V_Boost", "VREF_2V048", "VREF_1V024", "Vm_Int", "AP", "Spike_Out"], '
    marker = "**{"
    pos = new_block.find(marker)
    if pos < 0:
        # Insert before the final closing '),'.
        pos = new_block.rfind("),")
    new_block = new_block[:pos] + insertion + new_block[pos:]
text = text[:match.start()] + new_block + text[match.end():]

# 3. Add exact suite-case filtering if absent.
if "--suite-test-name" not in text:
    parser_pattern = re.compile(
        r'(?P<indent>\s*)parser\.add_argument\(["\']--test-name["\'],\s*default=["\']full_operating["\']\)'
    )
    pm = parser_pattern.search(text)
    if not pm:
        raise SystemExit("Could not locate the --test-name parser argument in Spice.py.")
    indent = pm.group("indent")
    addition = (
        pm.group(0)
        + "\n"
        + indent
        + 'parser.add_argument("--suite-test-name", help="With --suite, run only the named specialised suite configuration.")'
    )
    text = text[:pm.start()] + addition + text[pm.end():]

if "if args.suite_test_name:" not in text:
    config_line = re.compile(
        r'(?P<indent>^[ \t]*)configs\s*=\s*test_configs\(generated_dir,\s*args\.profile\)\s*if\s*args\.suite\s*else\s*\[DeckConfig\(profile=args\.profile,\s*test_name=args\.test_name,\s*output_dir=generated_dir\)\]\s*$',
        re.MULTILINE,
    )
    cm = config_line.search(text)
    if not cm:
        raise SystemExit("Could not locate the suite configuration assignment in Spice.py.")
    indent = cm.group("indent")
    filter_block = (
        cm.group(0)
        + "\n"
        + indent
        + "if args.suite_test_name:\n"
        + indent
        + "    if not args.suite:\n"
        + indent
        + '        raise SystemExit("--suite-test-name requires --suite")\n'
        + indent
        + "    configs = [cfg for cfg in configs if cfg.test_name == args.suite_test_name]\n"
        + indent
        + "    if not configs:\n"
        + indent
        + "        available = ", 
    )
    # Build the last two lines separately to avoid quoting accidents.
    filter_block = (
        cm.group(0)
        + "\n"
        + indent + "if args.suite_test_name:\n"
        + indent + "    if not args.suite:\n"
        + indent + '        raise SystemExit("--suite-test-name requires --suite")\n'
        + indent + "    configs = [cfg for cfg in configs if cfg.test_name == args.suite_test_name]\n"
        + indent + "    if not configs:\n"
        + indent + '        available = ", ".join(cfg.test_name for cfg in test_configs(generated_dir, args.profile))\n'
        + indent + '        raise SystemExit(f"Unknown suite test {args.suite_test_name!r}. Available tests: {available}")'
    )
    text = text[:cm.start()] + filter_block + text[cm.end():]

write_changed(spice, original, text, "bound N06 runtime and add exact suite-case selection")


# 4. Update the old static regression that caused the reported failure.
test_static = ROOT / "tests" / "test_static.py"
text = read(test_static)
original = text
text = text.replace(
    'self.assertIn("BSOC NSOC N I={I(VSENSE)}", block)',
    'self.assertIn("FSOC NSOC N VSENSE 1", block)',
)
if 'self.assertIn("FSOC NSOC N VSENSE 1", block)' not in text:
    raise SystemExit("Could not verify the updated dynamic-battery assertion in tests/test_static.py.")
write_changed(test_static, original, text, "update dynamic-battery static regression")


# 5. Add/replace runtime regression tests so they reflect the intended state.
new_test = ROOT / "tests" / "test_dynamic_battery_runtime.py"
new_test_text = '''from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Spice


class DynamicBatteryRuntimeRegression(unittest.TestCase):
    def test_dynamic_battery_uses_linear_controlled_soc_current(self):
        text = (ROOT / "models" / "portable" / "lifeling_portable_models.lib").read_text(encoding="utf-8")
        block = text.split(".subckt LIF_CR2032_DYNAMIC", 1)[1].split(".ends LIF_CR2032_DYNAMIC", 1)[0]
        self.assertIn("FSOC NSOC N VSENSE 1", block)
        self.assertNotIn("max(0,min(1,V(NSOC,N)))", block)

    def test_cold_start_has_bounded_horizon_and_focused_outputs(self):
        cfg = next(c for c in Spice.test_configs(ROOT / "generated", "hybrid") if c.test_name in {"06_cold_start_dynamic_battery", "N_06_cold_start_dynamic_battery"})
        self.assertEqual(cfg.tstop, "50m")
        self.assertEqual(cfg.supply_mode, "coin_dynamic")
        self.assertEqual(cfg.save_nets, ["VDD", "V_Boost", "VREF_2V048", "VREF_1V024", "Vm_Int", "AP", "Spike_Out"])


if __name__ == "__main__":
    unittest.main()
'''
old = new_test.read_text(encoding="utf-8") if new_test.exists() else ""
write_changed(new_test, old, new_test_text, "install dynamic-battery runtime regressions")

print("\nPatch v8.1 applied successfully.")
print("Next: python -B -m unittest discover -s .\\tests -v")
