# Changelog

## 1.0-draft — Unreleased

- **Verification cannot report success over nothing.** `ztip verify` now reports how many
  envelopes it verified and how many references it resolved, discloses any content a bundle
  wrapper carries beside its envelopes, and fails closed on: an empty
  bundle; a `request_hash` that resolves to no transaction request carrying the same
  `transaction_id`; a duplicate `transaction_request` for one transaction (which previously
  shadowed the honest request silently); an authorization decision whose
  `human_approval_ref.approval_scope` binds a human approval to a transaction not present in
  the bundle; receipts for one transaction disagreeing on the terminal state; content that does not satisfy the envelope contract (protocol version,
  envelope type, transaction id, declared integrity metadata, each type's required fields); an
  envelope declaring a canonicalization or hash algorithm the runtime does not apply; a
  `succeeded` receipt that recorded no verification result, or whose every recorded check
  reports failure; a result that does not name the check and say whether it passed; and a JSON
  document that declares the same member name twice. An object carrying any ZTIP envelope field
  (`ztap_version`, `envelope_type`, `transaction_id`, `integrity`) is always verified as an
  envelope, even when it also carries an `envelopes` key — previously such an object was read
  as a wrapper and never checked, and testing only `envelope_type` left the same bypass open
  to anything that dropped or nulled that one field. The success line scopes its claim:
  integrity and structure, not authenticity, and annotation fields are outside the hash.
  Unreadable input now exits 2 with a message instead of a traceback — on `ztip hash` as well
  as `ztip verify`, including a file that is not UTF-8, an envelope with no canonical form,
  and a bundle with nothing to hash; verification findings still exit 1.
- **Schema floor for a success claim.** `execution-receipt.schema.json` types every
  `verification_results` entry in every receipt state, and requires the collection to be
  non-empty when `status` is `succeeded`; non-succeeded receipts may still record none. New
  `verification_result` definition in `ztip-envelope.schema.json` (`check_id`, `check_type`,
  `passed` required; identifiers must carry a visible character; results may not be keyed by an
  annotation name, which the hash excludes). `ztip-bundle.schema.json` now also describes the
  wrapper shape the shipped examples use — carrying the same precedence rule, so an envelope
  that also has an `envelopes` key is validated as an envelope — and the schemas alone now
  accept the conformance corpus. Normative text added to
  `SPEC.md` (Bundle Verification; What Hash Verification Does Not Answer; Recorded Results),
  `SCHEMA.md`, and `CONFORMANCE.md` (Bundle Verification Conformance; test-matrix rows T36b
  and T37-T48). No change to the hash rule or to `ztap_version`; all ten examples verify and
  validate unchanged.
- **CI exercises the runtime.** `validate.yml` previously ran only JSON syntax and example
  schema checks, so it never executed the reference runtime at all — it stayed green with
  `ztip/chain.py` unable to parse. It now runs `pytest tests/`, then installs the package and
  runs `ztip verify` over every example. The manual release workflow (`publish.yml`) runs the
  same three checks before it builds an artifact. `scripts/validate-examples.py` and the test
  suite moved from the deprecated `jsonschema.RefResolver` to the `referencing` registry API,
  now share the reference runtime's bundle splitter so the two shipped tools cannot disagree
  about what a document is, and now install a format checker so `"format": "date-time"` is
  actually validated rather than merely annotated (`requirements-dev.txt` floors
  `jsonschema[format-nongpl]>=4.18`). Validation errors report the specific field that failed
  instead of dumping the whole document.

### Breaking changes for implementers

These change verdicts on content that previously passed. Each is deliberate.

- **Partial bundles.** A bundle whose `request_hash` cannot be resolved — for example receipts
  held without their requests — now fails. Pass `--allow-unresolved-refs` (CLI) or
  `allow_unresolved_refs=True` (`ztip.chain.verify_bundle`) to verify it anyway; the success
  line then states that chain linkage was not verified.
- **Receipts.** A `succeeded` receipt with an empty `verification_results` no longer validates
  or verifies. Results in any receipt state must be structured — free text is rejected — and
  each must carry `check_id`, `check_type`, and a boolean `passed`.
- **Envelopes.** Content missing `ztap_version`, `integrity.canonicalization`,
  `integrity.hash_algorithm`, or a required field of its envelope type now produces a finding
  rather than verifying clean.
- **Timestamps.** `format: date-time` is now enforced by `scripts/validate-examples.py`, so a
  malformed `created_at` / `completed_at` that previously passed validation now fails it.
- **`ztip.chain`.** `verify_bundle` gains a keyword-only `allow_unresolved_refs`; positional
  callers are unaffected. `envelopes()`, `resolved_reference_count()` and
  `unverified_bundle_keys()` are public.

- **Protocol renamed: ZTAP → ZTIP (Zero Trust Intelligence Protocol)** — repo, package,
  CLI (`ztip hash` / `ztip verify`), schema filenames, and all documentation. The envelope
  field `ztap_version` is deliberately retained as a legacy name for hash stability (it sits
  inside the canonicalized content that envelope hashes cover); see the legacy-field note in
  `SCHEMA.md`. No hashes or envelope semantics changed.

- Initial protocol doctrine.
- `SPEC.md` baseline protocol definition.
- `SCHEMA.md` envelope and field model.
- `CONFORMANCE.md` conformance requirements and invariants.
- JSON Schema Draft 2020-12 files under `schemas/`.
- 10 protocol lifecycle examples under `examples/`.
- Example validation script: `scripts/validate-examples.py`.
- Completion verification: new normative `SPEC.md` section — independent verification of
  executor results; attestation never satisfies a required check; fail-closed via
  `COMPLETION_UNVERIFIED` / `VERIFY_UNAVAILABLE`.
- Canonicalization finalized: RFC 8785 (JSON Canonicalization Scheme) with SHA-256, normative
  in `SPEC.md` and `SCHEMA.md` (hash computed with `integrity.hash_value` removed and
  underscore-prefixed annotation keys stripped).
- Reference runtime: `ztip/` package (RFC 8785 canonicalization, SHA-256 hashing, hash-chain
  verification) with `ztip hash` and `ztip verify` CLI commands.
- Example integrity hashes are real and recomputable with the reference runtime.
- Status alignment: `SPEC.md` now carries the shared `1.0-draft` version string; stale
  pre-schema / not-for-implementation notices replaced across spec, schema status blocks,
  and example draft notices to match the shipped schemas and runtime.
