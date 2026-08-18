# Change Record

- **Date:** 2026-08-18
- **Type:** chore (packaging — ZTI UX wave 3, board card `zti:ux-w3`)
- **ADR reference:** none
- **What changed:**
  - Package version `1.0.0.dev1` → `1.0.0.dev2` in `pyproject.toml` — the one
    and only version reference. The protocol version string (`1.0-draft`
    across SPEC/SCHEMA/CONFORMANCE/schemas/examples) is separate law
    (AGENTS.md source-of-truth rule 2) and did NOT move.
  - Tracked `dist/` artifacts replaced: `ztip-1.0.0.dev1` sdist + wheel
    removed, `ztip-1.0.0.dev2` sdist + wheel added (built with `build` 1.5.0);
    tracked `ztip.egg-info/PKG-INFO` refreshed by the same build. This repo
    tracks its dist artifacts in git (existing convention, kept).
  - New `.github/workflows/publish.yml`: manual-dispatch-only PyPI publish via
    Trusted Publishing (OIDC, `pypa/gh-action-pypi-publish`, environment
    `pypi`, `id-token: write`). Inert until the operator registers the repo +
    workflow as a trusted publisher on the PyPI `ztip` project; never fires on
    push or tag.
- **Why:** The 2026-08-18 UX audit found the live PyPI listing's own install
  line fails as shown — the dev1 listing description predates the `--pre` fix.
  PyPI forbids filename reuse, so re-uploading the current README as the long
  description requires a new version. dev2 exists solely to carry the current
  README (with `pip install --pre ztip` at the top of Try It) onto the
  listing. Uploads are irreversible and stay the operator's: this change preps
  artifacts + the trusted-publishing path; nothing was uploaded from the barn.
- **Risk:** LOW — version metadata + rebuilt artifacts + an inert
  manual-dispatch workflow; no spec, schema, example, or runtime code touched.
- **Verified:** `twine check` PASSED on both dev2 artifacts (twine 7.0.0);
  sdist contents inspected (standard layout, no junk, PKG-INFO long
  description opens with the `--pre` install line); battery green after the
  bump — `scripts/validate-examples.py` 10/10 examples, `tests/test_runtime.py`
  8/8; failure-set grep clean (no dollar figures, no "ZTI Foundation", no ZTAP
  outside `ztap_version`/immutable history, no bare `pip install ztip`).
  Adversarial round exempt (docs+packaging wave, version metadata only,
  ADR-0005 / AGENT_OS §21.4); this battery is the universal closeout gate.
