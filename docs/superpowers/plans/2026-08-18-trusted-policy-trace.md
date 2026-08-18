# Trusted Policy Trace Implementation Plan

**Goal:** Make every portable policy score and backend result derive from a registry-authorized trace generated for that exact policy/action sequence.

**Architecture:** Add a registry authority record and deterministic reference runner, extend trace/replay identity with policy and actions, then route training/backend consumers exclusively through registry-issued assignments.

### Task 1: Registry authority

- [ ] Add failing tests rejecting a self-published bundle, registry hash drift,
  unknown scenario, and a receipt from another registry.
- [ ] Implement immutable `TrustedScenarioRegistry` loader that verifies the
  external registry receipt and compiled registry identity.
- [ ] Bind the reference `scenarios.json` through a retained external receipt.

### Task 2: Action-bound trace format and runner

- [ ] Add failing tests proving a trace rejects missing/reordered/nonfinite
  actions, policy digest mismatch, and action/state timestamp mismatch.
- [ ] Extend trace publication/replay with canonical policy/action fields.
- [ ] Add a bounded deterministic reference runner that creates a trace from
  the evaluated action sequence.

### Task 3: Trusted evaluation and closure

- [ ] Add failing tests that two different in-range policies cannot share a
  score, and every delivery runtime dependency is release-bound.
- [ ] Make training/backend accept only registry-issued assignments and bind
  policy/action identity in outputs.
- [ ] Expand v1.1 runtime closure, regenerate the release contract, run full
  tests and independent review before any push.
