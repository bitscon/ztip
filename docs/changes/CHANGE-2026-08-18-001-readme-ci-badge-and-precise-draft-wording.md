# Change Record

- **Date:** 2026-08-18
- **Type:** docs (README only — ZTI UX wave 2, board card `zti:ux-w2`)
- **ADR reference:** none
- **What changed:**
  - Badge row: a CI badge (shields.io workflow-status for `validate.yml`,
    branch `main`) added ahead of the existing PyPI / MIT / spec / status
    badges, linking to the Actions workflow page.
  - IETF wording made precise: "on file with the IETF" replaced with
    "published as an individual Internet-Draft, draft-mccormack-ztip; an
    Internet-Draft is a working document, not an IETF standard."
  - One factual availability sentence added to the "Relationship to ZTI and
    ZTI Core" section: "ZTI Core is complete and in early access." No pricing,
    no contact, no CTA — the protocol surface stays unpriced per the brand
    per-surface rules (BRAND.md §7); the full licensing story lives on the
    product surfaces (zti-cli README, the site).
  - Install line audit: `pip install --pre ztip` already correct (only
    1.0.0.dev1 exists on PyPI — verified via the PyPI JSON API); no bare
    `pip install ztip` anywhere in the repo. No change needed.
- **Why:** The 2026-08-18 UX audit's repo wave: public READMEs must match the
  site story staged by ux-w1 (zti-adoption e99853e) — precise Internet-Draft
  wording everywhere, CI surfaced, availability consistent.
- **Risk:** LOW — README-only; no spec, schema, example, or runtime text
  touched; brand per-surface rules applied.
- **Verified:** repo battery green after the edit —
  `scripts/validate-examples.py` (schemas + all 10 example bundles) and
  `tests/test_runtime.py` (8/8); failure-set grep clean (no dollar figures,
  no "ZTI Foundation", no ZTAP outside `ztap_version`/immutable history, no
  bare `pip install ztip`, no stale "in build"/"coming" availability); badge
  URL fetched HTTP 200; raw README render-check after push. Adversarial round
  exempt (docs-only wave, ADR-0005 / AGENT_OS §21.4); this battery is the
  universal closeout gate.
