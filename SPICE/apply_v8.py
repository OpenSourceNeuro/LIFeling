#!/usr/bin/env python3
"""Apply LIFeling SPICE dynamic-battery runtime patch v8 in place.

Run from the SPICE directory:
    python -B .\apply_v8.py

The script makes guarded replacements and writes .v8.bak backups before
changing existing files.
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path.cwd()


def guarded_replace(path: Path, old: str, new: str, label: str) -> None:
    if not path.is_file():
        raise SystemExit(f"Missing required file: {path}")
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"SKIP  {label}: already applied")
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Cannot safely apply {label}: expected one matching block in {path}, found {count}."
        )
    backup = path.with_suffix(path.suffix + ".v8.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"PATCH {label}: {path}")


model = ROOT / "models" / "portable" / "lifeling_portable_models.lib"
guarded_replace(
    model,
    "BOCV NOCV N V={2.55+0.50*max(0,min(1,V(NSOC,N)))-0.06*(1-max(0,min(1,V(NSOC,N))))^2}",
    """* The cold-start deck is intentionally short, so SOC remains inside 0..1.\n* Avoid nested max()/min() here: they add non-smooth behavioural derivatives\n* inside the 1 MHz converter loop and make the deck impractically slow.\nBOCV NOCV N V={2.55+0.50*V(NSOC,N)-0.06*(1-V(NSOC,N))^2}""",
    "simplify dynamic-battery OCV expression",
)
guarded_replace(
    model,
    "BSOC NSOC N I={I(VSENSE)}",
    """* A current-controlled source is equivalent to the former behavioural\n* current expression but is substantially cheaper for ngspice to solve.\nFSOC NSOC N VSENSE 1""",
    "replace behavioural SOC current with F source",
)

spice = ROOT / "Spice.py"
guarded_replace(
    spice,
    'DeckConfig(test_name="06_cold_start_dynamic_battery", tstop="250m", tstep="5u", supply_mode="coin_dynamic", battery_voltage=3.0, battery_resistance=35.0, battery_soc=0.75, **{k:v for k,v in common.items() if k not in {"supply_mode","battery_voltage","battery_resistance"}}),',
    'DeckConfig(test_name="06_cold_start_dynamic_battery", tstop="50m", tstep="5u", supply_mode="coin_dynamic", battery_voltage=3.0, battery_resistance=35.0, battery_soc=0.75, save_nets=["VDD", "V_Boost", "VREF_2V048", "VREF_1V024", "Vm_Int", "AP", "Spike_Out"], **{k:v for k,v in common.items() if k not in {"supply_mode","battery_voltage","battery_resistance"}}),',
    "bound dynamic-battery cold-start horizon",
)
guarded_replace(
    spice,
    'configs = test_configs(generated_dir, args.profile) if args.suite else [DeckConfig(profile=args.profile, test_name=args.test_name, output_dir=generated_dir)]\n    execution = []',
    '''configs = test_configs(generated_dir, args.profile) if args.suite else [DeckConfig(profile=args.profile, test_name=args.test_name, output_dir=generated_dir)]\n    if args.suite_test_name:\n        if not args.suite:\n            raise SystemExit("--suite-test-name requires --suite")\n        configs = [cfg for cfg in configs if cfg.test_name == args.suite_test_name]\n        if not configs:\n            available = ", ".join(cfg.test_name for cfg in test_configs(generated_dir, args.profile))\n            raise SystemExit(f"Unknown suite test {args.suite_test_name!r}. Available tests: {available}")\n    execution = []''',
    "add exact suite-case filter",
)
guarded_replace(
    spice,
    'parser.add_argument("--test-name", default="full_operating")\n    parser.add_argument("--ngspice-binary", default="auto")',
    '''parser.add_argument("--test-name", default="full_operating")\n    parser.add_argument(\n        "--suite-test-name",\n        help="With --suite, generate/run only the named specialised suite configuration.",\n    )\n    parser.add_argument("--ngspice-binary", default="auto")''',
    "add --suite-test-name CLI option",
)

test_static = ROOT / "tests" / "test_static.py"
guarded_replace(
    test_static,
    'self.assertIn("BSOC NSOC N I={I(VSENSE)}", block)',
    'self.assertIn("FSOC NSOC N VSENSE 1", block)',
    "update dynamic-battery discharge regression",
)

new_test = ROOT / "tests" / "test_dynamic_battery_runtime.py"
if not new_test.exists():
    new_test.write_text(
        '''from pathlib import Path\nimport sys\nimport unittest\n\nROOT = Path(__file__).resolve().parents[1]\nif str(ROOT) not in sys.path:\n    sys.path.insert(0, str(ROOT))\n\nimport Spice\n\n\nclass DynamicBatteryRuntimeRegression(unittest.TestCase):\n    def test_dynamic_battery_uses_linear_controlled_soc_current(self):\n        text = (ROOT / "models" / "portable" / "lifeling_portable_models.lib").read_text(encoding="utf-8")\n        block = text.split(".subckt LIF_CR2032_DYNAMIC", 1)[1].split(".ends LIF_CR2032_DYNAMIC", 1)[0]\n        self.assertIn("FSOC NSOC N VSENSE 1", block)\n        self.assertNotIn("max(0,min(1,V(NSOC,N)))", block)\n\n    def test_cold_start_has_bounded_horizon_and_focused_outputs(self):\n        cfg = next(c for c in Spice.test_configs(ROOT / "generated", "hybrid") if c.test_name == "06_cold_start_dynamic_battery")\n        self.assertEqual(cfg.tstop, "50m")\n        self.assertEqual(cfg.supply_mode, "coin_dynamic")\n        self.assertEqual(cfg.save_nets, ["VDD", "V_Boost", "VREF_2V048", "VREF_1V024", "Vm_Int", "AP", "Spike_Out"])\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
        encoding="utf-8",
    )
    print(f"ADD   runtime regression tests: {new_test}")
else:
    print(f"SKIP  runtime regression tests already present: {new_test}")

print("\nPatch v8 applied successfully.")
