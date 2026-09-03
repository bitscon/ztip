# Change Record

- **Date:** 2026-09-02
- **Type:** fix + spec (reference runtime, schemas, normative docs, CI) — first card
  of the vacuity remediation build, board card `zti:vac-protocol`
- **ADR reference:** none (no new architectural decision; this enforces rules the
  existing SPEC.md Completion Verification section already asserted)

## What changed

**Reference runtime — `ztip/chain.py`.** `verify_bundle` no longer reports an intact
bundle when it checked nothing meaningful. New finding codes, each fail-closed:

| Code | Refuses |
|---|---|
| `EMPTY_BUNDLE` | verification over zero envelopes |
| `REQUEST_HASH_UNRESOLVED` | a request reference naming a transaction request absent from the bundle — at the top-level field and at an authorization decision's approval scope |
| `REQUEST_HASH_BROKEN` | a reference whose request is present but does not hash to it |
| `CHILD_REQUEST_HASH_BROKEN` | a child reference whose request is present but does not hash to the declared child hash, or a container shape that would skip the check |
| `DUPLICATE_REQUEST` | two `transaction_request` envelopes sharing one `transaction_id` |
| `CONFLICTING_RECEIPTS` | receipts for one transaction disagreeing on the terminal state |
| `VERIFICATION_RESULTS_EMPTY` | a `succeeded` receipt that recorded no check result |
| `VERIFICATION_RESULT_MALFORMED` | a result that does not name the check or say whether it passed |
| `VERIFICATION_RESULT_UNSEALED` | a result stored under an annotation key, which the hash excludes |
| `SUCCESS_CONTRADICTS_RESULTS` | a `succeeded` receipt whose every recorded check reports failure |
| `RECEIPT_STATUS_INVALID` | a receipt status outside the defined set |
| `PROTOCOL_VERSION_MISSING` / `PROTOCOL_VERSION_UNSUPPORTED` | no `ztap_version`, or a major version this runtime does not verify |
| `INTEGRITY_METADATA_MISSING` / `INTEGRITY_ALGORITHM_UNSUPPORTED` | integrity that does not declare the rules it was sealed under, or declares ones this runtime does not apply |
| `REQUIRED_FIELD_MISSING` | a field the envelope type must carry (absent or null) |
| `ENVELOPE_TYPE_UNKNOWN` / `TRANSACTION_ID_MISSING` | content that is not a ZTIP envelope |
| `ENVELOPE_MALFORMED` / `ENVELOPE_UNHASHABLE` | a non-object entry, or one with no canonical form (previously an uncaught traceback) |
| `HASH_MISSING` / `HASH_MISMATCH` | the tamper check — unchanged in meaning, now pinned by tests |

`REQUEST_HASH_BROKEN` (a present-but-mismatched request) keeps its existing meaning and is
now distinct from an unresolvable reference. `envelopes()` is public so a caller's reported
count and the verifier's checked set are the same list. `verify_bundle` takes a keyword-only
`allow_unresolved_refs` for a deliberately partial bundle; positional callers are unaffected.

**CLI — `ztip/cli.py`.** `verify` reports how many envelopes it verified (and how many are
distinct, measured on the hashed form), how many request references it resolved, any content a
bundle wrapper carries beside its envelopes, any payload carried under an envelope's own
`envelopes` key, and any declared signature it cannot check. Its scope note names what it did
NOT do: field values were not validated against the schemas, a ZTIP hash proves nothing about
authenticity, and annotation fields are outside the hash. Exit codes are 0 verified, 1
findings, 2 unreadable input — a file that cannot be read no longer reads as a failed
verification, and no input produces a traceback. Every untrusted string on that surface — file
names, member names, envelope fields — is escaped, because stdout is what automation parses.

**Schemas.** `ztip-envelope.schema.json` gains a `verification_result` definition (`check_id`,
`check_type`, `passed` required; the rest typed when present) and a `visible_string` rule that
an identifier must carry a visible character — applied to check identifiers and to
`transaction_id`, and written so it means the same thing under Python and ECMA-262 regex
semantics. `execution-receipt.schema.json` types every result in every receipt state, requires
a non-empty result set when `status` is `succeeded`, and refuses results keyed by an annotation
name. `ztip-bundle.schema.json` describes the wrapper shape the shipped examples use, carrying
the same precedence rule the runtime applies, so the schemas alone accept the conformance
corpus and an envelope cannot hide behind a payload.

**Normative docs.** `SPEC.md`: a succeeded receipt must record at least one result; new
"What Hash Verification Does Not Answer" and "Bundle Verification" subsections.
`SCHEMA.md`: the `verification_results` field definition states the succeeded floor and points
requirement-correspondence at the control plane. `CONFORMANCE.md`: new "Bundle Verification
Conformance" subsection plus test-matrix rows T36b and T37–T48. `README.md` quickstart shows the real
output. `CHANGELOG.md` records all of it.

**Tooling.** `scripts/validate-examples.py` and `scripts/recompute_example_hashes.py` now share
the runtime's bundle splitter and its duplicate-member-name refusal, take an optional examples
directory so the shipped code itself is what the tests exercise, escape untrusted file names,
and refuse to report success over an empty or missing corpus. The validator moved to the
`referencing` registry API, installs a format checker so `date-time` is actually validated (and
refuses to run if that checking is unavailable), and reports the specific field that failed
rather than dumping the document.

**CI.** `validate.yml` runs `pytest tests/`, then installs the package and runs `ztip verify`
over every example. `publish.yml` runs the same gate before it builds a release artifact.
`requirements-dev.txt` adds `pytest` and floors `jsonschema[format-nongpl]>=4.18`.

**Tests.** New `tests/test_vacuity.py` — 179 regression tests, one or more per closed finding and
per finding raised in the review round, plus the shipped-content guard that every example passes
both the runtime floor and the schema, a drift guard that the runtime's required-field table
still matches the schemas, and a guard that every worked envelope example embedded in the
normative documents validates against the shipped schemas.

## Findings closed

From `zticore/docs/proof/2026-09-02-vacuity-scout-report.md` (2026-09-02 vacuity scout):
`verify-zero-checks-receipt`, `verify-empty-bundle`, `verify-dangling-request-hash`,
`verify-duplicate-request-shadowing`, `verify-schema-invalid-selfsealed`, `ci-validate-workflow`.

## Why

The scout proved `ztip verify` printed "integrity verified" over an empty bundle, over a
`succeeded` receipt that recorded zero checks, over a reference that resolved to nothing, over
a bundle carrying a forged duplicate request, and over self-sealed content that is not a ZTIP
envelope — and that the repository's only CI workflow went green with the runtime unable to
parse. This is the protocol's core claim, in a public MIT repository whose spec is posted as
an Internet-Draft. A verifier that cannot be trusted to refuse is worse than no verifier.

## Risk

**MEDIUM.** No hash rule, canonicalization rule, or field name changed, and all ten examples
verify and validate byte-identically — but `verify_bundle` is deliberately stricter, and
bundles that previously returned no findings can now return them. That is the intended
behaviour change and the reason for the review class. The one out-of-repo consumer effect is
registered below rather than silently absorbed.

## Verified

Every claim below was reproduced first-hand at seal time, not inferred.

**Hard constraints held.**

| Constraint | Evidence |
|---|---|
| `ztap_version` and the RFC 8785 / SHA-256 hash rule unchanged | `ztip/hashing.py` and `ztip/canonical.py` untouched; the schema diff does not mention `ztap_version`; the runtime only reads it |
| Existing receipts stay verifiable | `examples/` byte-identical to `HEAD`; 38 of 38 stored envelope hashes recompute exactly |
| 10/10 examples validate and verify | `scripts/validate-examples.py` 10/10 PASS; `ztip verify` exit 0 on all ten |
| Completeness rule left to the control plane | no check_id correspondence logic added; SPEC and SCHEMA both point that requirement at the plane |

**Battery.** 187 tests — 179 in `tests/test_vacuity.py` plus the 8 pre-existing runtime tests,
all green. Both CI workflows were reproduced step-for-step locally under `bash -e` in a clean
virtualenv: green on the clean tree; red with a syntax error planted in `ztip/chain.py` (at the
example-validation step, which now imports the runtime, and again at the test step); and red
with a semantic regression planted instead, at the test step. Under the old workflow both
breaks passed every step, which is the audit's regression case exactly. GitHub
Actions itself could not be observed (`gh` unauthenticated by design); the operator's Actions
tab is the confirming glance.

**Adversarial round — class L, two waves, second wave clean after remediation.**

| Wave | Lenses | Raised | Mechanized gate |
|---|---|---|---|
| 1 | vacuity refuter · spec/schema conformance · CI truth, test quality and blast radius | 28 | 18 mutations, 1 survivor (a real test gap, closed) |
| 2 | false-positive and over-reach · attack-the-remediation · published-claim truth | 27 | 39 mutations, then 49 after the fixes; 3 survivors, all real test gaps, closed |
| 3 | verify-the-wave-2-fixes · fresh-eyes final | 16 | 49 mutations, 1 survivor, closed |
| 4 | verify-the-wave-3-fixes · fresh-eyes final | 16 | 57 mutations, 1 survivor, closed |
| 5 | verify-the-wave-4-fixes · fresh-eyes final | 13 | 64 mutations, 1 survivor, closed |
| 6 | verify-the-wave-5-fixes · fresh-eyes final | 15 | 67 mutations, all killed |
| 7 | verify-the-wave-6-fixes · fresh-eyes final | 11 | 67 mutations, all killed |
| 8 | verify-the-wave-7-fixes · fresh-eyes final | 7 | 75 mutations, 75 killed; then 79 after wave 8's fixes |

Reviewers worked in isolated copies, read every file fresh from disk, and reported a finding
as confirmed only with a reproduction against live code. Every finding was re-reproduced by
the author before being acted on. Wave 1's critical finding was a total bypass: an object
carrying an `envelopes` key was read as a wrapper, so a `succeeded` receipt with zero results
hid behind a valid payload and was never checked at all — the exact vacuity this change
exists to refuse, reintroduced by the change's own splitter. Wave 2 then found that the
shipped schema validator still used the old splitter, so the two tools disagreed about what a
document is; they now share one. Wave 2 also found that the first fix for blank check
identifiers used a strip chain, which alternating whitespace and zero-width characters
defeats. Both are the documented pattern that remediation code carries its own defects.

Findings not fixed here are registered below. Nothing was left unreported.

Eight waves, 124 findings. The round was ended at wave 8 on the operator's instruction rather
than on a clean wave: severity had converged — wave 8's two lenses raised one schema
over-acceptance, one malformed-container skip and five documentation or test-coverage items,
with no new way to make the verifier report success over nothing — and each further wave costs
two deep reviewers and a full mutation gate. The deviation from "re-run until a wave comes back
clean" is recorded here deliberately, with the wave-8 findings all fixed before the seal and
the mutation gate ending at 79 of 79 killed.

Two findings deserve naming because they are this build's own failure mode, caught by the
round rather than by the author. Wave 6 found that the CI added by this change was **red on a
clean tree**: a test copied a script into a temporary directory, breaking that script's own
import path, and it passed locally only because the package happened to be installed. The
change record had already claimed "green on the clean tree". Wave 8 found the schema-side twin
of wave 1's critical: the wrapper branch added to `ztip-bundle.schema.json` accepted a
`succeeded` receipt with zero results as long as it also carried an `envelopes` key — the
runtime refused it, the published schema blessed it.

## Registered follow-ups (not worked here)

**Belongs to a future protocol card — the reference runtime diverges from RFC 8785 on numbers.**
Raised in wave 2 and reproduced. Two parts, one root cause in `ztip/canonical.py`:
non-integer numbers are refused outright (`ENVELOPE_UNHASHABLE`) although the schemas admit
`{"type": "number"}` for `expected_result` / `actual_result` and `requested_action.parameters`
is opaque; and integers at or above 10²¹ are serialized in full decimal where RFC 8785 requires
ES6 exponential form, so an envelope another conformant implementation sealed correctly is
reported `HASH_MISMATCH`. That is the worst class of false positive for an integrity tool.
Fixing it changes computed hashes for envelopes containing such values, which this card's hard
constraint forbids, and it is not one of the six findings this card closes. No shipped example
is affected. Recommended as its own card, ahead of any wider protocol adoption.

**Two receipts for one transaction with the same terminal state.** `DUPLICATE_REQUEST` closes
request shadowing and `CONFLICTING_RECEIPTS` closes receipts that disagree on the outcome, but
two `succeeded` receipts for one `transaction_id` with different recorded content still verify
clean. The rationale written for duplicate requests applies verbatim; SPEC carries the same
hole, permitting several envelopes per transaction without saying how many terminal receipts
one may have. A spec decision, not an implementation detail.

**Some hash-bearing references are still unresolved.** Two binding sites were closed here — the
top-level `request_hash` and an authorization decision's
`human_approval_ref.approval_scope`, which binds a human approval to the work it approved — and
a `child_receipt_ref` whose child request is present in the bundle must now declare that
request's real hash (`CHILD_REQUEST_HASH_BROKEN`). What remains: a child named with no request
in the bundle is not a finding, because example 08 legitimately exports two of its three
children, so whether a partial child set may verify is a protocol question; and
`child_receipt_hash` and `state_ref.state_hash` are not resolved at all. The CLI says "request
reference(s) resolved" rather than claiming more. Recommended as the next protocol card after
the demo work, alongside the RFC 8785 number defect.

**Non-receipt envelopes may carry `status` and `verification_results`.** Relabelling a receipt
as an `authorization_decision` reproduces the shape of the flagship vacuity, because the
envelope schemas do not forbid additional properties. The runtime now checks result *shape*
wherever results appear, so free text is refused; requiring the fields to be absent on other
envelope types would be a protocol tightening (`additionalProperties`) with real
backward-compatibility cost. Operator decision, not an implementation detail.

**`verification_actor` on a recorded result.** `SPEC.md` previously stated as a MUST that
results identify the verifying authority. Nothing enforces it, the schema lists the field as
optional, and none of the sixteen results in the ten shipped examples carry it. The text now
reads as the producer obligation it is. Promoting it back to a MUST means regenerating the
example hashes, which this card forbids.

**Cross-repo blast radius — belongs to the plane and evidence cards.** `ztip.chain.verify_bundle`
is imported by ZTI Core. Three consequences were reproduced by a reviewer: gate-minted receipts
record `check` rather than `check_type`, so every one now returns
`VERIFICATION_RESULT_MALFORMED` (one-line fix at the gate's receipt builder); legacy receipts
carrying `status: "blocked"` now return `RECEIPT_STATUS_INVALID`, since that value is not in
the protocol's status set; and an empty evidence-export window now reports `EMPTY_BUNDLE`
instead of verifying clean, which is the more honest result. None of this affects the plane's
live gating path, which uses `verify_envelope_hash` only.

**Internet-Draft.** One clause of the posted `draft-mccormack-ztip-00` is now contradicted:
its Security Considerations say integrity protection detects tampering with any envelope
content, while the repository states — and the runtime demonstrates — that non-normative
annotation fields are outside the hash by design. The draft already states the stripping rule
itself elsewhere, so it was self-inconsistent before this change; the repository's new text
makes it a flat contradiction. Everything else added here is absent from the draft rather than
contradicted by it. Whether to file a revised revision is the author's call and was not acted
on.
