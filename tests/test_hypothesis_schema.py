import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "robotics-design" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from assurance.hypothesis.schema import load_space, validate_space  # noqa: E402


def minimal_space() -> dict:
    return {
        "schema_version": 1,
        "space_id": "drive-tradeoff",
        "base_contract": {
            "path": "reference/design-contract.json",
            "sha256": "0" * 64,
        },
        "max_candidates": 2,
        "axes": [
            {
                "id": "wheel",
                "choices": [
                    {
                        "id": "small",
                        "operations": [
                            {
                                "target": "quantity:Q-WHEEL.value",
                                "value": {"value": 0.1, "unit": "m"},
                            }
                        ],
                    },
                    {
                        "id": "large",
                        "operations": [
                            {
                                "target": "quantity:Q-WHEEL.value",
                                "value": {"value": 0.2, "unit": "m"},
                            }
                        ],
                    },
                ],
            }
        ],
        "uncertainties": [],
        "objectives": [],
        "repair_rules": [],
        "evaluation": {
            "max_stage_evaluations": 32,
            "stages": ["contract_v1", "physical_v030"],
        },
    }


def errors_for(update) -> list[str]:
    data = minimal_space()
    update(data)
    return validate_space(data)


class HypothesisSpaceSchemaTests(unittest.TestCase):
    def test_minimal_space_is_valid_and_input_is_not_mutated(self):
        data = minimal_space()
        before = copy.deepcopy(data)

        self.assertEqual(validate_space(data), [])
        self.assertEqual(data, before)

    def test_root_must_be_object_with_exact_fields(self):
        for invalid in (None, [], "space", 1, True):
            with self.subTest(invalid=invalid):
                self.assertEqual(
                    validate_space(invalid),
                    ["hypothesis-space root must be a JSON object"],
                )

        data = minimal_space()
        del data["axes"]
        data["secret"] = True
        errors = validate_space(data)
        self.assertIn("root is missing fields: axes", errors)
        self.assertIn("root has unknown fields: secret", errors)

    def test_schema_version_and_budgets_require_exact_integers(self):
        for invalid in (True, 1.0, "1", None, [], 2):
            with self.subTest(field="schema_version", invalid=invalid):
                self.assertIn(
                    "schema_version must be integer 1",
                    errors_for(lambda data: data.__setitem__("schema_version", invalid)),
                )
        for invalid in (True, 1.0, 0, 10_001, None, []):
            with self.subTest(field="max_candidates", invalid=invalid):
                self.assertIn(
                    "max_candidates must be an integer from 1 through 10000",
                    errors_for(lambda data: data.__setitem__("max_candidates", invalid)),
                )
        for invalid in (True, 1.0, 0, 1_000_001, None, []):
            with self.subTest(field="max_stage_evaluations", invalid=invalid):
                errors = errors_for(
                    lambda data: data["evaluation"].__setitem__(
                        "max_stage_evaluations", invalid
                    )
                )
                self.assertIn(
                    "evaluation.max_stage_evaluations must be an integer from 1 through 1000000",
                    errors,
                )

    def test_identifiers_are_valid_and_unique_at_each_scope(self):
        self.assertTrue(
            any("space_id" in error for error in errors_for(lambda data: data.__setitem__("space_id", "bad id")))
        )

        data = minimal_space()
        data["axes"].append(copy.deepcopy(data["axes"][0]))
        self.assertIn("axes has duplicate id wheel", validate_space(data))

        data = minimal_space()
        data["axes"][0]["choices"].append(copy.deepcopy(data["axes"][0]["choices"][0]))
        self.assertIn("axes[0].choices has duplicate id small", validate_space(data))

        data = minimal_space()
        record = {
            "id": "temperature",
            "target": "quantity:Q-TEMP.value",
            "values": [{"value": 20, "unit": "degC"}],
            "hard": True,
        }
        data["uncertainties"] = [record, copy.deepcopy(record)]
        self.assertIn("uncertainties has duplicate id temperature", validate_space(data))

        data = minimal_space()
        objective = {"id": "mass", "source": "quantity:Q-MASS", "direction": "min"}
        data["objectives"] = [objective, copy.deepcopy(objective)]
        self.assertIn("objectives has duplicate id mass", validate_space(data))

        data = minimal_space()
        rule = {
            "id": "reduce-load",
            "diagnostic_code": "ARM.OVERLOAD",
            "owner_prefix": "component:",
            "operations": [
                {
                    "target": "quantity:Q-PAYLOAD.value",
                    "value": {"value": 1, "unit": "kg"},
                }
            ],
            "max_applications": 1,
        }
        data["repair_rules"] = [rule, copy.deepcopy(rule)]
        self.assertIn("repair_rules has duplicate id reduce-load", validate_space(data))

    def test_base_contract_is_closed_hash_bound_and_posix_normalized(self):
        data = minimal_space()
        del data["base_contract"]["sha256"]
        data["base_contract"]["extra"] = 1
        errors = validate_space(data)
        self.assertIn("base_contract is missing fields: sha256", errors)
        self.assertIn("base_contract has unknown fields: extra", errors)

        for invalid in (
            "",
            "/absolute.json",
            "C" + ":/absolute.json",
            "../escape.json",
            "dir/../escape.json",
            "./contract.json",
            "dir//contract.json",
            "dir\\contract.json",
            ".",
        ):
            with self.subTest(path=invalid):
                errors = errors_for(
                    lambda data: data["base_contract"].__setitem__("path", invalid)
                )
                self.assertTrue(
                    any("base_contract.path" in error for error in errors), errors
                )

        for invalid in ("A" * 64, "0" * 63, "g" * 64, 7, None):
            with self.subTest(sha=invalid):
                errors = errors_for(
                    lambda data: data["base_contract"].__setitem__("sha256", invalid)
                )
                self.assertIn(
                    "base_contract.sha256 must be a lowercase 64-character SHA-256 digest",
                    errors,
                )

    def test_axes_choices_and_operations_are_nonempty_lists(self):
        for path, update, expected in (
            (
                "axes",
                lambda data: data.__setitem__("axes", None),
                "axes must be a non-empty list",
            ),
            (
                "choices",
                lambda data: data["axes"][0].__setitem__("choices", []),
                "axes[0].choices must be a non-empty list",
            ),
            (
                "operations",
                lambda data: data["axes"][0]["choices"][0].__setitem__("operations", []),
                "axes[0].choices[0].operations must be a non-empty list",
            ),
        ):
            with self.subTest(path=path):
                self.assertIn(expected, errors_for(update))

        for update, expected in (
            (
                lambda data: data["axes"].__setitem__(0, None),
                "axes[0] must be an object",
            ),
            (
                lambda data: data["axes"][0]["choices"].__setitem__(0, None),
                "axes[0].choices[0] must be an object",
            ),
            (
                lambda data: data["axes"][0]["choices"][0]["operations"].__setitem__(0, None),
                "axes[0].choices[0].operations[0] must be an object",
            ),
        ):
            self.assertIn(expected, errors_for(update))

    def test_nested_records_are_closed_and_require_every_field(self):
        cases = [
            ("axis", lambda data: data["axes"][0], "id"),
            ("choice", lambda data: data["axes"][0]["choices"][0], "id"),
            (
                "operation",
                lambda data: data["axes"][0]["choices"][0]["operations"][0],
                "target",
            ),
            ("evaluation", lambda data: data["evaluation"], "stages"),
        ]
        for name, select, required in cases:
            with self.subTest(record=name):
                data = minimal_space()
                record = select(data)
                del record[required]
                record["extra"] = 1
                errors = validate_space(data)
                self.assertTrue(any("is missing fields" in error for error in errors), errors)
                self.assertTrue(any("has unknown fields: extra" in error for error in errors), errors)

        data = minimal_space()
        data["uncertainties"] = [{"id": "u", "target": "quantity:Q.value", "values": []}]
        errors = validate_space(data)
        self.assertIn("uncertainties[0] is missing fields: hard", errors)

        data = minimal_space()
        data["objectives"] = [{"id": "o", "source": "quantity:Q", "extra": 1}]
        errors = validate_space(data)
        self.assertIn("objectives[0] is missing fields: direction", errors)
        self.assertIn("objectives[0] has unknown fields: extra", errors)

        data = minimal_space()
        data["repair_rules"] = [
            {
                "id": "r",
                "diagnostic_code": "D",
                "owner_prefix": "component:",
                "operations": [],
                "extra": 1,
            }
        ]
        errors = validate_space(data)
        self.assertIn("repair_rules[0] is missing fields: max_applications", errors)
        self.assertIn("repair_rules[0] has unknown fields: extra", errors)

    def test_operation_targets_are_semantically_closed(self):
        valid_operations = [
            {"target": "quantity:Q-WHEEL.value", "value": {"value": 1, "unit": "m"}},
            {"target": "quantity:Q-WHEEL.tolerance", "value": {"value": 1, "unit": "mm"}},
            {"target": "component:C-MOTOR", "value": {"id": "C-MOTOR", "role": "motor"}},
            {"target": "evidence:E-DATA", "value": {"id": "E-DATA", "level": "parsed"}},
        ]
        valid_operations.extend(
            {"target": f"architecture.{field}", "value": ["item-a", "item-b"]}
            for field in (
                "features",
                "drive_units",
                "actuators",
                "moving_cables",
                "claimed_safety_functions",
            )
        )
        for operation in valid_operations:
            with self.subTest(target=operation["target"]):
                data = minimal_space()
                data["axes"][0]["choices"] = [
                    {"id": "only", "operations": [operation]}
                ]
                data["max_candidates"] = 1
                self.assertEqual(validate_space(data), [])

        forbidden = (
            "requirement:R",
            "requirements:R",
            "assumption:A",
            "analysis:A",
            "analysis:A.outputs.margin",
            "artifact:A",
            "artifact:A.sha256",
            "component:C.role",
            "evidence:E.level",
            "architecture.unknown",
            "schema_version",
            "candidate_id",
            "status",
            "quantity:Q",
            "quantity:.value",
            "quantity:bad id.value",
        )
        for target in forbidden:
            with self.subTest(target=target):
                errors = errors_for(
                    lambda data: data["axes"][0]["choices"][0]["operations"][0].__setitem__(
                        "target", target
                    )
                )
                self.assertTrue(any("unsupported semantic target" in error for error in errors), errors)

    def test_operation_value_types_and_replacement_identity_are_checked(self):
        for invalid in (
            1,
            {"value": True, "unit": "m"},
            {"value": math.inf, "unit": "m"},
            {"value": 1, "unit": ""},
            {"value": 1, "unit": "furlong"},
            {"value": 1, "unit": "m", "extra": 0},
        ):
            with self.subTest(quantity=invalid):
                errors = errors_for(
                    lambda data: data["axes"][0]["choices"][0]["operations"][0].__setitem__(
                        "value", invalid
                    )
                )
                self.assertTrue(any("operations[0].value" in error for error in errors), errors)

        for target, value in (
            ("component:C", {"id": "OTHER"}),
            ("component:C", []),
            ("evidence:E", {"id": "OTHER"}),
            ("evidence:E", None),
        ):
            with self.subTest(target=target, value=value):
                data = minimal_space()
                operation = data["axes"][0]["choices"][0]["operations"][0]
                operation.update(target=target, value=value)
                self.assertTrue(any("same id" in error for error in validate_space(data)))

        data = minimal_space()
        operation = data["axes"][0]["choices"][0]["operations"][0]
        operation.update(target="architecture.features", value=["a", "a"])
        self.assertTrue(any("must not contain duplicates" in error for error in validate_space(data)))

    def test_operation_targets_must_be_unique_within_each_choice(self):
        data = minimal_space()
        operations = data["axes"][0]["choices"][0]["operations"]
        operations.append(copy.deepcopy(operations[0]))
        self.assertIn(
            "axes[0].choices[0].operations has duplicate target quantity:Q-WHEEL.value",
            validate_space(data),
        )

    def test_cartesian_product_must_fit_candidate_budget(self):
        data = minimal_space()
        data["max_candidates"] = 1
        self.assertIn(
            "axes Cartesian product 2 exceeds max_candidates 1; reduce choices or raise max_candidates",
            validate_space(data),
        )

        data = minimal_space()
        axis = copy.deepcopy(data["axes"][0])
        axis["id"] = "motor"
        data["axes"].extend(copy.deepcopy(axis) for _ in range(20))
        for index, item in enumerate(data["axes"]):
            item["id"] = f"axis-{index}"
        data["max_candidates"] = 10_000
        self.assertTrue(any("exceeds max_candidates 10000" in error for error in validate_space(data)))

    def test_uncertainties_are_closed_typed_and_canonically_unique(self):
        data = minimal_space()
        data["uncertainties"] = [
            {
                "id": "payload-cases",
                "target": "quantity:Q-PAYLOAD.value",
                "values": [
                    {"value": 1, "unit": "kg"},
                    {"value": 2, "unit": "kg"},
                ],
                "hard": False,
            }
        ]
        self.assertEqual(validate_space(data), [])

        invalid_cases = (
            ("target", "quantity:Q-PAYLOAD.tolerance"),
            ("target", "component:C"),
            ("values", []),
            ("values", None),
            ("values", [{"value": True, "unit": "kg"}]),
            ("hard", 1),
            ("hard", None),
        )
        for field, invalid in invalid_cases:
            with self.subTest(field=field, invalid=invalid):
                data = minimal_space()
                uncertainty = {
                    "id": "u",
                    "target": "quantity:Q.value",
                    "values": [{"value": 1, "unit": "kg"}],
                    "hard": True,
                }
                uncertainty[field] = invalid
                data["uncertainties"] = [uncertainty]
                self.assertNotEqual(validate_space(data), [])

        data = minimal_space()
        data["uncertainties"] = [
            {
                "id": "u",
                "target": "quantity:Q.value",
                "values": [
                    {"value": 1, "unit": "kg"},
                    {"unit": "kg", "value": 1},
                ],
                "hard": True,
            }
        ]
        self.assertIn(
            "uncertainties[0].values has duplicate canonical value at index 1",
            validate_space(data),
        )

    def test_objective_sources_and_direction_are_closed(self):
        valid = (
            "quantity:Q-MASS",
            "analysis:A-DRIVE.outputs.margin",
            "analysis:A-DRIVE.outputs.per_wheel.left.margin",
            "evidence:minimum-level",
            "diagnostics:blocking-count",
        )
        for source in valid:
            for direction in ("min", "max"):
                with self.subTest(source=source, direction=direction):
                    data = minimal_space()
                    data["objectives"] = [
                        {"id": "objective", "source": source, "direction": direction}
                    ]
                    self.assertEqual(validate_space(data), [])

        invalid = (
            "quantity:Q.value",
            "analysis:A",
            "analysis:A.outputs",
            "analysis:A.outputs.",
            "analysis:A.outputs.a..b",
            "evidence:E",
            "diagnostics:all-count",
            None,
            [],
        )
        for source in invalid:
            with self.subTest(source=source):
                data = minimal_space()
                data["objectives"] = [
                    {"id": "objective", "source": source, "direction": "min"}
                ]
                self.assertTrue(any("source" in error for error in validate_space(data)))

        for direction in ("MIN", "minimum", 1, True, None):
            with self.subTest(direction=direction):
                data = minimal_space()
                data["objectives"] = [
                    {"id": "objective", "source": "quantity:Q", "direction": direction}
                ]
                self.assertTrue(any("direction" in error for error in validate_space(data)))

    def test_repair_rules_are_bounded_and_nonempty(self):
        base_rule = {
            "id": "repair",
            "diagnostic_code": "ARM.OVERLOAD",
            "owner_prefix": "component:",
            "operations": [
                {
                    "target": "quantity:Q-PAYLOAD.value",
                    "value": {"value": 1, "unit": "kg"},
                }
            ],
            "max_applications": 1,
        }
        data = minimal_space()
        data["repair_rules"] = [base_rule]
        self.assertEqual(validate_space(data), [])

        for field, invalid in (
            ("diagnostic_code", ""),
            ("diagnostic_code", None),
            ("owner_prefix", "  "),
            ("owner_prefix", []),
            ("operations", []),
            ("operations", None),
            ("max_applications", True),
            ("max_applications", 0),
            ("max_applications", 101),
        ):
            with self.subTest(field=field, invalid=invalid):
                data = minimal_space()
                rule = copy.deepcopy(base_rule)
                rule[field] = invalid
                data["repair_rules"] = [rule]
                self.assertNotEqual(validate_space(data), [])

    def test_evaluation_stage_names_dependencies_and_order_are_closed(self):
        valid_stage_sets = (
            ["contract_v1", "physical_v030"],
            ["contract_v1", "physical_v030", "objectives_v1"],
            [
                "contract_v1",
                "physical_v030",
                "uncertainty_v1",
                "counterexample_v1",
                "objectives_v1",
            ],
        )
        for stages in valid_stage_sets:
            with self.subTest(stages=stages):
                self.assertEqual(
                    errors_for(lambda data: data["evaluation"].__setitem__("stages", stages)),
                    [],
                )

        invalid_stage_sets = (
            None,
            [],
            ["contract_v1"],
            ["physical_v030", "contract_v1"],
            ["contract_v1", "physical_v030", "physical_v030"],
            ["contract_v1", "physical_v030", "unknown"],
            ["contract_v1", "physical_v030", "counterexample_v1"],
            ["contract_v1", "physical_v030", "objectives_v1", "uncertainty_v1"],
        )
        for stages in invalid_stage_sets:
            with self.subTest(stages=stages):
                self.assertNotEqual(
                    errors_for(lambda data: data["evaluation"].__setitem__("stages", stages)),
                    [],
                )

    def test_validate_space_handles_canonical_json_boundaries_without_raising(self):
        invalid_values = (
            math.nan,
            math.inf,
            -(2**63) - 1,
            2**63,
            {"nested": {1: "non-string-key"}},
        )
        for invalid in invalid_values:
            with self.subTest(invalid=invalid):
                errors = errors_for(
                    lambda data: data["axes"][0]["choices"][0]["operations"][0].__setitem__(
                        "value", invalid
                    )
                )
                self.assertNotEqual(errors, [])


class HypothesisSpaceLoadTests(unittest.TestCase):
    def _load_bytes(self, payload: bytes):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "space.json"
            path.write_bytes(payload)
            return load_space(path)

    def test_load_space_accepts_utf8_json_and_validates_it(self):
        payload = json.dumps(minimal_space(), ensure_ascii=False).encode("utf-8")
        loaded, errors = self._load_bytes(payload)
        self.assertEqual(errors, [])
        self.assertEqual(loaded, minimal_space())

    def test_load_space_rejects_duplicate_keys(self):
        payload = b'{"schema_version":1,"schema_version":1}'
        loaded, errors = self._load_bytes(payload)
        self.assertIsNone(loaded)
        self.assertTrue(any("duplicate JSON key: schema_version" in error for error in errors))

    def test_load_space_rejects_nonfinite_constants_and_overflowing_floats(self):
        for token in (b"NaN", b"Infinity", b"-Infinity", b"1e309"):
            with self.subTest(token=token):
                loaded, errors = self._load_bytes(b'{"value":' + token + b"}")
                self.assertIsNone(loaded)
                self.assertTrue(any("non-finite" in error for error in errors), errors)

    def test_load_space_rejects_integers_longer_than_308_digits(self):
        loaded, errors = self._load_bytes(b'{"value":' + (b"9" * 309) + b"}")
        self.assertIsNone(loaded)
        self.assertTrue(any("308 digits" in error for error in errors), errors)

    def test_load_space_rejects_invalid_utf8(self):
        loaded, errors = self._load_bytes(b'{"space_id":"\xff"}')
        self.assertIsNone(loaded)
        self.assertTrue(any("not valid UTF-8" in error for error in errors), errors)

    def test_load_space_rejects_json_deeper_than_64(self):
        payload = ("[" * 65 + "0" + "]" * 65).encode("ascii")
        loaded, errors = self._load_bytes(payload)
        self.assertIsNone(loaded)
        self.assertTrue(any("maximum JSON depth of 64" in error for error in errors), errors)

    def test_load_space_rejects_files_larger_than_five_mib(self):
        loaded, errors = self._load_bytes(b" " * (5 * 1024 * 1024 + 1))
        self.assertIsNone(loaded)
        self.assertTrue(any("maximum size of 5 MiB" in error for error in errors), errors)

    def test_load_space_reports_missing_file_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            loaded, errors = load_space(path)
        self.assertIsNone(loaded)
        self.assertEqual(errors, [f"hypothesis space does not exist: {path}"])


if __name__ == "__main__":
    unittest.main()
