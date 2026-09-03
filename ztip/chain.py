"""Integrity verification for ZTIP bundles.

Recomputes each envelope's hash, checks the structural floor every ZTIP envelope
must satisfy, and confirms that each ``request_hash`` resolves to the transaction
request actually present in the bundle.

``request_hash`` is the only *kind* of reference this module resolves, and it is
resolved at every site an envelope binds itself by one: the top-level field, and
an authorization decision's ``human_approval_ref.approval_scope`` (SPEC, Bundle
Verification — "Every binding site is resolved"). Other cross-envelope references
are NOT checked here, and two of them do carry hashes: ``child_receipt_ref`` may
carry ``child_request_hash`` and ``child_receipt_hash``, and ``state_ref`` may
carry ``state_hash``. A caller must not read "references resolved" as covering
them; the CLI says which references it counted. A bundle with no findings is internally
consistent: nothing it carries has been altered since it was sealed, and its
references hold. That is not the same as complete, authentic, or true.

Scope of the claim — read this before treating "no findings" as assurance:

  * A ZTIP integrity hash is recomputable by anyone holding this library, so an
    intact bundle is evidence of *self-consistency*, not of *authenticity*. This
    module never claims that a trusted party produced the envelopes.
  * Non-normative annotation fields — keys beginning with an underscore — are
    excluded from the hash by design, so their content is not covered by any
    finding here.
  * The structural floor is the ZTIP envelope contract: protocol version,
    envelope type, transaction identifier, the declared integrity metadata, and
    each type's required fields. Full conformance validation — field value
    formats, role vocabularies, reason-code namespacing — is the JSON Schema's
    job (``schemas/``, ``scripts/validate-examples.py``), not this module's.
  * Verification is never vacuous: a bundle with nothing in it, an envelope that
    is not a ZTIP envelope, a reference that resolves to nothing, and a
    ``succeeded`` receipt that recorded no check results are all findings, not
    silent passes.
"""

from __future__ import annotations

import json
from typing import Any

from .hashing import CANONICALIZATION, HASH_ALGORITHM, envelope_hash

_MISSING = object()

#: Envelope types defined by ZTIP 1.0-draft (``schemas/ztip-envelope.schema.json``).
ENVELOPE_TYPES = frozenset({
    "transaction_request",
    "authorization_decision",
    "execution_receipt",
    "evidence_record",
    "amendment_event",
})

#: Protocol major versions this runtime verifies. Deliberately looser than the
#: shipped schema, which pins the exact draft version: a runtime must stay able
#: to re-verify envelopes sealed under earlier 1.x drafts, while the schema
#: describes the version currently being written. ``ztap_version`` keeps its
#: legacy name because it sits inside the hashed content (see SCHEMA.md).
SUPPORTED_PROTOCOL_MAJORS = frozenset({"1"})

#: Terminal states an execution receipt may report
#: (``schemas/execution-receipt.schema.json``).
RECEIPT_STATUSES = frozenset({
    "succeeded",
    "failed",
    "rejected",
    "cancelled",
    "expired",
    "timed_out",
})

#: Fields every envelope must carry, and the additional fields each type must
#: carry. Mirrors the ``required`` field *names* in ``schemas/``, and the test
#: suite fails if those drift apart; it does not mirror field *values*, which
#: stay with the schema. The common set also decides what counts as an envelope
#: rather than a bundle wrapper (see :func:`envelopes`).
COMMON_REQUIRED_FIELDS = ("ztap_version", "envelope_type", "transaction_id", "integrity")

REQUIRED_FIELDS_BY_TYPE = {
    "transaction_request": (
        "atomicity_mode", "created_at", "requested_action", "requested_capabilities",
        "source_actor", "target_actor", "verification_requirements",
    ),
    "authorization_decision": (
        "authorization_status", "control_plane", "decision_id", "evaluated_at",
        "policy_refs", "reason_codes", "request_hash",
    ),
    "execution_receipt": (
        "actions_attempted", "actions_completed", "atomicity_result",
        "authorization_decision_ref", "completed_at", "control_plane", "reason_codes",
        "receipt_id", "request_hash", "source_actor", "started_at", "status",
        "target_actor", "verification_results",
    ),
    "evidence_record": (
        "evidence_hash", "evidence_id", "evidence_type", "produced_at", "produced_by",
        "request_hash",
    ),
    "amendment_event": (
        "amendment_id", "amendment_type", "created_at", "created_by",
        "linked_envelope_refs", "reason_codes", "request_hash",
    ),
}

#: Code points that occupy no visible space, so a string made only of them names
#: nothing. Kept as an explicit set because the JSON Schema mirror of this rule
#: (``visible_string`` in ``schemas/ztip-envelope.schema.json``) cannot express
#: Unicode properties portably; the test suite proves the two agree over every
#: code point.
_INVISIBLE = (
    "\u00ad"                      # soft hyphen
    "\u034f"                      # combining grapheme joiner
    "\u061c"                      # arabic letter mark
    "\u115f\u1160"                # hangul choseong/jungseong fillers
    "\u17b4\u17b5"                # khmer inherent vowels
    "\u180e"                      # mongolian vowel separator
    "\u200b\u200c\u200d\u200e\u200f"  # zero-width and directional marks
    "\u2060\u2061\u2062\u2063\u2064"  # word joiner and invisible operators
    "\u206a\u206b\u206c\u206d\u206e\u206f"  # deprecated format controls
    "\u2800"                      # braille pattern blank
    "\u3164"                      # hangul filler
    "\ufeff"                      # zero-width no-break space
    "\uffa0"                      # halfwidth hangul filler
)


class DuplicateJSONKeyError(ValueError):
    """A JSON object declared the same member name twice.

    RFC 8259 leaves duplicate-name behaviour to the parser, so such a document
    means different things to different readers while every hash still checks
    out. A canonical-hash integrity model cannot accept that ambiguity.
    """


def reject_duplicate_keys(pairs: list) -> dict:
    """``object_pairs_hook`` that refuses an ambiguous JSON object."""
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise DuplicateJSONKeyError(f"duplicate JSON member name {key!r}")
        seen[key] = value
    return seen


def envelopes(bundle: Any) -> list:
    """Return the envelope list a bundle carries.

    Accepts the three shipped bundle shapes: ``{"envelopes": [...]}``, a bare
    array of envelopes, or a single envelope object. This is the same split
    verification uses, so a caller reporting "N envelopes verified" and this
    module always agree on N.

    An object carrying any ZTIP envelope field is always treated as one envelope,
    even if it also carries an ``envelopes`` key. Reading such an object as a
    wrapper would leave the envelope itself unverified while the reported count
    described its payload instead — and the test cannot be "``envelope_type`` is
    set", because omitting or nulling that one field is exactly what an envelope
    hiding behind a payload would do.
    """
    if isinstance(bundle, dict):
        if any(field in bundle for field in COMMON_REQUIRED_FIELDS):
            return [bundle]
        if isinstance(bundle.get("envelopes"), list):
            return bundle["envelopes"]
    if isinstance(bundle, list):
        return bundle
    return [bundle]


def unverified_bundle_keys(bundle: Any) -> list[str]:
    """Content a bundle wrapper carries beside its envelopes.

    Such content is neither hashed nor verified, so a caller must disclose it
    rather than let it ride along unmentioned. It is not a defect — an export
    wrapper legitimately carries metadata — so it is reported, not refused.
    Underscore-prefixed keys are reported too: they are non-normative annotations
    by convention, but letting the convention suppress the disclosure would make
    it opt-out at the bundle author's choice.
    """
    if not isinstance(bundle, dict):
        return []
    if any(field in bundle for field in COMMON_REQUIRED_FIELDS):
        return []
    if not isinstance(bundle.get("envelopes"), list):
        return []
    return sorted(str(key) for key in bundle if key != "envelopes")


def verify_bundle(bundle: Any, *, allow_unresolved_refs: bool = False) -> list[dict]:
    """Return a list of integrity findings; an empty list means the bundle is intact.

    Each finding: ``{envelope_index, envelope_type, code, detail}``. ``envelope_index``
    is ``None`` for a finding about the bundle as a whole.

    Bundle-level codes:

    ``EMPTY_BUNDLE``
        No envelopes to verify. An empty bundle is not a verified bundle.
    Envelope codes:

    ``ENVELOPE_MALFORMED``
        An entry that is not a JSON object.
    ``ENVELOPE_TYPE_UNKNOWN``
        ``envelope_type`` missing, or not one of :data:`ENVELOPE_TYPES`.
    ``TRANSACTION_ID_MISSING``
        ``transaction_id`` missing or not a non-empty string.
    ``PROTOCOL_VERSION_MISSING`` / ``PROTOCOL_VERSION_UNSUPPORTED``
        No ``ztap_version``, or a major version this runtime does not verify.
    ``INTEGRITY_METADATA_MISSING`` / ``INTEGRITY_ALGORITHM_UNSUPPORTED``
        The integrity object does not declare the canonicalization and hash
        algorithm it was sealed under, or declares ones this runtime does not
        apply. Verifying an envelope under rules other than the ones it declares
        would make the report describe a computation nobody performed.
    ``REQUIRED_FIELD_MISSING``
        A field this envelope type must carry (see :data:`REQUIRED_FIELDS_BY_TYPE`).
    ``ENVELOPE_UNHASHABLE``
        Values outside the ZTIP value vocabulary, so no canonical form — and
        therefore no hash — exists for this envelope.
    ``HASH_MISSING`` / ``HASH_MISMATCH``
        No stored ``integrity.hash_value``, or one that does not match the
        recomputed hash. This is the tamper check.
    ``REQUEST_HASH_BROKEN``
        A ``request_hash`` whose transaction request *is* present but does not
        hash to the referenced value.
    ``REQUEST_HASH_UNRESOLVED``
        A ``request_hash`` that resolves to no transaction request present in the
        bundle. Checked at every site an envelope binds itself by hash — the
        top-level field and an authorization decision's
        ``human_approval_ref.approval_scope``, which is what binds a human
        approval to the work it approved. Suppressed only by ``allow_unresolved_refs=True``, which weakens
        the claim the caller may make: chain linkage was not verified.
    ``DUPLICATE_REQUEST``
        More than one ``transaction_request`` for one ``transaction_id``. Without
        this check the later one silently shadows the earlier, so a bundle
        carrying two contradictory requests verifies clean.
    ``CHILD_REQUEST_HASH_BROKEN``
        A ``child_receipt_ref`` whose child transaction request is present in the
        bundle but does not hash to the declared ``child_request_hash``.
    ``CONFLICTING_RECEIPTS``
        Receipts for one transaction reporting different terminal states. A
        transaction has one outcome; a reader would have to guess which.
    ``VERIFICATION_RESULTS_EMPTY`` / ``VERIFICATION_RESULT_MALFORMED``
        A ``succeeded`` receipt that recorded no check result, or results that do
        not say which check ran and whether it passed. Result *shape* is checked
        on any envelope that records ``verification_results``, not only on
        receipts: free text is not a check result wherever it appears.
    ``VERIFICATION_RESULT_UNSEALED``
        A result stored under an annotation key, which the hash excludes. The same
        hash describes the receipt with and without it, so it cannot count.
    ``SUCCESS_CONTRADICTS_RESULTS``
        A ``succeeded`` receipt whose every recorded check reports failure.
    ``RECEIPT_STATUS_INVALID``
        A receipt ``status`` outside :data:`RECEIPT_STATUSES`.
    """
    findings: list[dict] = []
    entries = envelopes(bundle)

    if not entries:
        findings.append(_finding(
            None, "bundle", "EMPTY_BUNDLE",
            "no envelopes to verify — an empty bundle is not a verified bundle"))
        return findings

    request_txns_seen: set = set()
    receipt_statuses: dict[str, set] = {}

    for index, env in enumerate(entries):
        if not isinstance(env, dict):
            findings.append(_finding(
                index, "unknown", "ENVELOPE_MALFORMED",
                f"entry is {type(env).__name__}, not a JSON object"))
            continue

        raw_type = env.get("envelope_type", _MISSING)
        findings.extend(_floor_findings(index, env, raw_type))
        etype = raw_type if isinstance(raw_type, str) else "unknown"

        try:
            computed = envelope_hash(env)
        except (TypeError, ValueError, NotImplementedError) as exc:
            findings.append(_finding(
                index, etype, "ENVELOPE_UNHASHABLE",
                f"no canonical form exists for this envelope: {exc}"))
            continue

        integrity = env.get("integrity")
        stored = integrity.get("hash_value") if isinstance(integrity, dict) else None
        if stored is None:
            findings.append(_finding(index, etype, "HASH_MISSING",
                                     "no integrity.hash_value present"))
        elif stored != computed:
            findings.append(
                _finding(index, etype, "HASH_MISMATCH",
                         f"stored {_short(stored)} != computed {_short(computed)}")
            )

        txn = env.get("transaction_id")
        if not isinstance(txn, str):
            # Not a usable key; the floor already reported it. Skip the
            # cross-envelope bookkeeping rather than raise on an unhashable value.
            continue

        if etype == "transaction_request":
            if txn in request_txns_seen:
                findings.append(
                    _finding(index, etype, "DUPLICATE_REQUEST",
                             "a second transaction_request for this transaction_id — "
                             "the request history is ambiguous")
                )
            request_txns_seen.add(txn)
        elif etype == "execution_receipt":
            status = env.get("status")
            if isinstance(status, str):
                receipt_statuses.setdefault(txn, set()).add(status)

    for txn, statuses in receipt_statuses.items():
        if len(statuses) > 1:
            findings.append(_finding(
                None, "execution_receipt", "CONFLICTING_RECEIPTS",
                f"transaction {txn!r} has receipts reporting {sorted(statuses)!r} — "
                "a transaction has one outcome"))

    request_hashes = _request_hashes(entries)
    ref_findings, _resolved = _reference_findings(
        entries, request_hashes, allow_unresolved_refs=allow_unresolved_refs)
    findings.extend(ref_findings)
    findings.extend(_child_reference_findings(entries, request_hashes))

    return findings


def _reference_findings(entries: list, request_hash_by_txn: dict,
                        *, allow_unresolved_refs: bool) -> tuple[list[dict], int]:
    """Resolve every ``request_hash``. Returns (findings, resolved count).

    Both callers resolve against the same map, built by :func:`_request_hashes`,
    so the count one of them prints and the findings the other prints can never
    describe different bundles.
    """
    findings: list[dict] = []
    resolved = 0
    for index, env in enumerate(entries):
        if not isinstance(env, dict):
            continue
        etype = env.get("envelope_type", "unknown")
        if not isinstance(etype, str):
            etype = "unknown"
        for where, txn, ref in _reference_sites(env):
            expected = request_hash_by_txn.get(txn) if isinstance(txn, str) else None
            if expected is None:
                if not allow_unresolved_refs:
                    findings.append(
                        _finding(index, etype, "REQUEST_HASH_UNRESOLVED",
                                 f"{where}: no transaction_request for this "
                                 "transaction_id is present in the bundle, so the "
                                 "request_hash cannot be resolved and the linkage "
                                 "cannot be verified")
                    )
            elif ref != expected:
                findings.append(
                    _finding(index, etype, "REQUEST_HASH_BROKEN",
                             f"{where}: request_hash does not match the referenced "
                             "request envelope")
                )
            else:
                resolved += 1
    return findings, resolved


def _child_reference_findings(entries: list, request_hashes: dict) -> list[dict]:
    """Check a `child_receipt_ref` whose child request is present in the bundle.

    A parent receipt may legitimately name a child whose request was not exported
    with it (example 08 does), so an absent child is not a finding — whether it
    should be is a protocol question, recorded as a follow-up. But when the child
    request IS present, its declared hash must match it: otherwise a parent can
    point at content sitting right there and claim a different one.
    """
    findings: list[dict] = []
    for index, env in enumerate(entries):
        if not isinstance(env, dict):
            continue
        refs = env.get("child_receipt_refs")
        if refs is None:
            continue
        etype = env.get("envelope_type", "unknown")
        if not isinstance(refs, list):
            # Fail closed: the container shape is attacker-chosen, and skipping an
            # unreadable one would disable this check on request.
            findings.append(_finding(
                index, etype, "CHILD_REQUEST_HASH_BROKEN",
                f"child_receipt_refs is {type(refs).__name__}, not an array, so the "
                "child bindings it declares cannot be checked"))
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                findings.append(_finding(
                    index, etype, "CHILD_REQUEST_HASH_BROKEN",
                    f"a child_receipt_refs entry is {type(ref).__name__}, not an "
                    "object, so the binding it declares cannot be checked"))
                continue
            child = ref.get("child_transaction_id")
            declared = ref.get("child_request_hash")
            if declared is None or not isinstance(child, str):
                continue
            actual = request_hashes.get(child)
            if actual is not None and declared != actual:
                findings.append(_finding(
                    index, etype, "CHILD_REQUEST_HASH_BROKEN",
                    f"child_receipt_refs: the request for {child!r} is present in this "
                    "bundle and does not hash to the declared child_request_hash"))
    return findings


def _reference_sites(env: dict):
    """Every place an envelope binds itself to a transaction request by hash.

    Not only the top-level ``request_hash``: an authorization decision's
    ``human_approval_ref.approval_scope`` carries its own ``transaction_id`` and
    ``request_hash``, and that pair is what binds a human approval to the work it
    approved. Leaving it unresolved is how an approval gets bound to a different
    transaction while the bundle still verifies.
    """
    ref = env.get("request_hash")
    if ref is not None:
        yield "request_hash", env.get("transaction_id"), ref

    approval = env.get("human_approval_ref")
    if approval is None:
        return
    if not isinstance(approval, dict):
        # Fail closed: an unreadable approval reference must not make the binding
        # vanish. Yielding an unresolvable site reports it instead.
        yield "human_approval_ref", None, ""
        return
    scope = approval.get("approval_scope")
    if scope is None:
        return
    if not isinstance(scope, dict):
        yield "human_approval_ref.approval_scope", None, ""
        return
    scope_ref = scope.get("request_hash")
    if scope_ref is None:
        # The scope exists but binds to nothing. Dropping the site silently would
        # lower the reported reference count with no signal that it did.
        yield "human_approval_ref.approval_scope", None, ""
        return
    yield ("human_approval_ref.approval_scope",
           scope.get("transaction_id"), scope_ref)


def _request_hashes(entries: list) -> dict:
    """Map each transaction id to the hash of its ``transaction_request``.

    Built here for both callers — :func:`verify_bundle` and
    :func:`resolved_reference_count` — so the count one of them prints and the
    findings the other prints can never describe different bundles.
    """
    hashes: dict[str, str] = {}
    for env in entries:
        if not isinstance(env, dict) or env.get("envelope_type") != "transaction_request":
            continue
        txn = env.get("transaction_id")
        if not isinstance(txn, str):
            continue
        try:
            hashes[txn] = envelope_hash(env)
        except (TypeError, ValueError, NotImplementedError):
            continue
    return hashes


def reference_count(bundle: Any) -> int:
    """How many request references the bundle carries, at every binding site.

    A caller reporting "N of M resolved" needs M from the same enumeration the
    resolver walks, or the two numbers describe different documents.
    """
    return sum(1 for env in envelopes(bundle) if isinstance(env, dict)
               for _site in _reference_sites(env))


def resolved_reference_count(bundle: Any) -> int:
    """How many ``request_hash`` references resolve to a request in the bundle.

    A caller reporting "references resolve" needs to know whether any reference
    was actually resolved: zero resolved references is not a verified chain.
    """
    entries = envelopes(bundle)
    _findings, resolved = _reference_findings(
        entries, _request_hashes(entries), allow_unresolved_refs=False)
    return resolved


def _floor_findings(index: int, env: dict, raw_type: Any) -> list[dict]:
    """Findings for the structural floor every ZTIP envelope must satisfy.

    This is the envelope contract, not a schema implementation: presence of the
    fields each type must carry, a protocol version this runtime verifies, and
    integrity metadata that states the rules the envelope was sealed under.
    Value-level conformance stays with ``schemas/``.
    """
    found: list[dict] = []
    label = raw_type if isinstance(raw_type, str) else "unknown"

    if not isinstance(raw_type, str) or raw_type not in ENVELOPE_TYPES:
        detail = ("envelope_type is missing" if raw_type is _MISSING
                  else f"envelope_type {_printable(raw_type)} is not a ZTIP envelope type")
        found.append(_finding(index, label, "ENVELOPE_TYPE_UNKNOWN", detail))

    txn = env.get("transaction_id")
    if not isinstance(txn, str) or not _has_content(txn):
        found.append(_finding(
            index, label, "TRANSACTION_ID_MISSING",
            "transaction_id missing or not a non-empty string"))

    version = env.get("ztap_version")
    if not isinstance(version, str) or not version:
        found.append(_finding(
            index, label, "PROTOCOL_VERSION_MISSING",
            "ztap_version missing or not a non-empty string"))
    elif version.replace("-", ".").split(".")[0] not in SUPPORTED_PROTOCOL_MAJORS:
        found.append(_finding(
            index, label, "PROTOCOL_VERSION_UNSUPPORTED",
            f"ztap_version {_printable(version)} is not a protocol version this runtime "
            "verifies"))

    found.extend(_integrity_findings(index, label, env.get("integrity")))

    if isinstance(raw_type, str):
        absent = [
            field for field in REQUIRED_FIELDS_BY_TYPE.get(raw_type, ())
            if env.get(field) is None
        ]
        if absent:
            found.append(_finding(
                index, label, "REQUIRED_FIELD_MISSING",
                f"{raw_type} does not carry {', '.join(absent)}"))

    if "verification_results" in env or raw_type == "execution_receipt":
        require_content = False
        if raw_type == "execution_receipt":
            status = env.get("status")
            if not isinstance(status, str) or status not in RECEIPT_STATUSES:
                found.append(_finding(
                    index, label, "RECEIPT_STATUS_INVALID",
                    f"status {_printable(status)} is not a ZTIP receipt status"))
            require_content = status == "succeeded"
        found.extend(_results_findings(
            index, label, env.get("verification_results"),
            require_content=require_content))

    return found


def _integrity_findings(index: int, label: str, integrity: Any) -> list[dict]:
    if not isinstance(integrity, dict):
        return [_finding(index, label, "INTEGRITY_METADATA_MISSING",
                         "integrity object missing")]
    absent = [
        field for field in ("canonicalization", "hash_algorithm")
        if not isinstance(integrity.get(field), str) or not integrity.get(field)
    ]
    if absent:
        return [_finding(
            index, label, "INTEGRITY_METADATA_MISSING",
            f"integrity does not declare {', '.join(absent)} — the rules it was sealed "
            "under are not stated, so it cannot be independently re-verified")]
    declared = (integrity["canonicalization"], integrity["hash_algorithm"])
    if declared != (CANONICALIZATION, HASH_ALGORITHM):
        return [_finding(
            index, label, "INTEGRITY_ALGORITHM_UNSUPPORTED",
            f"envelope declares {declared[0]!r} / {declared[1]!r}, which this runtime "
            f"does not apply; it verified under {CANONICALIZATION} / {HASH_ALGORITHM}")]
    return []


def _results_findings(index: int, label: str, results: Any,
                      *, require_content: bool) -> list[dict]:
    """Recorded results must be structured, and a ``succeeded`` receipt must have some.

    A success claim carrying no check results is the vacuity this verifier exists
    to refuse, so ``require_content`` (set for ``succeeded``) makes an empty
    result set a finding. Result *shape* is checked wherever results are recorded
    at all: free text is not a check result. Which checks were *required* is the
    control plane's question, not the protocol runtime's; this is only the floor
    that the field means something at all.
    """
    annotations: list = []
    if isinstance(results, list):
        items = list(enumerate(results))
    elif isinstance(results, dict):
        # Underscore-prefixed keys are stripped before hashing, so a result stored
        # under one is not covered by the seal: the same hash describes a receipt
        # with the result and one without it. It cannot count as a recorded check.
        annotations = [key for key in results if str(key).startswith("_")]
        items = [(key, value) for key, value in results.items()
                 if not str(key).startswith("_")]
    elif results is None:
        if require_content:
            return [_finding(
                index, label, "VERIFICATION_RESULTS_EMPTY",
                "status succeeded but no verification_results are recorded — "
                "a success that verified nothing is not a verified success")]
        return []
    else:
        # Malformed, not empty: the same value gets the same code in every state.
        return [_finding(
            index, label, "VERIFICATION_RESULT_MALFORMED",
            f"verification_results is {type(results).__name__}, not an array or object "
            "of check results")]

    found: list[dict] = []
    for key in annotations:
        found.append(_finding(
            index, label, "VERIFICATION_RESULT_UNSEALED",
            f"verification_results[{key!r}] is an annotation key, so it is excluded "
            "from the envelope hash — a check result the seal does not cover is not "
            "a recorded result"))

    if not items:
        if not require_content:
            return found
        return found + [_finding(
            index, label, "VERIFICATION_RESULTS_EMPTY",
            "status succeeded but verification_results records no check result — "
            "a success that verified nothing is not a verified success")]

    outcomes: list[Any] = []
    for key, item in items:
        if not isinstance(item, dict):
            found.append(_finding(
                index, label, "VERIFICATION_RESULT_MALFORMED",
                f"verification_results[{key!r}] is {type(item).__name__}, "
                "not an object"))
            continue
        missing = [
            field for field in ("check_id", "check_type")
            if not isinstance(item.get(field), str) or not _has_content(item.get(field))
        ]
        if not isinstance(item.get("passed"), bool):
            missing.append("passed")
        if missing:
            found.append(_finding(
                index, label, "VERIFICATION_RESULT_MALFORMED",
                f"verification_results[{key!r}] does not record "
                f"{', '.join(missing)}"))
        else:
            outcomes.append(item["passed"])

    if require_content and outcomes and not any(outcomes):
        found.append(_finding(
            index, label, "SUCCESS_CONTRADICTS_RESULTS",
            "status succeeded but every recorded check reports failure"))

    return found


def _has_content(value: Any) -> bool:
    """True when a string carries at least one visible character.

    Tested per character, not by stripping: a strip chain is defeated by
    alternating whitespace and zero-width characters, which is exactly the shape
    an identifier that names nothing would take.
    """
    if not isinstance(value, str):
        return False
    return any(not ch.isspace() and ch not in _INVISIBLE for ch in value)


def _finding(index: int | None, etype: Any, code: str, detail: str) -> dict:
    """Build a finding record.

    ``envelope_type`` is copied from the envelope, so it is attacker-controlled
    text. Findings are read by other code — some of it writing them to
    line-oriented logs — so a value that is not printable is rendered safely
    here rather than at each consumer.
    """
    return {"envelope_index": index, "envelope_type": _printable(etype),
            "code": code, "detail": detail}


def _printable(value: Any) -> str:
    """Render a value so it can never carry a raw control character.

    ``repr`` escapes strings but not an arbitrary object's ``__repr__``, and a
    reference runtime is handed in-memory envelopes as well as parsed ones.
    """
    text = value if isinstance(value, str) else repr(value)
    return text if text.isprintable() else json.dumps(text)


def _short(value: Any) -> str:
    """A short, safe rendering of an envelope-supplied value.

    Finding details are read directly by library consumers, some of which write
    them to line-oriented logs, so a value that carries a newline must never
    reach one verbatim.
    """
    text = _printable(value)
    return text[:16] + "..." if len(text) > 19 else text
