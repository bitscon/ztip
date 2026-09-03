# ZTIP Schema Draft

*Zero Trust Intelligence Protocol — Envelope Types, Field Definitions, and Integrity Model*

---

## Status

**DRAFT — Prose field model for `1.0-draft`.**

This document defines the field-level structure of ZTIP envelopes in prose. It resolves the
open questions documented in `SPEC.md` and establishes the schema decisions that machine-
readable schema files and reference implementations must conform to.

This is a draft. Field names are stable enough to reason about but not finalized. The
machine-readable JSON Schema files under `schemas/` are derived from this document and MUST
stay in sync with it — a change to either updates both in the same commit.

Current protocol working version: `1.0-draft`

This document should be read alongside `SPEC.md`, which defines the transaction lifecycle,
governance model, and core concepts that this schema implements.

---

## Design Principles

Every ZTIP schema decision is governed by the following principles, in order of precedence:

**1. Machine-verifiable.**
Every field required for governance decisions must be structurally checkable without human
interpretation. Governance cannot depend on free-text fields.

**2. Human-auditable.**
Every field required for audit must be readable by a person without decryption, decoding, or
proprietary tooling. ZTIP envelopes are plain JSON.

**3. Transport-agnostic.**
No field assumes a specific delivery mechanism. An envelope delivered by API, file, message
queue, or any other channel must be structurally identical. Transport metadata is not part of
the ZTIP envelope.

**4. Immutable submitted requests.**
The transaction request envelope is the canonical, unalterable record of what was asked.
All subsequent records — decisions, receipts, evidence, amendments — are separate linked
envelopes. Nothing modifies the original request.

**5. Hash-linked receipts.**
Every receipt references the original request envelope by its hash. The integrity chain
is the audit trail.

**6. Fail-closed is a schema invariant.**
If a required field is missing, the envelope is invalid and must be rejected. If a required
field is malformed, carries an unrecognized enumerated value, or contains content that cannot
be verified, the envelope is invalid. If an integrity hash fails verification, the envelope is
invalid. An invalid envelope does not proceed under any circumstances. There is no permissive
fallback at the schema level. Implementations must not attempt to infer or repair a malformed
envelope — they must reject it with a structured reason code and produce a receipt recording
the rejection. The reason codes that correspond to schema-level failures are defined in
Section 15.

**7. Freedom for engineers. Governance for the organization.**
Schema decisions favor the simplest structure that achieves verifiable governance. Complexity
that serves toolchain preferences, not governance requirements, is deferred or excluded.

---

## Envelope Types

ZTIP v1 defines five envelope types. Each envelope is a discrete JSON object with a defined
purpose, required fields, and an integrity record. Envelopes are not mutated after they are
finalized. New information is expressed as new envelopes, linked to prior ones by identifier
and hash.

| Envelope Type | Purpose |
|---|---|
| `transaction_request` | The original request, created by the source actor and submitted to the control plane. Immutable after submission. |
| `authorization_decision` | The control plane's policy evaluation outcome. Authorizes, rejects, or requests evidence or human approval. |
| `execution_receipt` | The outcome of the transaction — success, failure, cancellation, rejection, expiry, or timeout. |
| `evidence_record` | Supporting material submitted to satisfy a policy requirement, linked to a transaction by hash. |
| `amendment_event` | A linked record describing a modification to the transaction context. Does not alter the original request. |

All five types share a set of common fields defined in Section 5.

---

## Shared Envelope Fields

These fields are required on every ZTIP envelope regardless of type.

### `ztap_version`

**Required. String.**

The ZTIP protocol version under which this envelope was created. Implementations must reject
envelopes with unsupported major versions unless explicitly configured otherwise.

The current working version is `1.0-draft`. When v1 is finalized, this value becomes `1.0`.

> **Legacy field name.** The protocol was drafted under the working name ZTAP; the field is
> named `ztap_version` for that historical reason and is retained unchanged because the field
> name sits inside the canonicalized content that envelope hashes cover — renaming it would
> invalidate every existing hash. Treat it as a fixed protocol identifier, not a brand
> reference.

### `envelope_type`

**Required. String. Enumerated.**

The type of this envelope. Must be one of:
- `transaction_request`
- `authorization_decision`
- `execution_receipt`
- `evidence_record`
- `amendment_event`

Implementations must reject envelopes with unrecognized or absent `envelope_type`.

### `transaction_id`

**Required. String.**

A stable, globally unique identifier for the ZTIP transaction this envelope belongs to. All
envelopes in a transaction's lifecycle share the same `transaction_id`.

The transaction ID is assigned by the control plane upon receipt of the first
`transaction_request` envelope. The source actor may generate a proposed ID; the control plane
may accept or replace it. The control plane's assignment is authoritative.

Format: stable opaque string. UUID v4 is a reasonable default but not required by the
protocol. Exact format is implementation-defined, subject to uniqueness.

### `integrity`

**Required. Object.**

The integrity record for this envelope. Defined in full in Section 12.

The `integrity` object contains the canonicalization method, hash algorithm, and hash value
computed over this envelope. The integrity object must be the last field computed; the hash
is computed over the envelope with the `hash_value` field excluded (or set to a defined
empty sentinel), then the computed value is inserted.

See Section 12 for canonicalization rules, hash construction, and the full field definition.

---

## Actor Object

The actor object is used wherever an actor is referenced in a ZTIP envelope. It is not a
standalone envelope type — it is an embedded object used within `source_actor`,
`target_actor`, `control_plane`, `produced_by`, `created_by`, and similar fields.

### Fields

**`actor_id`** — Required. String.
A stable, unique identifier for this actor within the organization's control plane. This is
the canonical reference used across all envelopes and audit records.

**`role`** — Required. String or array of strings.
The ZTIP protocol role(s) this actor is performing in this transaction. Must be one or more
of the defined ZTIP roles: `operator`, `control_plane`, `source_actor`, `target_actor`,
`planner`, `executor`, `validator`, `auditor`, `runtime`.

**`display_name`** — Optional. String.
A human-readable name for this actor. Used for display and audit readability only. Not used
for governance decisions. Not required.

**`organization_id`** — Required. String.
The organization or tenant this actor belongs to, as registered with the control plane.
In v1 single-organization scope, this is the same for all actors in a transaction.

**`registration_ref`** — Required. String.
A reference to this actor's registration record in the control plane. Used to verify that
the actor is currently registered and active.

**`capability_claims`** — Required for `source_actor` and `target_actor`. Array of strings.
The capabilities this actor is registered to exercise in this transaction. For `source_actor`,
this records what the source is authorized to request. For `target_actor`, this records which
of its registered capabilities are being invoked.

Capabilities not in this list may not be invoked by or against this actor in this transaction.

**`implementation_ref`** — Optional. String.
A reference to the underlying implementation, tool, or system this actor represents. This is
metadata — it does not define the actor's role or capabilities. It supports audit readability
and debugging.

### Normative Rule: Role vs. Implementation

**Roles are protocol-level governance classifications. Implementations are optional metadata.**

The `role` field answers: *what governance function does this actor perform in this
transaction?* The `implementation_ref` field answers: *what tool, model, or system is behind
this actor?*

These are separate claims. They must never be conflated. Tool names, model names, vendor
names, and platform names must not appear as `role` values. The `role` field must only contain
valid ZTIP protocol role identifiers.

**Valid actor declarations:**

```json
{ "actor_id": "...", "role": "executor",  "implementation_ref": "custom-deploy-agent-v3" }
{ "actor_id": "...", "role": "planner",   "implementation_ref": "llm-gateway-local" }
{ "actor_id": "...", "role": "validator", "implementation_ref": "test-runner-ci" }
```

**Invalid actor declarations (schema rejection required):**

```json
{ "actor_id": "...", "role": "codex" }           // tool name is not a protocol role
{ "actor_id": "...", "role": "claude" }           // model name is not a protocol role
{ "actor_id": "...", "role": "github-actions" }   // platform name is not a protocol role
{ "actor_id": "...", "role": "gpt-4o" }           // model identifier is not a protocol role
```

A control plane must reject any envelope where `role` contains a value not in the defined
ZTIP role set. The reason code is `ROLE_INVALID`. There is no pass-through mode for
unrecognized role values.

The reason this rule is enforced at the schema level: if implementation names become protocol
roles, the governance model becomes vendor-dependent. ZTIP must remain implementable by any
compliant control plane regardless of which tools actors use internally.

---

## Capability Registry Model

ZTIP uses an **open governed registry** for capability identifiers, consistent with the reason
code, evidence type, and profile registries.

**Core capabilities** are reserved simple-name identifiers defined by the ZTIP protocol.
They are stable across implementations and must be recognized by all conforming control planes.

| Capability | Description |
|---|---|
| `file.read` | Read access to file system resources. |
| `file.write` | Write or modify file system resources. |
| `git.commit` | Create a git commit in a repository. |
| `git.push` | Push commits to a remote git repository. |
| `test.run` | Execute an automated test suite and capture results. |
| `approval.request` | Submit a request for human approval of a governed action. |
| `receipt.emit` | Produce and submit a ZTIP execution receipt. |

Additional core capabilities will be defined as the ZTIP profile ecosystem develops.

**Extension capabilities** address domain-specific actions not covered by the core set.
They must be namespaced using a reverse-domain format:

```
org.example/deploy_service
company.internal/update_firewall_rule
vendor.tool/create_ticket
```

### Capability Registry Rules

- Unknown core capability names (un-namespaced and not in the core set) are schema-invalid.
- Extension capability names are valid if syntactically namespaced and accepted by
  control-plane policy. Control planes may restrict which extension namespaces they accept.
- An actor's `capability_claims` must contain only capabilities registered for that actor
  in the control plane's capability registry.
- Executors must not claim capabilities they are not registered for. The control plane
  validates capability claims at registration time and at transaction evaluation time.
- A transaction requesting a capability not in the target actor's registered claims must be
  rejected with `CAPABILITY_MISSING`.

---

## Transaction Request Envelope

The transaction request envelope is the source record of a ZTIP transaction. It is created
by the source actor, submitted to the control plane, and — once submitted — is immutable.

All subsequent envelopes in the transaction reference this envelope by `transaction_id` and
by the hash recorded in the request's `integrity` object.

### Required Fields

**`ztap_version`** — See Section 5.

**`envelope_type`** — `"transaction_request"`

**`transaction_id`** — See Section 5. May be proposed by source actor; control plane assignment
is authoritative.

**`created_at`** — Required. Timestamp (ISO 8601, UTC).
The moment the source actor constructed this envelope. Set by the source actor. This is the
canonical creation time of the request.

**`source_actor`** — Required. Actor object.
The actor initiating this transaction. Must include `actor_id`, `role`, `organization_id`,
`registration_ref`, and `capability_claims`.

**`target_actor`** — Required. Actor object.
The actor being requested to perform the action. Must include `actor_id`, `role`,
`organization_id`, `registration_ref`, and `capability_claims` for the capability being
invoked.

ZTIP v1 supports exactly one `target_actor` per transaction. For fan-out work requiring
multiple targets, create separate child transactions linked by `parent_transaction_id`.

**`requested_action`** — Required. Object.
A structured description of what action is being requested, using the ZTIP standard action
wrapper. The wrapper defines the governance-relevant fields. Profile-specific parameters are
opaque to ZTIP core but are covered by the envelope hash.

The `requested_action` object must include:

- **`action_id`** — Required. String. A stable unique identifier for this specific action
  request, distinct from `transaction_id`. Used to bind approvals and receipts to the precise
  action authorized, preventing approval reuse across different actions in the same transaction
  context.
- **`action_type`** — Required. String. A structured classifier for the kind of action being
  requested (e.g., `deploy`, `query`, `notify`, `migrate`, `archive`). Used by policy engines
  to route authorization decisions. Must be machine-readable.
- **`profile`** — Required. String. The action profile that governs how `parameters` are
  interpreted. ZTIP uses an open governed registry for profiles, consistent with the reason
  code, evidence type, and capability registries. Core profiles are reserved by ZTIP;
  extension profiles must be namespaced.

  **Core profiles (ZTIP-defined):**
  - `ztip.core/fileops` — file system read/write operations
  - `ztip.core/gitops` — git repository operations (commit, push, branch)
  - `ztip.core/testops` — automated test execution and result capture
  - `ztip.core/approval` — human approval request transactions
  - `ztip.core/evidence` — evidence record submission transactions
  - `ztip.core/generic` — general-purpose transactions not covered by a specific core profile

  **Extension profiles** must be namespaced: `org.example/deploy`, `company.internal/migration`.

  Unknown profiles must **fail closed** — the transaction is rejected with `SCHEMA_INVALID`
  unless the control plane's policy explicitly allows unrecognized profiles. Profile-specific
  parameter validation is permitted but not required by ZTIP core. Parameters are always
  covered by the envelope hash regardless of whether they are profile-validated.
- **`description`** — Required. String. A human-readable description of what this action does.
  Used for audit readability and operator approval display. Not used for policy decisions.
- **`parameters`** — Required. Object.
  Profile-specific parameters required to perform the action. The content is opaque to ZTIP
  core and interpreted according to the declared `profile`. Parameters are still included in
  the envelope hash, so any modification is detectable. They must not contain credentials,
  secrets, or PII unless the deployment context explicitly governs this.
- **`required_capabilities`** — Required. Array of strings. The capabilities from the
  `target_actor`'s capability claims that this action will exercise. Must be a subset of
  `requested_capabilities` at the transaction level. Used for fine-grained capability
  validation.
- **`risk_level`** — Required. String. Enumerated. The risk level declared by the source actor
  for this action. Must be one of: `low`, `medium`, `high`, `critical`. Used by policy engines
  to route authorization decisions to the appropriate approval threshold.

  The source actor declares `risk_level` as part of the request. The control plane evaluates
  it — it must not be accepted blindly. The control plane may accept, elevate, or reject based
  on policy. See the `evaluated_risk_level` fields in the Authorization Decision envelope for
  how the control plane records its evaluation. A source actor may not use a lower-than-accurate
  risk level to bypass stricter policy thresholds; the control plane is responsible for
  independent risk assessment.
- **`expected_outputs`** — Required. Array of strings or objects.
  A structured description of what this action is expected to produce. Used to set
  verification expectations. Each entry should be machine-checkable (e.g., a service health
  check, a file hash, a deployment status, a receipt reference).

**`requested_capabilities`** — Required. Array of strings.
The capability or capabilities being invoked against the target actor. Must be a subset of
the capabilities registered for the target actor. The control plane validates this against
the target actor's registration.

**`atomicity_mode`** — Required. String. Enumerated.
The atomicity requirement for this transaction. Must be one of:
- `atomic_required` *(default — assumed if absent)*
- `best_effort_allowed`
- `non_atomic_explicitly_allowed`

If absent, implementations must treat this transaction as `atomic_required`. Non-default
modes must be explicitly declared and will be subject to policy evaluation.

**`verification_requirements`** — Required. Array of verification check objects.
Defines what must be verified for the transaction to be considered succeeded. Each entry is a
verification check. The verifying actor or the control plane evaluates these checks against
the `execution_receipt`'s `verification_results`.

Each verification check object must include:

- **`check_id`** — Required. String. A stable unique identifier for this check within the
  transaction. Used to link `verification_results` in the receipt back to the original
  requirement.
- **`check_type`** — Required. String. A structured classifier for the kind of check (e.g.,
  `service_health`, `file_hash`, `command_exit_code`, `deployment_status`, `policy_approval`,
  `receipt_reference`, `external_uri_reachable`). Must be machine-readable.
- **`description`** — Required. String. Human-readable description of what is being verified.
  Used for operator review and audit. Not used for automated evaluation.
- **`required`** — Required. Boolean. Whether this check must pass for the transaction to be
  `succeeded`. A check with `required: false` is informational — its failure does not cause
  the transaction to fail, but it is recorded in the receipt.
- **`expected_evidence_type`** — Optional. String. The evidence type (from the core evidence
  type registry) expected to satisfy this check, if evidence is needed. Used when the
  verification check requires a submitted evidence record.
- **`expected_result`** — Required. Object or string. The expected outcome of this check in a
  machine-evaluable form. Free text alone is invalid. Valid examples: `"healthy"`,
  `{"exit_code": 0}`, `{"hash": "sha256:abc123..."}`, `{"status": "deployed", "version":
  "2.4.1"}`. Invalid examples: `"looks good"`, `"review manually later"`.
- **`verification_actor`** — Optional. String. The `actor_id` of the actor expected to
  perform this verification check, if it requires a specific verifier. If absent, the
  control plane or a designated validator verifies. The target actor's own report of its
  results is attestation, not verification (see `SPEC.md`, Completion Verification).
- **`failure_reason_code`** — Optional. String. The reason code to record in the receipt if
  this check fails. Should be a valid ZTIP reason code (e.g., `VERIFY_FAILED`) or a
  namespaced extension code.

Vague or free-text-only verification requirements are schema-invalid. A check whose
`expected_result` is a string like `"looks good"`, `"seems fine"`, or `"review manually
later"` is not machine-evaluable and must be rejected.

**`integrity`** — Required. Integrity object. See Section 12.
The hash of this transaction request envelope. This hash becomes the canonical reference
(`request_hash`) for all subsequent envelopes in this transaction.

### Optional Fields

**`parent_transaction_id`** — Optional. String.
If this transaction is a child of a parent transaction (e.g., one step in a fan-out workflow),
the parent's `transaction_id` is recorded here. This links child transactions to their parent
for audit and workflow reconstruction.

**`evidence_requirements`** — Optional. Object or array.
If the source actor anticipates that evidence will be required — or wishes to proactively
attach evidence references — this field records what evidence is available or expected.
The control plane may additionally require evidence not declared here.

**`expiry_request`** — Optional. Timestamp (ISO 8601, UTC) or duration.
The source actor's requested expiration time for this transaction. This is a request, not an
instruction. The control plane sets the authoritative `expires_at` on the authorization
decision. The control plane may honor, shorten, or extend the source actor's request.

**`constraints`** — Optional. Object.
Any additional constraints on execution that the source actor wishes to record. Examples
might include environment constraints, concurrency limits, or ordering dependencies.
The semantics of `constraints` are subject to specification; initially treated as advisory
unless policy references specific constraint types.

**`break_glass_context`** — Optional. Object.
Emergency-governance metadata for break-glass transactions. Presence of this object indicates
the request is using an emergency authorization path and must be evaluated with stricter
policy and evidence requirements. This field does not bypass authorization.

`break_glass_context` should include:
- `incident_ref` — Required. Stable incident reference (ticket, case, or event ID).
- `named_approver_requirement` — Required. Identifier for the specific approver actor or
  approver role required for emergency authorization.
- `reason` — Required. Structured emergency justification for using break-glass.
- `compensating_controls` — Required. Array of controls that reduce risk during emergency
  execution (e.g., live supervision, bounded scope, additional logging, pre-staged rollback).
- `expires_at` — Required. Time-bounded expiration for emergency authorization context.
- `post_incident_review_required` — Required. Boolean flag indicating whether a mandatory
  post-incident review is required.
- `post_incident_review_by` — Optional. Timestamp by which the post-incident review must be
  completed.

**`notes`** — Optional. String.
A human-readable description of the purpose or context of this transaction. Used for audit
readability only. Not used for governance decisions. Free text is permitted here precisely
because it has no governance authority.

---

## Authorization Decision Envelope

The authorization decision envelope is produced by the control plane after evaluating a
transaction request. It is not created by the source or target actor. It records the
control plane's policy-based authorization outcome and, if authorized, the validity window
within which the transaction must be executed.

### Required Fields

**`ztap_version`** — See Section 5.

**`envelope_type`** — `"authorization_decision"`

**`transaction_id`** — See Section 5. Must match the `transaction_id` of the request.

**`decision_id`** — Required. String.
A unique identifier for this specific authorization decision. A transaction may have at most
one authoritative authorization decision per evaluation cycle, but may receive multiple
decisions if evidence is submitted iteratively. Each decision has its own `decision_id`.

**`request_hash`** — Required. String.
The hash of the transaction request envelope this decision evaluates. Must exactly match the
hash recorded in the transaction request's `integrity.hash_value`. This is the binding
reference that ties the decision to the original request.

**`control_plane`** — Required. Actor object.
The control plane that produced this decision. Role must be `control_plane`.

**`evaluated_at`** — Required. Timestamp (ISO 8601, UTC).
The time at which the control plane completed its evaluation.

**`authorization_status`** — Required. String. Enumerated.
The outcome of policy evaluation. Must be one of:
- `auto_authorized` — policy permits the transaction without human review. No human approval
  was required or requested.
- `human_approval_required` — policy requires a human approver before the transaction may
  proceed. The transaction is blocked pending approval. This decision will be followed by a
  new `authorization_decision` envelope with status `human_approved` once approval is granted.
- `human_approved` — a human approval was required by policy and has been granted and
  recorded. This status is distinct from `auto_authorized` so that human involvement is
  machine-detectable in the audit trail without requiring inspection of approval sub-fields.
  The control plane issues a new `authorization_decision` envelope with this status when
  approval is received — it does not amend the prior `human_approval_required` envelope.
- `evidence_required` — policy requires additional evidence before a decision can be made.
- `rejected` — policy denies the transaction.
- `expired` — the transaction's validity window elapsed before evaluation completed.

**Human approval is policy-conditional, not universal.** Whether a transaction requires
human approval is determined entirely by organizational policy. `human_approved` is one
possible outcome — it is not the default, and it is not required for every transaction.
Transactions that do not require human involvement use `auto_authorized`.

**`policy_refs`** — Required. Array of strings.
References to the policies evaluated in reaching this decision. These are the basis for the
authorization outcome. Required for all outcomes, including rejections. The format of policy
references is implementation-defined, but they must be stable identifiers resolvable in the
control plane's policy registry.

**`reason_codes`** — Required. Array of strings.
Structured reason codes for this decision. Required for all outcomes. For `auto_authorized`,
this confirms which policy basis authorized the transaction. For `rejected`, this records
the specific reason(s) for denial. See Section 15 for defined reason code categories.

**`integrity`** — Required. Integrity object. See Section 12.

### Conditional Fields

**`authorized_at`** — Conditional. Required when `authorization_status` is `auto_authorized`
or `human_approved`. Timestamp (ISO 8601, UTC). The moment the control plane issued
authorization.

**`expires_at`** — Conditional. Required when `authorization_status` is `auto_authorized`
or `human_approved`. Timestamp (ISO 8601, UTC). The authoritative expiration time for this
authorization. The transaction must be accepted and execution must begin before this
timestamp. After `expires_at`, the transaction moves to `expired` regardless of state.

The control plane owns `expires_at`. The source actor's `expiry_request` in the transaction
request is advisory. The control plane may honor, shorten, or extend it based on policy.

Authorization records are transaction-specific and single-use. An authorization record may
not be applied to a different transaction, and an expired authorization record must not be
reused. Doing so is a replay and must be rejected with reason code `APPROVAL_REPLAYED`.

**`human_approval_ref`** — Conditional. Required when `authorization_status` is
`human_approval_required` or `human_approved`.

When `human_approval_required` is issued, the object contains:
- `approval_requested_at` — when the approval request was issued (required),
- `required_approver` — the actor ID or role required to approve (required),
- `approval_expires_at` — optional, when the approval window expires if not granted.

When `human_approved` is issued (a new envelope with a new `decision_id`), the object
additionally contains:
- `approved_by` — the actor ID of the approver who granted approval (required),
- `approved_at` — the timestamp when approval was granted (required),
- `approval_scope` — a structured binding object confirming the approval is transaction-
  specific and non-transferable (required). See the `approval_scope` definition below.
- `approval_evidence_refs` — optional references to evidence records that accompanied the
  approval (e.g., incident ticket, authorization form).

**`approval_scope` object fields:**

The `approval_scope` object binds the approval to the exact context in which it was granted.
An approval outside this scope must be rejected with `APPROVAL_REPLAYED`.

- `transaction_id` — Required. The `transaction_id` this approval applies to.
- `request_hash` — Required. The `integrity.hash_value` of the original `transaction_request`
  envelope. Binds the approval to the unmodified request.
- `action_ids` — Required. Array. The `action_id` values from `requested_action` that this
  approval covers. An approval that does not reference the specific action IDs cannot be used
  to authorize those actions.
- `target_actor_id` — Required. The `actor_id` of the target actor this approval covers.
- `approved_capabilities` — Required. Array. The specific capabilities covered by this
  approval, as a subset of the transaction's `requested_capabilities`.
- `expires_at` — Required. The timestamp after which this approval is invalid, even if the
  transaction has not expired. Approvals must have a finite validity window.
- `single_use` — Required. Boolean. Whether this approval may be used only once. Default is
  `true`. A control plane may permit multi-use approvals for specific policy contexts, but
  must record this explicitly. An approval with `single_use: true` is consumed when the
  transaction advances past `authorized` and may not be reused for any subsequent transaction.

The two-envelope model is deliberate: the original `human_approval_required` envelope is
immutable and remains in the audit trail. The `human_approved` envelope is a separate linked
record with its own `decision_id`. Both are retained. The immutability rule applies to both.

**`declared_risk_level`** — Conditional. Present when the control plane evaluated risk level.
String. The `risk_level` as declared by the source actor in `requested_action`. Recorded for
audit traceability when the control plane changes the level.

**`evaluated_risk_level`** — Conditional. Present when the control plane changed or confirmed
the risk level. String. The risk level as assessed by the control plane after policy evaluation.
If the control plane accepted the source actor's declared level without change, this field may
be omitted or set to match `declared_risk_level`. If the control plane elevated the risk, this
field records the elevated level and reason codes should include `RISK_LEVEL_ESCALATED`.

**`risk_evaluation_reason`** — Optional. String.
A human-readable explanation of why the control plane changed or confirmed the declared risk
level. Used for audit readability. No governance authority.

**`required_evidence`** — Conditional. Required when `authorization_status` is
`evidence_required`. An object or array describing what evidence must be submitted before
the control plane can make a final decision. Each entry should identify the evidence type
required and any constraints on its content.

**`evidence_refs`** — Optional. Array of strings.
References to `evidence_id` values from `evidence_record` envelopes that were accepted and
evaluated in reaching this authorization decision. Present on `auto_authorized` and
`human_approved` decisions when evidence was submitted and accepted. Allows the audit trail
to link authorization decisions to the specific evidence records that satisfied policy
requirements.

---

## Execution Receipt Envelope

The execution receipt is the outcome record of a ZTIP transaction. It is produced by the
target actor (or a validator actor) after execution completes — whether successfully or not.
It is submitted to the control plane for verification and retention.

A receipt is required for every terminal transaction state: `succeeded`, `failed`,
`rejected`, `cancelled`, `expired`, and `timed_out`. All outcomes use the same receipt
structure. The `status` field determines the outcome.

### Required Fields

**`ztap_version`** — See Section 5.

**`envelope_type`** — `"execution_receipt"`

**`transaction_id`** — See Section 5.

**`receipt_id`** — Required. String.
A unique identifier for this receipt.

**`request_hash`** — Required. String.
The hash of the original transaction request envelope. Must match the `integrity.hash_value`
of the `transaction_request` envelope. This is the binding reference that proves this receipt
corresponds to the original, unmodified request.

**`authorization_decision_ref`** — Required. String.
The `decision_id` of the authorization decision that authorized this transaction to proceed.
For receipts produced before authorization (e.g., a `rejected` receipt produced during
evaluation), this field references the decision that caused the rejection.

**`source_actor`** — Required. Actor object.
The actor that originated the transaction.

**`target_actor`** — Required. Actor object.
The actor that performed (or attempted) the requested work.

**`control_plane`** — Required. Actor object.
The control plane that authorized this transaction.

**`started_at`** — Required. Timestamp (ISO 8601, UTC).
When execution began. For receipts where execution never started (e.g., `rejected`), this
records the time the terminal state was reached.

**`completed_at`** — Required. Timestamp (ISO 8601, UTC).
When execution ended, regardless of outcome.

**`status`** — Required. String. Enumerated.
The outcome of the transaction. Must be one of:
- `succeeded` — execution completed and verification passed.
- `failed` — execution was attempted but did not complete successfully, or verification failed.
- `rejected` — the transaction was rejected before execution (policy, schema, identity).
- `cancelled` — an authorized actor cancelled the transaction before completion.
- `expired` — the transaction's validity window elapsed.
- `timed_out` — a required step exceeded its allowed time window.

**`reason_codes`** — Required. Array of strings.
Structured reason codes. For `succeeded`, this confirms the policy and capability basis.
For all other statuses, this records the specific cause. See Section 15. An empty array is
valid only for `succeeded`.

**`actions_attempted`** — Required. Array of objects or strings.
A structured record of which actions the target actor attempted. Each entry should identify
the specific action and, where applicable, the system or resource acted upon. For transactions
where no execution was attempted (e.g., `rejected`), this is an empty array.

**`actions_completed`** — Required. Array of objects or strings.
A structured record of which actions successfully completed. For `succeeded`, this should
match `actions_attempted` in full. For `failed` or `timed_out`, this records the partial
state — what was completed before failure. This is the field that enables partial-state
reconstruction under `PARTIAL_STATE_BLOCKED`.

**`verification_results`** — Required. Object or array.
The results of checking the execution outcome against the `verification_requirements` from
the transaction request. Must be structured — not free text. Each requirement from the
request should have a corresponding pass/fail result here.

Where the field is an object, its keys are check identifiers and must not begin with an
underscore: underscore-prefixed keys are non-normative annotations, excluded from the envelope
hash, so a result stored under one is not covered by the seal — the same hash describes the
receipt with and without it.

Every entry, in any receipt state, must be a structured result: `check_id`, `check_type`, and
a boolean `passed` are required, and `expected_result`, `actual_result`, `verification_actor`,
`evidence_ref`, and `failure_reason_code` are optional and typed when present. `check_id` and
`check_type` must each carry at least one visible character — an identifier made of spaces or
zero-width characters names nothing.

When `status` is `succeeded`, the field **must** additionally be non-empty — a non-empty array
of result objects, or a non-empty object whose values are result objects: a success that
recorded no result asserts a completion that nothing checked. Receipts in a non-succeeded
terminal state may record no results, because execution may never have reached verification;
the field itself is still required, and an empty collection is how "none" is expressed.

Correspondence between the results here and the `verification_requirements` of the request,
matched by `check_id`, is a control-plane acceptance rule (see `SPEC.md`, Fail-Closed
Acceptance), not a schema constraint.

**`atomicity_result`** — Required. Object.
Records whether atomicity requirements were met. Must include:
- `mode_declared` — the `atomicity_mode` from the transaction request,
- `outcome` — whether the transaction executed atomically, partially, or non-atomically,
- `rollback_performed` — boolean, whether rollback was attempted,
- `partial_state_description` — structured description of any partial state reached (required
  when `PARTIAL_STATE_BLOCKED` is a reason code).

**`integrity`** — Required. Integrity object. See Section 12.

### Optional Fields

**`evidence_refs`** — Optional. Array of strings.
References to evidence record `evidence_id` values that were submitted in support of this
transaction. Allows the audit trail to link receipts to their supporting evidence.

**`prior_state_ref`** — Optional. Object.
Reference to the pre-change state relevant to this receipt, primarily for governance
transactions. Used to support rollback analysis and audit traceability.

`prior_state_ref` fields:
- `state_uri` — Optional. Stable URI/locator for the prior state snapshot or record.
- `state_hash` — Optional. Hash of the referenced prior state snapshot.
- `state_label` — Optional. Human-readable label for the prior state reference.

At least one of `state_uri` or `state_hash` should be present.

**`new_state_ref`** — Optional. Object.
Reference to the resulting post-change state relevant to this receipt, primarily for
governance transactions. Used for audit comparison and forward verification.

`new_state_ref` fields:
- `state_uri` — Optional. Stable URI/locator for the resulting state snapshot or record.
- `state_hash` — Optional. Hash of the referenced resulting state snapshot.
- `state_label` — Optional. Human-readable label for the resulting state reference.

At least one of `state_uri` or `state_hash` should be present.

**`child_receipt_refs`** — Optional. Array of objects.
Used by parent/orchestrator receipts in fan-out patterns to link child transaction outcomes.
Each child reference identifies the child transaction and the corresponding child receipt/hash.

Each `child_receipt_ref` object should include:
- `child_transaction_id` — Required. The child transaction identifier.
- `child_receipt_ref` — Optional. Child receipt identifier (`receipt_id`) or durable receipt
  locator.
- `child_request_hash` — Optional. Child transaction request hash.
- `child_receipt_hash` — Optional. Child receipt envelope hash.

At least one of `child_receipt_ref`, `child_request_hash`, or `child_receipt_hash` should be
present for each child entry.

**`notes`** — Optional. String.
Human-readable summary of the outcome. Used for audit readability. No governance authority.

---

## Evidence Record Envelope

An evidence record is supporting material submitted to satisfy a policy requirement identified
by the control plane. It is a linked envelope — it references the transaction it supports by
`transaction_id` and `request_hash` — but it is not a modification to the original request.

Evidence may be inline (the content is in the envelope) or by reference (the envelope records
metadata and a locator for externally stored evidence).

### Required Fields

**`ztap_version`** — See Section 5.

**`envelope_type`** — `"evidence_record"`

**`transaction_id`** — See Section 5.

**`evidence_id`** — Required. String.
A unique identifier for this evidence record.

**`request_hash`** — Required. String.
The hash of the transaction request envelope this evidence supports. Binds the evidence to
the original, immutable request.

**`produced_by`** — Required. Actor object.
The actor that produced or submitted this evidence.

**`produced_at`** — Required. Timestamp (ISO 8601, UTC).
When this evidence was produced or captured.

**`evidence_type`** — Required. String.
A structured identifier for the type of evidence. ZTIP defines a set of core evidence types.
Extension evidence types are permitted but must use a namespaced format
(`org.example/custom-type`). An unknown non-namespaced type must be rejected.

**Core evidence types (ZTIP-defined):**

| Type | Description |
|---|---|
| `test_result` | Output or summary of an automated test run. Includes pass/fail status and test identifier. |
| `command_output` | The stdout/stderr output and exit code of a command or script execution. |
| `file_hash` | A cryptographic hash of a specific file or artifact, for integrity verification. |
| `commit_ref` | A reference to a specific git commit or source control revision. |
| `pull_request_ref` | A reference to a pull request or code review, including status. |
| `approval_record` | A structured record of an approval granted by a human or system. |
| `policy_decision` | The output of a policy engine evaluation (e.g., OPA decision, IAM allow/deny). |
| `deployment_status` | The result of a deployment operation, including service health and version confirmation. |
| `log_excerpt` | A bounded, timestamped excerpt from an operational or audit log. |
| `external_uri` | A reference to an externally hosted resource, with the hash of its content at submission time. |
| `inline_value` | Structured inline data that does not fit another core type. Must include a `schema` or `format` descriptor. |

Extension types must use a namespaced format: `org.example/my-evidence-type`. Extension
types are valid within the organization's control plane but cannot be assumed portable across
implementations. Control planes may restrict which extension namespaces they accept.

**`evidence_hash`** — Required. String.
A SHA-256 hash of the evidence content (inline or referenced). For inline content, computed
over the canonicalized `evidence_content` field. For external references, computed over the
referenced content at the time of evidence submission. Used to verify that the evidence
presented for policy evaluation has not been altered.

**`integrity`** — Required. Integrity object. See Section 12.

### Conditional Fields

**`evidence_content`** — Conditional. Required if evidence is inline.
The evidence content, embedded directly in the envelope. Must be structured (object or array),
not free text, wherever possible. Free-text evidence has no machine-verifiable governance value.

**`evidence_uri`** — Conditional. Required if evidence is by reference.
A stable URI or locator for externally stored evidence. The evidence at this location at the
time of submission is what the `evidence_hash` was computed over.

**`notes`** — Optional. String. Required if `evidence_type` is `other`.

---

## Amendment Event Envelope

An amendment event records a change to the context, parameters, or standing of a transaction
after the original request was submitted. It does not modify the original `transaction_request`
envelope. The original request is immutable; the amendment event is a linked record.

An amendment event is itself a ZTIP envelope, subject to the same governance model. It must
be authorized by the control plane. An unauthorized amendment event is not a valid amendment.

### Required Fields

**`ztap_version`** — See Section 5.

**`envelope_type`** — `"amendment_event"`

**`transaction_id`** — See Section 5.

**`amendment_id`** — Required. String.
A unique identifier for this amendment event.

**`request_hash`** — Required. String.
The hash of the original `transaction_request` envelope being referenced. Immutably binds
this amendment to the original request.

**`created_by`** — Required. Actor object.
The actor that created this amendment event.

**`created_at`** — Required. Timestamp (ISO 8601, UTC).
When this amendment event was created.

**`amendment_type`** — Required. String. Enumerated.
The type of change this amendment records. Initial types:
- `context_update` — additional context is being provided without changing the request itself.
- `cancellation_request` — the creating actor is requesting cancellation of the transaction.
  **Important:** a `cancellation_request` amendment does not automatically cancel the
  transaction. The control plane must evaluate the amendment, verify the requesting actor has
  authorization to cancel (either by policy or by explicit operator approval), and then issue
  the appropriate state transition and receipt. Cancellation is not inferred from the
  amendment's existence.
- `evidence_addition` — new evidence is being linked to the transaction.
- `deadline_extension_request` — a request to extend the authorization validity window.
  The control plane decides whether to honor the request. Not automatic.
- `operator_note` — an operator is recording a structured note on the transaction record.

**Amendment lifecycle rule:** An amendment event is a linked governed envelope — it does not
mutate the original request or automatically change transaction state. Any amendment that
would alter authorization scope, target actor, requested action, cancellation state, expiry,
evidence requirements, or governance state must be evaluated by the control plane before it
takes effect. The control plane responds with a new `authorization_decision` or an
`execution_receipt` (in the case of cancellation reaching a terminal state). Both the
amendment event and the control plane's response are retained in the audit trail.

**`reason_codes`** — Required. Array of strings.
Structured reason codes explaining why this amendment was created. See Section 15.

**`linked_envelope_refs`** — Required. Array of strings.
Identifiers of other envelopes (by their respective `_id` field: `decision_id`,
`evidence_id`, `receipt_id`, or another `amendment_id`) that this amendment references
or relates to.

**`integrity`** — Required. Integrity object. See Section 12.

### Optional Fields

**`amendment_content`** — Optional. Object.
The structured content of the amendment, where applicable. For `context_update`, this
contains the additional context. For `operator_note`, this contains the structured note.

**`notes`** — Optional. String. Human-readable explanation. No governance authority.

---

## Integrity Object and Hashing

Every ZTIP envelope contains an `integrity` object. This object records how the envelope was
hashed and the resulting hash value. It is the foundation of ZTIP's tamper-detection model.

### Integrity Object Fields

**`canonicalization`** — Required. String.
The canonicalization method applied to the envelope before hashing. Default value: `RFC8785-JCS`.

**`hash_algorithm`** — Required. String.
The hash algorithm used. Default value: `SHA-256`.

**`hash_value`** — Required. String.
The hex-encoded hash of the canonicalized envelope. See "Hash Construction" below.

**`signed`** — Optional. Boolean. Future use.
Whether this envelope has been cryptographically signed. Signing is not required by ZTIP v1.
This field is reserved for future use. If absent, treated as `false`.

**`signature_ref`** — Optional. String. Future use.
A reference to the signature record, if `signed` is `true`. Undefined for v1.

### Canonicalization

ZTIP v1 uses **RFC 8785 JSON Canonicalization Scheme (JCS)** as the default canonicalization
method.

RFC 8785 defines a deterministic canonical representation of JSON for cryptographic operations.
It constrains JSON to I-JSON (the interoperable subset of JSON as defined in RFC 7493) and
applies deterministic property sorting and Unicode normalization. The result is that the same
logical JSON object produces the same byte sequence regardless of how it was originally
serialized, by whom, or on which platform.

ZTIP requires RFC 8785 JCS canonicalization because:
- ZTIP envelopes may move between systems over any transport.
- Different serializers may produce whitespace differences, property ordering differences,
  or number representation differences.
- Hash verification must succeed across systems. This requires the canonical form to be
  identical wherever it is computed.

Implementations must canonicalize the envelope using RFC 8785 JCS before computing the hash.

### Hash Construction

The hash is computed over the **canonicalized envelope with exactly one envelope field
excluded: `integrity.hash_value`**. Non-normative annotation keys — keys whose names begin
with an underscore (`_`), used for documentation labels in examples — are not envelope
fields and are stripped recursively before canonicalization.

Only `integrity.hash_value` is excluded. The rest of the `integrity` object —
`canonicalization`, `hash_algorithm`, and `signed` — is included in the hash input.
This means the declared hash algorithm and canonicalization method are themselves protected
by the hash. A modification to the declared algorithm or canonicalization method changes the
hash, making it detectable.

The `integrity.hash_value` field must be excluded because its value depends on the hash
output — including it creates a circular dependency. Beyond `integrity.hash_value` and
underscore-prefixed annotation keys, no other exclusions are applied to the base envelope.
If signature fields are added in future versions, their exclusion rules will be defined at
that time.

The correct procedure:

1. Construct the full envelope object with all required fields populated, including the
   `integrity` object with `canonicalization`, `hash_algorithm`, and `signed` as applicable.
2. Remove the `integrity.hash_value` field. (Removal, not an empty-string placeholder —
   the two are not hash-equivalent under RFC 8785.) All other `integrity` fields remain
   present and unchanged.
3. Strip all underscore-prefixed annotation keys, recursively, if any are present.
4. Apply RFC 8785 JCS canonicalization to the complete envelope.
5. Compute SHA-256 over the canonical byte sequence.
6. Encode the result as a lowercase hex string.
7. Set `integrity.hash_value` to this value.

**Why not exclude the entire `integrity` object?** Excluding the entire object would mean
the declared `canonicalization` and `hash_algorithm` values are not part of the verified
content. An attacker could claim the envelope uses a different algorithm without detection.
Including these fields in the hash input ensures they are tamper-evident.

### Hash Linkage Chain

ZTIP's audit integrity depends on the following hash linkage:

```
transaction_request.integrity.hash_value
  ↑ referenced by
authorization_decision.request_hash
  ↑ referenced by
execution_receipt.request_hash
  ↑ also referenced by
evidence_record.request_hash
amendment_event.request_hash
```

Each subsequent envelope references the `request_hash` of the original `transaction_request`.
This binds every outcome envelope to the original, immutable request.

A receipt whose `request_hash` does not match the original transaction request's
`integrity.hash_value` is invalid and must be rejected by the control plane.

### What Hash Verification Answers

- **Is this the original request?** Recompute the hash of the `transaction_request` envelope.
  If it matches `integrity.hash_value`, the envelope has not been altered since submission.
- **Does this receipt correspond to this request?** Compare the receipt's `request_hash` to
  the transaction request's `integrity.hash_value`. A match proves the receipt was produced
  for this specific, unmodified request.
- **Has this evidence been altered?** Recompute the hash over the evidence content and compare
  to `evidence_hash`. A match proves the evidence has not changed since it was recorded.
- **Has the audit log been tampered with?** Hash-verify each stored envelope independently.
  A failed hash verification on any stored envelope indicates potential tampering.

---

## Validity Windows

ZTIP v1 governs transaction time boundaries with three required timestamps and one optional
source request field.

### Timestamp Fields

**`created_at`** (on `transaction_request`)
Set by the source actor at envelope construction time. Records when the request was created.
The source actor owns this value.

**`authorized_at`** (on `authorization_decision`)
Set by the control plane at the moment authorization is issued. Records when the transaction
was cleared to proceed. The control plane owns this value.

**`expires_at`** (on `authorization_decision`)
Set by the control plane. Records when the authorization expires. A transaction that has not
reached `accepted` state before `expires_at` must transition to `expired`. The control plane
owns this value.

`expires_at` is the authoritative validity boundary. No transaction may proceed past its
`expires_at`, regardless of progress state.

### Source Actor TTL Request

**`expiry_request`** (on `transaction_request`, optional)
The source actor may include a requested expiration time (as an absolute timestamp or
relative duration) in the transaction request. This communicates the source actor's
intent — how long this request is relevant.

The `expiry_request` is advisory. The control plane decides the final `expires_at`. The
control plane may honor the source actor's request, shorten it per policy, or extend it.

This design reflects the protocol's governance model: the source actor declares intent;
the control plane holds authority.

### Expiry Behavior

When `expires_at` is reached:
- If the transaction has not reached `accepted`, it transitions to `expired`.
- The control plane produces an `execution_receipt` with `status: "expired"`.
- The transaction is terminal. A new transaction must be created to retry.
- Expiry produces the same receipt structure as any other terminal outcome.

---

## Atomicity Fields

Atomicity declarations appear in the `transaction_request` envelope and atomicity outcomes
appear in the `execution_receipt` envelope.

### In `transaction_request`: `atomicity_mode`

Declares the atomicity requirement for this transaction. Required.

| Value | Meaning |
|---|---|
| `atomic_required` | The transaction must complete fully or not at all. Default. |
| `best_effort_allowed` | Partial completion is permitted if explicitly declared and policy allows. |
| `non_atomic_explicitly_allowed` | Non-atomic execution is permitted. Must be explicitly declared and control-plane-authorized. |

If absent, `atomic_required` is assumed.

### In `execution_receipt`: `atomicity_result`

Records the actual atomicity outcome. Required.

| Sub-field | Required | Description |
|---|---|---|
| `mode_declared` | Yes | The `atomicity_mode` from the transaction request. |
| `outcome` | Yes | `full` (all steps completed), `partial` (some steps completed), or `none` (no steps completed). |
| `rollback_performed` | Yes | Boolean. Whether rollback was attempted when partial execution occurred. |
| `partial_state_description` | Conditional | Required when `outcome` is `partial`. Structured description of what was and was not completed. |

### Non-Atomic Execution

Non-default atomicity modes (`best_effort_allowed`, `non_atomic_explicitly_allowed`) must be:
1. Explicitly declared in the `transaction_request`.
2. Evaluated by the control plane during policy evaluation.
3. Confirmed or rejected in the `authorization_decision`.
4. Fully reflected in the `execution_receipt`.

A target actor that encounters a partial execution state under `atomic_required` and cannot
roll back must fail the transaction with reason code `PARTIAL_STATE_BLOCKED` and produce a
receipt with `atomicity_result.outcome: "partial"` and a populated
`partial_state_description`.

---

## Reason Codes

Reason codes are structured string identifiers that appear in `authorization_decision`,
`execution_receipt`, and `amendment_event` envelopes. They make failure and rejection causes
machine-readable without requiring interpretation of free-text fields.

Reason codes are arrays. Multiple codes may apply to a single outcome.

### Reason Code Registry Model

ZTIP uses an **open governed registry** for reason codes:

- **Core reason codes** are defined and maintained by the ZTIP protocol. They are reserved
  identifiers. Implementations must recognize and correctly handle core codes. An unknown
  core reason code in a received envelope is a structural error.
- **Extension reason codes** allow implementations to express domain-specific failure modes
  that are not covered by the core set. Extension codes must be namespaced using a
  reverse-domain format: `org.example/DEPLOY_WINDOW_CLOSED`, `com.acme/QUOTA_EXCEEDED`.
- **Un-namespaced unknown codes** are invalid. An implementation that receives an envelope
  containing an un-namespaced code it does not recognize must treat it as `SCHEMA_INVALID`.
- Control planes may restrict which extension namespaces they accept. A control plane that
  does not recognize an extension namespace may reject the envelope with `SCHEMA_INVALID`.

This model ensures the core protocol remains stable and interoperable while allowing
organizations to extend reason code coverage for their specific deployment contexts.

### Core Reason Code Registry

The following codes are defined by ZTIP v1. They are reserved identifiers and must not be
redefined by extensions.

**Structural**

| Code | Appears In | Meaning |
|---|---|---|
| `SCHEMA_INVALID` | Decision, Receipt | The envelope does not conform to the required ZTIP schema. |

**Identity**

| Code | Appears In | Meaning |
|---|---|---|
| `ROLE_INVALID` | Decision, Receipt | The actor does not hold a valid ZTIP role for this operation. |
| `ACTOR_UNREGISTERED` | Decision, Receipt | The actor is not registered with the control plane. |

**Authorization**

| Code | Appears In | Meaning |
|---|---|---|
| `AUTHORITY_MISSING` | Decision | Required authority or delegation is absent from the transaction. |
| `POLICY_DENIED` | Decision, Receipt | The control plane policy explicitly denies this transaction. |
| `APPROVAL_REPLAYED` | Decision, Receipt | A prior approval was reused outside its allowed scope, validity window, transaction binding, or single-use constraint. Authorization records are transaction-specific and non-reusable. |
| `RISK_LEVEL_ESCALATED` | Decision | The control plane elevated the risk level declared by the source actor. The evaluated risk level triggers stricter policy requirements (additional evidence, human approval, or rejection). |

**Capability**

| Code | Appears In | Meaning |
|---|---|---|
| `CAPABILITY_MISSING` | Decision, Receipt | The target actor does not hold the requested capability. |

**Acceptance**

| Code | Appears In | Meaning |
|---|---|---|
| `TARGET_REJECTED` | Receipt | The target actor declined to accept the authorized transaction. |

**Execution**

| Code | Appears In | Meaning |
|---|---|---|
| `ACTION_FAILED` | Receipt | The target actor attempted the action and it failed. |
| `VERIFY_FAILED` | Receipt | The result did not pass the verification requirements. |
| `COMPLETION_UNVERIFIED` | Receipt | A receipt claimed success but one or more required verification checks were satisfied only by executor attestation and were never independently verified. Checks that run independently and fail are `VERIFY_FAILED`. This is a fail-closed condition. |
| `VERIFY_UNAVAILABLE` | Receipt | Required verification could not be executed — the verifier was unavailable or the declared checks could not run. The transaction must not resolve as succeeded. This is a fail-closed condition. |

**Temporal**

| Code | Appears In | Meaning |
|---|---|---|
| `TIMEOUT` | Receipt | A required step was not completed within its allowed time window. |
| `EXPIRED` | Decision, Receipt | The transaction's validity window elapsed. |

**Control**

| Code | Appears In | Meaning |
|---|---|---|
| `CANCELLED` | Receipt, Amendment | The transaction was explicitly cancelled by an authorized actor. |

**Integrity**

| Code | Appears In | Meaning |
|---|---|---|
| `INTEGRITY_FAILED` | Decision, Receipt | A hash check failed. The envelope or receipt may have been tampered with. |

**Policy / Evidence**

| Code | Appears In | Meaning |
|---|---|---|
| `EVIDENCE_MISSING` | Decision | Required evidence was not submitted within the required window. |

**Atomicity**

| Code | Appears In | Meaning |
|---|---|---|
| `PARTIAL_STATE_BLOCKED` | Receipt | Partial execution occurred under `atomic_required`. Transaction failed closed. |

**Registry**

| Code | Appears In | Meaning |
|---|---|---|
| `REGISTRY_INCONSISTENT` | Decision | The control plane cannot verify internal consistency of its actor, capability, policy, or transaction registry. Authorization is refused until consistency is restored. This is a fail-closed condition. |

### Usage Rules

- Reason codes must be present in every `authorization_decision` and `execution_receipt`,
  including successful outcomes. An empty array is valid only for `status: "succeeded"` receipts.
- Core reason codes are stable reserved identifiers. They will not be removed or redefined
  between minor versions. Breaking changes to core codes require a major version increment.
- Extension reason codes must use a namespaced format: `org.example/CODE_NAME`.
- Un-namespaced codes that are not in the core registry are schema-invalid.
- Implementations must not use free-text fields in place of reason codes for machine-governed
  decisions. Free-text context belongs in `notes` fields, not reason code arrays.

---

## Versioning

### `ztap_version`

Every ZTIP envelope must include a `ztap_version` field. This field identifies the version
of the ZTIP protocol specification under which the envelope was created. (The field keeps
the protocol's original working name — see the legacy-field note in Section 5.)

The current working version is `1.0-draft`. When v1 is finalized, envelopes should use `1.0`.

Version format: `<major>.<minor>[-<qualifier>]`

Examples: `1.0`, `1.1`, `1.0-draft`, `2.0-rc1`

### Version Compatibility Rules

- **Implementations must reject envelopes with an unsupported major version** unless
  explicitly configured to accept them. An implementation that supports `1.x` must reject
  a `2.0` envelope unless it has been explicitly updated to support ZTIP v2.
- **Minor versions within the same major version must be backwards-compatible.** A `1.1`
  envelope must be processable by a `1.0` implementation, though the `1.0` implementation
  may not understand new optional fields introduced in `1.1`.
- **The `1.0-draft` qualifier signals pre-release status.** Implementations processing
  `1.0-draft` envelopes must treat them as non-production. A production control plane may
  reject `draft`-qualified envelopes at its discretion.
- **Breaking schema changes require a major version increment.** Adding required fields,
  removing fields, or changing field semantics incompatibly constitutes a breaking change.
  Adding optional fields does not.

### Control Plane Version Enforcement

A compliant ZTIP control plane must:
- Record the `ztap_version` from every submitted envelope.
- Reject envelopes with unsupported major versions with reason code `SCHEMA_INVALID`.
- Include its own supported version range in its conformance documentation.

### Multi-Version Audit Trail

As ZTIP protocol versions evolve, a control plane's audit log will accumulate envelopes from
multiple versions. The governing rule:

**Every envelope is verified according to the `ztap_version` declared in that envelope.**

Specifically:
- Hash verification must use the canonicalization method and hash algorithm declared in the
  envelope's own `integrity` object — not the control plane's current default.
- Audit stores must retain the `ztap_version`, `integrity.canonicalization`, and
  `integrity.hash_algorithm` fields alongside every stored record so that each envelope
  can be re-verified later without requiring external version knowledge.
- A control plane must not silently reinterpret an older-version envelope under the schema
  rules of a newer version. Structural validation must apply the rules in effect at the time
  the envelope was created.
- Envelopes with unsupported major versions must be rejected for active authorization. They
  may remain in the audit log as historical records if they were stored when that version
  was supported.
- When a control plane upgrades, existing audit records from prior supported versions remain
  auditable under the rules of their original version. The upgrade does not retroactively
  invalidate prior records.

---

## Conceptual Examples

The following examples illustrate ZTIP envelope structure using the field names defined in
this document.

> **Draft notation.** These examples are conceptual. Field names, value formats, and
> structure are illustrative of this draft schema and will change before v1 schema freeze.
> Do not use these examples as implementation targets.

---

### Example 1: Transaction Request Envelope

A planning agent requests a production deployment. No parent transaction. Auto-authorization
is expected per policy.

```json
{
  "ztap_version": "1.0-draft",
  "envelope_type": "transaction_request",
  "transaction_id": "ztip-txn-0a1b2c3d4e5f",
  "created_at": "2026-04-24T14:00:00Z",
  "source_actor": {
    "actor_id": "agent-planner-001",
    "role": ["planner", "source_actor"],
    "display_name": "Planning Agent",
    "organization_id": "org-acme-corp",
    "registration_ref": "reg://agents/planner-001",
    "capability_claims": ["approval.request"],
    "implementation_ref": "architect-agent-v2"
  },
  "target_actor": {
    "actor_id": "agent-executor-deploy-001",
    "role": ["executor", "target_actor"],
    "display_name": "Deployment Executor",
    "organization_id": "org-acme-corp",
    "registration_ref": "reg://agents/executor-deploy-001",
    "capability_claims": ["org.acme/deploy_service"]
  },
  "requested_action": {
    "action_id": "act-0a1b2c3d4e5f-deploy",
    "action_type": "deploy",
    "profile": "org.acme/deployment",
    "description": "Deploy billing-api v2.4.1 to production.",
    "parameters": {
      "service": "billing-api",
      "environment": "production",
      "version": "2.4.1"
    },
    "required_capabilities": ["org.acme/deploy_service"],
    "risk_level": "medium",
    "expected_outputs": [
      { "type": "deployment_status", "expected": "deployed" }
    ]
  },
  "requested_capabilities": ["org.acme/deploy_service"],
  "atomicity_mode": "atomic_required",
  "verification_requirements": [
    {
      "check_id": "chk-01-health",
      "check_type": "service_health",
      "description": "billing-api must be healthy in production after deployment.",
      "required": true,
      "expected_result": { "status": "healthy", "target": "billing-api.production" },
      "failure_reason_code": "VERIFY_FAILED"
    },
    {
      "check_id": "chk-01-version",
      "check_type": "deployment_status",
      "description": "Deployed version must match the requested version.",
      "required": true,
      "expected_result": { "version": "2.4.1", "target": "billing-api.production" },
      "failure_reason_code": "VERIFY_FAILED"
    }
  ],
  "expiry_request": "2026-04-24T14:30:00Z",
  "integrity": {
    "canonicalization": "RFC8785-JCS",
    "hash_algorithm": "SHA-256",
    "hash_value": "a3f9e1c7b2d04851..."
  }
}
```

---

### Example 2: Authorization Decision Envelope

The control plane evaluates the above request and auto-authorizes it.

```json
{
  "ztap_version": "1.0-draft",
  "envelope_type": "authorization_decision",
  "transaction_id": "ztip-txn-0a1b2c3d4e5f",
  "decision_id": "ztip-dec-9f8e7d6c5b4a",
  "request_hash": "a3f9e1c7b2d04851...",
  "control_plane": {
    "actor_id": "control-plane-primary",
    "role": ["control_plane"],
    "organization_id": "org-acme-corp",
    "registration_ref": "reg://control-plane/primary"
  },
  "evaluated_at": "2026-04-24T14:00:03Z",
  "authorization_status": "auto_authorized",
  "policy_refs": [
    "policy://deployments/production/auto-approve-v1"
  ],
  "reason_codes": [],
  "authorized_at": "2026-04-24T14:00:03Z",
  "expires_at": "2026-04-24T14:20:00Z",
  "integrity": {
    "canonicalization": "RFC8785-JCS",
    "hash_algorithm": "SHA-256",
    "hash_value": "7c3a51d9f0b2e648..."
  }
}
```

Note: `expires_at` was set to 20 minutes by the control plane. The source actor had requested
30 minutes. The control plane shortened the window per policy. This is the authoritative
validity boundary.

---

### Example 3: Execution Receipt Envelope — Success

The deployment completes and verification passes.

```json
{
  "ztap_version": "1.0-draft",
  "envelope_type": "execution_receipt",
  "transaction_id": "ztip-txn-0a1b2c3d4e5f",
  "receipt_id": "ztip-rcpt-1a2b3c4d5e6f",
  "request_hash": "a3f9e1c7b2d04851...",
  "authorization_decision_ref": "ztip-dec-9f8e7d6c5b4a",
  "source_actor": {
    "actor_id": "agent-planner-001",
    "role": ["planner", "source_actor"],
    "organization_id": "org-acme-corp",
    "registration_ref": "reg://agents/planner-001"
  },
  "target_actor": {
    "actor_id": "agent-executor-deploy-001",
    "role": ["executor", "target_actor"],
    "organization_id": "org-acme-corp",
    "registration_ref": "reg://agents/executor-deploy-001"
  },
  "control_plane": {
    "actor_id": "control-plane-primary",
    "role": ["control_plane"],
    "organization_id": "org-acme-corp",
    "registration_ref": "reg://control-plane/primary"
  },
  "started_at": "2026-04-24T14:00:08Z",
  "completed_at": "2026-04-24T14:03:41Z",
  "status": "succeeded",
  "reason_codes": [],
  "actions_attempted": [
    { "action": "deploy_service", "target": "billing-api", "environment": "production" }
  ],
  "actions_completed": [
    { "action": "deploy_service", "target": "billing-api", "environment": "production" }
  ],
  "verification_results": [
    {
      "check_id": "chk-01-health",
      "check_type": "service_health",
      "expected_result": { "status": "healthy" },
      "actual_result": { "status": "healthy" },
      "passed": true
    },
    {
      "check_id": "chk-01-version",
      "check_type": "deployment_status",
      "expected_result": { "version": "2.4.1" },
      "actual_result": { "version": "2.4.1" },
      "passed": true
    }
  ],
  "atomicity_result": {
    "mode_declared": "atomic_required",
    "outcome": "full",
    "rollback_performed": false
  },
  "integrity": {
    "canonicalization": "RFC8785-JCS",
    "hash_algorithm": "SHA-256",
    "hash_value": "5e2f7a9b3c014d62..."
  }
}
```

---

## Open Questions

The blocking questions raised by this draft were resolved before the machine-readable schema
files under `schemas/` were produced. The open items that remain do not block them.

The following questions were resolved by operator decision and are documented here for
traceability. Open questions that remain unresolved follow.

**Resolved:**

1. ~~**`requested_action` sub-structure.**~~ Resolved. ZTIP defines a standard action wrapper
   with required fields: `action_id`, `action_type`, `profile`, `description`, `parameters`,
   `required_capabilities`, `risk_level`, `expected_outputs`. Parameters are opaque to ZTIP
   core but covered by the envelope hash. Unknown profiles fail closed unless policy allows.

2. ~~**`verification_requirements` sub-structure.**~~ Resolved. ZTIP defines a standard
   verification check array. Each check requires: `check_id`, `check_type`, `description`,
   `required`, `expected_result`. Free-text-only checks are invalid.

3. ~~**Reason code registry governance.**~~ Resolved. Open governed registry. ZTIP core defines
   reserved codes. Extension codes must be namespaced (`org.example/CODE`). Unknown un-namespaced
   codes are schema-invalid.

4. ~~**Evidence type registry.**~~ Resolved. Same open governed registry model. Core evidence types
   defined in Section 10. Extension types must be namespaced.

5. ~~**`amendment_type` lifecycle.**~~ Resolved. Amendments do not automatically mutate transaction
   state. `cancellation_request` requires control-plane evaluation and authorization. The control
   plane issues the resulting state transition and receipt.

6. **Actor object in receipts.** Receipts are self-contained verifiable records. This is
   deliberate. The redundancy is intentional: a receipt must be independently verifiable without
   querying the control plane's actor registry. This question is closed — receipts remain
   self-contained.

7. ~~**Hash exclusion rule.**~~ Resolved. Exclude only `integrity.hash_value` (by removal),
   plus underscore-prefixed non-normative annotation keys, which are stripped recursively
   before canonicalization. The rest of the `integrity` object (`canonicalization`,
   `hash_algorithm`, `signed`) remains in the hash input, ensuring the declared algorithm
   and method are tamper-evident.

9. ~~**`human_approval_ref` update model.**~~ Resolved. The control plane issues a new
   `authorization_decision` with a new `decision_id` and `authorization_status: "human_approved"`.
   The original envelope is immutable. Both envelopes are retained. `approval_scope` binds the
   approval to the specific transaction, request hash, action IDs, target actor, and capabilities.
   `examples/02-human-approval-required.json` uses `"human_approved"` accordingly.

**All prior blocking questions resolved.** See traceability list above.

**Subsequently resolved (did not block schemas):**

8. ~~**Multi-version audit log.**~~ Resolved. Every envelope is verified per its own declared
   `ztap_version`. Audit stores must retain `ztap_version`, `canonicalization`, and
   `hash_algorithm` alongside every record. Control planes must not reinterpret older envelopes
   under newer schema rules. See the Multi-Version Audit Trail section in Versioning.

10. ~~**Capability namespacing.**~~ Resolved. Open governed registry. Core capabilities use
    simple reserved names (`file.read`, `git.commit`). Extension capabilities must be namespaced
    (`org.example/deploy_service`). Unknown un-namespaced capabilities are schema-invalid.

11. ~~**`requested_action.profile` registry.**~~ Resolved. Open governed registry. Core profiles
    are `ztip.core/*`. Extension profiles must be namespaced. Unknown profiles fail closed unless
    policy explicitly allows. Defined in Transaction Request Envelope section.

12. ~~**`risk_level` policy integration.**~~ Resolved. Source actor declares; control plane
    evaluates and may elevate. `declared_risk_level`, `evaluated_risk_level`, and
    `risk_evaluation_reason` fields on `authorization_decision`. `RISK_LEVEL_ESCALATED` reason code.

**Still open (informational, do not block schemas):**

A. **Break-glass envelope type.** The break-glass principle is defined in SPEC.md. The minimum
   evidence fields for break-glass authorization have been described in SPEC.md but not yet
   formalized as schema fields. A future pass should define these as a structured evidence type
   or a dedicated amendment type.

B. **`requested_action.profile` versioning.** When a profile's parameter schema changes, how
   are profile versions expressed? e.g., `ztip.core/gitops@2` or `ztip.core/gitops/v2`.
   Currently unspecified.

---

## Next Steps

This document has defined the prose schema for all five ZTIP v1 envelope types, the actor
and integrity objects, the validity window model, atomicity fields, reason codes, and
versioning rules.

**Delivered so far:**

1. **Open-question review** — the blocking questions above are resolved (see the
   traceability list under Open Questions).

2. **`examples/`** — ten reference lifecycle bundles covering every envelope type, every
   authorization outcome, and the key failure modes (auto-authorized success,
   human-approval, evidence-required, rejection, `PARTIAL_STATE_BLOCKED` failure,
   cancellation, expiry, child transaction, break-glass, governance transaction), with
   real recomputable integrity hashes.

3. **`schemas/`** — machine-readable JSON Schema files derived from this document.
   `SCHEMA.md` is the authoritative specification; `schemas/` is its implementation.

4. **`WHITEPAPER.md`** — the external-facing adoption document.

5. **Repo governance files** — `CONTRIBUTING.md`, `LICENSE`, `CHANGELOG.md`, and
   `CONFORMANCE.md`, which formalizes minimum control plane conformance requirements from
   `SPEC.md` Section 9.

**Remaining before v1:** resolve the non-blocking open questions above and freeze field
names for a `1.0` release.

---

> ZTIP Schema Draft — `1.0-draft`.
> Derived from `SPEC.md`; implemented as the JSON Schemas under `schemas/`.
> **Freedom for engineers. Governance for the organization.**
