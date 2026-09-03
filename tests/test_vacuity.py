"""Verification must never report success over nothing.

Every test here is a reproduction of a way `ztip verify` (or the shipped receipt
schema) previously reported "integrity verified" while nothing had been checked,
found by the 2026-09-02 vacuity audit. Each one now fails closed.

These are regression tests for the protocol's core honesty property: a green
result means envelopes were checked, and the printed claim covers only what was
actually checked.
"""

import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ztip.chain import (  # noqa: E402
    _INVISIBLE,
    _has_content,
    COMMON_REQUIRED_FIELDS,
    REQUIRED_FIELDS_BY_TYPE,
    envelopes,
    reference_count,
    resolved_reference_count,
    unverified_bundle_keys,
    verify_bundle,
)
from ztip.hashing import envelope_hash, verify_envelope_hash  # noqa: E402

EXAMPLES = REPO_ROOT / "examples"
SCHEMAS = REPO_ROOT / "schemas"


# ── helpers ──────────────────────────────────────────────────────────────────

def codes(findings):
    return {f["code"] for f in findings}


def reseal(envelope):
    """Recompute the envelope's own hash, as a forger with the open library would.

    The integrity object must exist before the hash is computed: the hash covers
    every integrity field except hash_value itself, so sealing an envelope that
    had no integrity object at hash time produces a mismatch, not a seal.
    """
    envelope.setdefault("integrity", {})
    envelope["integrity"]["hash_value"] = envelope_hash(envelope)
    assert verify_envelope_hash(envelope), "fixture did not actually self-seal"
    return envelope


@pytest.fixture()
def chain():
    """The shipped happy-path chain: request, decision, succeeded receipt."""
    doc = json.loads((EXAMPLES / "01-auto-authorized-success.json").read_text("utf-8"))
    return copy.deepcopy(doc["envelopes"])


def schema_registry():
    """Built exactly as scripts/validate-examples.py builds it, so this suite and
    the shipped validator can never disagree about what the schemas say."""
    resources = []
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        doc = json.loads(path.read_text("utf-8"))
        resource = Resource.from_contents(doc)
        resources.append((path.name, resource))
        schema_id = doc.get("$id")
        if isinstance(schema_id, str) and schema_id and schema_id != path.name:
            resources.append((schema_id, resource))
    return Registry().with_contents(
        (uri, resource.contents) for uri, resource in resources)


@pytest.fixture(scope="module")
def bundle_validator():
    registry = schema_registry()
    bundle_schema = json.loads((SCHEMAS / "ztip-bundle.schema.json").read_text("utf-8"))
    Draft202012Validator.check_schema(bundle_schema)
    return Draft202012Validator(
        bundle_schema, registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER)


def test_the_validator_actually_resolves_its_references():
    """A schema whose $refs silently fail to resolve accepts everything — the
    classic way a schema tightening does nothing at all."""
    with pytest.raises(Exception):
        list(Draft202012Validator(
            {"$ref": "no-such.schema.json"},
            registry=schema_registry()).iter_errors({}))


def test_the_receipt_schema_reference_really_binds(bundle_validator):
    """Prove the succeeded conditional is applied, not silently skipped."""
    doc = json.loads((EXAMPLES / "01-auto-authorized-success.json").read_text("utf-8"))
    envs = doc["envelopes"]
    assert schema_errors(bundle_validator, envs) == []
    envs[2]["verification_results"] = [{"check_id": "a", "passed": True}]
    errors = schema_errors(bundle_validator, envs)
    assert errors, "a result missing check_type must be rejected"


def schema_errors(validator, envelope_list):
    return list(validator.iter_errors(envelope_list))


# ── finding: an empty bundle read as "integrity verified" ────────────────────

@pytest.mark.parametrize("empty", [[], {"envelopes": []}])
def test_empty_bundle_is_not_a_pass(empty):
    assert codes(verify_bundle(empty)) == {"EMPTY_BUNDLE"}


def test_empty_bundle_exits_nonzero_through_the_cli(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 1
    assert "EMPTY_BUNDLE" in proc.stdout
    assert "integrity verified" not in proc.stdout


def test_verify_reports_how_many_envelopes_it_verified(tmp_path):
    proc = _run_verify(EXAMPLES / "01-auto-authorized-success.json")
    assert proc.returncode == 0
    assert "3 envelope(s) verified" in proc.stdout


def test_verify_states_that_it_did_not_check_authenticity():
    proc = _run_verify(EXAMPLES / "01-auto-authorized-success.json")
    assert "not proof of authenticity" in proc.stdout


# ── finding: a succeeded receipt that recorded zero check results ────────────

def test_succeeded_receipt_with_no_results_fails_verification(chain):
    chain[2]["verification_results"] = []
    reseal(chain[2])
    assert "VERIFICATION_RESULTS_EMPTY" in codes(verify_bundle({"envelopes": chain}))


def test_succeeded_receipt_with_no_results_fails_the_schema(chain, bundle_validator):
    chain[2]["verification_results"] = []
    reseal(chain[2])
    assert schema_errors(bundle_validator, chain), \
        "the shipped schema still blesses a success that verified nothing"


def test_succeeded_receipt_results_must_say_what_was_checked(chain):
    chain[2]["verification_results"] = [{"note": "trust me"}]
    reseal(chain[2])
    assert "VERIFICATION_RESULT_MALFORMED" in codes(verify_bundle({"envelopes": chain}))


def test_succeeded_receipt_results_must_say_what_was_checked_schema(chain, bundle_validator):
    chain[2]["verification_results"] = [{"note": "trust me"}]
    reseal(chain[2])
    assert schema_errors(bundle_validator, chain)


def test_non_succeeded_receipt_may_carry_no_results(chain, bundle_validator):
    """A rejected or failed transaction never reached verification. That is honest."""
    failed = json.loads((EXAMPLES / "05-failed-partial-state.json").read_text("utf-8"))
    failed["envelopes"][2]["verification_results"] = []
    reseal(failed["envelopes"][2])
    assert verify_bundle(failed) == []
    assert schema_errors(bundle_validator, failed["envelopes"]) == []


def test_succeeded_receipt_with_an_empty_results_map_is_refused(chain, bundle_validator):
    """The object shape must not be a way around the non-empty rule."""
    chain[2]["verification_results"] = {}
    reseal(chain[2])
    assert "VERIFICATION_RESULTS_EMPTY" in codes(verify_bundle({"envelopes": chain}))
    assert schema_errors(bundle_validator, chain), \
        "an empty results map still passes the schema"


def test_succeeded_receipt_with_a_junk_results_map_is_refused(chain, bundle_validator):
    chain[2]["verification_results"] = {"chk-a": {"note": "trust me"}}
    reseal(chain[2])
    assert "VERIFICATION_RESULT_MALFORMED" in codes(verify_bundle({"envelopes": chain}))
    assert schema_errors(bundle_validator, chain)


def test_results_may_be_an_object_keyed_by_check_id(chain, bundle_validator):
    chain[2]["verification_results"] = {
        "chk-a": {"check_id": "chk-a", "check_type": "service_health", "passed": True}}
    reseal(chain[2])
    assert verify_bundle({"envelopes": chain}) == []
    assert schema_errors(bundle_validator, chain) == []


# ── finding: a request_hash resolving to no present request ──────────────────

def test_request_hash_referencing_an_absent_request_is_a_finding(chain):
    _request, decision, receipt = chain
    findings = verify_bundle({"envelopes": [decision, receipt]})
    assert codes(findings) == {"REQUEST_HASH_UNRESOLVED"}
    assert len(findings) == 2


def test_request_hash_pointing_at_nothing_at_all_is_a_finding(chain):
    chain[2]["request_hash"] = "0" * 64
    reseal(chain[2])
    findings = verify_bundle({"envelopes": [chain[1], chain[2]]})
    assert "REQUEST_HASH_UNRESOLVED" in codes(findings)


def test_unresolved_refs_are_skipped_only_when_explicitly_allowed(chain):
    _request, decision, receipt = chain
    assert verify_bundle({"envelopes": [decision, receipt]},
                         allow_unresolved_refs=True) == []


def test_the_opt_out_says_linkage_was_not_verified(tmp_path, chain):
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"envelopes": [chain[1], chain[2]]}), encoding="utf-8")
    proc = _run_verify(path, "--allow-unresolved-refs")
    assert proc.returncode == 0
    assert "0 of 2 request reference(s) resolved" in proc.stdout
    assert "NOT fully verified" in proc.stdout


def test_a_present_but_wrong_request_is_still_broken_not_unresolved(chain):
    request, decision, receipt = chain
    request["requested_action"]["parameters"]["version"] = "tampered"
    reseal(request)
    findings = verify_bundle({"envelopes": [request, decision, receipt]})
    assert "REQUEST_HASH_BROKEN" in codes(findings)


# ── finding: a duplicate transaction_request shadowing the honest one ────────

def test_duplicate_request_for_one_transaction_is_a_finding(chain):
    request, decision, receipt = chain
    forged = copy.deepcopy(request)
    forged["requested_action"]["parameters"]["version"] = "9.9.9-attacker"
    reseal(forged)
    # Forged first, honest last: last-wins resolution used to bless this bundle.
    findings = verify_bundle({"envelopes": [forged, request, decision, receipt]})
    assert "DUPLICATE_REQUEST" in codes(findings)


def test_distinct_child_transactions_are_not_duplicates():
    """Example 08 carries three requests under three transaction ids. Still clean."""
    doc = json.loads((EXAMPLES / "08-child-transaction.json").read_text("utf-8"))
    assert verify_bundle(doc) == []


# ── finding: self-sealed, schema-invalid content read as verified ────────────

def test_self_sealed_illegal_receipt_status_is_a_finding():
    garbage = reseal({
        "ztap_version": "1.0-draft",
        "envelope_type": "execution_receipt",
        "transaction_id": "ztip-txn-garbage",
        "status": "TOTALLY_MADE_UP",
        "integrity": {"hash_algorithm": "SHA-256", "canonicalization": "RFC8785-JCS"},
    })
    found = codes(verify_bundle(garbage))
    # The hash is genuinely self-consistent — that is the point. A valid self-hash
    # over invalid content must not read as a verified envelope.
    assert "HASH_MISMATCH" not in found and "HASH_MISSING" not in found
    assert "RECEIPT_STATUS_INVALID" in found


def test_self_sealed_non_envelope_is_a_finding():
    junk = reseal({"not_even": "an envelope"})
    found = codes(verify_bundle(junk))
    assert "HASH_MISMATCH" not in found and "HASH_MISSING" not in found
    assert "ENVELOPE_TYPE_UNKNOWN" in found
    assert "TRANSACTION_ID_MISSING" in found


def test_an_entry_that_is_not_an_object_is_a_finding():
    assert "ENVELOPE_MALFORMED" in codes(verify_bundle(["just a string"]))


def test_an_unhashable_envelope_is_a_finding_not_a_crash():
    findings = verify_bundle([{
        "ztap_version": "1.0-draft",
        "envelope_type": "evidence_record",
        "transaction_id": "ztip-txn-float",
        "value": 1.5,  # outside the ZTIP value vocabulary
        "integrity": {"hash_value": "x"},
    }])
    assert "ENVELOPE_UNHASHABLE" in codes(findings)


# ── the floor never contradicts the schema on shipped content ────────────────

def test_every_example_passes_both_the_runtime_floor_and_the_schema(bundle_validator):
    example_files = sorted(EXAMPLES.glob("*.json"))
    assert len(example_files) == 10, "example corpus changed — update this count"
    for path in example_files:
        doc = json.loads(path.read_text("utf-8"))
        assert verify_bundle(doc) == [], f"{path.name} no longer verifies"
        assert schema_errors(bundle_validator, envelopes(doc)) == [], \
            f"{path.name} no longer validates"


# ── the tamper check itself — the reason this tool exists ────────────────────

def test_a_tampered_envelope_is_caught(chain):
    """Without this, every other check guards a document nobody validated."""
    chain[2]["completed_at"] = "2099-01-01T00:00:00Z"
    findings = verify_bundle({"envelopes": chain})
    assert "HASH_MISMATCH" in codes(findings)


def test_a_tampered_envelope_fails_through_the_cli(tmp_path, chain):
    chain[2]["actions_completed"] = []
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps({"envelopes": chain}), encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 1
    assert "HASH_MISMATCH" in proc.stdout


def test_an_envelope_with_no_stored_hash_is_caught(chain):
    del chain[2]["integrity"]["hash_value"]
    assert "HASH_MISSING" in codes(verify_bundle({"envelopes": chain}))


# ── a wrapper key must not shadow the envelope carrying it ──────────────────

def test_an_envelope_carrying_an_envelopes_key_is_still_verified(chain):
    """The decoy attack: hide a vacuous receipt behind a valid payload."""
    request, _decision, receipt = chain
    receipt["verification_results"] = []
    receipt["envelopes"] = [copy.deepcopy(request)]
    reseal(receipt)
    findings = verify_bundle(receipt)
    assert "VERIFICATION_RESULTS_EMPTY" in codes(findings)
    assert envelopes(receipt) == [receipt], "the outer envelope must be what is verified"


def test_content_beside_the_envelopes_list_is_reported(chain):
    """Reported, not refused: an export wrapper legitimately carries metadata,
    but a caller must be told it was not covered."""
    doc = {"envelopes": chain, "summary": "approved by the CFO"}
    assert verify_bundle(doc) == []
    assert unverified_bundle_keys(doc) == ["summary"]


def test_annotation_keys_beside_the_envelopes_list_do_not_fail_the_bundle():
    """Every shipped example carries one. Disclosed, never a finding."""
    doc = json.loads((EXAMPLES / "01-auto-authorized-success.json").read_text("utf-8"))
    assert "_ztip_example" in doc
    assert verify_bundle(doc) == []
    assert unverified_bundle_keys(doc) == ["_ztip_example"]


# ── the floor is the whole envelope contract, not a subset ──────────────────

@pytest.mark.parametrize("field", ["ztap_version"])
def test_a_missing_protocol_version_is_a_finding(chain, field):
    chain[2].pop(field)
    reseal(chain[2])
    assert "PROTOCOL_VERSION_MISSING" in codes(verify_bundle({"envelopes": chain}))


def test_an_unsupported_protocol_version_is_a_finding(chain):
    chain[2]["ztap_version"] = "9.9-draft"
    reseal(chain[2])
    assert "PROTOCOL_VERSION_UNSUPPORTED" in codes(verify_bundle({"envelopes": chain}))


def test_undeclared_integrity_metadata_is_a_finding(chain):
    chain[2]["integrity"].pop("hash_algorithm")
    reseal(chain[2])
    assert "INTEGRITY_METADATA_MISSING" in codes(verify_bundle({"envelopes": chain}))


def test_an_envelope_declaring_another_hash_rule_is_a_finding(chain):
    """Verifying under rules the envelope does not declare reports a computation
    nobody performed."""
    chain[2]["integrity"]["hash_algorithm"] = "MD5"
    reseal(chain[2])
    assert "INTEGRITY_ALGORITHM_UNSUPPORTED" in codes(verify_bundle({"envelopes": chain}))


@pytest.mark.parametrize("field", ["receipt_id", "atomicity_result", "started_at",
                                   "actions_completed", "authorization_decision_ref"])
def test_a_receipt_missing_a_required_field_is_a_finding(chain, field):
    chain[2].pop(field)
    reseal(chain[2])
    assert "REQUIRED_FIELD_MISSING" in codes(verify_bundle({"envelopes": chain}))


def test_a_receipt_without_a_request_hash_cannot_claim_linkage(chain):
    chain[2].pop("request_hash")
    reseal(chain[2])
    assert "REQUIRED_FIELD_MISSING" in codes(verify_bundle({"envelopes": chain}))


def test_the_required_field_table_matches_the_shipped_schemas():
    """Drift between the runtime floor and the schemas would make one of them lie."""
    for name, path in [
        ("transaction_request", "transaction-request.schema.json"),
        ("authorization_decision", "authorization-decision.schema.json"),
        ("execution_receipt", "execution-receipt.schema.json"),
        ("evidence_record", "evidence-record.schema.json"),
        ("amendment_event", "amendment-event.schema.json"),
    ]:
        doc = json.loads((SCHEMAS / path).read_text("utf-8"))
        required = set()
        for part in doc["allOf"]:
            required |= set(part.get("required", []))
        expected = set(REQUIRED_FIELDS_BY_TYPE[name]) | set(COMMON_REQUIRED_FIELDS)
        expected.discard("ztap_version")
        expected.discard("envelope_type")
        expected.discard("transaction_id")
        expected.discard("integrity")
        assert set(REQUIRED_FIELDS_BY_TYPE[name]) == required, \
            f"{name}: runtime floor and schema disagree on required fields"


# ── results must be structured wherever they are recorded ───────────────────

@pytest.mark.parametrize("junk", ["everything checked out", 7, True])
def test_results_that_are_not_a_collection_are_refused(chain, junk):
    chain[2]["verification_results"] = junk
    reseal(chain[2])
    assert "VERIFICATION_RESULT_MALFORMED" in codes(verify_bundle({"envelopes": chain}))


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_the_same_malformed_value_gets_the_same_code_in_every_state(chain, status):
    """An implementer keying on codes must not get a different classification for
    identical input just because the receipt reports a different outcome."""
    chain[2]["status"] = status
    chain[2]["reason_codes"] = [] if status == "succeeded" else ["ACTION_FAILED"]
    chain[2]["verification_results"] = "all checks passed"
    reseal(chain[2])
    assert "VERIFICATION_RESULT_MALFORMED" in codes(verify_bundle({"envelopes": chain}))


def test_a_succeeded_receipt_with_no_results_field_at_all_is_empty_not_malformed(chain):
    del chain[2]["verification_results"]
    reseal(chain[2])
    found = codes(verify_bundle({"envelopes": chain}))
    assert "VERIFICATION_RESULTS_EMPTY" in found
    assert "REQUIRED_FIELD_MISSING" in found


def test_free_text_results_are_refused_on_a_failed_receipt(chain, bundle_validator):
    failed = json.loads((EXAMPLES / "05-failed-partial-state.json").read_text("utf-8"))
    failed["envelopes"][2]["verification_results"] = ["it broke", "trust me"]
    reseal(failed["envelopes"][2])
    assert "VERIFICATION_RESULT_MALFORMED" in codes(verify_bundle(failed))
    assert schema_errors(bundle_validator, failed["envelopes"])


def test_a_result_that_is_not_an_object_is_refused(chain):
    chain[2]["verification_results"] = ["all checks passed"]
    reseal(chain[2])
    assert "VERIFICATION_RESULT_MALFORMED" in codes(verify_bundle({"envelopes": chain}))


@pytest.mark.parametrize("blank", [" ", "\u200b", "\t\n"])
def test_a_blank_check_identifier_certifies_nothing(chain, bundle_validator, blank):
    chain[2]["verification_results"] = [
        {"check_id": blank, "check_type": blank, "passed": True}]
    reseal(chain[2])
    assert "VERIFICATION_RESULT_MALFORMED" in codes(verify_bundle({"envelopes": chain}))
    assert schema_errors(bundle_validator, chain)


def test_a_success_whose_every_check_failed_is_a_finding(chain):
    chain[2]["verification_results"] = [
        {"check_id": "chk-a", "check_type": "service_health", "passed": False}]
    reseal(chain[2])
    assert "SUCCESS_CONTRADICTS_RESULTS" in codes(verify_bundle({"envelopes": chain}))


def test_a_success_with_a_mix_of_outcomes_is_left_to_the_control_plane(chain):
    """Which checks were required is not the protocol runtime's question."""
    chain[2]["verification_results"] = [
        {"check_id": "chk-a", "check_type": "service_health", "passed": True},
        {"check_id": "chk-b", "check_type": "deployment_status", "passed": False}]
    reseal(chain[2])
    assert verify_bundle({"envelopes": chain}) == []


# ── one transaction, one outcome ────────────────────────────────────────────

def test_two_receipts_disagreeing_on_the_outcome_are_a_finding(chain):
    request, decision, receipt = chain
    other = copy.deepcopy(receipt)
    other["status"] = "failed"
    other["reason_codes"] = ["ACTION_FAILED"]
    other["receipt_id"] = "rcpt-second"
    reseal(other)
    findings = verify_bundle({"envelopes": [request, decision, receipt, other]})
    assert "CONFLICTING_RECEIPTS" in codes(findings)


def test_a_second_receipt_agreeing_on_the_outcome_is_not_a_finding(chain):
    """SPEC allows several envelopes per transaction; only disagreement is a defect."""
    request, decision, receipt = chain
    other = copy.deepcopy(receipt)
    other["receipt_id"] = "rcpt-second"
    reseal(other)
    assert verify_bundle({"envelopes": [request, decision, receipt, other]}) == []


# ── the reported numbers must be true ───────────────────────────────────────

def test_repeated_entries_do_not_inflate_the_reported_count(tmp_path, chain):
    doc = {"envelopes": chain + [copy.deepcopy(chain[2]) for _ in range(19)]}
    path = tmp_path / "repeats.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    proc = _run_verify(path)
    assert "22 envelope(s) (3 distinct)" in proc.stdout


def test_a_bundle_with_no_references_does_not_claim_linkage(tmp_path, chain):
    doc = {"envelopes": [chain[0]]}
    path = tmp_path / "request-only.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 0
    assert "no request references present" in proc.stdout


def test_resolved_reference_count_matches_the_chain(chain):
    assert resolved_reference_count({"envelopes": chain}) == 2


# ── unreadable input is not a verification verdict ──────────────────────────

def test_duplicate_json_member_names_are_refused(tmp_path):
    path = tmp_path / "dup.json"
    path.write_text('{"envelope_type": "execution_receipt", "envelope_type": "x"}',
                    encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 2
    assert "unambiguous" in proc.stderr


@pytest.mark.parametrize("content", ["not json", ""])
def test_unreadable_input_exits_two_not_one(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 2, "an unreadable file must not look like a failed verification"
    assert "Traceback" not in proc.stderr


def test_a_missing_file_exits_two_without_a_traceback(tmp_path):
    proc = _run_verify(tmp_path / "nope.json")
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr


def test_an_unhashable_transaction_id_is_a_finding_not_a_crash():
    findings = verify_bundle([{
        "ztap_version": "1.0-draft",
        "envelope_type": "transaction_request",
        "transaction_id": ["not", "a", "string"],
        "integrity": {"hash_algorithm": "SHA-256", "canonicalization": "RFC8785-JCS",
                      "hash_value": "x"},
    }])
    assert "TRANSACTION_ID_MISSING" in codes(findings)


# ── the CI gate itself must stay wired ──────────────────────────────────────

def test_ci_runs_the_test_suite():
    """The audit's regression case: CI stayed green with the runtime unable to parse."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "validate.yml").read_text("utf-8")
    assert "pytest tests/" in workflow


def test_the_release_workflow_runs_the_test_suite():
    workflow = (REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text("utf-8")
    assert "pytest tests/" in workflow


# ── wave-2 regressions: the fixes themselves ────────────────────────────────

@pytest.mark.parametrize("blank", [" ", "\u200b", "\t\n", "\u200b \u200b \u200b",
                                   " \u200b\t\u200c "])
def test_no_arrangement_of_invisible_characters_reads_as_an_identifier(blank):
    """A strip chain is defeated by alternating whitespace and zero-width marks."""
    assert _has_content(blank) is False


def test_a_visible_identifier_is_accepted():
    assert _has_content("chk-01") is True
    assert _has_content(" \u200b x \u200b ") is True


def test_invisible_identifiers_are_refused_by_runtime_and_schema(chain, bundle_validator):
    chain[2]["verification_results"] = [
        {"check_id": "\u200b \u200b", "check_type": "\u200b \u200b", "passed": True}]
    reseal(chain[2])
    assert "VERIFICATION_RESULT_MALFORMED" in codes(verify_bundle({"envelopes": chain}))
    assert schema_errors(bundle_validator, chain)


def test_an_invisible_transaction_id_is_refused(chain, bundle_validator):
    for env in chain:
        env["transaction_id"] = "\u200b \u200b"
        reseal(env)
    assert "TRANSACTION_ID_MISSING" in codes(verify_bundle({"envelopes": chain}))
    assert schema_errors(bundle_validator, chain), \
        "the schema still accepts a transaction_id that names nothing"


def test_the_schema_applies_the_visible_rule_to_transaction_id():
    """The rule is only enforced where it is referenced."""
    envelope_schema = json.loads(
        (SCHEMAS / "ztip-envelope.schema.json").read_text("utf-8"))
    txn = envelope_schema["$defs"]["common_envelope"]["properties"]["transaction_id"]
    assert txn == {"$ref": "#/$defs/visible_string"}


# ── wrapper content is disclosed, not refused ───────────────────────────────

def test_an_export_wrapper_with_metadata_still_verifies(chain):
    """A real audit-trail export carries export metadata. The duty is to report
    that content, not to refuse the bundle."""
    doc = {"envelopes": chain, "export_id": "exp-1", "exported_at": "2026-09-02T00:00:00Z"}
    assert verify_bundle(doc) == []
    assert unverified_bundle_keys(doc) == ["export_id", "exported_at"]


def test_the_cli_discloses_unverified_wrapper_content(tmp_path, chain):
    path = tmp_path / "export.json"
    path.write_text(json.dumps({"envelopes": chain, "summary": "approved by the CFO"}),
                    encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 0
    assert "summary" in proc.stdout
    assert "not hashed and was not verified" in proc.stdout


def test_annotation_keys_are_reported_as_sidecar_content(chain):
    """An annotation is still unverified content beside the envelopes. Excluding
    it would make the disclosure opt-out at the bundle author's choice."""
    assert unverified_bundle_keys({"envelopes": chain, "_note": "hi"}) == ["_note"]


def test_the_disclosure_marks_which_keys_are_annotations(tmp_path, chain):
    path = tmp_path / "annotated.json"
    path.write_text(json.dumps({"envelopes": chain, "_note": "hi", "summary": "x"}),
                    encoding="utf-8")
    proc = _run_verify(path)
    assert '"_note" (annotation)' in proc.stdout
    assert '"summary"' in proc.stdout


def test_a_declared_signature_this_runtime_cannot_check_is_named(tmp_path, chain):
    chain[2]["integrity"]["signed"] = True
    reseal(chain[2])
    path = tmp_path / "signed.json"
    path.write_text(json.dumps({"envelopes": chain}), encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 0
    assert "does not check signatures" in proc.stdout


def test_the_scope_note_says_schema_validation_did_not_run():
    proc = _run_verify(EXAMPLES / "01-auto-authorized-success.json")
    assert "not validated against the schemas" in proc.stdout


def test_a_single_envelope_is_never_read_as_a_wrapper(chain):
    """An envelope that lost its envelope_type must not have its own fields
    reported as unverified content beside the envelopes."""
    receipt = chain[2]
    del receipt["envelope_type"]
    assert unverified_bundle_keys(receipt) == []
    found = codes(verify_bundle(receipt))
    assert "ENVELOPE_TYPE_UNKNOWN" in found


# ── counts must be measured on the hashed form ──────────────────────────────

def test_a_duplicate_cannot_hide_behind_an_annotation_field(tmp_path, chain):
    twin = copy.deepcopy(chain[2])
    twin["_copy"] = "2"          # outside the hash, so this is the same envelope
    path = tmp_path / "twins.json"
    path.write_text(json.dumps({"envelopes": chain + [twin]}), encoding="utf-8")
    proc = _run_verify(path)
    assert "4 envelope(s) (3 distinct)" in proc.stdout


def test_partial_mode_still_reports_how_many_references_resolved(tmp_path, chain):
    orphan = copy.deepcopy(chain[2])
    orphan["transaction_id"] = "ztip-txn-elsewhere"
    orphan["receipt_id"] = "rcpt-orphan"
    reseal(orphan)
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"envelopes": chain + [orphan]}), encoding="utf-8")
    proc = _run_verify(path, "--allow-unresolved-refs")
    assert proc.returncode == 0
    assert "2 of 3 request reference(s) resolved" in proc.stdout


# ── a required field that is present but null is not carried ────────────────

def test_a_null_required_field_is_missing(chain):
    chain[2]["atomicity_result"] = None
    reseal(chain[2])
    assert "REQUIRED_FIELD_MISSING" in codes(verify_bundle({"envelopes": chain}))


# ── unreadable input, on every command ──────────────────────────────────────

def test_a_non_utf8_file_is_unreadable_not_unverified(tmp_path):
    path = tmp_path / "binary.json"
    path.write_bytes(b'\xff\xfe{"a":1}')
    proc = _run_verify(path)
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr


def test_hash_refuses_an_unhashable_envelope_without_a_traceback(tmp_path):
    path = tmp_path / "float.json"
    path.write_text(json.dumps([{
        "ztap_version": "1.0-draft", "envelope_type": "evidence_record",
        "transaction_id": "t", "value": 1.5, "integrity": {"hash_value": "x"}}]),
        encoding="utf-8")
    proc = _run_hash(path)
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr


def test_hash_refuses_an_empty_bundle(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    proc = _run_hash(path)
    assert proc.returncode == 2, "hashing nothing must not exit 0"


# ── the two shipped tools must agree on what a document is ──────────────────

def test_the_validator_and_the_runtime_use_the_same_splitter(tmp_path, chain):
    """The decoy: a vacuous receipt hiding behind an `envelopes` key. Both shipped
    tools must read it as one envelope, or one blesses what the other refuses.

    This runs the real validator script, not a re-implementation of it."""
    request, _decision, receipt = chain
    receipt["verification_results"] = []
    receipt["envelopes"] = [copy.deepcopy(request)]
    reseal(receipt)
    assert envelopes(receipt) == [receipt]
    assert "VERIFICATION_RESULTS_EMPTY" in codes(verify_bundle(receipt))

    (tmp_path / "decoy.json").write_text(json.dumps(receipt), encoding="utf-8")
    proc = _run_validator(tmp_path)
    assert proc.returncode == 1, \
        "the shipped validator read the decoy as a wrapper and blessed it"


def test_the_shipped_validator_checks_timestamp_formats(tmp_path, chain):
    chain[2]["completed_at"] = "definitely not a date"
    reseal(chain[2])
    (tmp_path / "bad-time.json").write_text(
        json.dumps({"envelopes": chain}), encoding="utf-8")
    proc = _run_validator(tmp_path)
    assert proc.returncode == 1, "the shipped validator does not check date-time formats"
    assert "date-time" in proc.stdout


def test_the_shipped_validator_names_the_field_that_failed(tmp_path, chain):
    """A stricter validator that dumps the whole document tells a contributor
    nothing about what to fix."""
    chain[2]["verification_results"] = []
    reseal(chain[2])
    (tmp_path / "empty-results.json").write_text(
        json.dumps({"envelopes": chain}), encoding="utf-8")
    proc = _run_validator(tmp_path)
    assert proc.returncode == 1
    assert "$[2].verification_results" in proc.stdout


def test_both_shipped_tools_refuse_the_same_ambiguous_document(tmp_path):
    """The splitter is shared; so must the parser be. A last-wins reading of a
    duplicated member changed a receipt's status in one tool and not the other."""
    src = (EXAMPLES / "05-failed-partial-state.json").read_text("utf-8")
    dup = src.replace('"status": "failed"', '"status": "failed", "status": "succeeded"', 1)
    assert dup != src
    (tmp_path / "dup.json").write_text(dup, encoding="utf-8")

    validator = _run_validator(tmp_path)
    assert validator.returncode == 1
    assert "ambiguous JSON" in validator.stdout
    assert "Traceback" not in validator.stderr

    cli = _run_verify(tmp_path / "dup.json")
    assert cli.returncode == 2


def test_the_shipped_validator_accepts_the_real_examples():
    proc = _run_validator(EXAMPLES)
    assert proc.returncode == 0


def test_an_envelope_with_a_payload_key_is_not_a_wrapper(chain):
    """The decoy shape again, through the disclosure path: the outer object is an
    envelope, so its own fields are not 'content beside the envelopes'."""
    request, _decision, receipt = chain
    receipt["envelopes"] = [copy.deepcopy(request)]
    reseal(receipt)
    assert unverified_bundle_keys(receipt) == []


def test_every_schema_reference_resolves(bundle_validator):
    """A registry that fails to resolve makes the schemas accept everything. This
    checks the real registry, not an empty one."""
    registry = schema_registry()
    resolver = registry.resolver()
    unresolved = []
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        doc = json.loads(path.read_text("utf-8"))
        base = resolver.lookup(path.name).resolver
        for ref in _refs(doc):
            try:
                base.lookup(ref)
            except Exception:  # noqa: BLE001
                unresolved.append(f"{path.name} -> {ref}")
    assert unresolved == [], f"unresolvable references: {unresolved}"


def _refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def test_timestamp_formats_are_actually_checked(chain, bundle_validator):
    """`format` is annotation-only unless a format checker is installed."""
    chain[2]["completed_at"] = "definitely not a date"
    reseal(chain[2])
    assert schema_errors(bundle_validator, chain), \
        "format checking is not active — 'format': 'date-time' validates nothing"


# ── the spec's own worked examples must satisfy the spec ────────────────────

# ── wave-3 regressions ──────────────────────────────────────────────────────

@pytest.mark.parametrize("hide", ["null", "delete"])
def test_an_envelope_cannot_become_a_wrapper_by_hiding_its_type(tmp_path, chain, hide):
    """The decoy again: dropping or nulling `envelope_type` must not turn a
    vacuous receipt into a wrapper whose payload gets counted instead of it."""
    request, _decision, receipt = chain
    receipt["verification_results"] = []
    if hide == "null":
        receipt["envelope_type"] = None
    else:
        del receipt["envelope_type"]
    receipt["envelopes"] = [copy.deepcopy(request)]
    reseal(receipt)
    assert envelopes(receipt) == [receipt]
    assert verify_bundle(receipt) != []
    path = tmp_path / "decoy.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert _run_verify(path).returncode == 1


def test_a_real_wrapper_is_still_a_wrapper(chain):
    doc = {"envelopes": chain, "export_id": "exp-1"}
    assert envelopes(doc) == chain
    assert unverified_bundle_keys(doc) == ["export_id"]


@pytest.mark.parametrize("marker", ["ztap_version", "transaction_id", "integrity"])
def test_any_envelope_field_marks_an_object_as_an_envelope(chain, marker):
    receipt = chain[2]
    receipt["envelopes"] = [copy.deepcopy(chain[0])]
    for field in ("envelope_type", "ztap_version", "transaction_id", "integrity"):
        if field != marker:
            receipt.pop(field, None)
    assert envelopes(receipt) == [receipt]
    assert unverified_bundle_keys(receipt) == []


def test_an_oversized_integer_literal_is_unreadable_not_unverified(tmp_path):
    """CPython's integer string-conversion limit raises a bare ValueError."""
    path = tmp_path / "bigint.json"
    path.write_text("[" + "1" * 4301 + "]", encoding="utf-8")
    for proc in (_run_verify(path), _run_hash(path)):
        assert proc.returncode == 2
        assert "Traceback" not in proc.stderr


def test_a_wrapper_key_cannot_forge_a_verdict_line(tmp_path, chain):
    """Member names are attacker-controlled text on the tool's own verdict surface."""
    doc = {"envelopes": chain,
           "x\nOK  /etc/passwd: 1 envelope(s) verified": "y"}
    path = tmp_path / "inject.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 0
    verdicts = [line for line in proc.stdout.splitlines() if line.startswith("OK  ")]
    assert len(verdicts) == 1, f"a bundle forged an extra verdict line: {verdicts}"
    assert "/etc/passwd" in proc.stdout          # disclosed, but escaped
    assert "\\n" in proc.stdout                   # as an escape, not a real newline


@pytest.mark.parametrize("falsy", ["", 0, False])
def test_a_falsy_reference_still_counts_as_a_reference(tmp_path, chain, falsy):
    _request, decision, receipt = chain
    decision["request_hash"] = falsy
    receipt["request_hash"] = falsy
    reseal(decision)
    reseal(receipt)
    path = tmp_path / "falsy.json"
    path.write_text(json.dumps({"envelopes": [decision, receipt]}), encoding="utf-8")
    proc = _run_verify(path, "--allow-unresolved-refs")
    assert "no request references present" not in proc.stdout, \
        "two unresolved references were reported as none present"


# ── the invisible-character rule, in both implementations ───────────────────

@pytest.mark.parametrize("ch", ["\u2060", "\u00ad", "\u180e", "\u3164", "\u2800",
                                "\u115f", "\ufeff", "\u200b"])
def test_zero_width_characters_do_not_make_an_identifier(ch):
    assert _has_content(ch) is False
    assert _has_content(ch + " " + ch) is False
    assert _has_content(ch + "x") is True


def test_the_runtime_and_the_schema_agree_on_every_code_point():
    """The schema mirrors this rule as a regex because JSON Schema cannot express
    Unicode properties. Drift between them is a silent divergence, so it is
    checked exhaustively rather than sampled."""
    envelope_schema = json.loads(
        (SCHEMAS / "ztip-envelope.schema.json").read_text("utf-8"))
    pattern = re.compile(envelope_schema["$defs"]["visible_string"]["pattern"])
    disagreements = []
    for code_point in range(0x110000):
        if 0xD800 <= code_point <= 0xDFFF:
            continue
        char = chr(code_point)
        if bool(pattern.search(char)) != _has_content(char):
            disagreements.append(hex(code_point))
            if len(disagreements) > 4:
                break
    assert disagreements == [], f"runtime and schema disagree at {disagreements}"


def test_the_invisible_set_is_not_empty():
    """Guards the exhaustive test above against a vacuous pass."""
    assert len(set(_INVISIBLE)) >= 10


def test_the_validator_refuses_to_run_without_timestamp_checking(tmp_path):
    """A format checker with no date-time checker validates nothing. Silently
    passing in that state is the exact vacuity this suite exists to prevent."""
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "rfc3339_validator.py").write_text(
        "raise ImportError('blocked for this test')", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(stub))
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate-examples.py"),
         str(EXAMPLES)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=env)
    assert proc.returncode == 1
    assert "date-time format checking is unavailable" in proc.stdout


# ── wave-4 regressions: a result the seal does not cover ────────────────────

def test_a_result_keyed_by_an_annotation_name_does_not_count(chain, bundle_validator):
    """The hash strips underscore keys, so the same hash describes this receipt
    with the result and without it. It cannot satisfy the non-empty rule."""
    receipt = chain[2]
    receipt["verification_results"] = {
        "_ghost": {"check_id": "c1", "check_type": "assertion", "passed": True}}
    reseal(receipt)
    found = codes(verify_bundle({"envelopes": chain}))
    assert "VERIFICATION_RESULT_UNSEALED" in found
    assert "VERIFICATION_RESULTS_EMPTY" in found
    assert schema_errors(bundle_validator, chain)


def test_the_ghost_result_hashes_identically_to_no_result(chain):
    """The property that makes it a vacuity, stated as a test."""
    receipt = chain[2]
    receipt["verification_results"] = {
        "_ghost": {"check_id": "c1", "check_type": "assertion", "passed": True}}
    with_ghost = envelope_hash(receipt)
    receipt["verification_results"] = {}
    assert envelope_hash(receipt) == with_ghost


def test_an_annotation_key_alongside_a_real_result_is_still_reported(chain):
    receipt = chain[2]
    receipt["verification_results"] = {
        "chk-a": {"check_id": "chk-a", "check_type": "service_health", "passed": True},
        "_ghost": {"check_id": "c1", "check_type": "assertion", "passed": True}}
    reseal(receipt)
    found = codes(verify_bundle({"envelopes": chain}))
    assert "VERIFICATION_RESULT_UNSEALED" in found
    assert "VERIFICATION_RESULTS_EMPTY" not in found


# ── the schemas alone must accept the conformance corpus ────────────────────

def test_the_bundle_schema_accepts_the_shipped_example_files_as_written(bundle_validator):
    """An implementer building from schemas/ alone must not reject all ten
    examples because the wrapper they use was never described."""
    for path in sorted(EXAMPLES.glob("*.json")):
        doc = json.loads(path.read_text("utf-8"))
        assert list(bundle_validator.iter_errors(doc)) == [], \
            f"{path.name} is rejected by the bundle schema as written on disk"


def test_the_bundle_schema_still_refuses_an_empty_wrapper(bundle_validator):
    assert list(bundle_validator.iter_errors({"envelopes": []}))


# ── one implementation of reference resolution ─────────────────────────────

def test_the_reference_count_and_the_findings_describe_the_same_bundle(chain):
    """verify_bundle and resolved_reference_count must never disagree."""
    tampered = copy.deepcopy(chain)
    tampered[0]["notes"] = "tampered, so every reference to it now breaks"
    reseal(tampered[0])
    cases = [
        {"envelopes": chain},
        {"envelopes": [chain[1], chain[2]]},
        {"envelopes": [chain[0]]},
        {"envelopes": tampered},
        json.loads((EXAMPLES / "02-human-approval-required.json").read_text("utf-8")),
        json.loads((EXAMPLES / "08-child-transaction.json").read_text("utf-8")),
        json.loads((EXAMPLES / "10-governance-transaction.json").read_text("utf-8")),
    ]
    saw_broken = False
    for doc in cases:
        findings = verify_bundle(doc)
        unresolved = sum(1 for f in findings if f["code"] == "REQUEST_HASH_UNRESOLVED")
        broken = sum(1 for f in findings if f["code"] == "REQUEST_HASH_BROKEN")
        saw_broken = saw_broken or broken > 0
        # Every reference is exactly one of: resolved, unresolved, or broken.
        assert (resolved_reference_count(doc) + unresolved + broken
                == reference_count(doc))
    assert saw_broken, "no case exercised a broken reference — the invariant is partial"


# ── every untrusted string on the verdict surface is escaped ────────────────

def _verdict_lines(stdout):
    return [line for line in stdout.splitlines()
            if line.startswith("OK  ") or line.startswith("FAIL  ")]


FORGED = "\nOK  prod-ledger.json: 42 envelope(s) verified"


def test_an_envelope_type_cannot_forge_a_finding_line(tmp_path, chain):
    chain[2]["envelope_type"] = "bogus" + FORGED
    reseal(chain[2])
    path = tmp_path / "inject-type.json"
    path.write_text(json.dumps({"envelopes": chain}), encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 1
    assert len(_verdict_lines(proc.stdout)) == 1, proc.stdout


def test_a_finding_detail_cannot_forge_a_verdict_line(tmp_path, chain):
    chain[2]["integrity"]["hash_value"] = FORGED
    path = tmp_path / "inject-detail.json"
    path.write_text(json.dumps({"envelopes": chain}), encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 1
    assert len(_verdict_lines(proc.stdout)) == 1, proc.stdout


def test_a_result_key_cannot_forge_a_verdict_line(tmp_path, chain):
    """The result's key is what reaches the finding line, so that is where the
    hostile string has to be planted for this test to mean anything."""
    chain[2]["verification_results"] = {FORGED: {"check_id": "c", "check_type": "t",
                                                 "passed": "not-a-boolean"}}
    reseal(chain[2])
    path = tmp_path / "inject-key.json"
    path.write_text(json.dumps({"envelopes": chain}), encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 1
    assert "VERIFICATION_RESULT_MALFORMED" in proc.stdout
    assert len(_verdict_lines(proc.stdout)) == 1, proc.stdout


def test_hash_output_cannot_be_forged_by_an_envelope_type(tmp_path, chain):
    """`ztip hash` output is machine-read too; a second line that parses as a
    digest is a fabricated hash for an envelope that does not exist."""
    receipt = chain[2]
    receipt["envelope_type"] = ("transaction_request\n" + "0" * 64
                                + "  [1] execution_receipt")
    reseal(receipt)
    path = tmp_path / "hash-inject.json"
    path.write_text(json.dumps([receipt]), encoding="utf-8")
    proc = _run_hash(path)
    assert proc.returncode == 0
    digest_lines = [line for line in proc.stdout.splitlines() if "  [" in line]
    assert len(digest_lines) == 1, proc.stdout


@pytest.mark.parametrize("valid", [True, False])
def test_a_hostile_file_name_cannot_forge_a_verdict_line(tmp_path, chain, valid):
    """Both verdict lines are forgeable surfaces; the OK line is the one an
    attacker wants."""
    hostile = tmp_path / ("evil" + FORGED + "_.json")
    body = json.dumps({"envelopes": chain}) if valid else "[]"
    try:
        hostile.write_text(body, encoding="utf-8")
    except OSError:
        pytest.skip("this filesystem rejects newlines in names")
    proc = _run_verify(hostile)
    assert proc.returncode == (0 if valid else 1)
    assert len(_verdict_lines(proc.stdout)) == 1, proc.stdout


def test_the_validator_output_cannot_be_forged_by_a_file_name(tmp_path, chain):
    hostile = tmp_path / ("aa\nPASS 99-forged.json\n"
                          "Validation completed successfully: 99 example file(s) "
                          "passed..json")
    try:
        hostile.write_text(json.dumps({"envelopes": chain}), encoding="utf-8")
    except OSError:
        pytest.skip("this filesystem rejects newlines in names")
    proc = _run_validator(tmp_path)
    forged = [line for line in proc.stdout.splitlines()
              if line.startswith("PASS ") or line.startswith("Validation completed")]
    assert len(forged) == 2, f"the file name forged validator output:\n{proc.stdout}"


def test_a_finding_detail_is_escaped_for_library_consumers(chain):
    """The CLI escapes on the way out, but `verify_bundle`'s detail is read
    directly by other code."""
    chain[2]["verification_results"] = {FORGED: {"check_id": "c", "check_type": "t",
                                                 "passed": "not-a-boolean"}}
    reseal(chain[2])
    details = [f["detail"] for f in verify_bundle({"envelopes": chain})
               if f["code"] == "VERIFICATION_RESULT_MALFORMED"]
    assert details
    assert all("\n" not in detail for detail in details), details


# ── an empty-string reference is a reference ────────────────────────────────

def test_a_falsy_reference_is_still_resolved_or_reported(chain):
    """Guarded at the library, not only in the CLI's tally line."""
    _request, decision, receipt = chain
    decision["request_hash"] = ""
    receipt["request_hash"] = ""
    reseal(decision)
    reseal(receipt)
    findings = verify_bundle({"envelopes": [decision, receipt]})
    assert [f["code"] for f in findings].count("REQUEST_HASH_UNRESOLVED") == 2


# ── the boundary of the wrapper rule, stated as a test ─────────────────────

def test_an_object_with_no_envelope_fields_at_all_is_a_wrapper(chain):
    """Stripping every ZTIP field leaves something that is not an envelope by any
    definition. It is read as a wrapper, and everything it carries is disclosed."""
    receipt = chain[2]
    for field in ("ztap_version", "envelope_type", "transaction_id", "integrity"):
        receipt.pop(field, None)
    receipt["envelopes"] = [copy.deepcopy(chain[0])]
    assert envelopes(receipt) == receipt["envelopes"]
    disclosed = unverified_bundle_keys(receipt)
    assert "status" in disclosed and "verification_results" in disclosed


def test_an_envelope_carrying_a_payload_says_the_payload_was_not_verified(tmp_path, chain):
    receipt = chain[2]
    receipt["envelopes"] = [copy.deepcopy(chain[0])]
    reseal(receipt)
    path = tmp_path / "nested.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    proc = _run_verify(path)
    assert "were not verified as separate envelopes" in proc.stdout


# ── the schema regex must mean the same thing in every engine ──────────────

def test_the_visible_pattern_uses_no_engine_dependent_shorthand():
    """JSON Schema specifies ECMA-262 regex semantics; Python's \\s covers code
    points ECMA-262's does not, so the shorthand would make the schema and the
    runtime disagree for any non-Python implementer."""
    envelope_schema = json.loads(
        (SCHEMAS / "ztip-envelope.schema.json").read_text("utf-8"))
    pattern = envelope_schema["$defs"]["visible_string"]["pattern"]
    for shorthand in ("\\s", "\\S", "\\w", "\\W", "\\d", "\\D", "\\b"):
        assert shorthand not in pattern, f"{shorthand} is engine-dependent"


# ── wave-5 regressions ─────────────────────────────────────────────────────

def test_the_validator_output_cannot_be_forged_by_a_member_name(tmp_path, chain):
    """The validator's own PASS lines are a parseable surface, and its input is
    by definition an untrusted submitted document."""
    chain[2]["verification_results"] = {
        "ok\nPASS 99-forged.json\nValidation completed successfully: 99 example file(s) "
        "passed.": {"check_id": "c", "check_type": "t", "passed": "yes"}}
    reseal(chain[2])
    (tmp_path / "evil.json").write_text(json.dumps({"envelopes": chain}), encoding="utf-8")
    proc = _run_validator(tmp_path)
    assert proc.returncode == 1
    forged = [line for line in proc.stdout.splitlines()
              if line.startswith("PASS ") or line.startswith("Validation completed")]
    assert len(forged) == 1, f"the document forged validator output:\n{proc.stdout}"
    assert forged[0].startswith("Validation completed with")


def test_a_verified_bundle_stays_verified_on_an_ascii_terminal(tmp_path):
    """The verdict must not depend on what the terminal can encode."""
    env = dict(os.environ, PYTHONIOENCODING="ascii")
    proc = subprocess.run(
        [sys.executable, "-m", "ztip.cli", "verify",
         str(EXAMPLES / "01-auto-authorized-success.json")],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=env)
    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr
    assert proc.stdout.startswith("OK  ")


def test_a_nested_payload_inside_a_wrapper_is_still_disclosed(tmp_path, chain):
    request, decision, receipt = chain
    receipt["envelopes"] = [copy.deepcopy(request), copy.deepcopy(decision)]
    reseal(receipt)
    path = tmp_path / "nested-in-wrapper.json"
    path.write_text(json.dumps({"envelopes": [request, decision, receipt]}),
                    encoding="utf-8")
    proc = _run_verify(path)
    assert "were not verified as separate envelopes" in proc.stdout


def test_the_hash_tool_refuses_an_ambiguous_document(tmp_path):
    """The third shipped tool that reads example bundles."""
    work = tmp_path / "examples"
    work.mkdir()
    for path in sorted(EXAMPLES.glob("*.json")):
        (work / path.name).write_text(path.read_text("utf-8"), encoding="utf-8")
    (work / "99-dup.json").write_text('{"envelopes": [{"a": 1, "a": 2}]}',
                                      encoding="utf-8")
    script = REPO_ROOT / "scripts" / "recompute_example_hashes.py"
    proc = subprocess.run([sys.executable, str(script), str(work)],
                          capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert proc.returncode == 1
    assert "ambiguous JSON" in proc.stdout
    assert "Traceback" not in proc.stderr
    for path in sorted(EXAMPLES.glob("*.json")):
        assert (work / path.name).read_text("utf-8") == path.read_text("utf-8"), \
            f"{path.name} was rewritten"


def test_the_hash_tool_is_a_no_op_on_the_real_corpus(tmp_path):
    work = tmp_path / "examples"
    work.mkdir()
    for path in sorted(EXAMPLES.glob("*.json")):
        (work / path.name).write_text(path.read_text("utf-8"), encoding="utf-8")
    script = REPO_ROOT / "scripts" / "recompute_example_hashes.py"
    for flags in ([], ["--refresh"]):
        proc = subprocess.run([sys.executable, str(script), str(work), *flags],
                              capture_output=True, text=True, cwd=str(REPO_ROOT))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        for path in sorted(EXAMPLES.glob("*.json")):
            assert (work / path.name).read_text("utf-8") == path.read_text("utf-8"), \
                f"{path.name} changed under {flags or ['(no flags)']}"


# ── an approval must bind to the work it approved ───────────────────────────

@pytest.fixture()
def approval_chain():
    doc = json.loads((EXAMPLES / "02-human-approval-required.json").read_text("utf-8"))
    return copy.deepcopy(doc["envelopes"])


def _approval_scope(envs):
    for env in envs:
        scope = (env.get("human_approval_ref") or {}).get("approval_scope")
        if isinstance(scope, dict):
            return env, scope
    raise AssertionError("example 02 no longer carries an approval scope")


def test_the_shipped_approval_example_resolves_its_scope(approval_chain):
    """Guards the tests below against a corpus change that makes them vacuous."""
    _env, scope = _approval_scope(approval_chain)
    assert scope["request_hash"] and scope["transaction_id"]
    assert reference_count({"envelopes": approval_chain}) == 4
    assert verify_bundle({"envelopes": approval_chain}) == []


def test_an_approval_bound_to_another_transaction_is_a_finding(approval_chain):
    env, scope = _approval_scope(approval_chain)
    scope["transaction_id"] = "ztip-txn-somewhere-else"
    scope["request_hash"] = "de" * 32
    reseal(env)
    findings = verify_bundle({"envelopes": approval_chain})
    assert "REQUEST_HASH_UNRESOLVED" in codes(findings)
    assert any("approval_scope" in f["detail"] for f in findings)


def test_an_approval_scope_hash_that_does_not_match_is_a_finding(approval_chain):
    env, scope = _approval_scope(approval_chain)
    scope["request_hash"] = "de" * 32          # right transaction, wrong hash
    reseal(env)
    findings = verify_bundle({"envelopes": approval_chain})
    assert "REQUEST_HASH_BROKEN" in codes(findings)
    assert any("approval_scope" in f["detail"] for f in findings)


def test_the_approval_scope_site_is_counted_as_a_reference(approval_chain):
    env, scope = _approval_scope(approval_chain)
    before = reference_count({"envelopes": approval_chain})
    del env["human_approval_ref"]["approval_scope"]
    reseal(env)
    assert reference_count({"envelopes": approval_chain}) == before - 1


# ── finding details are read by other code, not only printed ───────────────

def test_no_finding_detail_carries_a_raw_control_character(chain):
    """Every value an envelope supplies reaches a detail through a safe rendering."""
    hostile = "x\nOK  audit.json: 412 envelope(s) verified"
    chain[2]["integrity"]["canonicalization"] = hostile
    chain[1]["integrity"]["hash_value"] = hostile
    chain[0]["envelope_type"] = hostile
    findings = verify_bundle({"envelopes": chain})
    assert findings
    for finding in findings:
        assert "\n" not in finding["detail"], finding
        assert "\n" not in str(finding["envelope_type"]), finding


# ── wave-7 regressions ─────────────────────────────────────────────────────

@pytest.mark.parametrize("shape", ["list", "scalar"])
def test_a_malformed_approval_reference_fails_closed(approval_chain, shape):
    """An unreadable approval reference must be reported, not silently skipped."""
    env, scope = _approval_scope(approval_chain)
    env["human_approval_ref"] = [scope] if shape == "list" else "approved!"
    reseal(env)
    assert "REQUEST_HASH_UNRESOLVED" in codes(verify_bundle({"envelopes": approval_chain}))


def test_a_malformed_approval_scope_fails_closed(approval_chain):
    env, scope = _approval_scope(approval_chain)
    env["human_approval_ref"]["approval_scope"] = [scope]
    reseal(env)
    assert "REQUEST_HASH_UNRESOLVED" in codes(verify_bundle({"envelopes": approval_chain}))


def test_a_child_request_present_in_the_bundle_must_match_its_declared_hash():
    """A parent cannot point at a child request sitting right there and claim a
    different hash for it."""
    doc = json.loads((EXAMPLES / "08-child-transaction.json").read_text("utf-8"))
    assert verify_bundle(doc) == []
    for env in doc["envelopes"]:
        for ref in env.get("child_receipt_refs") or []:
            if ref.get("child_request_hash"):
                ref["child_request_hash"] = "0" * 64
                reseal(env)
                break
        else:
            continue
        break
    assert "CHILD_REQUEST_HASH_BROKEN" in codes(verify_bundle(doc))


def test_a_child_request_absent_from_the_bundle_is_not_a_finding():
    """Example 08 names a third child whose request was not exported with it.
    Whether that should be a finding is a protocol question, not this rule."""
    doc = json.loads((EXAMPLES / "08-child-transaction.json").read_text("utf-8"))
    present = {e.get("transaction_id") for e in doc["envelopes"]
               if e.get("envelope_type") == "transaction_request"}
    named = {ref.get("child_transaction_id")
             for env in doc["envelopes"] for ref in env.get("child_receipt_refs") or []}
    assert named - present, "example 08 no longer exercises an absent child"
    assert verify_bundle(doc) == []


def test_a_declared_signature_reference_is_named(tmp_path, chain):
    chain[2]["integrity"]["signature_ref"] = "kms://prod/key-7#sig-1"
    reseal(chain[2])
    path = tmp_path / "sigref.json"
    path.write_text(json.dumps({"envelopes": chain}), encoding="utf-8")
    proc = _run_verify(path)
    assert proc.returncode == 0
    assert "does not check signatures" in proc.stdout


# ── the hash tool answers for what it looked at ────────────────────────────

def _run_hash_tool(*args):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "recompute_example_hashes.py"), *args],
        capture_output=True, text=True, cwd=str(REPO_ROOT))


@pytest.mark.parametrize("target", ["empty", "missing", "not-a-dir"])
def test_the_hash_tool_refuses_to_report_success_over_nothing(tmp_path, target):
    """Its own rule: a pass that examined nothing is not a pass."""
    if target == "empty":
        (tmp_path / "empty").mkdir()
        arg = str(tmp_path / "empty")
    elif target == "missing":
        arg = str(tmp_path / "nowhere")
    else:
        arg = str(REPO_ROOT / "README.md")
    proc = _run_hash_tool(arg)
    assert proc.returncode == 1, proc.stdout


def test_the_hash_tool_escapes_the_file_name(tmp_path):
    work = tmp_path / "examples"
    work.mkdir()
    hostile = work / "bb\nDone: 0 total placeholder replacement(s).json"
    try:
        hostile.write_text(json.dumps(
            json.loads((EXAMPLES / "01-auto-authorized-success.json").read_text("utf-8"))),
            encoding="utf-8")
    except OSError:
        pytest.skip("this filesystem rejects newlines in names")
    proc = _run_hash_tool(str(work))
    done = [line for line in proc.stdout.splitlines() if line.startswith("Done:")]
    assert len(done) == 1, f"the file name forged a Done line:\n{proc.stdout}"


def test_the_hash_tool_reads_a_bundle_the_way_the_other_tools_do(tmp_path):
    """A bare array is a bundle for every other shipped tool."""
    work = tmp_path / "examples"
    work.mkdir()
    doc = json.loads((EXAMPLES / "01-auto-authorized-success.json").read_text("utf-8"))
    (work / "bare-array.json").write_text(json.dumps(doc["envelopes"]), encoding="utf-8")
    proc = _run_hash_tool(str(work))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr


@pytest.mark.parametrize("flags", [[], ["--refresh"]])
def test_the_hash_tool_argument_order_does_not_matter(tmp_path, flags):
    work = tmp_path / "examples"
    work.mkdir()
    for path in sorted(EXAMPLES.glob("*.json")):
        (work / path.name).write_text(path.read_text("utf-8"), encoding="utf-8")
    proc = _run_hash_tool(*flags, str(work))
    assert proc.returncode == 0, proc.stdout
    proc = _run_hash_tool(str(work), *flags)
    assert proc.returncode == 0, proc.stdout


# ── the payload disclosure counts every shape ──────────────────────────────

@pytest.mark.parametrize("payload,expected", [
    ([{"a": 1}, {"b": 2}], "2 entr"),
    ({"x": {"a": 1}, "y": {"b": 2}, "z": {}}, "3 entr"),
    ("not even a list", "1 entr"),
    (0, "1 entr"),
])
def test_a_payload_of_any_shape_is_disclosed(tmp_path, chain, payload, expected):
    receipt = chain[2]
    receipt["envelopes"] = payload
    reseal(receipt)
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    proc = _run_verify(path)
    assert expected in proc.stdout, proc.stdout


def readme_quickstart_claims(readme: str) -> list:
    """The output lines the README quickstart claims the tool prints.

    Raises if it finds none: a guard that goes green over an empty claim set is
    the defect this suite exists to refuse, and a README rewrite would otherwise
    disarm it silently.
    """
    block = readme.split("## Try It (60 seconds)", 1)[1].split("```", 2)[1]
    claimed = [line.lstrip("# ").rstrip() for line in block.splitlines()
               if line.startswith("#") and "OK  " in line or line.strip().startswith("#     ")]
    if len(claimed) < 3:
        raise AssertionError("the quickstart no longer shows output to check against")
    return claimed


def test_the_readme_claim_parser_refuses_an_empty_claim_set():
    """Guards the guard below."""
    with pytest.raises(AssertionError):
        readme_quickstart_claims(
            "## Try It (60 seconds)\n\n```bash\nztip verify x\n```\n")


def test_the_readme_quickstart_shows_what_the_tool_actually_prints():
    """The first thing a reader of a public protocol repo runs. Every line the
    quickstart claims must appear in the real output. The reverse — that the tool
    prints nothing the quickstart omits — is not checked here: the quickstart is
    an excerpt by design."""
    claimed = readme_quickstart_claims((REPO_ROOT / "README.md").read_text("utf-8"))
    # the quickstart uses a repo-relative path, and the tool echoes what it was given
    proc = _run_verify("examples/01-auto-authorized-success.json")
    actual = " ".join(proc.stdout.split())
    missing = [fragment for fragment in claimed
               if fragment.strip() and " ".join(fragment.split()) not in actual]
    assert not missing, ("README quickstart claims output the tool does not print:\n"
                         + "\n".join(missing) + "\n\nactual:\n" + proc.stdout)


@pytest.mark.parametrize("container", [{"a": 1}, "a string", 7, True])
def test_a_malformed_child_reference_container_fails_closed(container):
    """The container shape is attacker-chosen; skipping it would disable the
    check on request. Asserted on the container-level message, so it cannot be
    satisfied by the per-entry guard instead."""
    doc = json.loads((EXAMPLES / "08-child-transaction.json").read_text("utf-8"))
    for env in doc["envelopes"]:
        if env.get("child_receipt_refs"):
            env["child_receipt_refs"] = container
            reseal(env)
            break
    else:
        pytest.fail("example 08 no longer carries child_receipt_refs")
    findings = verify_bundle(doc)
    assert "CHILD_REQUEST_HASH_BROKEN" in codes(findings)
    assert any("child_receipt_refs is" in f["detail"] and "not an array" in f["detail"]
               for f in findings), findings


def test_a_non_object_child_reference_entry_fails_closed():
    doc = json.loads((EXAMPLES / "08-child-transaction.json").read_text("utf-8"))
    for env in doc["envelopes"]:
        if env.get("child_receipt_refs"):
            env["child_receipt_refs"] = ["just a string"]
            reseal(env)
            break
    assert "CHILD_REQUEST_HASH_BROKEN" in codes(verify_bundle(doc))


def test_an_approval_scope_that_binds_to_nothing_is_reported(approval_chain):
    """A scope with no request_hash declares no binding; dropping the site would
    lower the reported count with no signal that it did."""
    env, scope = _approval_scope(approval_chain)
    before = reference_count({"envelopes": approval_chain})
    del scope["request_hash"]
    reseal(env)
    assert reference_count({"envelopes": approval_chain}) == before
    assert "REQUEST_HASH_UNRESOLVED" in codes(verify_bundle({"envelopes": approval_chain}))


def test_a_hostile_repr_cannot_reach_a_finding_record():
    """A reference runtime is handed in-memory envelopes too, and repr() escapes
    strings but not an arbitrary object's __repr__."""
    class Hostile:
        def __repr__(self):
            return "hostile\nOK  audit.json: 9 envelope(s) verified"

    findings = verify_bundle([{
        "ztap_version": "1.0-draft", "envelope_type": Hostile(),
        "transaction_id": "t",
        "integrity": {"canonicalization": "RFC8785-JCS", "hash_algorithm": "SHA-256",
                      "hash_value": Hostile()},
    }])
    assert findings
    for finding in findings:
        assert "\n" not in finding["detail"], finding
        assert "\n" not in str(finding["envelope_type"]), finding


def test_the_bundle_schema_refuses_an_envelope_wearing_a_wrapper(bundle_validator, chain):
    """The schema-side twin of the splitter rule: an object declaring envelope
    fields is an envelope, so it cannot slip through the wrapper branch."""
    request, _decision, receipt = chain
    receipt["verification_results"] = []
    receipt["envelopes"] = [copy.deepcopy(request)]
    reseal(receipt)
    assert list(bundle_validator.iter_errors(receipt)), \
        "the bundle schema accepted a vacuous receipt as a wrapper"


def test_the_bundle_schema_still_accepts_a_real_wrapper(bundle_validator, chain):
    assert list(bundle_validator.iter_errors({"envelopes": chain, "_note": "x"})) == []


def _fenced_json_blocks(path):
    """Yield (line_number, parsed) for every ```json block in a markdown file."""
    lines = path.read_text("utf-8").splitlines()
    inside, start, buf = False, 0, []
    for number, line in enumerate(lines, 1):
        if not inside and line.strip() in ("```json", "```jsonc"):
            inside, start, buf = True, number, []
            continue
        if inside and line.strip() == "```":
            inside = False
            try:
                yield start, json.loads("\n".join(buf))
            except json.JSONDecodeError:
                continue          # prose fragments and partial snippets
            continue
        if inside:
            buf.append(line)


def test_the_worked_envelope_examples_in_the_docs_are_conformant(tmp_path):
    """A protocol document whose own canonical example fails its own schema
    teaches implementers the wrong shape. Checked with the shipped validator, so
    the failure message names the field."""
    written = 0
    for name in ("SCHEMA.md", "SPEC.md", "README.md", "CONFORMANCE.md"):
        for line_number, doc in _fenced_json_blocks(REPO_ROOT / name):
            candidates = doc if isinstance(doc, list) else [doc]
            for position, item in enumerate(candidates):
                if not isinstance(item, dict) or "envelope_type" not in item:
                    continue
                # Worked examples carry illustrative hashes, so integrity is not
                # checked here — only the shape the document teaches.
                probe = copy.deepcopy(item)
                probe["integrity"] = {
                    "canonicalization": "RFC8785-JCS",
                    "hash_algorithm": "SHA-256",
                    "hash_value": "0" * 64,
                }
                target = tmp_path / f"{name}-{line_number}-{position}.json"
                target.write_text(json.dumps([probe]), encoding="utf-8")
                written += 1
    assert written >= 3, f"only {written} worked envelope examples found — check is vacuous"
    proc = _run_validator(tmp_path)
    assert proc.returncode == 0, \
        f"the docs teach a non-conformant envelope shape:\n{proc.stdout}"


def test_the_docs_contain_worked_envelope_examples_to_check():
    """Guards the test above against silently checking nothing."""
    found = 0
    for name in ("SCHEMA.md", "SPEC.md"):
        for _line, doc in _fenced_json_blocks(REPO_ROOT / name):
            candidates = doc if isinstance(doc, list) else [doc]
            found += sum(1 for d in candidates
                         if isinstance(d, dict) and "envelope_type" in d)
    assert found >= 3, f"only {found} worked envelope examples found — the check is vacuous"


def _run_validator(examples_dir):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate-examples.py"),
         str(examples_dir)],
        capture_output=True, text=True, cwd=str(REPO_ROOT))


def _run_hash(path, *flags):
    return subprocess.run(
        [sys.executable, "-m", "ztip.cli", "hash", str(path), *flags],
        capture_output=True, text=True, cwd=str(REPO_ROOT))


def _run_verify(path, *flags):
    return subprocess.run(
        [sys.executable, "-m", "ztip.cli", "verify", str(path), *flags],
        capture_output=True, text=True, cwd=str(REPO_ROOT))
