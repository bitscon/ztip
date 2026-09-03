<p align="center">
  <img src="docs/assets/ztip-banner.svg" alt="ZTIP — Zero Trust Intelligence Protocol. The open protocol for governed agent transactions. Code freedom, Verified." width="100%" />
</p>

<p align="center">
  <a href="https://github.com/bitscon/ztip/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/bitscon/ztip/validate.yml?branch=main&label=ci" alt="CI" /></a>
  <a href="https://pypi.org/project/ztip/"><img src="https://img.shields.io/pypi/v/ztip?color=f97316" alt="PyPI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-f97316" alt="License: MIT" /></a>
  <a href="SPEC.md"><img src="https://img.shields.io/badge/spec-1.0--draft-f97316" alt="Spec: 1.0-draft" /></a>
  <img src="https://img.shields.io/badge/status-pre--release-8e95a3" alt="Status: pre-release" />
</p>

# ZTIP — Zero Trust Intelligence Protocol

> Every agent handoff is a trust decision. ZTIP makes that decision provable.

**Freedom for engineers. Governance for the organization.**

---

## Try It (60 seconds)

```bash
git clone https://github.com/bitscon/ztip.git && cd ztip
pip install .                   # the reference runtime + CLI

ztip verify examples/01-auto-authorized-success.json
# OK  examples/01-auto-authorized-success.json: 3 envelope(s) verified — hashes
# recomputable, 2 request reference(s) resolved to the requests they name
#     note: the bundle also carries "_ztip_example" (annotation) beside its envelopes;
#     that content is not hashed and was not verified
#     scope: integrity and the envelope contract only — field values were not validated
#     against the schemas (scripts/validate-examples.py does that), a ZTIP hash is
#     recomputable by anyone so this is not proof of authenticity, and annotation fields
#     (keys beginning with _) are outside the hash by design

ztip hash examples/01-auto-authorized-success.json
# prints the RFC 8785 + SHA-256 envelope hashes
```

`pip install --pre ztip` installs the last published pre-release from PyPI. It is behind this
repository: the verification rules described below landed after it, so install from a clone to
follow along.

All ten lifecycle examples under `examples/` carry real, recomputable integrity
hashes — tamper with any hashed field and `ztip verify` fails closed. So does an
empty bundle, a reference to an envelope that is not there, and a receipt that
reports success without recording a single check: `verify` says how many envelopes
it verified and how many references it resolved, and never reports a pass over
nothing. What it does not do is judge field values against the full schema, or
prove who produced an envelope — it says so on every run, and
`scripts/validate-examples.py` is the schema check. Annotation fields (keys
beginning with `_`) sit outside the hash by design and are not covered. The protocol
summary is also published as an individual Internet-Draft,
[draft-mccormack-ztip](https://datatracker.ietf.org/doc/draft-mccormack-ztip/);
an Internet-Draft is a working document, not an IETF standard.

---

## What Is ZTIP?

ZTIP is an open protocol for governed agent transactions.

When one AI agent invokes another — or when an agent requests an action from a system, a human,
or a workflow — that interaction is a transaction. ZTIP defines how that transaction must be
structured so it is authorized, verifiable, and auditable after the fact.

ZTIP does not dictate transport. It does not restrict which agent framework, model, or tool your
engineers use. It governs the **transaction itself**: what was requested, whether it was authorized
by policy, and what happened.

The transport does not matter:

- API call
- File on disk
- Message queue
- GitHub PR
- Chat message
- Workflow engine trigger

ZTIP governs the **transaction artifact**, not how it moves.

---

## The Problem

AI agents are being chained together at scale. Planners invoke executors. Orchestrators invoke
specialists. Tools invoke tools.

None of these handoffs, in today's frameworks, carry governance. One agent passes a message to
another. The other runs it. Nothing is signed. Nothing is policy-checked. Nothing is auditable.

This is ambient authority — the most dangerous kind. An agent that can call another agent
implicitly holds the combined power of both, with none of the accountability of either.

At the same time, the answer is not to lock down which tools engineers can use. That creates
friction, slows delivery, and drives workarounds. Engineers need freedom to use whatever agent
tools help them move fast.

ZTIP solves both sides of that tension.

**Freedom for engineers. Governance for the organization.**

---

## Key Benefits

- **Tool-agnostic governance.** Engineers use any agent, model, or framework. ZTIP wraps the
  transaction, not the tool. No forced migration. No approved-tools list.
- **Every handoff is auditable.** Requests and their outcomes are captured as structured JSON
  artifacts with cryptographic integrity hashes. Every transaction leaves a record.
- **Policy-based authorization.** Transactions are evaluated against organizational policy.
  Some are auto-authorized. Some require human approval. Some are rejected outright. The policy
  decides — not the transport, not the agent.
- **No implicit trust.** There is no "trusted internal network" where governance is relaxed.
  A transaction without a valid authorization record does not pass.
- **Human-readable artifacts.** ZTIP artifacts are plain JSON. Integrity is enforced via
  cryptographic hashes, not encryption. Any person or system can read, store, and verify them.

---

## Relationship to ZTI and ZTI Core

ZTIP is part of the Zero Trust Intelligence (ZTI) ecosystem. The three components are distinct:

| Component | What It Is |
|-----------|-----------|
| **ZTI** | The verification doctrine: do not trust AI output blindly — verify it before it acts. |
| **ZTIP** | The open protocol: defines how governed agent transactions are structured and recorded. |
| **ZTI Core** | A control-plane implementation: evaluates policy, issues authorization records, and stores ZTIP artifacts. |

```text
ZTI (verification doctrine)
  └── ZTIP (open transaction protocol)
        └── ZTI Core (control plane — evaluates policy, authorizes, audits)
```

ZTIP is the protocol. ZTI Core is one compliant implementation of the control plane that enforces
it. Organizations may use ZTI Core or build their own compliant control plane. ZTI Core is
complete and in early access.

---

## How a Governed Transaction Works

1. **An agent initiates a request.** It packages the request as a ZTIP transaction artifact —
   structured JSON describing what is being requested, by whom, and for what purpose.
2. **The control plane evaluates policy.** The artifact is submitted to the control plane (e.g.,
   ZTI Core). Policy determines the outcome: auto-authorize, require human approval, request
   additional evidence, or reject.
3. **An authorization record is issued.** If approved, the control plane appends an authorization
   record to the artifact. The artifact is now a complete, verifiable transaction.
4. **The target agent or system acts.** Only transactions carrying a valid authorization record
   proceed. The artifact, not a side-channel, is the proof of permission.
5. **The artifact is stored.** The complete transaction — request, policy evaluation, authorization
   outcome, and result — is recorded. The integrity hash chain makes post-hoc modification
   detectable.

---

## Conceptual Example

*The following is illustrative only — a conceptual sketch, not the specified form. The
specified envelope model lives in `SCHEMA.md` and `schemas/`, with complete lifecycle bundles
under `examples/`.*

```json
{
  "ztap_version": "1.0-draft",
  "transaction_id": "txn_abc123",
  "requesting_agent": "planner-agent-7f3a",
  "target_capability": "deploy",
  "request_payload": {
    "service": "billing-api",
    "environment": "production"
  },
  "authorization": {
    "policy_evaluated": true,
    "outcome": "approved",
    "approved_by": "policy://deploy/production/auto",
    "recorded_at": "2026-04-24T14:00:00Z"
  },
  "integrity": {
    "payload_hash": "sha256:e3b0c44298fc...",
    "artifact_hash": "sha256:a1b2c3d4e5f6..."
  }
}
```

> **Note:** This example illustrates the concept of a governed transaction artifact. The
> specified form differs — see `SCHEMA.md` and the JSON Schemas under `schemas/` for the
> canonical envelope model, and `VISION.md` for the governing principles behind the design.
> The version field is named `ztap_version` after the protocol's original working name; it is
> retained for hash stability (see the legacy-field note in `SCHEMA.md`).

In this example, the transaction was authorized by policy automatically — no human approval was
required. A different policy configuration might have required a human to approve before
`artifact_hash` could be finalized and the transaction allowed to proceed.

---

## Authorization Is Policy-Conditional

ZTIP does not require human approval for every transaction. Authorization is determined by
organizational policy, evaluated by the control plane. Possible outcomes include:

- **Auto-authorized** — policy permits this transaction without human review.
- **Human approval required** — policy requires a named approver or role to sign off.
- **Additional evidence required** — policy requires supplemental context before a decision.
- **Rejected** — policy does not permit this transaction.

ZTIP supports all of these outcomes. The protocol records the outcome and the basis for it.
The organization defines the policy.

---

## What ZTIP Does Not Define (Yet)

ZTIP is in draft. The following are not yet specified:

- Transport bindings (how artifacts move between agents and the control plane)
- SDK or library interfaces
- Identity and signing requirements

The canonical schema (`SCHEMA.md` and `schemas/`) and the hash requirements (RFC 8785 JSON
Canonicalization Scheme with SHA-256 integrity hashes) are now specified.

These will be defined as the specification matures. See `VISION.md` for the principles that
will guide those decisions.

---

## Current Status

ZTIP is in **draft specification**. The doctrine (`SPEC.md`), envelope schema (`SCHEMA.md` and
`schemas/`), conformance requirements (`CONFORMANCE.md`), and lifecycle examples (`examples/`)
are drafted. This repository is the canonical home for that work.

The repository also ships a reference runtime: the `ztip/` Python package implements RFC 8785
canonicalization, SHA-256 hashing, and hash-chain integrity verification, with a `ztip` CLI
(`ztip hash`, `ztip verify`) that fails closed on any integrity or envelope-contract defect —
and states the limits of what it checked on every run. Full schema conformance is
`scripts/validate-examples.py`. The integrity hashes in the `examples/` files are real and
recomputable with the runtime.

Contributions, questions, and alignment discussions are welcome.

---

## Authorship and Stewardship

ZTIP was created by **Chad McCormack** as part of the Zero Trust Intelligence (ZTI) ecosystem.

This repository is maintained under the `bitscon` GitHub organization and released under the MIT License.

For citation metadata, see [CITATION.cff](CITATION.cff). For author and stewardship information, see [AUTHORS.md](AUTHORS.md).

---

> ZTIP: the open protocol for governed agent transactions.
> Where ZTI asks "was this decision verified?", ZTIP asks "was this handoff governed?"
