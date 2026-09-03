# ZTIP Conformance Draft

*Zero Trust Intelligence Protocol — What It Means to Be Compliant*

---

## Status

**DRAFT — Conformance target for ZTIP `1.0-draft`.**

This document defines conformance requirements for implementations of the Zero Trust Agent
Protocol. It is derived from `SPEC.md` and `SCHEMA.md`. Where this document conflicts with
those, `SPEC.md` is authoritative on governance model and lifecycle, and `SCHEMA.md` is
authoritative on field definitions.

This is an early draft. Conformance test fixtures, certification procedures, and formal
conformance claim formats have not yet been defined.

Do not build production certification processes against this draft.

---

## Conformance Philosophy

ZTIP conformance is grounded in the following non-negotiable principles:

**Fail-closed is a protocol invariant, not a configuration option.**
A conforming implementation must reject invalid, unknown, expired, tampered, or unauthorized
transactions under all circumstances. There is no permissive fallback mode. Ambiguity resolves
to denial.

**Integrity is mandatory.**
Every ZTIP envelope must carry a valid `integrity` object. Implementations must compute and
verify hashes. An envelope without a verifiable hash is not a ZTIP envelope.

**Encryption is policy-conditional.**
ZTIP v1 does not require encryption. Envelopes are plain JSON by default and must be human-
auditable without decryption. Encryption may be layered on top for specific deployment
contexts, but it is not a core conformance requirement and must not be a prerequisite for
envelope processing.

**Transport is out of scope.**
ZTIP conformance is not concerned with how envelopes are delivered. A conforming
implementation must not assume any transport. Governance is enforced at the envelope level,
not at the network layer.

**ZTIP governs the action, not the pipe.**
A conforming actor, runtime, or control plane must refuse governed work unless a valid,
verified ZTIP authorization record exists for the specific action being requested. The fact
that a message arrived over a secure channel does not make it authorized. The authorization
record governs. The transport does not.

---

## Conformance Levels

ZTIP defines three conformance levels. Higher levels include the requirements of all lower
levels. A conforming implementation must declare which level it targets.

---

### Level 1 — Envelope Validator

An Envelope Validator can parse, validate, and report on the structural correctness of ZTIP
envelopes. It does not need to evaluate policy, manage actor registrations, or process
transactions end-to-end.

**An Envelope Validator MUST:**

- Parse any ZTIP envelope presented to it.
- Validate that all required shared fields are present: `ztap_version`, `envelope_type`,
  `transaction_id`, `integrity`. An identifier made only of whitespace or zero-width
  characters names nothing and does not satisfy "present".
- Validate that `envelope_type` is one of the five defined ZTIP types.
- Reject envelopes with an unsupported or unrecognized `ztap_version` major version.
- Validate that actor `role` fields contain only defined ZTIP protocol role values.
- Reject envelopes where `role` contains tool names, model names, vendor names, or any value
  not in the ZTIP protocol role set.
- Validate that `integrity.canonicalization` and `integrity.hash_algorithm` are present.
- Validate that `integrity.hash_value` is present and non-empty.
- Verify the envelope hash: recompute the hash using the declared canonicalization and
  algorithm, and confirm it matches `integrity.hash_value`. An implementation that does not
  implement a declared canonicalization or algorithm must report the envelope as unverifiable
  under its declared rules — never verify it under a different default and report success.
- Validate that all reason codes appearing in envelopes are either core ZTIP codes or
  namespaced extension codes. Reject un-namespaced unknown codes.
- Validate that all evidence types appearing in envelopes are either core ZTIP types or
  namespaced extension types. Reject un-namespaced unknown types.
- Report structural validation failures with a structured reason code from the ZTIP core set.
- Reject a `verification_results` entry that is not a structured result, and reject an empty
  `verification_results` when `status` is `succeeded` (see Receipt Conformance).

**An Envelope Validator that reports a result over a bundle MUST additionally** apply the
Bundle Verification Conformance rules below. These are cross-envelope properties: an
implementation that only ever validates one envelope at a time does not incur them, and does
not claim them.

**An Envelope Validator MAY:**

- Accept or warn on `1.0-draft` envelopes at its discretion.
- Perform profile-specific validation of `requested_action.parameters` if it knows the profile.
- Validate the `requested_action.risk_level` field against expected values.

---

### Level 2 — Control Plane

A Level 2 Control Plane can manage the full transaction lifecycle: receive submissions,
evaluate policy, authorize or reject transactions, issue authorization records, receive
receipts, and maintain an auditable record.

**A Level 2 Control Plane MUST satisfy all Level 1 requirements, plus:**

**Transaction ingestion:**
- Accept `transaction_request` envelopes from registered source actors.
- Assign a stable `transaction_id` and acknowledge receipt.
- Reject submissions from unregistered actors with `ACTOR_UNREGISTERED`.

**Actor and capability management:**
- Maintain a registry of registered actors with their roles and capability claims.
- Validate that the `source_actor` is registered and active.
- Validate that the `target_actor` is registered and active.
- Validate that all `requested_capabilities` are registered against the `target_actor`.
- Reject capability mismatches with `CAPABILITY_MISSING`.
- Maintain registry consistency as described in SPEC.md Section 9 (Requirement 9).
- Refuse to issue authorization decisions while any registry is in an inconsistent state.
  Emit `REGISTRY_INCONSISTENT` if this occurs.

**Policy evaluation:**
- Evaluate the transaction against organizational policy.
- Produce an `authorization_decision` envelope with one of the defined `authorization_status`
  values: `auto_authorized`, `human_approval_required`, `evidence_required`, `rejected`,
  `expired`.
- Include `policy_refs` referencing the policies evaluated.
- Include `reason_codes` on all outcomes, including authorizations.

**Human approval handling:**
- When `human_approval_required` is issued, track the approval request and its scope.
- When approval is received, issue a new `authorization_decision` with `authorization_status:
  "human_approved"` and a fully populated `human_approval_ref` including `approval_scope`.
- Never reuse or transfer an approval. An approval is transaction-specific, action-bound,
  target-bound, and single-use by default.
- Enforce `approval_scope.expires_at`. An expired approval must not be honored.
- Detect and reject approval replay with `APPROVAL_REPLAYED`.

**Integrity:**
- Verify the `integrity.hash_value` of every submitted envelope.
- Reject envelopes with integrity failures with `INTEGRITY_FAILED`.
- Include a valid `integrity` object on every envelope it produces.
- Record the `request_hash` in every `authorization_decision` envelope.

**Audit trail:**
- Retain every submitted envelope, every decision, every receipt, and every evidence record.
- Store records in an append-only, hash-linked audit log.
- Make the audit trail queryable by `transaction_id`, actor, time range, and outcome.

**Receipt handling:**
- Accept `execution_receipt` envelopes from target actors or validators.
- Verify that `receipt.request_hash` matches the original `transaction_request` hash.
- Reject receipts with mismatched hashes with `INTEGRITY_FAILED`.
- Record the receipt in the audit trail.

**Registry consistency:**
- Detect and report inconsistency in actor, capability, policy, or transaction registries.
- Fail closed when consistency cannot be verified.

---

### Level 3 — Governed Executor / Runtime

A Level 3 Governed Executor is a target actor, runtime, or execution system that performs
work on behalf of governed transactions. It is the entity at the trust boundary where
governance is finally enforced by either accepting or refusing action.

**A Level 3 Governed Executor MUST satisfy all Level 1 requirements, plus:**

**Authorization verification before action:**
- Refuse to perform any governed action unless it holds a valid, verified ZTIP authorization
  record for that specific action. This is non-negotiable. An unverified message — regardless
  of how it arrived — is not sufficient basis for action.
- Verify the following before accepting a transaction:
  - The envelope carries a valid `authorization_decision` with `authorization_status` of
    `auto_authorized` or `human_approved`.
  - The `authorization_decision.request_hash` matches the `transaction_request`'s
    `integrity.hash_value`.
  - The `authorization_decision.expires_at` has not elapsed.
  - The `target_actor.actor_id` in the envelope matches its own registered identity.
  - The `requested_capabilities` are within its registered capability claims.
- Reject transactions that fail any of these checks with the appropriate reason code.
- Never execute based on an unverified message, an ambient instruction, or an informal
  approval that has not been recorded as a ZTIP authorization record.

**Receipt production:**
- Produce an `execution_receipt` for every terminal transaction state.
- Include `request_hash` matching the original transaction request.
- Include `authorization_decision_ref` referencing the decision that authorized execution.
- Include structured `verification_results` checked against the transaction's
  `verification_requirements`. A receipt with `status: "succeeded"` must record at least one
  result, each naming the check (`check_id`, `check_type`) and whether it passed.
- Include `atomicity_result` accurately recording whether execution was atomic, partial, or
  non-atomic, and whether rollback was performed.
- Include `reason_codes` on all non-succeeded receipts.

**Atomicity enforcement:**
- Default to `atomic_required` behavior unless the transaction explicitly declares otherwise.
- Fail closed with `PARTIAL_STATE_BLOCKED` if partial execution occurs under `atomic_required`
  and rollback is not possible.
- Include `partial_state_description` in the `atomicity_result` when `PARTIAL_STATE_BLOCKED`
  occurs.

---

## Required Invariants

The following invariants are mandatory for all conforming implementations at all levels.
Violation of any invariant makes an implementation non-conforming.

| Invariant | Required Action on Violation |
|---|---|
| Unsupported major `ztap_version` | Reject with `SCHEMA_INVALID` |
| Missing required field | Reject with `SCHEMA_INVALID` |
| Invalid `role` value (any non-ZTIP value) | Reject with `ROLE_INVALID` |
| Tool name, model name, or vendor name as `role` | Reject with `ROLE_INVALID` |
| Unregistered actor | Reject with `ACTOR_UNREGISTERED` |
| Missing registered capability | Reject with `CAPABILITY_MISSING` |
| Policy explicitly denied | Reject with `POLICY_DENIED` |
| `integrity.hash_value` mismatch | Reject with `INTEGRITY_FAILED` |
| `expires_at` elapsed | Reject with `EXPIRED` |
| Authorization replay detected | Reject with `APPROVAL_REPLAYED` |
| Non-atomic partial execution under `atomic_required` | Fail with `PARTIAL_STATE_BLOCKED` |
| Registry inconsistency detected at control plane | Refuse authorization with `REGISTRY_INCONSISTENT` |
| Free-text-only `verification_requirements` | Reject with `SCHEMA_INVALID` |
| Un-namespaced unknown reason code | Reject with `SCHEMA_INVALID` |
| Un-namespaced unknown evidence type | Reject with `SCHEMA_INVALID` |
| Un-namespaced unknown capability identifier | Reject with `CAPABILITY_MISSING` or `SCHEMA_INVALID` |
| Unknown action profile (unless policy explicitly allows) | Reject with `SCHEMA_INVALID` |
| Un-namespaced unknown profile identifier | Reject with `SCHEMA_INVALID` |
| Source-declared `risk_level` accepted without evaluation | Non-conformant authorization |
| Envelope hash verified with wrong version's rules | Reject with `INTEGRITY_FAILED` |

These invariants are not configurable. They are not defaults. They are protocol rules.

---

## Role and Capability Conformance

Roles are governance classifications defined by the ZTIP protocol. A conforming implementation
must enforce the following:

- Only the defined ZTIP protocol roles are valid `role` values: `operator`, `control_plane`,
  `source_actor`, `target_actor`, `planner`, `executor`, `validator`, `auditor`, `runtime`.
- Tool names, model names, vendor product names, SaaS platform names, and runtime identifiers
  are not valid roles and must be rejected with `ROLE_INVALID`.
- `implementation_ref` is optional metadata. It has no governance authority. A conforming
  control plane must not use `implementation_ref` as the basis for authorization decisions.
- Capability claims are separate from role assignments. Holding a role does not automatically
  grant capabilities. Each capability must be explicitly registered against the actor.
- A transaction requesting a capability not registered for the target actor must be rejected
  with `CAPABILITY_MISSING`.

### Capability Namespacing Conformance

Capability identifiers follow an open governed registry model. A conforming implementation must:

- Accept ZTIP core capabilities by their reserved simple names (e.g., `file.read`, `git.push`,
  `test.run`). The full core capability set is defined in `SCHEMA.md`.
- Require extension capabilities to use a reverse-domain namespaced format
  (e.g., `org.example/deploy_service`). Extension capabilities without a namespace are
  schema-invalid.
- Reject un-namespaced unknown capability identifiers with `CAPABILITY_MISSING` or
  `SCHEMA_INVALID` as appropriate.
- Allow control planes to restrict which extension namespaces are accepted within their
  deployment.

### Profile Conformance

Action profiles follow the same open governed registry model. A conforming control plane must:

- Recognize ZTIP core profiles (`ztip.core/fileops`, `ztip.core/gitops`, `ztip.core/testops`,
  `ztip.core/approval`, `ztip.core/evidence`, `ztip.core/generic`).
- Accept extension profiles only if they are namespaced (`org.example/deploy`).
- Reject un-namespaced unknown profile values with `SCHEMA_INVALID` unless control-plane
  policy explicitly permits unrecognized profiles.
- Always include `parameters` in the envelope hash regardless of whether the profile is
  known to the control plane.

---

## Integrity Conformance

A conforming implementation must:

- Include a valid `integrity` object on every envelope it produces.
- Use RFC 8785 JSON Canonicalization Scheme (JCS) as the default canonicalization method.
- Use SHA-256 as the default hash algorithm.
- Compute the hash by:
  1. Constructing the full envelope, then removing the `integrity.hash_value` field.
     (Removal, not an empty-string placeholder — the two are not hash-equivalent under
     RFC 8785.) All other `integrity` fields remain present and unchanged.
  2. Stripping all underscore-prefixed annotation keys, recursively, if any are present.
  3. Applying RFC 8785 JCS canonicalization.
  4. Computing SHA-256 over the canonical byte sequence.
  5. Encoding the result as a lowercase hex string.
  6. Setting `integrity.hash_value` to this value.
- Note: only `integrity.hash_value` (and underscore-prefixed annotation keys, which are
  not envelope fields) is excluded from the hash input. All other `integrity` fields —
  `canonicalization`, `hash_algorithm`, `signed` — are included. This ensures the
  declared algorithm and canonicalization method are themselves tamper-evident.
- Verify the hash on every received envelope before processing. Reject hash mismatches with
  `INTEGRITY_FAILED`.
- Never process, forward, or store an envelope with a failed hash without recording the failure.

A conforming control plane must additionally:
- Maintain a hash-linked audit log. Each stored record must reference the prior record's hash.
- Make the hash chain available for auditor verification.

### Bundle Verification Conformance

A *bundle* is a set of ZTIP envelopes verified together — the envelopes of one transaction,
an audit-trail export, or an evidence package. An implementation that reports a verification
result over a bundle must:

- Split a document the same way in every tool it ships: an object declaring any ZTIP envelope
  field is one envelope even when it also carries an `envelopes` key; only an object declaring
  none of them is a wrapper. Two tools that disagree about what a document is will disagree
  about whether it verifies.
- Report how many envelopes it verified. A caller must never be able to read "nothing to
  verify" as "everything verified".
- Refuse to report success over an empty bundle.
- Report a `request_hash` that resolves to no transaction request present in the bundle as
  unverified linkage, not as an intact reference. An implementation MAY offer an explicit
  partial-bundle mode; in that mode it must state that chain linkage was not verified.
- Reject a bundle carrying more than one `transaction_request` for a single `transaction_id`.
  The request history is ambiguous, and the later request silently shadows the earlier one
  while every hash still verifies.
- Refuse to report content as a verified envelope when it lacks a defined `envelope_type`, a
  non-empty `transaction_id`, or — for a receipt — a defined `status`. A self-computed hash
  over arbitrary content is not envelope verification.
- Verify under the canonicalization and hash algorithm each envelope declares, and report an
  envelope declaring rules the implementation does not apply rather than verifying it under a
  different default.
- Resolve a `request_hash` against the `transaction_request` carrying the same
  `transaction_id`, at every site an envelope binds itself by hash — including an
  authorization decision's `human_approval_ref.approval_scope`, which binds a human approval
  to the work it approved — and report receipts for one `transaction_id` that disagree on the
  terminal state.
- Reject a document whose JSON objects declare the same member name twice: parsers disagree on
  what such a document says, while every hash still verifies.
- Report content carried in a bundle wrapper beside the envelopes and non-normative
  annotations. It is neither hashed nor verified. This is a disclosure duty: such content does
  not make the bundle invalid, and must not be reported as an integrity defect.
- Reject a verification result stored under an annotation key: annotation fields are excluded
  from the envelope hash, so such a result is not covered by the seal and does not count as
  recorded.
- Reject a `succeeded` receipt whose every recorded verification result reports failure: a
  success contradicted by its own record is not a verified success.
- Scope its reported claim to what it checked. Hash verification establishes intactness, not
  authenticity, not that any declared check was executed, and not the content of non-normative
  annotation fields, which are excluded from the hash by design.

### Multi-Version Integrity Conformance

A conforming control plane that stores envelopes from multiple ZTIP versions must:

- Verify each stored envelope using the `canonicalization` and `hash_algorithm` declared
  in that envelope's own `integrity` object — not the control plane's current default. Where
  the declared rules are not implemented, report the envelope as unverifiable under them
  rather than substituting a default.
- Retain `ztap_version`, `integrity.canonicalization`, and `integrity.hash_algorithm`
  alongside every stored envelope so each can be independently re-verified at any time.
- Not silently reinterpret older-version envelopes under newer schema rules. Version-specific
  validation applies to each record according to its declared version.
- Reject envelopes with unsupported major versions for active authorization. Historical
  records from prior supported versions remain auditable but are not re-authorized.

---

## Authorization Conformance

A conforming control plane must recognize and correctly handle all six `authorization_status`
values:

| Status | Meaning |
|---|---|
| `auto_authorized` | Policy permits the transaction without human review. |
| `human_approval_required` | Policy requires human approval before proceeding. Transaction blocked. |
| `human_approved` | Human approval was required, granted, and recorded. Distinct from `auto_authorized`. |
| `evidence_required` | Additional evidence must be submitted before a decision can be made. |
| `rejected` | Policy denies the transaction. Terminal. |
| `expired` | The transaction's validity window elapsed. Terminal. |

A conforming implementation must:
- Never collapse `human_approved` into `auto_authorized`. The distinction is required so
  human involvement is machine-detectable in the audit trail.
- Issue a new `authorization_decision` envelope (with a new `decision_id`) when a
  `human_approval_required` decision transitions to `human_approved`. The original envelope
  is immutable and must be retained.
- Bind every human approval to its `approval_scope`: `transaction_id`, `request_hash`,
  `action_ids`, `target_actor_id`, `approved_capabilities`, `expires_at`, and `single_use`.
- Enforce `approval_scope.expires_at` on every approval.
- Treat approvals as single-use by default. Reject replay with `APPROVAL_REPLAYED`.

---

## Receipt Conformance

Every terminal transaction state must produce an `execution_receipt`. A conforming
implementation must not allow a transaction to reach a terminal state without a receipt.

A conforming receipt must:
- Include `request_hash` matching the `integrity.hash_value` of the original
  `transaction_request` envelope.
- Include `authorization_decision_ref` referencing the `decision_id` of the authorizing
  decision.
- Include `status` with one of the defined values: `succeeded`, `failed`, `rejected`,
  `cancelled`, `expired`, `timed_out`.
- Include `reason_codes`. An empty array is valid only for `status: "succeeded"`.
- Include `actions_attempted` and `actions_completed`. Empty arrays are valid only when no
  execution was attempted.
- Include structured `verification_results` corresponding to each entry in the transaction's
  `verification_requirements`, identified by `check_id`. At least one result is required when
  `status` is `succeeded`; an empty result set is valid only for a non-succeeded receipt.
- Include `atomicity_result` with `mode_declared`, `outcome`, and `rollback_performed`.
  Include `partial_state_description` when `outcome` is `partial`.
- Include `evidence_refs` when evidence records were submitted and are relevant to the receipt.
- Include a valid `integrity` object.

---

## Evidence Conformance

A conforming implementation must:
- Recognize and correctly process all ZTIP core evidence types defined in Section 10 of
  `SCHEMA.md`.
- Accept extension evidence types only if they are namespaced (`org.example/type-name`).
- Reject un-namespaced unknown evidence types with `SCHEMA_INVALID`.
- Verify `evidence_hash` against the referenced evidence content when evaluating evidence.
- Include `evidence_refs` in `authorization_decision` envelopes when evidence records were
  accepted and influenced the authorization outcome.

---

## Reason Code Conformance

ZTIP uses an open governed registry for reason codes. A conforming implementation must:

- Recognize and correctly handle all ZTIP core reason codes.
- Accept extension reason codes only if they are namespaced (`org.example/CODE_NAME`).
- Reject un-namespaced unknown reason codes with `SCHEMA_INVALID`.
- Not use free-text in place of reason codes for machine-governed decisions.
- Include reason codes on all `authorization_decision` and `execution_receipt` envelopes.

---

## Trust Boundary Conformance

**ZTIP does not secure the pipe. ZTIP governs the action.**

A conforming actor, runtime, tool, or control plane must refuse governed work unless a
valid, verified ZTIP transaction exists and is verified at the point of action.

Specifically, a conforming Level 3 Governed Executor must:
- Refuse any instruction to perform governed work that does not arrive with a valid,
  unexpired ZTIP authorization record.
- Not treat transport-level authentication (API keys, TLS, session tokens) as a substitute
  for a ZTIP authorization record.
- Not infer authorization from conversational context, AI model confidence, or ambient
  trust in the source system.
- Not execute based on an unsigned, unverified, or informal instruction, even from a system
  it considers "trusted."

The corollary: an ungoverned message can exist in the world. It cannot be promoted to
governed, authorized work inside a ZTIP-compliant environment without passing through the
control plane's evaluation and receiving a valid authorization record.

---

## Non-Conforming Behaviors

The following behaviors make an implementation non-conforming. They are listed explicitly
because they are common failure modes in multi-agent governance systems.

**Envelope and schema violations:**
- Accepting an envelope with a missing required field rather than rejecting with `SCHEMA_INVALID`.
- Attempting to infer or repair a malformed field rather than rejecting it.
- Accepting an unrecognized `envelope_type` rather than rejecting with `SCHEMA_INVALID`.

**Role violations:**
- Using a tool name (e.g., `codex`, `cursor`), model name (e.g., `claude`, `gpt-4`), vendor
  name, or platform name as an actor `role` value.
- Accepting such values from submitted envelopes rather than rejecting with `ROLE_INVALID`.
- Using `implementation_ref` as the basis for authorization decisions.

**Integrity violations:**
- Skipping hash verification on received envelopes.
- Accepting an envelope with a hash mismatch rather than rejecting with `INTEGRITY_FAILED`.
- Mutating a submitted `transaction_request` envelope after it has been assigned a
  `transaction_id`. Submitted envelopes are immutable.

**Authorization violations:**
- Treating `human_approved` and `auto_authorized` as equivalent statuses.
- Reusing a prior authorization record for a different transaction.
- Honoring an approval after its `approval_scope.expires_at` has elapsed.
- Using a `single_use: true` approval for a second transaction.
- Failing to record `approval_scope` on human-approved transactions.

**Execution boundary violations:**
- A target actor executing based on an unverified message, ambient instruction, or informal
  approval that does not carry a valid ZTIP authorization record.
- A control plane issuing authorization while its registries are in an inconsistent state.
- A runtime or adapter escalating its own execution authority without a governance artifact.

**Audit trail violations:**
- Allowing a transaction to reach a terminal state without producing a receipt.
- Producing a receipt that does not reference `request_hash`.
- Omitting `reason_codes` from a non-succeeded receipt.
- Storing audit records in a non-append-only, non-hash-linked log.

---

## Minimal Test Matrix

The following table defines a minimum set of positive and negative conformance tests. Each
test should be implementable as a deterministic, automated check. A conforming implementation
must pass all applicable tests for its declared conformance level.

Rows marked **L1-B** apply only to an implementation that reports a verification result over a
*bundle* — a set of envelopes verified together (see Bundle Verification Conformance). They are
cross-envelope properties, so they are not expressible in the single-envelope JSON Schema; an
Envelope Validator that only ever validates one envelope at a time is not held to them.

| # | Test | Type | Level | Expected Result |
|---|---|---|---|---|
| T01 | Submit a structurally valid envelope | Positive | L1 | Accepted, hash verified |
| T02 | Submit envelope with missing `ztap_version` | Negative | L1 | Rejected: `SCHEMA_INVALID` |
| T03 | Submit envelope with missing `integrity.hash_value` | Negative | L1 | Rejected: `SCHEMA_INVALID` |
| T04 | Submit envelope with corrupted `integrity.hash_value` | Negative | L1 | Rejected: `INTEGRITY_FAILED` |
| T05 | Submit envelope with `role: "codex"` | Negative | L1 | Rejected: `ROLE_INVALID` |
| T06 | Submit envelope with `role: "claude"` | Negative | L1 | Rejected: `ROLE_INVALID` |
| T07 | Submit envelope with `role: "executor"` | Positive | L1 | Role accepted |
| T08 | Submit envelope with unsupported major version | Negative | L1 | Rejected: `SCHEMA_INVALID` |
| T09 | Submit envelope with un-namespaced unknown reason code | Negative | L1 | Rejected: `SCHEMA_INVALID` |
| T10 | Submit envelope with un-namespaced unknown evidence type | Negative | L1 | Rejected: `SCHEMA_INVALID` |
| T11 | Submit envelope with namespaced extension reason code | Positive | L1 | Accepted |
| T12 | Submit transaction from registered actor | Positive | L2 | `submitted` state, decision issued |
| T13 | Submit transaction from unregistered actor | Negative | L2 | Rejected: `ACTOR_UNREGISTERED` |
| T14 | Request capability not registered to target actor | Negative | L2 | Rejected: `CAPABILITY_MISSING` |
| T15 | Submit transaction matching `auto_authorized` policy | Positive | L2 | `authorization_status: "auto_authorized"` |
| T16 | Submit transaction matching `rejected` policy | Negative | L2 | `authorization_status: "rejected"`, `POLICY_DENIED` |
| T17 | Submit transaction requiring evidence | Positive | L2 | `authorization_status: "evidence_required"` |
| T18 | Submit transaction requiring human approval | Positive | L2 | `authorization_status: "human_approval_required"` |
| T19 | Issue human approval and verify `human_approved` status | Positive | L2 | New decision with `authorization_status: "human_approved"` |
| T20 | Replay a consumed single-use approval | Negative | L2 | Rejected: `APPROVAL_REPLAYED` |
| T21 | Submit receipt with mismatched `request_hash` | Negative | L2 | Rejected: `INTEGRITY_FAILED` |
| T22 | Submit receipt linked to correct `request_hash` | Positive | L2 | Receipt accepted and recorded |
| T23 | Transaction expires before acceptance | Positive | L2 | Receipt with `status: "expired"` |
| T24 | Executor verifies hash before accepting transaction | Positive | L3 | Transaction accepted |
| T25 | Executor receives transaction with hash mismatch | Negative | L3 | Rejected: `INTEGRITY_FAILED` |
| T26 | Executor receives transaction with elapsed `expires_at` | Negative | L3 | Rejected: `EXPIRED` |
| T27 | Executor receives instruction without authorization record | Negative | L3 | Refused — no action taken |
| T28 | Partial execution under `atomic_required` without rollback | Negative | L3 | `PARTIAL_STATE_BLOCKED` in receipt |
| T29 | Successful execution produces receipt with `request_hash` | Positive | L3 | Receipt references original hash |
| T30 | Control plane refuses authorization when registry inconsistent | Negative | L2 | `REGISTRY_INCONSISTENT` |
| T31 | Extension capability with valid namespace accepted | Positive | L1 | Accepted |
| T32 | Un-namespaced unknown capability rejected | Negative | L1 | Rejected: `SCHEMA_INVALID` |
| T33 | Extension profile with valid namespace accepted | Positive | L2 | Evaluated per policy |
| T34 | Unknown un-namespaced profile rejected | Negative | L2 | Rejected: `SCHEMA_INVALID` |
| T35 | Control plane elevates declared risk level, records `evaluated_risk_level` | Positive | L2 | Decision includes `RISK_LEVEL_ESCALATED` and `evaluated_risk_level` |
| T36 | Hash verification uses envelope's declared algorithm, not current default | Positive | L2 | Historical record verified with its own declared method |
| T36b | Envelope declares a canonicalization or algorithm the implementation does not implement | Negative | L1 | Reported unverifiable under its declared rules — never verified under a substitute default |
| T37 | Verify an empty bundle (no envelopes) | Negative | L1-B | Refused — not reported as verified |
| T38 | Verify a bundle whose `request_hash` names an absent transaction request | Negative | L1-B | Reported as unverified linkage, not intact |
| T39 | Verify a bundle with two `transaction_request` envelopes sharing one `transaction_id` | Negative | L1-B | Rejected — ambiguous request history |
| T40 | Receipt with `status: "succeeded"` and an empty `verification_results` (`[]` or `{}`) | Negative | L1 | Rejected: `SCHEMA_INVALID` |
| T41 | Receipt with `status: "failed"` and an empty `verification_results` (`[]`) | Positive | L1 | Accepted — verification may never have been reached |
| T42 | Self-sealed content with an undefined `envelope_type` or receipt `status` | Negative | L1 | Rejected: `SCHEMA_INVALID` — a valid self-hash is not verification |
| T43 | Receipt with `verification_results` omitted entirely, any status | Negative | L1 | Rejected: `SCHEMA_INVALID` — the field is required; an empty collection is how "none" is expressed |
| T44 | A `verification_results` entry that is free text rather than a structured result | Negative | L1 | Rejected: `SCHEMA_INVALID` |
| T45 | Receipt with `status: "succeeded"` whose every recorded result reports `passed: false` | Negative | L1-B | Refused — a success contradicted by its own record |
| T46 | `succeeded` receipt whose only result is keyed by an underscore-prefixed name | Negative | L1 | Rejected — the result is outside the envelope hash, so it is not a recorded result |
| T47 | Approval scope whose `request_hash`/`transaction_id` name a transaction not present in the bundle | Negative | L1-B | Reported as unverified linkage — an approval must bind to the work it approved |
| T48 | An envelope that also carries an `envelopes` key | Negative | L1 | Validated as one envelope, never as a wrapper around its payload |

---

## Open Questions

The following conformance questions are unresolved and require operator input before a
finalized conformance specification can be published:

1. **Conformance claim format.** How does an implementation declare its conformance level?
   Is there a machine-readable conformance manifest, a self-attestation document, or a test
   report format? This is needed before third-party conformance testing is possible.

2. **Level boundary between L1 and L2.** Can a tool be conformant at L1 without any control
   plane behavior? The current definition suggests yes — a standalone envelope validator with
   no policy engine is a valid L1 implementation. This should be confirmed.

3. ~~**`requested_action.profile` registry conformance.**~~ Resolved. Unknown un-namespaced
   profiles fail closed with `SCHEMA_INVALID` unless policy explicitly allows. Extension
   profiles must be namespaced. See Profile Conformance section and test T33–T34.

5. ~~**Multi-version audit trail conformance.**~~ Resolved. Each envelope is verified against
   its own declared `ztap_version` rules. See Multi-Version Integrity Conformance section
   and test T36.

**Still open:**

1. **Conformance claim format.** How does an implementation declare its conformance level?
   Machine-readable manifest, self-attestation, or test report format?

2. **Partial Level 2 conformance.** Is there a use case for an "audit-only control plane"
   that stores and verifies but does not manage registrations or issue authorizations?

4. **Break-glass conformance.** Minimum evidence fields for break-glass authorization at a
   Level 2 control plane are described in SPEC.md but not yet formalized as schema-level
   required fields. Pending further specification.

6. **Profile versioning.** When a profile's parameter schema changes, what is the profile
   version expression format? (`ztip.core/gitops@2`? `ztip.core/gitops/v2`?)

---

## Next Steps

**Delivered since this conformance draft was written:** the resolved decisions are applied
in `examples/` (including `authorization_status: "human_approved"` in example 02 and the
`requested_action` / `verification_requirements` structures throughout); the
machine-readable JSON Schemas ship under `schemas/` (implementation targets, not
specification authorities); `WHITEPAPER.md` and the repo governance files
(`CONTRIBUTING.md`, `LICENSE`, `CHANGELOG.md`) exist; and the repository is public.

**Remaining:**

1. **Conformance test fixtures** — a set of valid and intentionally invalid ZTIP envelopes
   for use in automated conformance testing. These support the test matrix above.

2. **Resolve the open questions above** — including the profile/version expression format —
   and freeze the conformance targets for a `1.0` release.

---

> ZTIP Conformance Draft — `1.0-draft`.
> Derived from `SPEC.md` and `SCHEMA.md`.
> **Freedom for engineers. Governance for the organization.**
