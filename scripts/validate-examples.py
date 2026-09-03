#!/usr/bin/env python3
"""Validate example bundles against schemas/ztip-bundle.schema.json.

    validate-examples.py [examples_dir]

Defaults to the repository's own ``examples/``. The optional directory lets the
test suite point this exact code at planted fixtures, so the shipped validator
is what gets tested rather than a re-implementation of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ztip.chain import (  # noqa: E402
    DuplicateJSONKeyError,
    envelopes,
    reject_duplicate_keys,
)


def format_error_path(error: Any) -> str:
    """Render the failing location.

    Object keys come from the document under validation, so they are escaped: a
    newline in a member name would otherwise let a submitted example print lines
    that look like this tool's own PASS output.
    """
    if not error.absolute_path:
        return "$"
    path = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            path += f"[{part}]"
        elif str(part).isprintable():
            path += f".{part}"
        else:
            path += f".{json.dumps(str(part))}"
    return path


def _discriminator_failure(error: Any) -> bool:
    """True for the `envelope_type` const mismatch every non-matching branch of the
    envelope oneOf produces. It says only "this is a different envelope type",
    never what is wrong with the envelope in hand."""
    return error.validator == "const" and "envelope_type" in list(error.absolute_path)


def _live_leaves(error: Any) -> list:
    """Leaf errors, with whole branches dropped when they failed on the
    discriminator: the envelope schema is a oneOf over five envelope types, so
    four branches always fail on `envelope_type` alone and none of their
    complaints are about the envelope in hand."""
    context = list(getattr(error, "context", None) or ())
    if not context:
        return [error]
    branches: dict = {}
    for sub in context:
        key = list(sub.schema_path)[0] if list(sub.schema_path) else None
        branches.setdefault(key, []).append(sub)
    kept: list = []
    for errs in branches.values():
        if any(_discriminator_failure(e) for e in errs):
            continue
        for err in errs:
            kept.extend(_live_leaves(err))
    return kept or [error]


def safe_name(path: Path) -> str:
    """File names come from the directory under validation, so a name carrying a
    newline could otherwise print lines that look like this tool's PASS output."""
    return path.name if path.name.isprintable() else json.dumps(path.name)


def deepest_error(error: Any) -> Any:
    """Return the most specific sub-error under a composite (oneOf/anyOf) failure.

    Without this, a failure anywhere inside an envelope is reported as "the whole
    document is not valid under any of the given schemas", which tells a
    contributor nothing about what to fix.

    """
    return max(_live_leaves(error), key=lambda e: len(list(e.absolute_path)))


def load_json(path: Path) -> Any:
    """Load JSON, refusing a document that declares the same member name twice.

    The same rule the reference runtime applies: parsers disagree about what such
    a document says while every hash still verifies, so it is not verifiable.
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=reject_duplicate_keys)


def main() -> int:
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError:
        print(
            "ERROR: Missing dependency 'jsonschema' (>=4.18, which provides"
            " 'referencing'). Install dev dependencies with:"
            " pip install -r requirements-dev.txt"
        )
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    schemas_dir = repo_root / "schemas"
    examples_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root / "examples"
    bundle_schema_path = schemas_dir / "ztip-bundle.schema.json"

    if not bundle_schema_path.exists():
        print(f"ERROR: Schema not found: {bundle_schema_path}")
        return 1

    resources = []
    for schema_path in sorted(schemas_dir.glob("*.schema.json")):
        schema_doc = load_json(schema_path)
        resource = Resource.from_contents(schema_doc)
        resources.append((schema_path.name, resource))
        schema_id = schema_doc.get("$id")
        if isinstance(schema_id, str) and schema_id and schema_id != schema_path.name:
            resources.append((schema_id, resource))
    registry = Registry().with_contents(
        (uri, resource.contents) for uri, resource in resources
    )

    # Without a format checker, "format": "date-time" is annotation-only. Worse,
    # jsonschema installs a checker for it only when the format extra is present,
    # so an incomplete install yields a validator that silently blesses malformed
    # timestamps. Refuse to run rather than report a pass that checked less.
    if "date-time" not in Draft202012Validator.FORMAT_CHECKER.checkers:
        print(
            "ERROR: date-time format checking is unavailable, so timestamps would"
            " not be validated. Install the dev dependencies with:"
            " pip install -r requirements-dev.txt"
        )
        return 1

    bundle_schema = load_json(bundle_schema_path)
    Draft202012Validator.check_schema(bundle_schema)
    validator = Draft202012Validator(
        bundle_schema, registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER)

    failures = 0
    example_files = sorted(examples_dir.glob("*.json"))

    if not example_files:
        print(f"ERROR: No example files found in {examples_dir}")
        return 1

    for example_path in example_files:
        try:
            raw_doc = load_json(example_path)
        except json.JSONDecodeError as exc:
            print(f"FAIL {safe_name(example_path)}")
            print(f"  - JSON parse error at line {exc.lineno}, column {exc.colno}: {exc.msg}")
            failures += 1
            continue
        except DuplicateJSONKeyError as exc:
            print(f"FAIL {safe_name(example_path)}")
            print(f"  - ambiguous JSON: {exc}. Parsers disagree about what this "
                  "document says while every hash still verifies.")
            failures += 1
            continue

        # The same splitter the reference runtime verifies with, so the two
        # shipped tools can never disagree about what a document is.
        instance = envelopes(raw_doc)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))

        if errors:
            failures += 1
            print(f"FAIL {safe_name(example_path)}")
            for err in errors[:10]:
                # A oneOf failure reports the whole instance. Descend into the
                # branch errors and report the most specific one instead.
                deepest = deepest_error(err)
                message = deepest.message[:240]
                if not message.isprintable():
                    message = json.dumps(message)
                print(f"  - {format_error_path(deepest)}: {message}")
            if len(errors) > 10:
                print(f"  - ... {len(errors) - 10} additional validation errors")
        else:
            print(f"PASS {safe_name(example_path)}")

    if failures:
        print(f"\nValidation completed with {failures} failing example file(s).")
        return 1

    print(f"\nValidation completed successfully: {len(example_files)} example file(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
