import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "robotics-design" / "SKILL.md"
VISUALIZATION_CONTRACT = (
    ROOT / "skills" / "robotics-design" / "references" / "visualization-contract.md"
)


class RoboticsDesignBehaviorTests(unittest.TestCase):
    def test_robot_render_requests_route_to_visualization_contract(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("references/visualization-contract.md", text)
        self.assertIn("Photorealistic, product, task, concept, or marketing robot renders", text)

    def test_skill_forbids_generative_reposing_and_reconfiguration(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("Never ask a generative model to articulate, repose, unfold, or reconfigure a robot", text)
        self.assertIn("A disclaimer does not make a structurally wrong robot image acceptable", text)

    def test_visualization_contract_assigns_pose_to_deterministic_model(self):
        self.assertTrue(VISUALIZATION_CONTRACT.is_file())
        text = VISUALIZATION_CONTRACT.read_text(encoding="utf-8")
        self.assertIn("CAD, URDF, or SDF owns topology and pose", text)
        self.assertIn("image-to-image appearance pass", text)
        self.assertIn("required_landmarks == observed_landmarks", text)

    def test_visualization_contract_requires_upstream_pose_change(self):
        text = VISUALIZATION_CONTRACT.read_text(encoding="utf-8")
        self.assertIn("change the pose upstream", text)
        self.assertIn("The image model never solves kinematics", text)

    def test_visualization_contract_documents_manifest_schema(self):
        text = VISUALIZATION_CONTRACT.read_text(encoding="utf-8")
        for field in (
            "`source_model`",
            "`source_pose`",
            "`reference_images`",
            "`required_landmarks`",
            "`observed_landmarks`",
            "`allowed_changes`",
            "`forbidden_changes`",
            "`review`",
        ):
            self.assertIn(field, text)


if __name__ == "__main__":
    unittest.main()
