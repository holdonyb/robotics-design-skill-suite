import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
CLI = SCRIPTS / "validate_design_contract.py"
sys.path.insert(0, str(SCRIPTS))

from assurance.engine import evaluate_contract, serialize_report  # noqa: E402
from tests.test_assurance_contract import valid_contract  # noqa: E402


URDF = """<robot name="engine-fixture">
  <link name="base"><inertial><mass value="2"/><inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial></link>
</robot>
"""


def write_fixture(root, plugin=None):
    robot = root / "robot.urdf"
    robot.write_text(URDF, encoding="utf-8")
    digest = hashlib.sha256(robot.read_bytes()).hexdigest()
    data = valid_contract()
    data["requirements"][0]["verification"] = "AN-BATTERY"
    data["architecture"] = {
        "features": ["battery_powered"],
        "drive_units": [],
        "actuators": [],
        "moving_cables": [],
        "claimed_safety_functions": [],
    }
    data["artifacts"][0]["sha256"] = digest
    quantity_specs = (
        ("Q-VOLTAGE", "voltage", 48.0, "V", "component:BATTERY"),
        ("Q-PEAK-POWER", "power", 100.0, "W", "project:system"),
        ("Q-CONTINUOUS-POWER", "power", 50.0, "W", "project:system"),
        ("Q-BAT-CONT-CURRENT", "current", 10.0, "A", "component:BATTERY"),
        ("Q-BAT-PEAK-CURRENT", "current", 20.0, "A", "component:BATTERY"),
        ("Q-USABLE-ENERGY", "energy", 100000.0, "J", "component:BATTERY"),
        ("Q-RUNTIME", "time", 1000.0, "s", "project:system"),
        ("Q-BMS-CURRENT", "current", 10.0, "A", "component:BMS"),
        ("Q-PROTECTION-CURRENT", "current", 10.0, "A", "component:PROTECTION"),
        ("Q-CONTACTOR-CURRENT", "current", 10.0, "A", "component:CONTACTOR"),
        ("Q-CONVERTER-POWER", "power", 100.0, "W", "component:CONVERTER"),
    )
    data["quantities"] = [
        {
            "id": quantity_id,
            "dimension": dimension,
            "value": {"value": value, "unit": unit},
            "owner": owner,
            "source": (
                "evidence:EV-CATALOG"
                if owner.startswith("component:")
                else "evidence:EV-ASSUMPTIONS"
            ),
            "evidence_level": (
                "parsed" if owner.startswith("component:") else "assumed"
            ),
        }
        for quantity_id, dimension, value, unit, owner in quantity_specs
    ]
    component_specs = (
        ("BATTERY", "battery", {"nominal_voltage": "Q-VOLTAGE", "continuous_current": "Q-BAT-CONT-CURRENT", "peak_current": "Q-BAT-PEAK-CURRENT", "usable_energy": "Q-USABLE-ENERGY"}),
        ("BMS", "bms", {"continuous_current": "Q-BMS-CURRENT"}),
        ("PROTECTION", "main_protection", {"rated_current": "Q-PROTECTION-CURRENT"}),
        ("CONTACTOR", "contactor", {"continuous_current": "Q-CONTACTOR-CURRENT"}),
        ("CONVERTER", "dc_converter", {"continuous_power": "Q-CONVERTER-POWER"}),
    )
    data["components"] = [
        {
            "id": component_id,
            "role": role,
            "state": "verified_part",
            "interfaces": [f"IF-{component_id}"],
            "bindings": ["feature:battery_powered"],
            "manufacturer": "Fixture Components",
            "part_number": f"FIX-{component_id}",
            "source_url": "https://example.com/catalog",
            "source_date": "2026-08-13",
            "source_evidence": "evidence:EV-CATALOG",
            "limits": {name: f"quantity:{quantity_id}" for name, quantity_id in limits.items()},
            "supports_claims": ["REQ-PAYLOAD"],
        }
        for component_id, role, limits in component_specs
    ]
    quantities_by_id = {item["id"]: item for item in data["quantities"]}
    catalog = root / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "locator": "https://example.com/catalog",
                "observed_date": "2026-08-13",
                "components": [
                    {
                        "id": component["id"],
                        "manufacturer": component["manufacturer"],
                        "part_number": component["part_number"],
                        "limits": {
                            name: quantities_by_id[reference[9:]]["value"]
                            for name, reference in component["limits"].items()
                        },
                    }
                    for component in data["components"]
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    catalog_digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    assumptions = root / "assumptions.json"
    assumptions.write_text('{"fixture":"battery-demand"}\n', encoding="utf-8")
    assumptions_digest = hashlib.sha256(assumptions.read_bytes()).hexdigest()
    data["evidence"] = [
        {
            "id": "EV-CATALOG",
            "kind": "component_catalog_v1",
            "level": "parsed",
            "source": {"path": "catalog.json", "sha256": catalog_digest},
            "locator": "https://example.com/catalog",
            "observed_date": "2026-08-13",
            "supports": [
                *(
                    f"quantity:{item['id']}"
                    for item in data["quantities"]
                    if item["owner"].startswith("component:")
                ),
                *(f"component:{item['id']}" for item in data["components"]),
            ],
        },
        {
            "id": "EV-ASSUMPTIONS",
            "level": "assumed",
            "source": {"path": "assumptions.json", "sha256": assumptions_digest},
            "supports": [
                f"quantity:{item['id']}"
                for item in data["quantities"]
                if item["owner"] == "project:system"
            ],
        },
    ]
    data["analyses"] = [
        {
            "id": "AN-BATTERY",
            "plugin": "battery_v1",
            "covers": ["requirement:REQ-PAYLOAD", "feature:battery_powered"],
            "inputs": {
                "voltage_v": "quantity:Q-VOLTAGE",
                "peak_power_w": "quantity:Q-PEAK-POWER",
                "continuous_power_w": "quantity:Q-CONTINUOUS-POWER",
                "max_continuous_current_a": "quantity:Q-BAT-CONT-CURRENT",
                "max_peak_current_a": "quantity:Q-BAT-PEAK-CURRENT",
                "usable_energy_j": "quantity:Q-USABLE-ENERGY",
                "required_runtime_s": "quantity:Q-RUNTIME",
            },
        }
    ]
    if plugin:
        data["analyses"] = [
            {
                "id": "AN-X",
                "plugin": plugin,
                "covers": ["requirement:REQ-PAYLOAD"],
                "inputs": {},
            }
        ]
    contract = root / "design-contract.json"
    contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return contract, robot


class AssuranceEngineTests(unittest.TestCase):
    def test_valid_evaluation_is_promotable_and_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract, _ = write_fixture(Path(temp_dir))
            first, errors = evaluate_contract(contract)
            second, second_errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertEqual(second_errors, [])
        self.assertTrue(first.promotable)
        self.assertEqual(serialize_report(first), serialize_report(second))
        report = json.loads(serialize_report(first))
        self.assertEqual(report["metadata"]["schema_version"], 1)
        self.assertRegex(report["metadata"]["contract_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(report["metadata"]["evidence_coverage"], "2/2")
        self.assertEqual(report["metadata"]["minimum_evidence_level"], "assumed")
        self.assertEqual(
            report["metadata"]["evidence_level_counts"], {"assumed": 3, "parsed": 8}
        )

    def test_changed_artifact_invalidates_hash_bound_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract, robot = write_fixture(Path(temp_dir))
            robot.write_text(URDF.replace('value="2"', 'value="3"'), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertFalse(report.promotable)
        codes = {item.code for item in report.diagnostics}
        self.assertIn("EVIDENCE.STALE_ARTIFACT", codes)

    def test_verified_component_catalog_requires_semantic_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract, _ = write_fixture(root)
            catalog = root / "catalog.json"
            catalog.write_text('{"arbitrary":"self-asserted evidence"}\n', encoding="utf-8")
            data = json.loads(contract.read_text(encoding="utf-8"))
            data["evidence"][0]["source"]["sha256"] = hashlib.sha256(
                catalog.read_bytes()
            ).hexdigest()
            contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertFalse(report.promotable)
        self.assertTrue(
            any(
                item.code == "EVIDENCE.COMPONENT_CATALOG"
                for item in report.diagnostics
            )
        )

    def test_analysis_rating_must_equal_verified_component_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract, _ = write_fixture(root)
            data = json.loads(contract.read_text(encoding="utf-8"))
            battery = next(item for item in data["components"] if item["id"] == "BATTERY")
            battery["limits"].pop("nominal_voltage")
            contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertFalse(report.promotable)
        self.assertTrue(
            any(item.code == "PHY.ANALYSIS.RATING_LIMIT" for item in report.diagnostics)
        )

    def test_unknown_analysis_plugin_is_indeterminate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract, _ = write_fixture(Path(temp_dir), "imaginary_solver")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertFalse(report.promotable)
        self.assertTrue(any(item.code == "PHY.PLUGIN.UNKNOWN" for item in report.diagnostics))

    def test_nonempty_physical_contract_without_analysis_is_not_promotable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract, _ = write_fixture(Path(temp_dir))
            data = json.loads(contract.read_text(encoding="utf-8"))
            data["analyses"] = []
            contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertFalse(report.promotable)
        self.assertTrue(
            any(item.code == "PHY.ANALYSIS.MISSING" for item in report.diagnostics)
        )

    def test_known_analysis_cannot_exist_without_matching_architecture_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract, _ = write_fixture(Path(temp_dir))
            data = json.loads(contract.read_text(encoding="utf-8"))
            data["architecture"] = {
                "features": [],
                "drive_units": [],
                "actuators": [],
                "moving_cables": [],
                "claimed_safety_functions": [],
            }
            for component in data["components"]:
                component["bindings"] = []
            data["analyses"][0]["covers"] = ["requirement:REQ-PAYLOAD"]
            contract.write_text(json.dumps(data, indent=2), encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertFalse(report.promotable)
        self.assertTrue(
            any(item.code == "PHY.ANALYSIS.UNDECLARED_SCOPE" for item in report.diagnostics)
        )

    def test_analysis_inputs_resolve_owned_quantities(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract, _ = write_fixture(root)
            report, errors = evaluate_contract(contract)
        self.assertEqual(errors, [])
        self.assertTrue(report.promotable)
        self.assertGreater(
            report.analyses[0]["outputs"]["peak_current_a"],
            0.0,
        )

    def test_schema_errors_do_not_create_a_physical_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            contract = Path(temp_dir) / "bad.json"
            contract.write_text("[]", encoding="utf-8")
            report, errors = evaluate_contract(contract)
        self.assertIsNone(report)
        self.assertEqual(errors, ["contract root must be a JSON object"])

    def test_cli_exit_codes_and_report_collision_are_actionable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract, _ = write_fixture(root)
            report_path = root / "evidence.json"
            success = subprocess.run(
                [sys.executable, str(CLI), str(contract), "--report", str(report_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertTrue(report_path.is_file())

            collision = subprocess.run(
                [sys.executable, str(CLI), str(contract), "--report", str(report_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(collision.returncode, 2)
            self.assertIn("report already exists", collision.stderr)
            self.assertNotIn("Traceback", collision.stderr)

            bad = root / "bad.json"
            bad.write_text("{", encoding="utf-8")
            malformed = subprocess.run(
                [sys.executable, str(CLI), str(bad)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(malformed.returncode, 2)
            self.assertIn("ERROR:", malformed.stderr)
            self.assertNotIn("Traceback", malformed.stderr)


if __name__ == "__main__":
    unittest.main()
