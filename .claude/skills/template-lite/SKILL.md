---
name: template-lite
description: Config-agnostic, template-only conversion — produce a .final.vm from a Word doc with NO registry, NO config, and NO plugin, driven entirely as a conversation in the Claude session (no run_demo wrapper). Use when the product config doesn't exist yet, the user says "no config / config-agnostic / just the template / don't need the plugin yet", or a customer wants a template before committing to configuration. Conditionals still promote to plugin keys so Leg 4 can be run later, unchanged, once config arrives.
---

# Template-lite — config-agnostic, template-only, conversation-driven

Produce a `.final.vm` from a `.docx` with **no registry, no config, no plugin**.
The Claude session is the interface: no `run_demo.py`, no intake package, no
customer CSV handoff ceremony. You (the agent) play the registry's role
conversationally; the user answers questions instead of filling forms — though
they may edit the `variants.csv` directly if they prefer.

**What still holds from the full flow:** the marker syntax (`{field}`,
`[[$token]]`, `[Name/]`, `[Name?]`), the condition DSL, and the renderingData
table in CLAUDE.md. **What changes:** no Leg -1/Leg 2 (you resolve paths by
hand), no Leg 4 (the plugin is deferred until the user *willingly* provides
config — never push them toward it), and validation is the **shape band only**
(see "What is verified" below).

## The flow

1. **Ingest, registry-less.** Doc in `workspace/inbox/<stem>(segment|quote).docx`:

   ```
   python3 -m velocity_converter.leg0_ingest --input <doc> --no-registry --output-dir workspace/output/<stem>
   ```

   `--no-registry` (required — without it Leg 0 auto-discovers the repo's
   ZenCover registry up-tree and classifies/validates against the wrong
   product). Loop/region classification uses the registry-less fallbacks;
   marker/token integrity checks all still hard-error as usual.

2. **Conditions, conversationally.** For each row in the generated
   `variants.csv` (in `workspace/action-needed/` when under `workspace/`,
   else next to the outputs), ask the user in chat: *when should this show,
   and what should it say?* Write their answers into the CSV yourself — this
   is lite mode, the CSV is an internal artifact, not a customer handoff.
   Conditions must still parse under the DSL (`present`/`absent`, `==`, `in`;
   never `!= null`); with no registry, validation is syntax-only, so
   double-check field names with the user — nothing will catch a typo'd
   accessor. Then:

   ```
   python3 -m velocity_converter.leg0_ingest --parse-variants-csv <csv> --no-registry --output-dir workspace/output/<stem>
   ```

   Conditionals **still promote to plugin keys** (`${data.<token>}` in the
   template, condition + text recorded in `<stem>.conditional-registry.yaml`).
   That file is the deferred half: when the user later brings config, run
   Leg 4 against the same mapping — the template never changes.

3. **Manual mapping — you are the registry.** For every variable in
   `<stem>.mapping.yaml` with an empty `data_source`, determine the final
   **spliced** velocity path and set it directly in the mapping (sanctioned:
   manual mapping is the by-design registry-less path; Leg 3's own report
   says "edit data_source in the .mapping.yaml"). Ask the user two things
   per field when unsure: *system field or custom field?* and *does it live
   on the account, the policy, or the quote?* Then apply the CLAUDE.md
   renderingData table — never emit a pre-splice `$data.data.<f>`:

   | Doc root | Field kind | data_source |
   |---|---|---|
   | (segment) | system (core Policy) | `$data.policy.<f>` |
   | (segment) | custom | `$data.segment.data.<f>` |
   | (quote) | system | `$data.quote.<f>` |
   | (quote) | custom | `$data.quote.data.<f>` |
   | any | account | `$data.account.data.<f>` |
   | (segment) | items loop | `$data.segment.items`, fields `$item.data.<f>` |

4. **Finalize.**

   ```
   python3 -m velocity_converter.leg3_substitute --suggested workspace/output/<stem>/<stem>.mapping.yaml --vm workspace/output/<stem>/<stem>.annotated.html
   ```

5. **Done-gate — shape band.** Run
   `python3 tools/validate_demo.py <stem>` **without** `--registry`, and grep
   the `.final.vm` per the CLAUDE.md checklist (no `$TBD_`, no `$doc.`, no
   bare `$data.data.`, every field under an entity key). State the verdict
   honestly, including the limits below.

## What is verified (and what is NOT) without config

Say this to the user plainly — it is the lite-mode contract:

- **Verified:** marker/token integrity, condition-DSL syntax + document-scope
  rules, full doc-prose coverage, renderingData *shape* (entity keys present,
  no pre-splice paths).
- **NOT verifiable without config:** that any accessor actually **exists** on
  the real product model; that a name you keyed as `$data.policy.<f>` is truly
  a system field; whether the template renders real data. A fat-fingered field
  name passes every lite check and renders to nothing.
- The `${data.<token>}` conditionals render **empty** until a plugin exists —
  the template is deploy-shaped, not render-complete.

## Upgrading later (only when the user asks)

When the user willingly provides a config/registry: run Leg 2 on the same
mapping to get real verdicts on your hand-mapped paths, then Leg 4 for the
plugin (the conditional-registry already carries every block). Do not
proactively push this — producing the template is the whole job here.
