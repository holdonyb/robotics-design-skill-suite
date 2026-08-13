import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.units import QuantityError, to_si  # noqa: E402


class AssuranceUnitTests(unittest.TestCase):
    def test_supported_units_convert_explicitly(self):
        self.assertAlmostEqual(
            to_si({"value": 120, "unit": "rpm"}, "angular_velocity"),
            4.0 * math.pi,
        )
        self.assertEqual(to_si({"value": 250, "unit": "mm"}, "length"), 0.25)
        self.assertEqual(to_si({"value": 1, "unit": "Wh"}, "energy"), 3600.0)
        self.assertEqual(
            to_si({"value": 25, "unit": "degC"}, "temperature"),
            298.15,
        )
        self.assertEqual(to_si({"value": 0.5, "unit": "ohm"}, "resistance"), 0.5)
        self.assertEqual(
            to_si({"value": 2.0, "unit": "K/W"}, "thermal_resistance"), 2.0
        )

    def test_dimension_mismatch_fails_closed(self):
        with self.assertRaisesRegex(QuantityError, "expected torque"):
            to_si({"value": 5, "unit": "kg"}, "torque")

    def test_bare_number_fails_closed(self):
        with self.assertRaisesRegex(QuantityError, "object with value and unit"):
            to_si(5, "torque")

    def test_bool_nan_infinity_and_unknown_unit_fail_closed(self):
        for value in (True, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(QuantityError):
                    to_si({"value": value, "unit": "N*m"}, "torque")
        with self.assertRaisesRegex(QuantityError, "unsupported unit"):
            to_si({"value": 1, "unit": "horse"}, "force")

    def test_unknown_dimension_fails_closed(self):
        with self.assertRaisesRegex(QuantityError, "unsupported dimension"):
            to_si({"value": 1, "unit": "m"}, "brightness")


if __name__ == "__main__":
    unittest.main()
