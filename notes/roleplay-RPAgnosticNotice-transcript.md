# Roleplay transcript — RPAgnosticNotice(segment)

Renata (solutions consultant, they/them) is authoring a **simple renewal notice**
for a product whose Socotra config *does not exist yet*. There is no customer JAR
and — the crux of this session — **no registry may inform the run**. The research
question: *can a template be config-agnostic (authored/generated with NO registry)
and still be verifiable?*

Doc: greeting, policy number, renewal date, and one binary `[[$loyaltyDiscount]]`
conditional paragraph.

## Stage 0 — Discover (and a design collision)

**Renata:** "The config isn't built. I have no bare-leaf resolver, no JAR. I just
want a renewal letter I can hand-verify before any of that exists."

The guided flow assumes a registry: the author writes bare `{leaf}` and the
pipeline resolves the accessor. With no registry there is nothing to resolve a
`{leaf}` against — and a dotted `{policy.policyNumber}` would only become a stuck
`$TBD_policy.policyNumber` (Leg 0 emits the TBD token; without a registry/path-map
nothing ever fills its `data_source`, so it survives into the `.final.vm` and the
validator rejects it). So Renata does the resolution *by hand*, writing the FINAL
velocity path straight into the Word body, per CLAUDE.md's renderingData table for
a `(segment)` doc:

- policy number = core Policy **system** field → `$data.policy.policyNumber`
- renewal date  = typed Segment **custom** field → `$data.segment.data.renewalDate`

These are plain velocity, not `{markers}` — so Leg 0 has nothing to annotate and
they flow through as literal text. The one conditional stays a named block,
`[[$loyaltyDiscount]]`, because its wording/condition still belong in `variants.csv`.

## Stage 1 — The wrapper won't go registry-less (finding #1)

The three sanctioned wrapper commands can't run this scenario:

- `tools/run_demo.py` hardcodes `REGISTRY = "registry/path-registry.yaml"` as a
  module constant and passes `registry=…` into `intake`, `legminus1_apply`, and
  `leg2`, plus `--registry` into the validator. There is **no flag** to disable it.
- `velocity_converter/agent.py` defaults `registry` to the same on-disk path when
  the `registry=` param is omitted — so even hand-driving `RUN_PIPELINE` still
  consults the repo registry.

Per the task's sanctioned exception, Renata falls back to the raw leg scripts
(documented in CLAUDE.md) with no `registry=` parameter.

```
python3 -m velocity_converter.leg0_ingest \
  --input "workspace/inbox/RPAgnosticNotice(segment).docx" \
  --output-dir "workspace/output/RPAgnosticNotice(segment)"
```

Ran clean registry-less. `mapping.yaml` has `variables: []` (no `{markers}` — the
hand-written paths are literal text), the two hand-written accessors survive
verbatim into `annotated.html`, and `[[$loyaltyDiscount]]` became `$doc.loyaltyDiscount`
with a two-row `variants.csv`. Leg 0's token-integrity verifier and its
bare-`[[block]]` hard-error both ran — they are pure string/structure checks, no
registry involved.

## Stage 2 — Human fill, and a hidden registry gate (finding #2)

Renata fills `variants.csv`:

```
loyaltyDiscount,loyaltyDiscountAmount present,"As a valued long-standing customer, a loyalty discount has been applied to your renewal premium."
loyaltyDiscount,,
```

First parse attempt **hard-failed**:

```
python3 -m velocity_converter.leg0_ingest --parse-variants-csv ".../RPAgnosticNotice(segment).variants.csv" --output-dir ".../RPAgnosticNotice(segment)/"
  Error: variant CSV validation failed (registry NOT written):
    - loyaltyDiscount: 'loyaltyDiscountAmount' did not resolve to any registry field
```

The surprise: `--parse-variants-csv` has **no `--registry` flag**. It calls
`_discover_registry()`, which walks up to 8 directories from the CSV/output paths
looking for `registry/path-registry.yaml` — and inside this repo it *always* finds
the ZenCover registry, then validates every condition accessor against it. There is
no opt-out. For a genuinely config-agnostic product this is wrong: a perfectly good
condition on a field that doesn't exist in *some other product's* registry is
rejected.

To get the intended registry-less behaviour, the parse inputs (CSV + sidecar +
mapping) were relocated to a temp tree **outside** the repo, where
`_discover_registry` returns `None`. Re-run there:

```
Wrote .../RPAgnosticNotice(segment).conditional-registry.yaml   (exit 0)
```

The *identical* condition that hard-failed with the registry present now passes.
In `condition_dsl.parse_variants_csv`, accessor-existence validation is gated on
`if registry and scope:` — with `registry=None` it degrades to **DSL syntax only**
(`parse_condition` still builds the AST; `item.*` at document scope is still
rejected). The registry was copied back into the repo output dir for the rest of
the run.

## Stage 3 — Finalize (registry-less Leg 3)

No `{markers}` means no `data_source` to resolve, so Leg 2 is skipped entirely
(nothing for it to do, and it *requires* a registry). Seed the `.vm` from the
annotated HTML (what the agent does internally) and run Leg 3 directly — Leg 3
takes no registry:

```
cp annotated.html → RPAgnosticNotice(segment).vm
python3 -m velocity_converter.leg3_substitute --suggested ".../RPAgnosticNotice(segment).mapping.yaml"
```

`.final.vm` resolved refs:

```
$data.policy.policyNumber
$data.segment.data.renewalDate
${data.loyaltyDiscount}
```

No `$TBD_`, no `$data.data.`, no leftover `$doc.`.

## Stage 4 — Done-gate

```
python3 tools/validate_demo.py "RPAgnosticNotice(segment)"
ran 43 checks on .../RPAgnosticNotice(segment).final.vm
PASS — template matches the document and renderingData shape is correct.
```

**PASS — with no registry consulted by the validator.** The validator only needs a
registry for one specific check (bare-system-field names); everything else it does
is config-free.

---

## Config-agnostic verifiability — findings

The template **is** verifiable without config — but only for a specific, coarse
band of correctness. Each layer, classified:

| Layer | Verdict | Evidence |
|---|---|---|
| (a) Marker / token integrity (Leg 0 hard errors) | **Works config-agnostic** | Leg 0 ran registry-less; `_verify_token_integrity` + bare-`[[block]]` error are pure string checks; `[[$loyaltyDiscount]]` → `$doc.loyaltyDiscount` cleanly |
| (b) Condition-DSL parse/validate | **Degrades to syntax-only** | Syntax parse + doc-scope `item.*` rejection are config-free; **accessor existence** is `if registry and scope`-gated. Repo registry present → `loyaltyDiscountAmount` hard-fails; registry absent → passes. **No CLI opt-out** — auto-discovery forces any up-tree registry |
| (c) Doc-coverage (validate_demo) | **Works config-agnostic** | Pure docx-vs-`.vm` prose/structure diff; 43 checks ran, `--registry` never opened |
| (d) renderingData-shape grep | **Partially degrades** | `$data.data.*` guard + unknown-entity-key guard are registry-free; the **bare-system-field** guard needs the registry's system-field name list. Empirically: a bare `$data.policyNumber` (no entity key, renders to nothing) **PASSES** config-agnostic but is caught **MISMATCH** with the registry |
| (e) Leg 4 plugin compile-check | **Impossible without config** | Needs `--customer-jar` + `--datamodel-jar` (the compiled config) for `validate_path`/`javac`. No config = no plugin verification (not run in the demo either) |
| (f) Live render | **Impossible without config** | Needs a deployed plugin + tenant; and `${data.loyaltyDiscount}` is normally computed by that plugin, so config-agnostic it renders empty — cannot be live-verified |

**The entity-key splice never happens config-agnostic.** Normally Leg 2 `_reprefix`
/ Leg 0 pre-fill splice the rendering-root entity key onto a registry/JAR verdict.
Here Renata typed the spliced form by hand — so *she* owns splice correctness, and
the only automated backstop is the coarse shape-grep in (d), which has a registry
hole exactly where a hand-typed system field could drop its entity key.

**The boundary.** Config-agnostic verification covers **shape and structure**: are
the markers consumed, is the DSL syntactically valid, does every doc line appear in
the template, does every `$data.X` sit under a *plausible* entity key, is there any
naked `$data.data.*`. It cannot cover **existence or semantics**: does this accessor
exist on the real model, is `policyNumber` a system field that must carry the
`policy` key, does the condition reference a real field, does the plugin populate
`${data.loyaltyDiscount}`, does it render. Two tooling gaps make the boundary worse
than it needs to be: the wrapper has no registry-less mode, and `--parse-variants-csv`
silently binds to whatever registry is up-tree with no opt-out — so "config-agnostic"
is reachable only by physically relocating inputs outside the repo.
