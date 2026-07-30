from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Spice
from lifeling_spice import runner


class SuiteRuntimeRegression(unittest.TestCase):
    def test_power_switch_off_uses_operating_point(self):
        configs = Spice.test_configs(ROOT / "generated", "hybrid")
        power_off = next(cfg for cfg in configs if cfg.test_name == "09_power_switch_off")
        self.assertEqual(power_off.switch_state, "off")
        self.assertEqual(power_off.analysis, "op")

    def test_run_deck_has_timeout_and_stale_cleanup(self):
        signature = inspect.signature(runner.run_deck)
        self.assertIn("timeout_seconds", signature.parameters)
        source = inspect.getsource(runner.run_deck)
        self.assertIn("subprocess.TimeoutExpired", source)
        self.assertIn("stale_path.unlink()", source)


if __name__ == "__main__":
    unittest.main()
