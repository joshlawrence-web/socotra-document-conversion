# Feature note — structured condition system (condition DSL)

**Status:** not started — saved for later (2026-06-12)
**Context:** follow-up to the occurrence-symbol work (`{$x}` / `{x}` / `{+x}` / `{*x}`
→ plugin-side occurrence guards). Conditions are the remaining raw-string path
through the pipeline.

## Problem — current state is raw-string passthrough

### Parse side (`velocity_converter/leg0_ingest.py:525`)

- `parse_conditional_form` grabs the first line after `Condition:`, zero validation.
  Junk, typos, wrong roots, prose — all land verbatim in `conditional-registry.yaml`.
- Contract validation checks YAML *shape*, not condition *content*.
- Operator hardcoded `"AND"`. The registry schema supports a conditions list +
  operator, but the form parse can never produce more than one condition —
  a customer writing `a != null && b == "x"` passes through as one opaque string.

### Translate side (`velocity_converter/leg4_generate_plugin.py:161` and `:76`)

Two regexes, no grammar:

- `_rewrite_condition_root` — one hardcoded substitution
  (`policy.data.` → `segment.data.`).
- `_accessor_to_java` — appends `()` to dotted chains, leaves everything else
  untouched. Consequences:
  - **Bare identifier** (`quoteNumber != null`) → emitted verbatim → doesn't
    compile. Live example: the pipeline test fixtures' condition seeds produce a
    non-compiling plugin today, and `tests/pipeline/run_test_pipeline.py`
    deliberately skips compile-check, so nothing catches it before deploy.
  - **Latent equality bug**: `policy.data.riderType == "AirBag"` →
    `segment.data().riderType() == "AirBag"` — Java *reference* equality on
    String. Works only by interning luck or if the leaf is an enum.
  - **No null-stepping**: `segment.data().x() == "y"` NPEs if `data()` is null —
    the occurrence guards generate stepwise null checks two lines away; conditions
    don't.
  - **No javap verification**: `_walk_java_chain` validates field-token paths but
    conditions bypass it entirely.
  - **Late scope errors**: a quote field in a policy doc is detected at Leg 4;
    the block silently renders empty in both overloads with only a WARN.

## Design sketch — small grammar, validate early, codegen from structure

Same shape as the occurrence-symbol work:

1. **Grammar** — `<path> <op> <literal>` with ops
   `== != > >= < <= present absent in`, joined by `and` / `or`.
   ~40 lines of parsing, no dependency.
2. **Parse at Leg 0, not Leg 4** — form-parse produces structured triples
   (`{path, op, value}` + operator) into `conditional-registry.yaml` instead of
   raw strings. Bad syntax → validation report back to the customer at
   form-parse time, the only moment they're in the loop.
3. **Validate against path-registry + javap** — path exists, root legal for the
   scope, leaf type vs literal type (string op on a number → error). Reuse
   `_walk_java_chain` — already built.
4. **Codegen from AST** — stepwise null-safe chain (same helper as occurrence
   guards), `Objects.equals()` for equality, `compareTo` for BigDecimal/dates,
   enum-aware. Scope classification computed once at parse time and stored, not
   re-derived per overload.
5. **Back-compat** — registry keeps a `raw:` string alongside the structure;
   old registries fall back to current passthrough behavior.

## Payoff ranking

1. Structured parse + early validation — kills the silent-junk class.
2. `Objects.equals()` codegen — kills the latent `==` reference-equality bug.
3. Null-stepping in condition code — kills the NPE class (original goal of the
   occurrence work).

## Related pre-existing issue

The fixture condition seeds (`tests/pipeline/condition_seeds.yaml`) use bare and
per-exposure paths (`quoteNumber != null`, `item.data.* != null`) that generate
non-compiling Java. Fix the seeds and/or wire compile-check into the test runner
once this DSL lands — early validation would have rejected those seeds.
