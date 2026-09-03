"""``ztip`` command-line interface.

    ztip hash <file>     Print the SHA-256 (RFC 8785) hash of each envelope.
    ztip verify <file>   Recompute hashes, check the envelope floor, and resolve
                         references; fail-closed on any defect.

``verify`` reports how many envelopes it verified and how many references it
resolved. A bundle with nothing in it is a failure, not a pass: automation must
never be able to read "nothing to verify" as "everything verified".

Exit codes:

  0   verified
  1   integrity findings — the bundle is not verified
  2   the input could not be read as a ZTIP bundle
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .chain import (
    DuplicateJSONKeyError,
    envelopes,
    reference_count,
    reject_duplicate_keys,
    resolved_reference_count,
    unverified_bundle_keys,
    verify_bundle,
)
from .hashing import envelope_hash

def _safe(value: Any) -> str:
    """Render a value for the verdict surface.

    File names, member names and envelope fields are all attacker-influenced text,
    and stdout is what automation parses. A raw newline in any of them lets a
    document print a line that looks like this tool's own verdict.
    """
    text = value if isinstance(value, str) else repr(value)
    return text if text.isprintable() else json.dumps(text)


EXIT_VERIFIED = 0
EXIT_FINDINGS = 1
EXIT_UNREADABLE = 2

SCOPE_NOTE = (
    "    scope: integrity and the envelope contract only — field values were not validated "
    "against the schemas (scripts/validate-examples.py does that), a ZTIP hash is "
    "recomputable by anyone so this is not proof of authenticity, and annotation fields "
    "(keys beginning with _) are outside the hash by design"
)


class InputError(Exception):
    """The file could not be read as a ZTIP bundle."""


def _load(path: str) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"{path} is not UTF-8 text: {exc}") from exc
    try:
        return json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except DuplicateJSONKeyError as exc:
        raise InputError(
            f"{path} is not unambiguous JSON: {exc}. A canonical-hash integrity model "
            "cannot verify a document that different parsers read differently."
        ) from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"{path} is not valid JSON: {exc}") from exc
    except ValueError as exc:
        # e.g. CPython's integer string-conversion limit — a bare ValueError,
        # not a JSONDecodeError, so it would otherwise reach the user as a
        # traceback and exit 1, which means "not verified" rather than "unread".
        raise InputError(f"{path} could not be parsed: {exc}") from exc
    except RecursionError as exc:
        raise InputError(f"{path} is nested too deeply to parse") from exc


def cmd_hash(args: argparse.Namespace) -> int:
    entries = envelopes(_load(args.file))
    if not entries:
        raise InputError(f"{args.file}: no envelopes to hash")
    for index, env in enumerate(entries):
        if not isinstance(env, dict):
            raise InputError(
                f"{args.file}: entry [{index}] is {type(env).__name__}, not a JSON object")
        try:
            digest = envelope_hash(env)
        except (TypeError, ValueError, NotImplementedError) as exc:
            raise InputError(
                f"{args.file}: entry [{index}] has no canonical form: {exc}") from exc
        print(f"{digest}  [{index}] {_safe(env.get('envelope_type', '?'))}")
    return EXIT_VERIFIED


def cmd_verify(args: argparse.Namespace) -> int:
    doc = _load(args.file)
    entries = envelopes(doc)
    count = len(entries)
    distinct = len({_identity(e) for e in entries})
    findings = verify_bundle(doc, allow_unresolved_refs=args.allow_unresolved_refs)
    nested = sum(_payload_size(entry) for entry in entries if isinstance(entry, dict))
    signed = sum(1 for entry in entries
                 if isinstance(entry, dict) and isinstance(entry.get("integrity"), dict)
                 and (entry["integrity"].get("signed")
                      or entry["integrity"].get("signature_ref")))

    tally = f"{count} envelope(s)"
    if distinct != count:
        tally += f" ({distinct} distinct)"
    sidecar = unverified_bundle_keys(doc)

    if findings:
        print(f"FAIL  {_safe(args.file)}: {tally} checked, "
              f"{len(findings)} integrity finding(s)")
        for finding in findings:
            index = finding["envelope_index"]
            where = "bundle" if index is None else index
            print(f"  - [{where}] {_safe(finding['envelope_type'])}: "
                  f"{finding['code']} — {_safe(finding['detail'])}")
        _report_sidecar(sidecar)
        _report_nested(nested)
        _report_signed(signed)
        return EXIT_FINDINGS

    refs = resolved_reference_count(doc)
    total_refs = reference_count(doc)
    if args.allow_unresolved_refs and refs < total_refs:
        linkage = (f"{refs} of {total_refs} request reference(s) resolved; the rest "
                   "were allowed to go unresolved, so chain linkage was NOT fully "
                   "verified")
    elif refs:
        linkage = f"{refs} request reference(s) resolved to the requests they name"
    else:
        linkage = "no request references present, so no linkage was verified"
    print(f"OK  {_safe(args.file)}: {tally} verified — hashes recomputable, {linkage}")
    _report_sidecar(sidecar)
    _report_nested(nested)
    _report_signed(signed)
    print(SCOPE_NOTE)
    return EXIT_VERIFIED


def _identity(envelope: Any) -> str:
    """The hashed identity of an envelope, so duplicates cannot hide behind
    annotation fields that are outside the hash."""
    if isinstance(envelope, dict):
        try:
            return envelope_hash(envelope)
        except (TypeError, ValueError, NotImplementedError):
            pass
    return repr(envelope)


def _payload_size(entry: dict) -> int:
    """How much content an envelope carries under its own `envelopes` key.

    Any shape counts: a list, an object, or a scalar. The point of the note is
    that this content was not verified as separate envelopes, and that is true
    whatever shape it takes.
    """
    payload = entry.get("envelopes")
    if payload is None:
        return 0
    if isinstance(payload, (list, dict)):
        return len(payload)
    return 1


def _report_signed(count: int) -> None:
    if count:
        print(f"    note: {count} envelope(s) declare a signature (integrity.signed or "
              "integrity.signature_ref); this runtime does not check signatures, so that "
              "declaration was not verified")


def _report_nested(count: int) -> None:
    if count:
        print(f"    note: {count} entr(y/ies) carried under an envelope's own "
              "`envelopes` key were not verified as separate envelopes")


def _report_sidecar(keys: list) -> None:
    """Disclose wrapper content. Key names come from the document, so they are
    quoted and escaped: an unescaped newline in a member name would let a bundle
    forge a verdict line in this tool's own output."""
    if keys:
        shown = ", ".join(
            json.dumps(key) + (" (annotation)" if key.startswith("_") else "")
            for key in keys)
        print(f"    note: the bundle also carries {shown} beside its "
              "envelopes; that content is not hashed and was not verified")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ztip", description="ZTIP reference runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    p_hash = sub.add_parser("hash", help="print the hash of each envelope in a file")
    p_hash.add_argument("file")
    p_hash.set_defaults(func=cmd_hash)

    p_verify = sub.add_parser("verify", help="verify bundle integrity (fail-closed)")
    p_verify.add_argument("file")
    p_verify.add_argument(
        "--allow-unresolved-refs",
        action="store_true",
        help="do not fail on a request_hash whose transaction request is absent "
             "(for a partial bundle, e.g. receipts held without their requests). "
             "The success line then states that chain linkage was not verified.",
    )
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    # The verdict and its exit code must not depend on what the terminal can
    # encode: an ASCII stdout would otherwise turn a verified bundle into a
    # traceback and exit 1, which reads as "not verified".
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):  # pragma: no cover - exotic streams
            pass

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except InputError as exc:
        print(f"ERROR  {_safe(str(exc))}", file=sys.stderr)
        return EXIT_UNREADABLE
    except RecursionError:
        print(f"ERROR  {_safe(args.file)}: nesting too deep to canonicalize",
              file=sys.stderr)
        return EXIT_UNREADABLE


if __name__ == "__main__":
    sys.exit(main())
