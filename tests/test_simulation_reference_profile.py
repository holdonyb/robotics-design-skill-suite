import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.reference_profile import (  # noqa: E402
    ReferenceProfileError,
    load_reference_runner_profile,
)


class ReferenceRunnerProfileTests(unittest.TestCase):
    def test_loads_geometry_only_from_receipt_bound_ros_workspace(self):
        profile = load_reference_runner_profile(ROOT / "reference" / "mobile-manipulator")
        self.assertEqual(0.15, profile.wheel_radius_m)
        self.assertEqual(0.68, profile.wheel_separation_m)

    def test_rejects_xacro_geometry_drift_even_when_the_caller_never_supplies_profile(self):
        source = ROOT / "reference" / "mobile-manipulator"
        with tempfile.TemporaryDirectory() as raw:
            copied = Path(raw) / "reference"
            shutil.copytree(source, copied)
            xacro = copied / "ros2_ws/src/jx_mobile_manipulator_description/urdf/reference_mobile_manipulator.urdf.xacro"
            xacro.write_text(xacro.read_text(encoding="utf-8").replace('radius="0.15"', 'radius="0.14"', 1), encoding="utf-8")
            with self.assertRaisesRegex(ReferenceProfileError, "receipt-valid|SHA-256"):
                load_reference_runner_profile(copied)


if __name__ == "__main__":
    unittest.main()
