# Contributing to ZTIP

Thanks for helping improve ZTIP. This repository is the public protocol source for the Zero Trust Intelligence Protocol.

## Project Purpose
ZTIP defines governance rules and machine-readable envelope formats for governed agent work. This repo contains protocol docs, schemas, examples, and validation tooling.

## Contribution Scope
In scope:
- Protocol documentation (`SPEC.md`, `SCHEMA.md`, `CONFORMANCE.md`)
- JSON Schema files under `schemas/`
- Example envelopes under `examples/`
- The reference runtime under `ztip/` and its tests under `tests/`
- Validation and contributor tooling under `scripts/`

Out of scope for this repo:
- ZTI Core or other commercial control-plane product code
- Transport-specific protocol bindings as required core behavior

## Protocol Guardrails
Please preserve these protocol constraints in all contributions:
- Use only ZTIP protocol roles in `role` fields. Do not use vendor, tool, platform, or model names as roles.
- Do not add ZTI Core implementation code to this repo.
- Do not introduce implementation-specific runtime dependencies. Protocol artifacts must remain portable.
- Preserve transport neutrality.
- Preserve the integrity-over-encryption principle:
  - Integrity is mandatory.
  - Encryption is policy-conditional, not a core requirement.

## Protocol Change Process
For any protocol-impacting change:
1. Open an issue describing the problem, rationale, and expected impact.
2. Submit a PR that updates all affected artifacts together:
   - prose spec/conformance text as needed,
   - machine-readable schemas,
   - examples,
   - changelog entry.
3. Keep behavior fail-closed and backward-aware for `1.0-draft` unless a deliberate breaking change is proposed.

## Issues and Pull Requests
- Keep issues focused and reproducible.
- Link PRs to their issues.
- Explain motivation, scope, and tradeoffs.
- Include before/after notes for schema or example changes.
- Keep PRs reviewable; split large unrelated changes.

## Validation Requirements
Install the dev dependencies once:

```bash
python3 -m pip install -r requirements-dev.txt
```

If you change `schemas/`, `examples/`, or validation tooling, run:

```bash
python3 scripts/validate-examples.py
```

If you change anything under `ztip/` or `tests/`, run the reference runtime's tests:

```bash
python3 -m pytest tests/
```

CI runs both on every push and pull request, and the release workflow runs them before it
builds an artifact. Do not merge changes that break example validation or the test suite.

A note on what those tests are for: `tests/test_vacuity.py` exists to keep `ztip verify` from
ever reporting success over content it did not check. If you relax a rule there, say why in the
pull request — a verifier that cannot be trusted to refuse is worse than no verifier.

## Licensing
By contributing, you agree that your contributions are licensed under the repository's MIT License.
