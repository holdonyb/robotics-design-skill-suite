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
PHYSICAL_CONTRACT = (
    ROOT / "skills" / "robotics-design" / "references" / "physical-plausibility-contract.md"
)
HYPOTHESIS_CONTRACT = (
    ROOT / "skills" / "robotics-design" / "references" / "hypothesis-engine-contract.md"
)
AUTHORITY_CONTRACT = (
    ROOT / "skills" / "robotics-design" / "references" / "hardware-authority-contract.md"
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
            "`rendered_image`",
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

    def test_component_selection_and_feasibility_route_through_physical_contract(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("references/physical-plausibility-contract.md", text)
        self.assertIn(
            "before selecting components or claiming physical feasibility", text
        )
        self.assertIn("validate_design_contract.py", text)

    def test_physical_contract_blocks_incomplete_load_paths_and_premature_simulation(self):
        self.assertTrue(PHYSICAL_CONTRACT.is_file())
        text = PHYSICAL_CONTRACT.read_text(encoding="utf-8")
        for clause in (
            "motor, reducer, bearing, and motor driver",
            "Analytical gates run before simulation or training",
            "evidence level",
            "failure report",
            "engineering_placeholder",
            "thermal_duty_v1",
            "simulation cannot replace",
        ):
            self.assertIn(clause, text)

    def test_multi_candidate_requests_route_through_hypothesis_contract(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("references/hypothesis-engine-contract.md", text)
        self.assertIn("scripts/generate_design_hypotheses.py", text)
        self.assertIn("Never rank a candidate that bypassed the physical contract", text)
        for trigger in ("multi-concept", "parameter sweep", "robustness", "repair"):
            self.assertIn(trigger, text.lower())

    def test_hypothesis_contract_is_operational_and_preserves_claim_boundaries(self):
        self.assertTrue(HYPOTHESIS_CONTRACT.is_file())
        text = HYPOTHESIS_CONTRACT.read_text(encoding="utf-8")
        for required in (
            "contract_v1",
            "physical_v030",
            "uncertainty_v1",
            "counterexample_v1",
            "objectives_v1",
            "max_candidates",
            "max_stage_evaluations",
            "manifest_sha256",
            "validate_bundle",
            "owner_prefix",
            "screening-pareto.json",
            "BOM.PLACEHOLDER_BLOCKS_CLAIM",
            "unrepairable non-placeholder blocker",
            "Exit `0`",
            "Exit `1`",
            "Exit `2`",
            "simulation",
            "hardware",
        ):
            self.assertIn(required, text)

    def test_hypothesis_design_order_is_contract_then_search_then_simulation(self):
        design = (
            ROOT / "skills" / "robotics-design" / "references" / "design-contract.md"
        ).read_text(encoding="utf-8")
        gates = (
            ROOT / "skills" / "robotics-design" / "references" / "validation-gates.md"
        ).read_text(encoding="utf-8")
        self.assertIn("hypothesis-engine-contract.md", design)
        self.assertIn("physical contract -> bounded hypothesis search -> simulation", design)
        self.assertIn("Hypothesis exploration", gates)
        self.assertIn("hard counterexample", gates)

    def test_hardware_authority_route_binds_external_scope_without_granting_motion(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("references/hardware-authority-contract.md", text)
        self.assertTrue(AUTHORITY_CONTRACT.is_file())
        contract = AUTHORITY_CONTRACT.read_text(encoding="utf-8")
        for phrase in (
            "external_human_attestation",
            "design contract",
            "reachable emergency stop",
            "never grants procurement or motion authority",
        ):
            self.assertIn(phrase, contract)


if __name__ == "__main__":
    unittest.main()
