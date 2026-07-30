from pathlib import Path
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
