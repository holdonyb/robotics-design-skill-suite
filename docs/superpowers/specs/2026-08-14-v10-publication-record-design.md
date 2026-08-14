# v1.0 Publication Record Design

## Problem

The v1.0 release contract deliberately hashes `PROJECT_STATUS.md` and the
candidate audit. After the public tag is published, rewriting either file with
observed CI or release facts would make the released tree fail its own
reproducibility check. The published GitHub Release is already authoritative,
but the default branch lacks a durable, repository-local record that points to
that observed external evidence.

## Decision

Add `docs/releases/v1.0-publication-record.md` in a post-release commit. It is
explicitly a record about the published tag, not an input to the v1.0 release
contract and not a replacement for the candidate audit. It will name the
release commit and link the reviewed PR, main CI, main Jazzy/Harmonic consumer
simulation, tag CI, and GitHub Release. It will preserve the exact software-
and-simulation-only boundary.

This avoids three worse alternatives:

1. Rewrite hash-bound artifacts and invalidate `v1.0.0`.
2. Claim that the candidate audit itself observed events that happened later.
3. Treat CI or simulation as physical robot, bench, commissioning, task, or
   certification evidence.

## Invariants

- The record must identify `v1.0.0` and release commit
  `01c3740687016dd34c830e024ece062b7158c26f`.
- Every external assertion must have a direct GitHub link.
- It must state that reference bench, commissioning, and task intakes remain
  empty and that `hardware_claims: false` remains the release-contract result.
- It must explicitly deny procurement, fabrication, energization, device
  access, robot motion, physical performance, and certification claims.
- The v1 candidate audit and `PROJECT_STATUS.md` remain byte-identical, so the
  released tag continues to validate with its tracked contract.

## Verification

`tests/test_public_hygiene.py` will require the record, exact release facts,
direct links, and the non-hardware boundary. The existing v1 release validator
and distribution validator must remain green without regenerating the release
contract.
