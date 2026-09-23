> **Read `ESTATE.md` first** - it says where this repository lives and which law applies here.

# AGENTS

## System Identity

ztip is the canonical home of the ZTIP (Zero Trust Intelligence Protocol) specification,
schemas, conformance criteria, and examples. It is a standalone open-source project:
the repository MUST build, validate, and be understood on its own, with no dependency
on any private sibling repository or a parent workspace's private state.

## Project Identity

- **Type:** python-tool (spec corpus + validator/runtime tooling)
- **GitHub remote:** bitscon/ztip
- **Deploy target:** none

## Source-of-Truth Rules

1. `SPEC.md` is the protocol canon. Schema files under `schemas/` and examples under
   `examples/` MUST conform to it.
2. Spec, schemas, and examples MUST agree on one protocol version string. A change
   that moves the version updates all three plus `CHANGELOG.md` in the same commit.
3. Example envelopes MUST carry real, recomputable integrity hashes. Placeholder
   hashes are a defect, not a convention.
4. Generated or recomputed artifacts (example hashes, conformance vectors) come from
   tooling in `scripts/` — never hand-edited.

## Portability Rules (keep the protocol vendor-neutral)

The worth of an open protocol is that it is implementation-agnostic. Therefore:

- Do not encode any single implementation's module paths, class names, internal
  document names, or private governance identifiers into spec text, schemas, or examples.
- Define roles, scopes, and phases generically; never adopt one deployment's specific
  identifiers as protocol vocabulary.
- Do not introduce a runtime dependency on any private repository or its state; protocol
  artifacts must remain portable.

## Prohibited Actions

- Modify files outside ztip/
- Delete files without explicit instruction
- Claim ZTIP replaces MCP or A2A, or imply encryption is mandatory (see the public
  positioning/alignment docs for locked terminology)
- Add a dependency on any private repository's paths, runtime state, or governance logic

## Change Discipline

Every spec-content or code task records a Change Record under `docs/changes/`
(`CHANGE-YYYY-MM-DD-NNN-<slug>.md`). Validators (`scripts/` against `schemas/` +
`examples/`) must pass before commit.

## Reporting Requirement

Every agent session must end with a list of all files created or modified.
