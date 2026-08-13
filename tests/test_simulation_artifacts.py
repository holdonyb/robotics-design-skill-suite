import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference" / "mobile-manipulator"
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402
from assurance.simulation.artifacts import validate_artifact_manifest  # noqa: E402


EXPECTED_OUTPUTS = {
    "model/generated/reference_mobile_manipulator.step",
    "model/generated/reference_mobile_manipulator.urdf",
    "model/generated/reference_mobile_manipulator.sdf",
    "model/generated/reference_mobile_manipulator.srdf",
    "model/generated/controllers.yaml",
    "model/generated/bridge.yaml",
    "model/generated/view.rviz",
    "model/generated/package.xml",
    "model/generated/CMakeLists.txt",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generator_python():
    configured = os.environ.get("ROBOTICS_CAD_PYTHON")
    if configured:
        return configured
    if importlib.util.find_spec("build123d") is not None:
        return sys.executable
    local = Path("E" + ":/.codex/runtimes/robotics-design/Scripts/python.exe")
    if local.is_file():
        return str(local)
    return None


class SimulationArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._fixture_tmp = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls._fixture_tmp.name) / "fixture"
        shutil.copytree(REFERENCE, cls.fixture_root)

    @classmethod
    def tearDownClass(cls):
        cls._fixture_tmp.cleanup()

    def _generate_once(self, output):
        executable = generator_python()
        if executable is None:
            self.skipTest("build123d runtime is unavailable; portable manifest/drift tests still run")
        completed = subprocess.run(
            [
                executable,
                str(REFERENCE / "model" / "generate_reference_model.py"),
                "--out",
                str(output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stdout + completed.stderr)

    def generate(self, output):
        shutil.copytree(self.fixture_root, output, dirs_exist_ok=True)

    def manifest(self, root):
        return json.loads((root / "simulation" / "artifact-manifest.json").read_text(encoding="utf-8"))

    def rehash(self, root, relative):
        manifest_path = root / "simulation" / "artifact-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for output in manifest["outputs"]:
            if output["path"] == relative:
                output["sha256"] = sha256(root / relative)
        manifest_path.write_bytes(canonical_bytes(manifest))

    def test_generation_is_byte_reproducible_and_manifest_closed(self):
        first = Path(self._fixture_tmp.name) / "first"
        second = Path(self._fixture_tmp.name) / "second"
        self._generate_once(first)
        self._generate_once(second)
        first_files = {
            path.relative_to(first).as_posix(): path.read_bytes()
            for path in first.rglob("*") if path.is_file()
        }
        second_files = {
            path.relative_to(second).as_posix(): path.read_bytes()
            for path in second.rglob("*") if path.is_file()
        }
        self.assertEqual(first_files, second_files)
        self.assertEqual(validate_artifact_manifest(first), [])
        manifest = self.manifest(first)
        self.assertEqual({item["path"] for item in manifest["outputs"]}, EXPECTED_OUTPUTS)
        geometry_sha = sha256(first / "model" / "geometry.json")
        self.assertEqual(manifest["geometry_source"]["sha256"], geometry_sha)
        self.assertTrue(all(item["source_sha256"] == geometry_sha for item in manifest["outputs"]))

    def test_manifest_rejects_tamper_extra_symlink_and_stale_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"
            self.generate(root)
            urdf = root / "model" / "generated" / "reference_mobile_manipulator.urdf"
            urdf.write_text(urdf.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertTrue(any("SHA-256" in item for item in validate_artifact_manifest(root)))

            self.generate(root)
            extra = root / "model" / "generated" / "manual.txt"
            extra.write_text("manual\n", encoding="utf-8")
            self.assertTrue(any("extra file" in item for item in validate_artifact_manifest(root)))

            self.generate(root)
            geometry = root / "model" / "geometry.json"
            data = json.loads(geometry.read_text(encoding="utf-8"))
            data["base"]["size_m"][0] = 0.81
            geometry.write_bytes(canonical_bytes(data))
            self.assertTrue(any("geometry source SHA-256" in item for item in validate_artifact_manifest(root)))

            if hasattr(os, "symlink"):
                self.generate(root)
                target = root / "model" / "generated" / "controllers.yaml"
                backup = root / "controllers-copy.yaml"
                shutil.copyfile(target, backup)
                target.unlink()
                try:
                    os.symlink(backup, target)
                except OSError:
                    pass
                else:
                    self.assertTrue(any("symlink" in item for item in validate_artifact_manifest(root)))

    def test_manifest_rejects_duplicate_keys_and_physical_or_contract_source_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"
            self.generate(root)
            manifest_path = root / "simulation" / "artifact-manifest.json"
            payload = manifest_path.read_text(encoding="utf-8")
            manifest_path.write_text(payload.replace('"schema_version":1', '"schema_version":1,"schema_version":1', 1), encoding="utf-8")
            self.assertTrue(any("duplicate JSON key" in item for item in validate_artifact_manifest(root)))

            self.generate(root)
            physical = root / "robot.urdf"
            physical.write_text(physical.read_text(encoding="utf-8").replace('mass value="100"', 'mass value="101"', 1), encoding="utf-8", newline="\n")
            self.assertTrue(any("physical source SHA-256" in item for item in validate_artifact_manifest(root)))

            self.generate(root)
            contract = root / "design-contract.json"
            contract.write_text(contract.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertTrue(any("contract source SHA-256" in item for item in validate_artifact_manifest(root)))

            self.generate(root)
            assumptions = root / "assumptions.json"
            data = json.loads(assumptions.read_text(encoding="utf-8"))
            data["simulation_dynamics"]["links"]["left_wheel_link"]["mass_kg"] = -1
            assumptions.write_bytes(canonical_bytes(data))
            manifest = self.manifest(root)
            manifest["assumptions_source"]["sha256"] = sha256(assumptions)
            for output in manifest["outputs"]:
                output["assumptions_source_sha256"] = sha256(assumptions)
            (root / "simulation" / "artifact-manifest.json").write_bytes(canonical_bytes(manifest))
            self.assertTrue(any("wheel dynamics" in item for item in validate_artifact_manifest(root)))

            self.generate(root)
            assumptions = root / "assumptions.json"
            data = json.loads(assumptions.read_text(encoding="utf-8"))
            data["simulation_dynamics"]["links"]["left_wheel_link"]["mass_kg"] = 6
            assumptions.write_bytes(canonical_bytes(data))
            manifest = self.manifest(root)
            manifest["assumptions_source"]["sha256"] = sha256(assumptions)
            for output in manifest["outputs"]:
                output["assumptions_source_sha256"] = sha256(assumptions)
            (root / "simulation" / "artifact-manifest.json").write_bytes(canonical_bytes(manifest))
            self.assertTrue(any("contract source does not hash-bind assumptions" in item for item in validate_artifact_manifest(root)))

    def test_manifest_requires_canonical_bytes_and_fixed_generator_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"
            self.generate(root)
            path = root / "simulation" / "artifact-manifest.json"
            path.write_text(json.dumps(self.manifest(root), indent=2) + "\n", encoding="utf-8", newline="\n")
            self.assertTrue(any("canonical" in item for item in validate_artifact_manifest(root)))

            self.generate(root)
            manifest = self.manifest(root)
            manifest["generator"]["version"] = "attacker"
            path.write_bytes(canonical_bytes(manifest))
            self.assertTrue(any("generator" in item for item in validate_artifact_manifest(root)))

    def test_rehashed_urdf_joint_transmission_collision_and_mass_drift_are_rejected(self):
        def wrong_axis(root):
            root.find("joint[@name='joint_2']/axis").set("xyz", "0 -1 0")

        def missing_transmission(root):
            root.remove(root.find("transmission[@name='joint_1_transmission']"))

        def mesh_collision(root):
            geometry = root.find("link[@name='base_link']/collision/geometry")
            for child in list(geometry):
                geometry.remove(child)
            ET.SubElement(geometry, "mesh", {"filename": "package://unbound/base.stl"})

        def mass_drift(root):
            root.find("link[@name='base_link']/inertial/mass").set("value", "99")

        def arm_inertia_drift(root):
            root.find("link[@name='arm_link_3']/inertial/inertia").set("iyy", "99")

        attacks = (
            (wrong_axis, "axis"),
            (missing_transmission, "transmission"),
            (mesh_collision, "primitive collision"),
            (mass_drift, "base mass"),
            (arm_inertia_drift, "arm_link_3 inertia"),
        )
        for mutate, expected in attacks:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "bundle"
                self.generate(root)
                relative = "model/generated/reference_mobile_manipulator.urdf"
                path = root / relative
                document = ET.parse(path)
                mutate(document.getroot())
                ET.indent(document.getroot(), space="  ")
                path.write_bytes(ET.tostring(document.getroot(), encoding="utf-8", xml_declaration=True) + b"\n")
                self.rehash(root, relative)
                self.assertTrue(any(expected in item for item in validate_artifact_manifest(root)), validate_artifact_manifest(root))

    def test_rehashed_srdf_and_bridge_policy_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"
            self.generate(root)
            relative = "model/generated/reference_mobile_manipulator.srdf"
            path = root / relative
            text = path.read_text(encoding="utf-8")
            text = text.replace("</robot>", '<disable_collisions link1="base_link" link2="tool0" reason="Manual"/></robot>')
            path.write_text(text, encoding="utf-8", newline="\n")
            self.rehash(root, relative)
            self.assertTrue(any("disabled collision" in item for item in validate_artifact_manifest(root)))

            self.generate(root)
            relative = "model/generated/reference_mobile_manipulator.srdf"
            path = root / relative
            document = ET.parse(path)
            document.getroot().remove(document.getroot().find("disable_collisions"))
            ET.indent(document.getroot(), space="  ")
            path.write_bytes(ET.tostring(document.getroot(), encoding="utf-8", xml_declaration=True) + b"\n")
            self.rehash(root, relative)
            self.assertTrue(any("disabled collision" in item for item in validate_artifact_manifest(root)))

            self.generate(root)
            relative = "model/generated/bridge.yaml"
            path = root / relative
            text = path.read_text(encoding="utf-8").replace("/clock", "/missing_clock")
            path.write_text(text, encoding="utf-8", newline="\n")
            self.rehash(root, relative)
            self.assertTrue(any("/clock" in item for item in validate_artifact_manifest(root)))

    def test_rehashed_sdf_joint_and_inertia_drift_are_rejected(self):
        attacks = (
            ("joint[@name='joint_2']/axis/xyz", "0 -1 0", "axis"),
            ("joint[@name='joint_3']/axis/limit/upper", "9", "limit"),
            ("link[@name='arm_link_4']/inertial/mass", "999", "mass"),
            ("link[@name='left_wheel_link']/inertial/inertia/iyy", "999", "inertia"),
        )
        for selector, value, expected in attacks:
            with self.subTest(selector=selector), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "bundle"
                self.generate(root)
                relative = "model/generated/reference_mobile_manipulator.sdf"
                path = root / relative
                document = ET.parse(path)
                node = document.getroot().find("model").find(selector)
                node.text = value
                ET.indent(document.getroot(), space="  ")
                path.write_bytes(ET.tostring(document.getroot(), encoding="utf-8", xml_declaration=True) + b"\n")
                self.rehash(root, relative)
                errors = validate_artifact_manifest(root)
                self.assertTrue(any(f"SDF" in item and expected in item for item in errors), errors)

    def test_tracked_reference_bundle_is_current_and_lf_only(self):
        self.assertEqual(validate_artifact_manifest(REFERENCE), [])
        manifest = self.manifest(REFERENCE)
        for output in manifest["outputs"]:
            path = REFERENCE / output["path"]
            self.assertEqual(sha256(path), output["sha256"])
            if path.suffix != ".step":
                payload = path.read_bytes()
                self.assertNotIn(b"\r", payload)
                self.assertTrue(payload.endswith(b"\n"))
                self.assertFalse(payload.endswith(b"\n\n"))
        attributes = subprocess.run(
            ["git", "check-attr", "eol", "--", *sorted(EXPECTED_OUTPUTS - {"model/generated/reference_mobile_manipulator.step"})],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertTrue(all(line.endswith(": lf") for line in attributes.stdout.splitlines()))


if __name__ == "__main__":
    unittest.main()
