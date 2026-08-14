import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_has_expected_schema(self):
        self.assertEqual(self.data["schema_version"], 1)
        self.assertEqual(self.data["suite"]["name"], "robotics-design-skill-suite")
        self.assertEqual(self.data["suite"]["version"], "0.9.0")

    def test_sources_are_pinned_and_licensed(self):
        source_ids = []
        for source in self.data["sources"]:
            source_ids.append(source["id"])
            self.assertRegex(source["repo"], r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
            self.assertTrue(re.fullmatch(r"[0-9a-f]{40}", source["commit"]))
            self.assertIn(source["license"], {"MIT", "Apache-2.0"})
            self.assertEqual(source["license_path"], "LICENSE")
            self.assertTrue(source["skills"])
        self.assertEqual(len(source_ids), len(set(source_ids)))

    def test_every_destination_name_is_unique(self):
        names = [skill["name"] for source in self.data["sources"] for skill in source["skills"]]
        names.extend(skill["name"] for skill in self.data["local_skills"])
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(
            set(names),
            {
                "cad",
                "cad-viewer",
                "step-parts",
                "dxf",
                "urdf",
                "sdf",
                "srdf",
                "ros2-engineering-skills",
                "ros2-sim",
                "robotics-design",
            },
        )

    def test_local_skill_paths_exist(self):
        for skill in self.data["local_skills"]:
            path = ROOT / skill["path"]
            self.assertTrue((path / "SKILL.md").is_file(), path)


if __name__ == "__main__":
    unittest.main()
