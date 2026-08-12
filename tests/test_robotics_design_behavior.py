import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "robotics-design" / "SKILL.md"
VISUALIZATION_CONTRACT = (
    ROOT / "skills" / "robotics-design" / "references" / "visualization-contract.md"
)
MISSION_CONTRACT = (
    ROOT / "skills" / "robotics-design" / "references" / "mission-animation-contract.md"
)
PATENT_CONTRACT = (
    ROOT / "skills" / "robotics-design" / "references" / "patent-design-around.md"
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

    def test_mission_animation_routes_to_traceable_motion_contract(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("references/mission-animation-contract.md", text)
        self.assertIn("validate_mission_animation_manifest.py", text)
        self.assertIn("Mission, operation, assembly, docking", text)

    def test_mission_contract_forbids_hand_authored_robot_joint_motion(self):
        self.assertTrue(MISSION_CONTRACT.is_file())
        text = MISSION_CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Never keyframe robot joint poses by hand", text)
        self.assertIn("One versioned trajectory owns robot pose over time", text)
        self.assertIn("contact state", text.lower())
        self.assertIn("J4", text)

    def test_patent_requests_route_through_research_and_design_contract(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("references/patent-design-around.md", text)
        self.assertIn("$deep-research", text)
        self.assertIn("Patent study, competitor-inspired design", text)

    def test_patent_contract_requires_claim_controls_and_legal_boundary(self):
        self.assertTrue(PATENT_CONTRACT.is_file())
        text = PATENT_CONTRACT.read_text(encoding="utf-8")
        for required in (
            "claim chart",
            "equivalents",
            "official register",
            "positive design requirements",
            "drift tests",
            "qualified counsel",
        ):
            self.assertIn(required, text.lower())
        self.assertIn("FTO", text)


if __name__ == "__main__":
    unittest.main()
