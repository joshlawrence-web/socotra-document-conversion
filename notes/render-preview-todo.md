# Render-preview testing pipeline — TODO

Goal: every suite run can optionally render its `.final.vm` output against a live
tenant via ad-hoc rendering (`--render-preview`), with plugin deploy automated as
the final piece. Owner key: **[Josh]** = needs you / tenant access, **[Claude]** =
I do it once unblocked.

## Phase A — access (unblocks everything)

- [ ] **[Josh]** Confirm sandbox tenant + grab its **tenant locator** (UUID)
- [ ] **[Josh]** Create a **PAT** (or service-account token) scoped to that tenant
      with the `documents` group's `render-external` permission
- [ ] **[Josh]** Confirm the **EC API base URL** for that environment
- [ ] **[Josh]** `cp .env.ai-documents.example .env.ai-documents` and fill in
      `AI_DOCUMENTS_API_URL`, `AI_DOCUMENTS_TENANT_LOCATOR`, `AI_DOCUMENTS_PAT`
      (`AI_DOCUMENTS_PRODUCT_NAME=ZenCover` is pre-filled in the example)

## Phase B — tenant carries the product + plugin

- [ ] **[Josh]** ZenCover config deployed on the tenant (paths must line up with
      `registry/path-registry.yaml` — same source of truth the pipeline uses)
- [ ] **[Claude]** Run the suite to produce a fresh combined
      `ZenCoverDocumentDataSnapshotPluginImpl.java` (tests/pipeline/output)
- [ ] **[Josh]** Deploy that plugin to the tenant (manual for now — UI/SDK,
      your call; automation is Phase E)

## Phase C — reference entities to render against

- [ ] **[Josh]** Create a ZenCover **quote** on the tenant → locator →
      `AI_DOCUMENTS_REFERENCE_QUOTE`
- [ ] **[Josh]** Issue a policy / get a **segment** locator →
      `AI_DOCUMENTS_REFERENCE_SEGMENT`
- [ ] **[Josh]** Seed enough data on them that fixture fields resolve: items array
      populated (the `[Item]` loop fixtures), discount field set (conditional
      fixtures) — strict Velocity rendering fails on missing references

## Phase D — first live shakedown (Claude, once A–C are checked)

- [ ] One-off `render_preview` of the simplest fixture (`TestQuoteSummary`)
      against the quote locator — verify the form-data call works outside Postman
- [ ] Confirm empirically: inline `documentConfig` accepted, response content type,
      error body shapes — tune client/validation to reality
- [ ] Full `python3 tests/pipeline/run_test_pipeline.py --auto --render-preview`
      across all five fixtures; fix any template/plugin issues it surfaces
- [ ] Strengthen the PASS bar: extract text from PDF previews (pdfplumber is
      already a dependency) and run the `$TBD_` / `$doc.cond` leak check on it

## Phase E — automation & hardening (deliberately last)

- [ ] **[Josh decides]** Plugin-deploy mechanism: SDK/gradle task vs Configuration
      Deployments API ("we have the technology")
- [ ] **[Claude]** Wire chosen deploy into the runner as a pre-render stage
      (`--deploy-plugin`?) so the mini-pipeline is: generate → deploy → render
- [ ] Decide CI stance: stays opt-in locally, or nightly job with secrets injected
- [ ] Rotate/expiry plan for the PAT (tokens expire; suite should fail with a
      clear "token expired" message — verify the 401 path says so)
