# Patent-Aware Robot Design Contract

Use this workflow when a robot design is influenced by a patent, competitor product, paper, teardown, or public demonstration. It is an engineering design-around screen, not a legal opinion.

## Evidence hierarchy

1. Obtain the official publication, complete claims, description, drawings, family and current official register or file-wrapper status.
2. Use patent aggregators for discovery only. Record conflicts between an aggregator and the official register.
3. Read each independent claim as a required combination of elements. Use dependent claims to identify narrower combinations and likely fallback positions.
4. Search earlier patents, papers, standards, and products before choosing an alternative; a change that avoids one document can enter older prior art or another live claim.
5. Preserve page, figure, paragraph, claim, family member, event date, URL, and retrieval date for every material fact.

## Required claim chart

Create a project-local claim chart with one row per limitation:

| Claim | Element/relationship | Source passage or figure | Current design | Proposed disposition | Literal-risk rationale | Equivalents-risk rationale | Owned artifact/test | Status |
|---|---|---|---|---|---|---|---|---|

Use `absent`, `materially different`, `unresolved`, or `present` for the proposed disposition. Do not use vague labels such as “looks different.” For a combination claim, preserve both the component and its claimed placement, connection, sequence, role, or control relationship.

## Design-around process

1. Freeze the baseline design and hash the reviewed artifacts.
2. Decompose every relevant independent claim; then review dependent claims and related families.
3. Mark literal overlap and credible equivalents. Treat substantially the same means, function, and result as a risk even when shape or naming differs.
4. Generate alternatives at architecture level before geometry level: topology, load path, sensing placement, power architecture, control distribution, interface roles, restraint, maintenance, and task sequence.
5. Select at least two independent distinguishing principles for each high-risk claim combination. Prefer differences that improve mission performance or serviceability and are visible in requirements, schematics, CAD, URDF/SDF, software, and tests.
6. Convert selected distinctions into positive design requirements and prohibited combinations in the project design contract.
7. Add drift tests so later optimization cannot silently reintroduce the claimed combination.
8. Re-run the claim chart after every interface-driving architecture change and before supplier release, design review, patent filing, manufacturing freeze, or external publication.

## Hard boundaries

- A drawing alone does not define scope; claims govern, with description and drawings used for interpretation.
- A rejected, lapsed, expired, pending, or apparently abandoned case is not enough to close FTO. Verify continuations, divisionals, re-examination, appeals, family members, and applicable territories.
- Do not conclude `non-infringing`, `patent-safe`, `clear to manufacture`, or `FTO complete`. State `preliminary engineering design-around controls applied` until qualified counsel reviews the live claim chart and official file wrapper.
- Do not copy a competitor’s ornamental appearance, dimension pattern, distinctive packaging, or undocumented implementation merely because it is absent from one independent claim.
- Keep patent analysis out of public marketing renders and supplier drawings unless disclosure is approved.

## Review package

Provide the source registry, annotated figures, claim chart, architecture overlap matrix, selected design constraints, rejected alternatives, automated drift tests, status uncertainties, and questions for qualified counsel. Record the exact design revision reviewed; legal review of an older revision does not transfer automatically.
