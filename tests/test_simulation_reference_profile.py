import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.simulation.reference_profile import (  # noqa: E402
    ReferenceProfileError,
    load_reference_runner_profile,
)
from assurance.simulation.artifacts import validate_ros_workspace_manifest  # noqa: E402


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

    def test_rejects_profile_sources_replaced_after_manifest_validation(self):
        source = ROOT / "reference" / "mobile-manipulator"
        with tempfile.TemporaryDirectory() as raw:
            copied = Path(raw) / "reference"
            shutil.copytree(source, copied)
            xacro = copied / "ros2_ws/src/jx_mobile_manipulator_description/urdf/reference_mobile_manipulator.urdf.xacro"
            controllers = copied / "ros2_ws/src/jx_mobile_manipulator_sim/config/controllers.yaml"

            def validate_then_replace(*args):
                errors = validate_ros_workspace_manifest(*args)
                xacro.write_text(xacro.read_text(encoding="utf-8").replace('radius="0.15"', 'radius="0.14"'), encoding="utf-8")
                controllers.write_text(controllers.read_text(encoding="utf-8").replace("wheel_radius: 0.15", "wheel_radius: 0.14"), encoding="utf-8")
                return errors

            with patch(
                "assurance.simulation.reference_profile.validate_ros_workspace_manifest",
                side_effect=validate_then_replace,
            ):
                with self.assertRaisesRegex(ReferenceProfileError, "SHA-256|receipt"):
                    load_reference_runner_profile(copied)


if __name__ == "__main__":
    unittest.main()
