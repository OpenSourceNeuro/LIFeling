from pathlib import Path
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
        self.assertEqual(cfg.supply_mode, "coin_fixed")
        self.assertAlmostEqual(cfg.battery_voltage, 2.92125, places=6)
        self.assertEqual(cfg.battery_resistance, 35.0)
        self.assertEqual(cfg.battery_rise_time, "1m")
        self.assertAlmostEqual(cfg.battery_voltage, 2.92125, places=6)
        self.assertEqual(cfg.battery_resistance, 35.0)
        self.assertEqual(cfg.battery_rise_time, "1m")
        self.assertEqual(cfg.save_nets, ["VDD", "V_Boost", "VREF_2V048", "VREF_1V024", "Vm_Int", "AP", "Spike_Out"])


if __name__ == "__main__":
    unittest.main()
