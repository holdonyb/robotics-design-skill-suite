# Robot Visualization Contract

Use this contract for photorealistic, product, task, concept, marketing, and image-generation views that claim to depict the designed robot.

## Authority Boundary

**CAD, URDF, or SDF owns topology and pose.** A deterministic equivalent is acceptable only when it can reproduce the same joint chain, axes, link proportions, interfaces, and joint values.

An image model may change:

- materials and surface finish;
- color;
- lighting;
- background and non-contact environment context.

It may not change topology, pose, joint count, joint axes, interfaces, link proportions, contact geometry, or tool attachment state. The image model never solves kinematics.

## Required Workflow

1. Freeze the mechanism, interface, and visual invariants in the design contract.
2. Set the exact task pose in CAD, URDF, SDF, or another deterministic kinematic model.
3. Produce deterministic isometric and orthographic reference views. Add views until every required joint and interface landmark can be enumerated without guessing.
4. Create a visual manifest with hashes of the source model, source pose, and reference images.
5. Use the exact target-pose render for an **image-to-image appearance pass**. The prompt must repeat the allowed and forbidden change lists.
6. Compare the generated image side by side with the deterministic references. Record only landmarks actually visible and identifiable.
7. Require `required_landmarks == observed_landmarks`, run `scripts/validate_visual_manifest.py`, and promote only after it passes.

If the requested task needs a different articulation, **change the pose upstream**, rerender the exact pose, and restart the appearance pass. Never ask an image model to unfold a stowed robot, move an arm, bend a joint, attach a tool, or invent a reverse view.

## Manifest Fields

| Field | Required content |
|---|---|
| `schema_version` | Integer `1` |
| `shot_id` | Stable non-empty identifier |
| `status` | `draft`, `rejected`, or `promoted` |
| `source_model` | Object with a manifest-relative `path` and lowercase `sha256` |
| `source_pose` | Object with a manifest-relative `path` and lowercase `sha256` |
| `reference_images` | Non-empty list of deterministic render path/hash objects |
| `required_landmarks` | Unique canonical joint/interface identifiers |
| `observed_landmarks` | Unique identifiers actually verified in the generated image |
| `allowed_changes` | Subset of `materials`, `surface_finish`, `color`, `lighting`, `background`, `environment` |
| `forbidden_changes` | Must include `topology`, `pose`, `joint_count`, `joint_axes`, `interfaces`, `link_proportions` |
| `review` | For promotion: non-empty `reviewer`, `method`, and `notes` |

All paths resolve from the manifest directory. A promoted manifest requires at least one landmark and exact set equality; ordering does not matter and duplicates are invalid.

## Landmark Rules

- Use canonical identifiers from the design model: `J1` through `J7`, `interface_A`, `interface_B`, and instance prefixes for multi-arm systems.
- Include passive docking ports, active end interfaces, tools, wheels, suspension pivots, or other identity-critical features when the shot claims to show them.
- Do not count a likely bulge, panel, or cylinder as a joint. Its axis and connection to adjacent links must be visually traceable.
- If perspective, lighting, cropping, or occlusion hides a required landmark, reject the shot or add a second view. Do not infer compliance.
- Extra apparent joints or interfaces are a mismatch, not harmless styling.

## Promotion States

| Status | Meaning | May ship as the designed robot? |
|---|---|---|
| `draft` | Awaiting generation or review | No |
| `rejected` | A visual invariant failed | No |
| `promoted` | Sources, hashes, landmarks, and review passed | Yes, within the stated claim boundary |

A disclaimer does not repair a structural mismatch. A free-form mood image may be retained only when it is clearly outside the engineering evidence chain and is not presented as the designed robot.

## Seven-Axis R-P-R Example

For one dual-ended seven-axis R-P-R / P / R-P-R arm, a minimal landmark set is:

```text
J1, J2, J3, J4, J5, J6, J7, interface_A, interface_B
```

For two rover arms, use `left_arm.*` and `right_arm.*`. A render that substitutes a generic seven-axis collaborative arm, hides the endpoint wrist groups, loses a four-claw port, or changes the central pitch joint fails even if the overall silhouette is attractive.

## Validator

Run:

```bash
python skills/robotics-design/scripts/validate_visual_manifest.py path/to/visual_manifest.json
```

The validator proves manifest consistency, source integrity, authorized change categories, landmark equality, and recorded review. It does not prove flight readiness, loads, thermal closure, collision clearance, or manufacturability.
