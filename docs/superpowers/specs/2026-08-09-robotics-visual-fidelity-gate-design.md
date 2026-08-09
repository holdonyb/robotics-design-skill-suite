# Robotics Visual Fidelity Gate v0.2.0

**Status:** Approved for implementation  
**Date:** 2026-08-09

## Problem

Photorealistic image generation can preserve the general appearance of a robot while silently changing its mechanism. In the observed failure, a deterministic stowed render was used as the only reference and the image model was asked to unfold the robot. The resulting rover image replaced the specified seven-axis R-P-R / P / R-P-R arms with generic collaborative-arm chains. The image looked plausible but no longer represented the designed robot.

This is a process failure, not a prompt-quality problem. A generative model must not own robot articulation, topology, joint axes, link proportions, or interfaces.

## Decision

Version 0.2.0 adds a hard visual-fidelity contract:

1. CAD, URDF, SDF, or an equivalent deterministic model owns topology and pose.
2. A generative image model may change only appearance and environment: materials, surface finish, color, lighting, background, and non-contact scene context.
3. Reposing, unfolding, reconfiguring, or inventing robot geometry with a generative model is prohibited.
4. Every promoted generated render needs a machine-checkable visual manifest.
5. Required joint and interface landmarks must match the observed landmark set exactly before promotion.
6. If a required landmark is occluded, the image is not sufficient evidence; create another deterministic view or reject it.
7. A disclaimer cannot convert a structurally wrong image into an acceptable concept image.

## Required Pipeline

```text
design contract
  -> deterministic CAD/URDF/SDF model
  -> exact target pose in the deterministic model
  -> reference views with visible joint/interface landmarks
  -> visual manifest with source hashes
  -> image-to-image appearance pass only
  -> landmark review
  -> manifest validation
  -> promotion
```

If a task needs a different pose, the pose is changed upstream and rendered again. The image model never solves kinematics.

## Visual Manifest

The manifest is JSON and contains:

- `schema_version`
- `shot_id`
- `status`: `draft`, `rejected`, or `promoted`
- `source_model`: relative path and SHA-256
- `source_pose`: relative path and SHA-256
- `reference_images`: one or more relative paths and SHA-256 values
- `required_landmarks`: unique canonical joint/interface identifiers
- `observed_landmarks`: unique identifiers verified in the generated image
- `allowed_changes`
- `forbidden_changes`
- `review`: reviewer, method, and notes

For a promoted asset:

- every source file exists and matches its recorded hash;
- `observed_landmarks` equals `required_landmarks` exactly;
- allowed changes are limited to appearance/environment categories;
- topology, pose, joint count, joint axes, interfaces, and link proportions are explicitly forbidden;
- reviewer and review method are present.

Draft and rejected assets may be incomplete, but they are never shippable.

## Landmark Convention

Landmarks use stable identifiers from the design contract, not descriptive prose. A seven-axis dual-ended R-P-R arm should include `J1` through `J7` plus both endpoint interfaces. Multi-arm systems prefix the mechanism instance, for example `left_arm.J1` and `right_arm.J1`.

Landmarks confirm visual presence and identity. They do not replace kinematic, collision, structural, thermal, electrical, or manufacturing validation.

## Enforcement Layers

1. **Skill routing:** any product, task, concept, or marketing render must load the visualization contract.
2. **Hard rule:** generative articulation/reconfiguration is forbidden.
3. **Executable gate:** `validate_visual_manifest.py` rejects missing hashes, unauthorized changes, and landmark mismatch.
4. **Repository tests:** behavioral clauses and validator behavior are regression-tested.
5. **Promotion state:** only a valid `promoted` manifest authorizes an image for presentation as the designed robot.

## Non-Goals

- Image comparison does not certify flight readiness.
- The gate does not infer loads, torque margins, radiation tolerance, or thermal closure from pixels.
- The gate does not make a generated image a CAD authority.
- The gate does not prohibit clearly labeled free-form mood boards that make no claim to depict the designed robot; such images remain outside the evidence chain and cannot replace design renders.

## Acceptance Criteria

- The observed “stowed reference -> generatively unfolded robot” workflow is explicitly forbidden.
- A valid promoted manifest passes the validator.
- A promoted manifest fails if one joint or interface landmark is missing or added.
- A manifest fails if pose or topology is listed as an allowed change.
- A manifest fails if a source file is modified after hashing.
- The main skill, validation gates, and design contract consistently describe deterministic pose ownership.
- Version and distribution validation pass at 0.2.0.
