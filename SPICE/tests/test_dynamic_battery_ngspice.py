from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "portable" / "lifeling_portable_models.lib"


class DynamicBatteryNgspiceRegression(unittest.TestCase):
    def test_ocv_uses_behavioural_voltage_source(self) -> None:
        text = MODEL.read_text(encoding="utf-8")
        self.assertIn("BOCV NOCV N V={", text)
        self.assertNotIn("VOCV NOCV N VALUE={", text)

    def test_dynamic_battery_subcircuit_is_present(self) -> None:
        text = MODEL.read_text(encoding="utf-8")
        self.assertIn(".subckt LIF_CR2032_DYNAMIC", text)
        self.assertIn(".ends LIF_CR2032_DYNAMIC", text)


if __name__ == "__main__":
    unittest.main()
