# ZTIP Specification Draft

*Zero Trust Intelligence Protocol — Transaction Lifecycle and Governance Model*

---

## Status

**DRAFT — `1.0-draft`. Pre-release; not yet a frozen production target.**

This document is the specification draft. It defines the transaction lifecycle, governance
model, and core concepts of the Zero Trust Intelligence Protocol in prose.

Field names, schema structures, transport bindings, and API interfaces are NOT finalized
here. Hash canonicalization is the exception: RFC 8785 JCS with SHA-256 is finalized for v1
(see Integrity and Hashing). The machine-readable JSON Schemas live in `schemas/` (with the
prose field model in `SCHEMA.md`), and a reference runtime lives in `ztip/`. This document
establishes the governing principles and lifecycle model that all schema and implementation
work must conform to.

This specification is versioned. The current working version is `1.0-draft` — the one
version string shared by the spec, the schemas, and the examples.

Treat `1.0-draft` envelopes as pre-release: suitable for evaluation and reference
implementations, not yet a frozen target for production guarantees.

---

## Purpose

ZTIP defines how governed transactions between agents — and between agents, humans, and systems
— must be structured so that every interaction is authorized, verifiable, and auditable.

The core problem ZTIP addresses: in modern multi-agent AI systems, one agent invokes another
with a plain function call or message. No policy is evaluated. No authorization is recorded.
No verifiable receipt is produced. The interaction happens, and nothing proves what was
requested, what was permitted, or what occurred.

This is ambient authority. It is incompatible with organizational governance.

ZTIP solves this by defining a structured transaction model in which:

- every request is captured in a formal envelope before any action is taken,
- every envelope is submitted to a control plane for policy evaluation,
- every authorization decision is recorded as part of the transaction,
- every result is returned as a linked receipt that can be verified against the original request,
- and the complete record is tamper-detectable via cryptographic hashes.

ZTIP is transport-agnostic. A ZTIP envelope may move by API, file, message queue, GitHub PR,
chat message, workflow engine, email, or any other channel. ZTIP governs the transaction
object, not the delivery mechanism.

**Freedom for engineers. Governance for the organization.**

---

## Non-Goals

ZTIP does not define:

- **Transport protocols.** How envelopes move between actors is out of scope. ZTIP defines
  what must be in the envelope, not how it is delivered.
- **Model selection.** ZTIP does not govern which AI models agents use or how they generate
  outputs.
- **Tool implementation.** ZTIP does not define how agent tools work internally. It governs
  transactions between actors, not the internals of any actor.
- **User interfaces.** How operators interact with the control plane, review approvals, or
  browse audit logs is implementation-specific.
- **Vendor-specific APIs.** ZTIP defines a conceptual control plane contract. Specific API
  endpoints, SDKs, and service configurations are outside the protocol scope.
- **Encryption.** ZTIP v1 requires hash-based integrity, not encryption. Encryption may be
  layered on top for specific deployment contexts but is not a protocol requirement.
- **Cross-organizational federation.** Initial scope is single-organization deployment. See
  the Next Steps section for future direction.

---

## The Trust Boundary

**ZTIP does not secure the pipe. ZTIP governs the action.**

ZTIP governance is not enforced by transport. An envelope that travels over a secure channel,
an authenticated API, an encrypted tunnel, or a trusted network is not a governed transaction
by virtue of its delivery method. Transport security and transaction governance are orthogonal.

ZTIP governance is enforced at the point of action. A target actor must refuse to perform
work unless it holds a valid, verifiable ZTIP authorization record for that specific action.
The authorization record — issued by the control plane — is what makes a transaction governed.
The transport is irrelevant.

This means:

- An ungoverned message may exist. It cannot become accepted, authorized, governed work inside
  a ZTIP-compliant environment unless it passes through the control plane's evaluation and
  produces a valid authorization record.
- A compliant target actor does not execute instructions delivered without a valid ZTIP
  authorization record, regardless of how those instructions arrived or who sent them.
- A compliant control plane does not issue authorizations without evaluating policy, regardless
  of how well-trusted the source actor appears to be.
- A compliant runtime does not escalate its own authority. The governance layer and the
  execution layer are permanently separate. The entity that governs does not execute. The
  entity that executes does not self-authorize.

The trust boundary is not defined by the network perimeter. It is defined by the authorization
record. This is the foundational principle from which ZTIP's entire governance model derives.

---

## Core Concepts

### ZTIP Transaction

The full governed unit of work. A transaction begins when a source actor creates a request and
ends when a final receipt is produced — whether the outcome is success, failure, rejection, or
cancellation.

A transaction is not a single message. It is a lifecycle. Multiple envelopes and receipts may
be associated with a single transaction as it moves through its states.

### ZTIP Envelope

The serialized JSON object that carries a transaction event. An envelope captures a point-in-time
state of a transaction: the original request, an authorization decision, an evidence submission,
an amendment event, or a final result.

Submitted envelopes are immutable. Once a transaction envelope has been submitted to the control
plane, it cannot be modified. Subsequent events — results, evidence, approvals — are separate
linked envelopes, not modifications to the original.

### ZTIP Receipt

The result envelope produced after a transaction reaches a terminal or intermediate state.
A receipt references the original transaction and the original request envelope by hash, links
the outcome to the request, and provides the information needed to verify that the result
corresponds to the authorized action.

Receipts are produced for all terminal outcomes: success, failure, rejection, cancellation,
and expiry.

### ZTIP Control Plane

The authority layer responsible for evaluating policy, recording authorization decisions, and
governing whether transactions may proceed. The control plane is the single authoritative
source for whether a given transaction is permitted under organizational policy.

The control plane is not defined by ZTIP as a specific product. ZTIP defines the conceptual
contract the control plane must satisfy. ZTI Core is one compliant implementation of this
contract.

### Actor

Any entity that participates in a ZTIP transaction — source, target, approver, or auditor.
Actors may be AI agents, automated systems, or humans. All actors must be identifiable to the
control plane.

### Role

A protocol-level classification of the function an actor performs within a transaction.
Roles are defined by ZTIP and are not implementation-specific. An actor may hold more than
one role depending on context.

Defined roles are listed in the Roles and Capabilities section.

### Capability

A declared ability that an actor can perform and that a transaction may request. Capabilities
are not roles. A role describes what function an actor serves in the governance model; a
capability describes what that actor can do.

Example: an actor with the role `executor` may hold capabilities such as `deploy_service`,
`run_query`, or `send_message`. These are distinct claims. A transaction requesting
`deploy_service` from an actor that does not hold that capability must be rejected.

### Evidence

Supporting material that accompanies a transaction to satisfy policy requirements. Evidence
may include test results, approval records, prior transaction receipts, compliance attestations,
or any other structured data the control plane requires before authorizing a transaction.

Evidence envelopes are linked to the transaction by hash.

---

## Transaction Lifecycle

A ZTIP transaction progresses through a defined set of states. Not all states are reached in
every transaction — a rejected transaction does not enter `executing`, and a cancelled
transaction may be cancelled from multiple earlier states.

### States

**`created`**
The transaction envelope has been constructed by the source actor. It has not yet been
submitted to the control plane. At this point the envelope exists only in the source actor's
context.

**`submitted`**
The envelope has been delivered to the control plane. The control plane has acknowledged
receipt. The transaction is now in the governance layer.

**`evaluated`**
The control plane has completed its evaluation of the transaction. Evaluation includes:
schema validity, actor identity and registration, role validity, capability claims, policy
compliance, and integrity requirements. The control plane has not yet issued a final
authorization decision.

**`authorized`**
The control plane has determined that the transaction is permitted to proceed. An authorization
record has been appended to the transaction. The target actor has not yet been notified or
agreed to act.

*Authorization means governance permitted it. It does not mean the target actor has agreed.*

**`rejected`**
The control plane determined that the transaction does not meet policy requirements. A rejection
receipt is produced with a structured reason code. Rejection occurs before any execution
attempt. No action is taken on the target system.

**`accepted`**
The target actor has received the authorized transaction envelope and agreed to perform the
requested work. This is a distinct state from `authorized`.

*Acceptance means the target actor agreed to act. It does not mean execution has begun.*

**`executing`**
The target actor is actively performing the requested work.

**`verifying`**
The result of execution is being checked against verification requirements defined in the
transaction or by policy. Verification must be performed by an authority independent of the
target actor: the control plane, a designated validator actor, or deterministic re-execution
of the declared checks. The target actor's own report of its results is attestation, not
verification. See the Completion Verification section.

**`succeeded`**
The transaction completed, and verification passed. A success receipt is produced and linked
to the original transaction.

**`failed`**
The transaction failed. Failure may occur during evaluation, authorization, execution,
or verification. A failure receipt is produced with a structured reason code. See the Failure Model and Reason Codes section
for defined reason categories.

**`cancelled`**
An operator or the control plane cancelled the transaction before it reached a terminal state.
Cancellation may occur from `created`, `submitted`, `evaluated`, `authorized`, or `accepted`.
A cancellation receipt is produced.

**`expired`**
The transaction's validity window elapsed before it reached `accepted` or a terminal state.
An expiry receipt is produced. Expiry is a form of failure and follows fail-closed behavior.

### State Transitions

```
created
  └─► submitted
        └─► evaluated
              ├─► authorized
              │     ├─► accepted
              │     │     └─► executing
              │     │           └─► verifying
              │     │                 ├─► succeeded
              │     │                 └─► failed
              │     └─► expired (before acceptance)
              ├─► rejected
              └─► failed (evaluation failure)

[from created, submitted, evaluated, authorized, accepted]
  └─► cancelled

[from submitted, evaluated, authorized, accepted]
  └─► expired
```

### Transition Rules

- A transaction may not advance to `authorized` without passing `evaluated`.
- A transaction may not advance to `executing` without reaching `accepted`.
- A transaction may not advance to `verifying` without completing `executing`.
- `rejected` and `failed` are terminal states. A new transaction must be created to retry.
- `cancelled` is terminal. The original transaction cannot be resumed.
- `expired` is terminal. Expiry is equivalent to failure for audit purposes.
- All terminal states must produce a receipt.

---

## Authorization Model

Authorization is determined by the control plane based on organizational policy. ZTIP does not
define authorization outcomes based on transaction type, actor identity, or any other attribute
directly. Policy governs.

### Authorization Outcomes

**`auto_authorized`**
The control plane determined that the transaction is within policy and authorized it to proceed
without human review. No human approval was required or requested.

**`human_approval_required`**
Policy requires a named individual or role to approve the transaction before it may proceed.
The transaction enters a waiting state. The control plane records the approval request, the
approver identity, and the approval timestamp when the approval is received. The transaction
does not advance until approval is granted.

**`evidence_required`**
Policy requires additional evidence before a decision can be made. The control plane specifies
what evidence is needed. The source actor or a delegated actor must submit a linked evidence
envelope. The transaction does not advance until sufficient evidence is received and evaluated.

**`rejected`**
Policy denies the transaction. The transaction moves to the `rejected` terminal state. A
structured reason code is recorded.

**`expired`**
The transaction's validity window elapsed before a decision was reached. The transaction moves
to the `expired` terminal state.

### Human-in-the-Loop

ZTIP supports human-in-the-loop approval as a policy-conditional outcome. Human approval is
not required for every transaction. Whether a transaction requires human approval, may be
auto-authorized, or must be rejected is determined entirely by organizational policy.

When human approval is required, ZTIP requires that:
- the approval request be recorded in the transaction,
- the approver identity be recorded,
- the approval timestamp be recorded, and
- the approval record be hash-linked to the transaction envelope.

An approval that is not recorded in the transaction is not a ZTIP-compliant approval.

Approvals are action-specific and single-use. An approval issued for one transaction may not
be applied to a different transaction. An authorization record that was consumed to advance a
prior transaction must not be replayed. An expired authorization record is invalid regardless
of whether the original approval was genuine. See `APPROVAL_REPLAYED` in the reason code
registry.

When an approval is received and recorded, the control plane issues a new authorization
decision envelope with `authorization_status: "human_approved"` — a distinct status that
makes human involvement machine-detectable. It does not reuse the `auto_authorized` status.
See `SCHEMA.md` for the full field definition.

### Break-Glass Access

Emergency or exceptional access pathways — commonly called "break-glass" — are governed
pathways with elevated evidence requirements, not authorization bypasses.

**Break-glass has more required evidence than standard authorization, not less.**

A ZTIP-compliant break-glass transaction must carry — at minimum — structured evidence
establishing:

- **Incident or ticket reference** — a stable identifier for the incident or event requiring
  emergency access.
- **Named approver** — the identity of the operator authorizing the break-glass action.
- **Reason code** — the specific reason emergency access is required.
- **Expiration** — a strict, short expiration timestamp after which the break-glass
  authorization is invalid. There is no indefinite emergency authorization.
- **Compensating controls** — what governance safeguards are in place during the period of
  emergency access.
- **Post-incident review reference** — a commitment to review and audit the break-glass
  action after the incident is resolved.

An expired or incomplete break-glass authorization is invalid and must fail closed. A
break-glass action that bypasses authorization is not a legitimate break-glass — it is an
unauthorized action, and must be treated as such in the audit trail.

ZTIP v1 does not define a dedicated break-glass envelope type. Break-glass transactions use
the existing authorization and evidence model, with policy requirements specifying the
evidence fields described above. This principle is normative; the schema implementation is
in progress.

---

## Identity and Actor Registration

All actors that participate in ZTIP transactions must be identifiable to the control plane.
ZTIP defines the identity *claims* that actors must be able to make; it does not mandate the
authentication mechanism used to verify those claims.

Compliant identity mechanisms may include, but are not limited to:
- API key with control plane registration
- Signed JWT (JSON Web Token)
- Mutual TLS (mTLS)
- Local registry identity
- Enterprise SSO delegation
- Platform-native identity (e.g., GitHub identity, cloud IAM role)

ZTIP requires that an actor's identity record include, at minimum, the conceptual equivalents of:

- **Actor identifier** — a stable, unique reference for this actor within the organization's
  control plane. Not necessarily a human-readable name.
- **Role or roles** — the protocol roles this actor is registered to perform.
- **Capability claims** — the specific capabilities this actor is authorized to exercise.
- **Organization or tenant context** — which organization this actor belongs to.
- **Registration status** — whether this actor is currently active and authorized to participate
  in transactions.

Exact field names are to be determined during schema specification.

### Tools Are Not Roles

A tool is a capability an actor can exercise. A role describes the actor's function within
the governance model.

An executor that can run a deployment tool holds the `executor` role and the `deploy_service`
capability. These are distinct claims and must be registered separately. Policy may authorize
a role without authorizing every capability that role may hold, and vice versa.

An actor's `implementation_ref` — the underlying tool, model, or system it is built on —
is metadata for audit readability and debugging. It is not a role. It carries no governance
authority. The control plane evaluates the registered role and capability claims, not the
implementation identity. See the normative rule in Roles and Capabilities.

### Unregistered Actors

A transaction submitted by an unregistered actor, or requesting action from an unregistered
target, must be rejected with reason code `ACTOR_UNREGISTERED`. ZTIP is fail-closed. An
unknown actor is not a trusted actor.

---

## Control Plane Contract

The ZTIP control plane must support the following logical operations. This section defines the
conceptual contract, not HTTP endpoints or API signatures. Those are implementation details.

### 1. Submit Transaction

Accept a transaction envelope from a source actor. Acknowledge receipt and assign the
transaction to the `submitted` state. Return a stable transaction reference.

Pre-conditions: the submitting actor must be identifiable. The envelope must be structurally
well-formed enough to process. Full schema and policy evaluation happens during evaluate.

### 2. Evaluate Transaction

Evaluate the submitted transaction against:
- schema validity
- actor identity and registration
- role authorization
- capability claims
- organizational policy
- evidence requirements
- integrity hash validity

Produce an evaluation record. Advance the transaction to `evaluated` or `failed`.

### 3. Authorize, Reject, or Request Evidence

Based on evaluation, the control plane must produce one of the defined authorization outcomes:
`auto_authorized`, `human_approval_required`, `evidence_required`, or `rejected`.

The decision must be recorded as a linked record on the transaction. The decision record must
include the outcome, the policy basis for the outcome, and a timestamp.

### 4. Record Decision

Every authorization decision — including rejections and evidence requests — must be durably
recorded in the control plane's audit log. Decisions are append-only. A decision record cannot
be modified after it is written.

### 5. Deliver Authorized Transaction

Once authorized, the control plane must deliver or make available the authorized transaction
envelope to the target actor. The delivery mechanism is transport-specific and out of scope.
The envelope delivered must include the authorization record appended by the control plane.

### 6. Receive Receipt

Accept a receipt envelope from the target actor or validator. The receipt must reference the
original transaction by its stable identifier and by the hash of the original request envelope.

### 7. Verify Receipt

Confirm that the receipt corresponds to the authorized transaction:
- the transaction identifier matches,
- the request hash in the receipt matches the original envelope hash,
- the receipt is structurally valid,
- every required verification check has been independently satisfied — by the control plane,
  a designated validator, or deterministic re-execution of the declared checks — not merely
  attested by the executor. See the Completion Verification section.

Verification may be performed by the control plane, a validator actor, or both, as defined by
policy. It must not be performed solely by the target actor that executed the action.

### 8. Retain Audit Trail

Every transaction, every envelope, every decision record, every receipt, and every evidence
envelope must be retained in the audit log. The audit trail is append-only. Entries must be
hash-linked to support tamper detection.

The audit trail is the authoritative record of what happened. It must be queryable by
transaction identifier, actor, time range, and outcome.

The hash chain makes tampering detectable: each stored record's hash references the prior
record. A gap or mismatch in the chain is evidence of inconsistency. A compliant control
plane must provide a mechanism for auditors to walk the hash chain and verify completeness.

### 9. Verify Registry Consistency

A compliant control plane must be able to verify the internal consistency of its own
registries before issuing authorization decisions. The registries in scope include:

- **Actor registry** — registered actors, their roles, and their capability claims.
- **Capability registry** — defined capabilities and their policy associations.
- **Policy registry** — active authorization policies and their scope.
- **Transaction registry** — the audit log of submitted transactions and their states.

A control plane that cannot verify its own registry consistency must not issue authorization
decisions. Registry inconsistency is a fail-closed condition. The reason code for this
failure mode is `REGISTRY_INCONSISTENT`.

**The governing principle:** an authorization decision issued against an inconsistent registry
cannot be verified. If the actor registry and the policy registry disagree about what an
actor is permitted to do, the resulting authorization decision is indeterminate. An
indeterminate authorization is not a governed authorization.

**The practical implication:** a control plane must detect registry inconsistency before it
matters — at startup, after configuration changes, and at any point where inconsistency would
affect the validity of an authorization decision about to be issued.

---

## Completion Verification

**An executor's claim of success is attestation. It is not verification.**

A transaction is not complete because the actor that performed the work says it is complete.
It is complete when the verification requirements declared in the request have passed under
an authority independent of that actor. The boundary between claimed completion and verified
completion is where the protocol's guarantees live.

### Verification Is Declared Before Execution

Verification requirements are declared in the transaction request, before any action is
taken. The `verification_requirements` of the envelope state what checks must pass for the
outcome to count as success. See `SCHEMA.md` for the full field definition. Criteria invented
after execution are not verification requirements; the envelope hash binds the checks that
count to the request that was authorized.

### The Independence Requirement

Verification must be performed by an authority independent of the target actor that executed
the action:

- the control plane,
- a designated `validator` actor, or
- deterministic re-execution of the declared checks.

The executor's own report of its results is attestation, not verification. Attestation is
input to verification — evidence to be checked, never the check itself. Attestation alone
must never satisfy a required verification check.

*The entity that executes does not verify its own work. This is the same separation that
forbids self-authorization, applied to completion.*

### Fail-Closed Acceptance

A receipt claiming `succeeded` is accepted as `succeeded` only when every required
verification check has passed under independent verification. The failure modes are
distinct and carry distinct reason codes:

- A required check that was independently executed and did not pass resolves the
  transaction `failed` with reason code `VERIFY_FAILED`.
- A required check that was never independently verified — satisfied only by executor
  attestation — resolves the transaction `failed` with reason code `COMPLETION_UNVERIFIED`.
- If required verification cannot be executed at all — the verifier is unavailable, the
  checks cannot run — the transaction must not resolve `succeeded`. It resolves `failed`
  with reason code `VERIFY_UNAVAILABLE`. An unverifiable success is not a success.

This is fail-closed behavior. There is no partial credit for checks that were merely
attested.

### Recorded Results

The `verification_results` recorded in the receipt carry the per-check outcomes, and should
identify the verifying authority through the `verification_actor` field defined in
`SCHEMA.md`. The receipt binds these results under the envelope hash: the record of what was
verified, and how it resolved, is as tamper-evident as the request it verifies.

Identifying the authority is a producer obligation. Envelope integrity verification does not
check it — a verifier cannot tell whether a named actor really performed the check — and the
schema does not require it. Treat its absence as a gap in the audit record, not as a
verification failure.

**A receipt with status `succeeded` must record at least one verification result.** A
success that recorded no result asserts a completion that nothing checked, and is not a
valid ZTIP receipt. Each recorded result must identify the check it reports — its
`check_id` and `check_type` — and whether it passed. Receipts in a non-succeeded terminal
state may legitimately carry no results, because execution may never have reached
verification; that case is honest and remains valid.

Recording results is a floor, not the whole of the requirement. Whether the results
correspond to the checks the request declared — every entry in `verification_requirements`
answered by a result carrying the same `check_id` — is settled by the control plane under
the Fail-Closed Acceptance rules above, not by envelope integrity verification.

### Determinism

Verification must be deterministic and reproducible: the same checks, evaluated against the
same state, must produce the same result. A verification that cannot be re-run has no
evidentiary weight.

**The governing principle:** an unverified success claim is indistinguishable from a failure
that reports itself as a success. If the only evidence of completion is the word of the actor
whose work is being judged, the record proves nothing.

**The practical implication:** a control plane must not record `succeeded` on the strength of
executor-supplied results alone. It must confirm — itself, through a validator, or by
re-running the declared checks — that every required check passed, before the success receipt
is accepted into the audit trail.

*Non-normative rationale:* autonomous agents reporting success for work that did not succeed,
or did not occur, is a documented failure mode of agent systems — not a hypothetical. ZTIP's
answer is structural rather than behavioral: the protocol does not ask executors to be more
honest. It removes the executor's claim from the position of settling the question.

---

## Integrity and Hashing

ZTIP v1 requires hash-based integrity verification. Encryption is not required by the initial
protocol specification and may be added as an optional layer in future versions or specific
deployment contexts.

### Principles

**The original envelope must be hashable.** A submitted transaction envelope must produce a
stable, deterministic hash. This hash serves as the canonical reference for the original
request throughout the transaction lifecycle.

**Receipts must reference the original request hash.** Any receipt produced in relation to a
transaction must include the hash of the original request envelope. This binds the result to
the request and makes it verifiable.

**Evidence must be hash-linked.** Evidence envelopes must include the hash of the transaction
they support. The transaction record must include the hashes of any evidence envelopes
submitted.

**Tampering must be detectable.** Any modification to a submitted envelope — any field, any
value — must produce a different hash, invalidating the hash reference chain.

### What Hash Verification Answers

- Is this the original envelope, or has it been altered?
- Does this receipt correspond to the request I submitted?
- Does the evidence correspond to the transaction it claims to support?
- Has the audit log been tampered with?

### What Hash Verification Does Not Answer

The integrity hash is computed from the envelope's own content, so anyone holding the
envelope can recompute it. That makes intactness checkable by everyone, and it means hash
verification is silent on three separate questions:

- **Authenticity.** An intact envelope is self-consistent. It is not evidence that a trusted
  party produced it. Binding an envelope to an identity requires a signature or an
  independent attestation, which ZTIP v1 does not mandate.
- **Whether a check actually ran.** Integrity binds the results a receipt records; it cannot
  establish that the recorded results came from executing the declared checks. That
  separation is the Completion Verification section's subject.
- **Whether the record is complete.** A bundle that verifies intact may still be missing
  envelopes. See Bundle Verification below.

A conformant implementation must not present hash verification as more than this. Reporting
"verified" over content whose scope was not checked is the failure mode these rules exist to
prevent.

### Bundle Verification

A *bundle* is a set of ZTIP envelopes verified together — the envelopes of one transaction,
an audit-trail export, or an evidence package. An implementation that verifies a bundle must
apply the following rules, each of which fails closed:

- **A wrapper carries envelopes; it is not one.** An object that declares any ZTIP envelope
  field — `ztap_version`, `envelope_type`, `transaction_id`, or `integrity` — is one envelope,
  even when it also carries an `envelopes` key, and it is verified as such. Reading it as a
  wrapper instead would leave the envelope itself unverified while the reported count described
  its payload. An object declaring none of those fields, and carrying an `envelopes` array, is
  a wrapper.
- **An empty bundle is not a verified bundle.** Verification over zero envelopes must not
  report success. An implementation must report how many envelopes it verified, so that a
  caller — human or automated — can never read "nothing to verify" as "everything verified".
- **References must resolve.** A `request_hash` that names a transaction request not present
  in the bundle leaves the linkage unverified, and must be reported as such. An
  implementation may offer an explicit mode for verifying a deliberately partial bundle; in
  that mode it must state that chain linkage was not verified.
- **One transaction request per transaction.** A bundle carrying more than one
  `transaction_request` for a single `transaction_id` has an ambiguous request history: a
  second request can shadow the first while every hash still checks out. This is invalid
  regardless of which request the receipts reference.
- **Envelopes must be ZTIP envelopes.** Content that does not satisfy the envelope contract —
  a protocol version the verifier supports, a known `envelope_type`, a `transaction_id`, an
  `integrity` object declaring the canonicalization and hash algorithm it was sealed under,
  and the fields that envelope type requires — is not verifiable ZTIP content, and a
  self-computed hash over it must not be reported as a verified envelope. Value-level
  conformance beyond that contract (identifier formats, role vocabularies, reason-code
  namespacing) is schema validation, and a verifier that does not perform it must not imply
  that it did.
- **Verify under the rules the envelope declares.** An envelope declaring a canonicalization
  or hash algorithm the verifier does not apply must be reported, not silently verified under
  the verifier's own default. Otherwise the report describes a computation nobody performed.
- **References resolve by transaction.** A `request_hash` is resolved against the
  `transaction_request` carrying the same `transaction_id`, and must equal that request's
  hash. Resolving by hash value alone would let a receipt bind itself to a different
  transaction's request.
- **Every binding site is resolved, not only the top-level field.** An authorization
  decision's `human_approval_ref.approval_scope` carries its own `transaction_id` and
  `request_hash`, and that pair is what binds a human approval to the work it approved. It is
  resolved under the same rule. Leaving it unchecked is how an approval for one transaction
  gets attached to another while every hash still verifies.
- **One transaction, one outcome.** A transaction may carry several envelopes and several
  receipts, but receipts reporting different terminal states for one `transaction_id` are
  contradictory: a reader would have to guess which one settles the transaction.
- **A success must not contradict its own record.** A `succeeded` receipt whose every recorded
  check reports failure is internally inconsistent, regardless of which checks were required.
- **A recorded result must be covered by the seal.** Non-normative annotation fields are
  excluded from the envelope hash, so a verification result stored under an annotation key is
  not bound by it: the same hash describes the receipt with the result and without it. Such a
  result does not count as recorded.
- **A recorded result is structured wherever it appears.** Any envelope recording
  `verification_results` records structured results — each naming the check and its outcome —
  not free text. The requirement that results be *present* applies to `succeeded` receipts;
  the requirement that they be *meaningful* applies wherever they are recorded.
- **Report what was counted, not what was submitted.** An implementation reporting a count
  states how many envelopes it verified and how many references it resolved. Zero resolved
  references is not a verified chain.
- **Content beside the envelopes is not verified.** A bundle wrapper may carry metadata — an
  export identifier, a timestamp — beside its envelopes. That content is outside every
  envelope hash, so an implementation must report it alongside its result. This is a
  disclosure duty, not grounds for refusal: an export wrapper legitimately carries metadata,
  and refusing it would push integrators to stop verifying exports.
- **The document must be unambiguous.** A JSON object that declares the same member name twice
  means different things to different parsers while every hash still checks out. An integrity
  model built on a canonical hash cannot accept that; such a document is not verifiable.

### Algorithm

ZTIP v1 uses SHA-256 as the hash algorithm and **RFC 8785 (JSON Canonicalization Scheme)**
as the canonicalization rule. This is finalized, not provisional. The integrity hash is
computed over the RFC 8785 canonical form of the envelope with the `integrity.hash_value`
field excluded and with non-normative annotation fields — keys beginning with an
underscore — removed. See `SCHEMA.md` (Integrity Object and Hashing) for the full hash
construction rules.

*Informative:* the repository's reference runtime — the `ztip/` package, with the
`ztip hash` and `ztip verify` CLI commands — implements this canonicalization and hashing
end-to-end.

Canonicalization must be deterministic: the same logical envelope must always produce the
same hash, regardless of how it was serialized or by whom.

---

## Immutability and Amendments

### The Immutability Rule

**Submitted transaction envelopes are immutable.**

Once a transaction envelope has been submitted to the control plane and assigned a transaction
identifier, the original envelope must not be modified. Its content is the canonical record of
what was requested.

This is not a technical limitation — it is a governance requirement. The integrity of the
audit trail depends on the original request being unalterable.

### Handling Changes

If the original request must change after submission, the correct actions are:

1. **Cancel the original transaction** and create a new one, or
2. **Create a linked amendment event** — a separate envelope that references the original
   transaction and records what changed, why, and under what authority.

Amendment events are themselves ZTIP envelopes. They are subject to the same governance model
as original transactions. An amendment that was not authorized by the control plane is not a
valid amendment.

### Linked Records

All subsequent events in a transaction's lifecycle — authorization decisions, evidence
submissions, approvals, amendment events, and receipts — are separate envelopes that reference
the original by transaction identifier and request hash. They do not modify the original.

The full transaction history is the ordered set of all linked envelopes, not a single mutable
record.

---

## Failure Model and Reason Codes

### Fail-Closed Is a Protocol Invariant

**Fail-closed is not a default setting. It is a protocol invariant.**

When a transaction cannot be completed — for any reason — the outcome is rejection or failure,
not continuation. There is no permissive fallback mode. Ambiguity resolves to denial, not
to permission.

A compliant actor, control plane, or implementation must reject a transaction under any of
the following conditions, without exception:

- **Invalid schema.** The envelope does not conform to the required ZTIP structure.
- **Unknown actor.** The submitting or target actor is not registered with the control plane.
- **Invalid role.** The actor's claimed role is not a recognized ZTIP protocol role.
- **Missing authority.** Required authority or delegation is absent from the envelope.
- **Missing capability.** The target actor does not hold the requested capability in its
  registered capability claims.
- **Integrity mismatch.** A hash check fails on any envelope in the transaction chain.
- **Expired transaction.** The transaction's validity window has elapsed.
- **Inconsistent registry.** The control plane cannot verify the internal consistency of its
  actor, capability, policy, or transaction registry.
- **Unsupported version.** The envelope carries a `ztap_version` the implementation does not
  support and has not been explicitly configured to accept.

In no circumstance may an implementation proceed when one of these conditions is true. There
is no "trusted internal path," no "known good actor" shortcut, and no administrative mode
that bypasses the fail-closed rule. Break-glass access is governed access with elevated
evidence requirements — it is not an authorization bypass. See the Break-Glass section in the
Authorization Model for the governing principle.

### Failure Receipts

Every failure must produce a structured receipt containing:
- the transaction identifier,
- the state at which failure occurred,
- a reason code from the defined set,
- a timestamp, and
- a hash of the original request envelope (where available).

Failure without a receipt is not ZTIP-compliant.

### Draft Reason Code Categories

The following are initial reason code categories. The authoritative registry — final codes,
categories, and extension rules — is the Core Reason Code Registry in `SCHEMA.md`.

| Reason Code | Category | Description |
|---|---|---|
| `SCHEMA_INVALID` | Structural | The envelope does not conform to the required schema. |
| `ROLE_INVALID` | Identity | The requesting actor does not hold a valid ZTIP role. |
| `ACTOR_UNREGISTERED` | Identity | The actor is not registered with the control plane. |
| `AUTHORITY_MISSING` | Authorization | Required authority or delegation is absent. |
| `POLICY_DENIED` | Policy | The control plane policy explicitly denies this transaction. |
| `CAPABILITY_MISSING` | Capability | The target actor does not hold the requested capability. |
| `TARGET_REJECTED` | Acceptance | The target actor declined to accept the authorized transaction. |
| `ACTION_FAILED` | Execution | The target actor attempted the action and it failed. |
| `VERIFY_FAILED` | Verification | The result did not pass verification requirements. |
| `COMPLETION_UNVERIFIED` | Verification | A required verification check was satisfied only by executor attestation and was never independently verified. Checks that run independently and fail resolve as `VERIFY_FAILED`. |
| `VERIFY_UNAVAILABLE` | Verification | Required verification could not be executed. The transaction must not resolve as succeeded. |
| `TIMEOUT` | Temporal | A required step was not completed within the allowed time window. |
| `EXPIRED` | Temporal | The transaction's validity window elapsed. |
| `CANCELLED` | Control | The transaction was explicitly cancelled by an authorized actor. |
| `INTEGRITY_FAILED` | Integrity | A hash check failed; the envelope or receipt may have been tampered with. |
| `EVIDENCE_MISSING` | Policy | Required evidence was not submitted within the required window. |
| `PARTIAL_STATE_BLOCKED` | Atomicity | The transaction reached a partial execution state and atomicity requirements prevented continuation. |

---

## Atomicity Model

### The Problem

Not all real-world operations are reversible. A deployment may succeed on three of four
services before failing on the fourth. A message may be sent before a downstream step fails.
ZTIP must handle partial execution states without assuming that rollback is always possible.

### Declared Atomicity Modes

Every ZTIP transaction must declare — or be evaluated against a policy that specifies — one
of the following atomicity modes:

**`atomic_required`** *(default)*
The transaction must either complete fully or not at all. If partial execution occurs and
rollback is not possible, the transaction must be failed with reason code
`PARTIAL_STATE_BLOCKED`. The failure receipt must record what partial state was reached.

**`best_effort_allowed`**
Partial completion is permitted if the source actor explicitly declares this mode and the
control plane policy permits it. The receipt must accurately record which steps succeeded and
which failed.

**`non_atomic_explicitly_allowed`**
Non-atomic execution is permitted. This mode must be explicitly authorized in the transaction
envelope and confirmed by the control plane. The receipt must record the actual execution
outcome in full, including any partial state.

### Default Behavior

The default atomicity mode is `atomic_required`. A transaction that does not declare an
atomicity mode is treated as `atomic_required`.

If an executor cannot guarantee atomicity and the transaction mode is `atomic_required`, the
transaction must fail closed with `PARTIAL_STATE_BLOCKED`. The executor must not proceed.

Non-atomic execution must be:
- explicitly declared in the transaction envelope,
- authorized by the control plane,
- and fully reflected in the receipt.

It is never the default. It is never inferred.

---

## Governance-Class Transactions

### Operational vs. Governance Transactions

Not all transactions carry the same governance risk. ZTIP distinguishes between two classes:

**Operational transactions** request ordinary work against systems, services, data, or
infrastructure. Deploying a service, running a query, sending a notification, archiving a
record. These are the standard transaction type described throughout this specification.

**Governance transactions** request modifications to the governance layer itself. Registering
a new actor, revoking a capability grant, modifying an authorization policy, changing approval
requirements, updating control plane configuration, or altering the audit trail structure.

### Why the Distinction Matters

A governance transaction can change the rules under which future operational transactions
are evaluated. A transaction that modifies who is permitted to do what must be held to a
stricter standard than the operational work it enables.

If an executor can register itself with new capabilities via an auto-authorized transaction,
the governance model has a fundamental gap. The authorization rules for governance-class
transactions must be stricter — not equal to or more permissive than — the authorization
rules for operational transactions.

### ZTIP v1 Guidance

ZTIP v1 does not define a separate envelope type for governance transactions. Governance
transactions use the same envelope structure as operational transactions. They are
distinguished by:

- the capabilities they request (capabilities that modify registry or policy state),
- the elevated evidence requirements the control plane applies to them, and
- the authorization approval level organizational policy assigns to them.

A compliant control plane should define policy that ensures governance-class transactions:

- require explicit operator approval, regardless of other auto-authorization rules,
- carry structured evidence of the change being requested and its policy justification,
- produce receipts that record the specific change made, the prior state, and the new state,
- and are clearly labeled as governance-class actions in the audit trail.

This is policy guidance for v1, not a schema requirement. It is included because
implementations that treat governance transactions identically to operational transactions
have an incomplete governance posture.

---

## Roles and Capabilities

### Normative Rule: Roles Are Governance Classifications, Not Implementation Labels

**This is a binding protocol rule.**

A role answers: *what governance function does this actor perform?*
An `implementation_ref` answers: *what tool, model, or system is this actor built on?*

These are separate claims and must never be conflated. Tool names, model names, vendor
product names, SaaS platform names, and runtime identifiers must not appear as `role` values.

**Valid role declarations:**

```
role: "executor",   implementation_ref: "custom-deploy-agent-v3"
role: "planner",    implementation_ref: "llm-gateway-local"
role: "validator",  implementation_ref: "test-runner-ci"
```

**Invalid role declarations:**

```
role: "codex"           // tool name is not a protocol role
role: "claude"          // model name is not a protocol role
role: "github-actions"  // platform name is not a protocol role
role: "gpt-4o"          // model identifier is not a protocol role
```

A control plane must reject any transaction envelope where an actor's `role` field contains a
value that is not a defined ZTIP protocol role. The reason code is `ROLE_INVALID`. There is
no pass-through mode for unrecognized role values.

Protocol roles must remain product-neutral so that ZTIP remains implementable by any
compliant control plane, regardless of which tools, models, or vendors actors use internally.

### Protocol Roles

The following roles are defined by the ZTIP protocol. They describe an actor's function in
the governance model — not their identity, implementation, or internal structure.

| Role | Description |
|---|---|
| `operator` | A human or human-delegated authority that configures policy, approves transactions when required, and manages the control plane. |
| `control_plane` | The ZTIP control plane instance. Evaluates policy, issues authorization records, records decisions, and retains the audit trail. |
| `source_actor` | The actor that initiates a transaction — creates the request envelope and submits it to the control plane. |
| `target_actor` | The actor that receives an authorized transaction, accepts it, and performs the requested work. |
| `planner` | An actor that produces structured plans or task decompositions, typically as input to executors. A planner does not execute. |
| `executor` | An actor that performs concrete actions against real systems. An executor does not plan independently. |
| `validator` | An actor that verifies results against defined criteria. A validator does not execute. |
| `auditor` | An actor with read-only access to the transaction log and receipts. Auditors do not participate in transaction execution. |
| `runtime` | An actor that provides execution infrastructure or environment. A runtime executes at the direction of executors. |

An actor may hold more than one role depending on registration and context. The control plane
enforces which roles an actor is permitted to perform in a given transaction.

### Role-to-Capability Binding

Roles do not automatically confer capabilities. An actor must be registered with both a role
and the specific capability claims that role permits them to exercise.

A transaction requesting capability `deploy_service` from an actor registered as `executor`
is valid only if that executor's registration includes `deploy_service` in its capability
claims. A capability not registered against an actor may not be invoked, regardless of role.

### Example Role Mapping

The following is an illustrative mapping, not a protocol requirement:

| Concrete Actor | ZTIP Role(s) |
|---|---|
| Human engineer / system owner | `operator` |
| Orchestration layer | `control_plane` |
| Planning agent | `planner`, `source_actor` |
| Execution agent | `executor`, `target_actor` |
| QA / test agent | `validator` |
| Infrastructure runtime | `runtime`, `target_actor` |

---

## Example Lifecycle Walkthrough

The following is a plain-language walkthrough of a ZTIP transaction for a production deployment
request. Field names are illustrative. This example assumes auto-authorization by policy —
no human approval is required.

---

**Step 1: Source actor creates the transaction envelope.**

A planning agent has determined that service `billing-api` should be deployed to the production
environment. It constructs a ZTIP transaction envelope containing:
- its own identity claim,
- the role it is acting in (`planner`, `source_actor`),
- the identity of the target actor (the executor registered for production deployments),
- the capability being requested (`deploy_service`),
- the request parameters (service name, environment, version),
- the declared atomicity mode (`atomic_required`),
- and a validity window (the transaction must be accepted within N minutes).

The planning agent computes a hash of the request payload and includes it in the envelope.

State: `created`

---

**Step 2: Source actor submits the envelope to the control plane.**

The planning agent delivers the envelope to the ZTIP control plane. The transport used (API
call, message queue, etc.) is irrelevant to the protocol.

The control plane acknowledges receipt and assigns a stable transaction identifier.

State: `submitted`

---

**Step 3: Control plane evaluates the transaction.**

The control plane checks:
- Is the planning agent registered? ✓
- Does it hold the `source_actor` role? ✓
- Is the target executor registered? ✓
- Does the executor hold the `deploy_service` capability? ✓
- Does the request hash match the payload? ✓
- Does policy permit this actor to request this capability against this target? ✓
- Is additional evidence required? (No, per policy for this service/environment combination.)

State: `evaluated`

---

**Step 4: Control plane authorizes the transaction.**

Policy determines this transaction may be auto-authorized. No human approval is required.

The control plane appends an authorization record to the transaction:
- outcome: `auto_authorized`
- policy reference that authorized it
- timestamp

State: `authorized`

---

**Step 5: Target actor receives and accepts the transaction.**

The authorized transaction envelope — now including the authorization record — is delivered
to the executor. The executor confirms:
- the envelope carries a valid authorization record from the control plane,
- the request hash matches the payload,
- the capability requested is in its registration,
- it is able to perform the work.

The executor accepts the transaction.

State: `accepted`

---

**Step 6: Executor performs the work.**

The executor deploys `billing-api` to production.

State: `executing`

---

**Step 7: Result is verified.**

The executor reports its results: the service is running, health checks pass, the version
matches. That report is attestation. A registered validator — acting independently of the
executor — evaluates the declared checks against the verification requirements specified in
the transaction and confirms the deployment succeeded.

State: `verifying`

---

**Step 8: Receipt is produced and returned.**

The executor produces a ZTIP receipt containing:
- the transaction identifier,
- the hash of the original request envelope,
- the execution outcome (success),
- verification result,
- timestamp,
- a hash of the receipt itself.

The receipt is submitted to the control plane, which verifies the request hash matches and
records the receipt in the audit trail.

State: `succeeded`

---

**Audit trail at conclusion:**

The control plane now holds a complete, hash-linked record of:
1. The original request envelope (immutable, hashed)
2. The evaluation record
3. The authorization record
4. The acceptance record
5. The execution receipt (hash-linked to the original request)

Any of these records can be independently verified. The chain of hashes makes tampering
detectable at any link.

---

## Open Questions

> **Traceability note:** The original pre-schema questions listed below have largely been
> addressed by operator decisions recorded in `SCHEMA.md` (see Next Steps for the items still
> open). They remain here for historical traceability until the schema is finalized and a
> changelog or decision log replaces them.

The following decisions required operator input before the ZTIP schema could be drafted:

1. **Validity window** — how is a transaction's validity window expressed? Is it a duration,
   an absolute timestamp, or both? Who sets it — the source actor, the control plane policy,
   or the transaction type?

2. **Receipt structure** — what is the minimum required content of a success receipt? A failure
   receipt? Are they the same structure with different fields populated, or separate envelope
   types?

3. **Evidence envelope structure** — what is the required structure for an evidence envelope?
   Is evidence typed (e.g., test results vs. compliance attestations), or is it treated as
   opaque structured data?

4. **Amendment events** — are amendment events a first-class envelope type with their own
   lifecycle, or are they a subtype of a general "linked event" structure?

5. **Cancellation authority** — who may cancel a transaction? Only the operator? The source
   actor? The control plane on behalf of a policy trigger? All of the above under different
   conditions?

6. **Target rejection** — when a target actor rejects an authorized transaction (reason code
   `TARGET_REJECTED`), is the source actor permitted to retry with a new transaction
   automatically, or does it require operator intervention?

7. **Partial state documentation** — when `PARTIAL_STATE_BLOCKED` occurs, what is the required
   structure of the failure receipt? What information must be recorded to support recovery or
   manual remediation?

8. **Multi-target transactions** — does ZTIP v1 support transactions that request actions from
   more than one target actor? Or is a ZTIP transaction strictly one source, one target?

9. **Canonical JSON and hash construction** — Resolved. RFC 8785 (JSON Canonicalization
   Scheme) with SHA-256 is the canonicalization and hash rule for ZTIP v1. Specified in
   `SCHEMA.md` (Integrity Object and Hashing) and implemented by the reference runtime
   (`ztip/` package, `ztip hash` / `ztip verify`).

10. **Control plane minimum conformance** — what is the minimum set of operations and behaviors
    a control plane must implement to be considered ZTIP-compliant? This is required before
    third-party control plane implementations can be evaluated.

---

## Next Steps

This document has established the doctrine, lifecycle, governance model, and core principles
that govern ZTIP. The logical sequence from here:

**Immediate: Resolve the remaining open questions.**
Most of the questions in the Open Questions section are resolved by decisions recorded in
`SCHEMA.md` — including question 1 (validity window), question 2 (receipt structure), and
question 9 (canonicalization: RFC 8785 JCS with SHA-256, implemented by the reference
runtime). The items still gating a confident v1 freeze are question 6 (retry/re-issue
semantics) and question 8 (multi-target actions).

**Delivered: `SCHEMA.md` and `schemas/`.**
The formal schema exists: `SCHEMA.md` defines field names, required vs. optional fields,
envelope types, versioning, and hash construction rules in prose, and the machine-readable
JSON Schema files live under `schemas/`.

**Delivered: `examples/`.**
Ten reference lifecycle bundles ship under `examples/`, covering the happy path, each failure
mode, and each authorization outcome, with real recomputable integrity hashes.

**Delivered: `WHITEPAPER.md`.**
The external-facing adoption document ships alongside this specification. It synthesizes the
problem, the solution, and the governance model for an executive or architect audience. It is
not a technical reference — it is the adoption document.

**Future: Cross-organizational federation.**
Multi-organization ZTIP interaction — where one organization's agents transact with another's,
each validated by their respective control planes — is explicitly deferred from v1 scope. It
is the logical extension of the single-organization model and should be addressed in a future
specification revision after v1 is stable.

---

> ZTIP Specification Draft — `1.0-draft`.
> Zero Trust Intelligence Protocol: the open protocol for governed agent transactions.
> **Freedom for engineers. Governance for the organization.**
