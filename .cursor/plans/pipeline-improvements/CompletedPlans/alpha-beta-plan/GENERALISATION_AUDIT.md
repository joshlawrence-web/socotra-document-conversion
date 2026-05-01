# GENERALISATION_AUDIT.md — CommercialAuto-coupling risk report

**Status:** Observational, written 2026-04-22 mid-way through
`PIPELINE_EVOLUTION_PLAN.md`. Not a deliverable of any numbered phase —
this file exists so a later agent can fold the items below into the
appropriate phase (likely Phase C/D or an interstitial hygiene pass)
without re-doing the audit.
**Audience:** The next agent working on the HTML → Velocity pipeline,
especially anyone preparing to run it against a non-CommercialAuto
Socotra config for the first time.
**Scope:** `html-to-velocity` + `mapping-suggester` skills plus
`extract_paths.py` and `convert.py`. Does NOT re-audit `SCHEMA.md`,
`CONFIG_COVERAGE.md`, or the Samples — those are doing their job.

---

## TL;DR

The **architecture** is generic where it counts. Both scripts walk the
config / registry structurally; neither hardcodes a product name, an
exposure name, or a coverage name into its control flow. The
`feature_support` refusal rule in the mapping-suggester is an explicit
"fail loudly on unsupported patterns" safety net — exactly the right
shape for generalisation.

The **prose** is heavily biased toward CommercialAuto. Examples,
docstring snippets, and review-file sample rows throughout SKILL.md and
the script comments use Vehicle / Driver / MedPay / Coll / Liability as
their stock vocabulary. None of this drives logic, but it risks
anchoring an LLM agent's reasoning on the auto domain when the skill is
applied to, say, a Homeowners or Commercial Property config.

The **one real silent-failure mode** is the hardcoded `account_paths`
list in `extract_paths.py`. A product with a `BusinessAccount` (or any
account shape outside the curated 9 Consumer-style fields) will get a
registry that quietly emits wrong account paths — no refusal fires
because there is no flag for it. This is already tracked as row 25 of
`CONFIG_COVERAGE.md` ("Account type variation"), scoped to Phase C/D.

Everything else is either (a) correct-by-design, (b) honestly flagged
by the refusal rule, or (c) cosmetic bias that's worth cleaning up but
not a correctness risk.

---

## 1. What is genuinely generic (keep as-is)

For grounding, so the next agent doesn't mistake these for gaps:

- **`extract_paths.py → build_registry()`** walks `products/*/`,
  `exposures/*/`, `coverages/*/`, `charges/*/`, `accounts/*/`,
  `customDataTypes/*/` generically. No exposure/coverage name list
  anywhere in control flow.
- **`parse_quantified_token()`** is pure syntax: splits any
  `"<Name><suffix>"` token into `(name, quantifier)` using the closed
  set `{"", "!", "?", "+", "*"}`. Product-agnostic.
- **`extract_paths.py → detect_features()`** scans for 10 structural
  features (nested iterables, CDTs, recursive CDTs, jurisdictional
  scopes, peril-based, multi-product, coverage terms, default-option
  prefix, auto-elements, array data-extensions). Emits
  `feature_support:` block. Generic.
- **`convert.py → load_iterables()`** reads `iterables:` from the
  registry at runtime and derives match prefixes from whatever names
  it finds. A Homeowners config with `Structure+` / `Content+` would
  yield `structure_` / `content_` prefixes automatically — no code
  change required.
- **`mapping-suggester/SKILL.md` Rule 1 / Rule 2 / Rule 3 / Rule 4 /
  Rule 5 / Rule 6** — the *logic* of every rule references registry
  fields (`iterables`, `requires_scope`, `quantifier`, `velocity`,
  `velocity_amount`) that are populated generically. No rule branches
  on a literal product/exposure/coverage name.
- **`feature_support` refusal rule** (SKILL.md Step 2a +
  `CONFIG_COVERAGE.md` §4) catches 8 of the 10 flags cleanly. If a new
  config lights any of them, the suggester emits `needs-skill-update`
  and refuses high-confidence matches instead of silently mis-mapping.

**Confidence that the skill will behave safely on an unsupported
config:** high. It will refuse loudly, which is the correct behaviour.

---

## 2. The one silent-failure gap: hardcoded `account_paths`

**File:** `.cursor/skills/mapping-suggester/scripts/extract_paths.py`
**Lines:** roughly 579–589 (the `account_paths` list inside
`build_registry()`).

```python
account_paths = [
    _unscoped_entry("name",         "Account name",   "string", "account", "$data.account.data.name"),
    _unscoped_entry("addressLine1", "Address line 1", "string", "account", "$data.account.data.addressLine1"),
    _unscoped_entry("addressLine2", "Address line 2", "string", "account", "$data.account.data.addressLine2"),
    _unscoped_entry("city",         "City",           "string", "account", "$data.account.data.city"),
    _unscoped_entry("state",        "State",          "string", "account", "$data.account.data.state"),
    _unscoped_entry("postalCode",   "Postal code",    "string", "account", "$data.account.data.postalCode"),
    _unscoped_entry("country",      "Country",        "string", "account", "$data.account.data.country"),
    _unscoped_entry("email",        "Email",          "string", "account", "$data.account.data.email"),
    _unscoped_entry("phone",        "Phone",          "string", "account", "$data.account.data.phone"),
]
```

### Why this is the worst item on the list

1. It runs unconditionally, ignoring `accounts/<Type>/config.json` even
   when one exists.
2. The refusal rule does NOT protect it — there is no
   `feature_support` flag for "account schema differs from the hardcoded
   list". A BusinessAccount (with `legalName`, `dba`, `fein`, etc.) or
   a modified ConsumerAccount (with extra fields, or missing some of
   the 9) will produce a registry that **looks plausible but is
   wrong**.
3. Downstream, the mapping-suggester will confidently emit
   `data_source: $data.account.data.phone` on fields that semantically
   mean something else — and because the path syntactically resolves
   in Velocity, even runtime testing might not catch it until the
   rendered document contains the wrong data.

### Suggested fix shape (for the Phase C/D agent)

Parallel to `extract_exposure()`: add an `extract_account()` that reads
`accounts/<Type>/config.json`, maps its `data` block through
`extract_data_fields()` with `category="account"` and prefix
`$data.account.data`, and emits system fields (`locator`, `name`,
`accountType`) separately. Multiple account types → emit all with a
`requires_scope` step keyed on the account type discriminator (or
gate via a new refusal flag if the template-level language doesn't
support it yet — decide in the PR).

**Cross-reference:** row 25 of `CONFIG_COVERAGE.md` already owns this.
The audit adds no new facts — just a louder flag that this is the one
place where "no refusal fires and the output is wrong" is possible.

---

## 3. Prose / example bias (cosmetic but worth addressing)

None of the items below change logic. They bias an agent's reasoning
when the skill is applied to a non-auto product.

### 3.1 `mapping-suggester/SKILL.md`

| Where | What | Why it matters |
|---|---|---|
| Rule 1 — "Coverage loops" paragraph (~line 144) | Wording: "a `coverages` loop nested inside a `vehicles` loop". | Logic is actually "a `coverages` loop nested inside **any exposure** loop". A Homeowners config with a `coverages` loop inside a `structures` loop would match the rule semantically but read as a mismatch to an LLM agent. **Suggested rewrite:** "a `coverages` loop nested inside an exposure loop (e.g. a `coverages` loop inside a `vehicles` loop on an auto product, or inside a `structures` loop on a property product)". |
| Rule 2 step 3 (~lines 188–191) | Worked example uses `loop_hint: Vehicle` + `#foreach ($vehicle in $data.vehicles)`. | Single example — fine on its own, but combined with the rest of the file it forms a pattern. Consider a second example from a different domain. |
| Rule 2 step 1 (~lines 134–135) | "(`vehicles` ↔ `Vehicle`). Accept obvious synonyms (`drivers` ↔ `Driver`)." | Synonym detection description names only auto entities. Generic rephrase: "accept obvious singular/plural synonyms (`vehicles` ↔ `Vehicle`, `drivers` ↔ `Driver`, `structures` ↔ `Structure`, `contents` ↔ `Content`)". |
| Rule 4 (~line 231) | "(e.g. MedPay, Umbi, Umpd, or any data-extension field typed `<T>?`)". | Same pattern — auto-only enumeration. The "or any data-extension field" clause saves it; keep the generic clause but swap the enumeration for a product-agnostic example. |
| Rule 6 charge disambiguation (~lines 249–258) + "Important constraints" bullet (~lines 802–808) | Uses `$data.charges.GoodDriverDiscount` in two places. | Swap for a generic `$data.charges.<ChargeName>`-style example. |
| Output format sample (~lines 320–417) | Full worked example is CommercialAuto (vehicles loop, Coll/Comp/Liability/MedPay/Umbi/Umpd coverages). `product: CommercialAuto` literal. | This is the single densest bias vector — an agent reading the skill to learn the output shape internalises an auto-shaped example. **Suggested:** either (a) keep one auto example + add a second example from a different domain, or (b) genericise to `Example+` / `Option1` / `Option2` style placeholders. I lean (a) — real examples are easier to reason about than abstract ones, provided there are two. |
| Cross-scope warnings table example (~line 532) | `vehicle_year`, `driver_first_name`. | Cosmetic; swap one row for a non-auto example. |

### 3.2 `html-to-velocity/SKILL.md`

| Where | What | Why it matters |
|---|---|---|
| "Loop context" section (~lines 107–123) | Prefix examples all auto (`vehicle_year`, `driver_first_name`). | Add one non-auto example or a generic rephrase. |
| "Iterable synonyms" table (~lines 127–134) | Only Vehicle and Driver rows. | **This one is more than cosmetic.** The table explicitly says "If you add a new iterable to the product config… add a row to this table so reviewers know which headings to expect." When switching configs, a human reviewer will have no synonym guidance for the new iterables. **Suggested:** either (a) move the table's mechanism into a `terminology.yaml` that lives with each product's config (Phase E is already scoped to this — see `PIPELINE_EVOLUTION_PLAN.md` Phase E), or (b) at minimum note in the table caption that rows are product-specific and the current rows are for CommercialAuto. |
| YAML mapping schema example (~lines 145–193) | Uses `insureds` and `vehicle_year`. Mixed — not pure auto, but still thin. | Low priority; the schema shape is self-explanatory. |

### 3.3 `extract_paths.py` docstrings + comments

| Where | What |
|---|---|
| Module docstring Velocity conventions block (~lines 11–20) | Every example path uses `$data.vehicles`, `$vehicle.Coll.*`, `GoodCustomerDiscount`. Consider adding a second domain's worth. |
| `parse_quantified_token()` docstring (~line 77) | "Split a contents-array token like `'Vehicle+'`, `'MedPay?'`, `'Coll'` or `'collision!'`". Replace with a product-agnostic selection (`'Primary+'`, `'Optional?'`, `'Bundled'`, `'default!'`). |
| `exposure_list_key()` / `iterator_var()` docstrings (~lines 108–123) | "e.g. Vehicle -> vehicles, Driver -> drivers". Fine as auto examples; add one non-auto pair. |
| `extract_coverage()` docstring (~lines 196–204) | "iterator='vehicle', coverage_name='Coll'". Add a second example. |
| `extract_exposure()` docstring (~line 259) | "future nested iterables (e.g. Driver+ embedded as a data-extension on Vehicle)". Domain-appropriate but narrow. |

### 3.4 `convert.py` docstrings + comments

| Where | What |
|---|---|
| Module docstring "Loop hints" section (~lines 24–30) | `vehicle_*` → Vehicle example. Add one non-auto example. |
| `_match_loop_hint()` docstring (~lines 244–247) | "canonical `vehicle_*` and `driver_*` test cases". Fine but swap-in a second domain helps. |
| "body text inside the opener's text node" comment (~line 535) | `{{#vehicles}} {{year}} {{make}} ...` example in a comment. Replace with a neutral name. |

---

## 4. Second-order generalisation concerns (not bugs, but watchpoints)

Items that are working today but could bite on the first real cross-
product run. Flagging so the next agent can probe these early.

### 4.1 `iterables_index` ordering is insertion-order

`extract_paths.py → build_registry()` appends exposures in the order
they appear in the product's `contents` list (plus any
`exposures/` subdirs not listed). `convert.py → load_iterables()` then
**re-sorts by prefix length descending** so the longer prefix wins on
a collision. That's the right tie-breaker, but worth calling out: if
a product has `SecondaryVehicle+` alongside `Vehicle+`, the longer
prefix (`secondaryvehicle_`) wins cleanly. If a product has
`Unit+` and `BusinessUnit+`, same story. Good.

**Watchpoint:** if a future product has iterables whose names are not
prefix-distinct (e.g. `Vehicle+` and `CommercialVehicle+` where the
human might name variables `commercial_vehicle_*` OR
`commercialvehicle_*`), the heuristic may miss one direction. Surface
via Leg 2 `.review.md` if it ever happens — don't pre-fix.

### 4.2 `singularize()` in `convert.py` is rough English

Lines ~77–86. Handles `-ies`, `-ses/xes/zes/ches/shes`, generic `-s`.
Falls back to `<name>_item`. Fine for the iterables we've seen. Any
product with irregular plurals (`children`, `criteria`, `data`,
`analyses`) will fall through to `<name>_item` — ugly but not broken,
and a human reviewer can override in the YAML.

### 4.3 `system_paths` is hardcoded but reasonable

Lines ~567–576. The 8 fields (`locator`, `productName`, `policyNumber`,
`currency`, `policyStartTime`, `policyEndTime`, `created`, `updated`)
are the **universal** Socotra renderingData policy-level fields, not
CommercialAuto-specific. Unlike `account_paths` this is a defensible
hardcoding. Leave as-is; if Socotra Core adds a new universal field,
add it here.

### 4.4 Refusal-rule coverage is contractually complete but behaviourally untested

Eight of 10 flags route to refusal; two (`auto_elements`,
`array_data_extensions`) are rule-supported. `CONFIG_COVERAGE.md` §4
records this whitelist. But on CommercialAuto every flag is `false`,
so the refusal branch has never actually fired in a live run. **Phase
C fixtures** (the 10 under `conformance/fixtures/`, currently unpopulated)
are the planned place to exercise this. Worth a PR-level reminder:
the first Phase C fixture to author should be one that sets a refusal
flag true (e.g. `coverage-terms/`) so we have a live regression
anchor.

### 4.5 The `CONFIG_COVERAGE.md` matrix is a B1 seed — presence of a row
is not proof the feature is actually supported

Rows like 3 (`Exposure quantifier '?'`) claim "partial" handling via
Rule 4. That claim is plausible but untested against a config that
uses `?` on an exposure (CommercialAuto doesn't). Same for every row
where "In CommercialAuto?" is `no`. **Don't treat the matrix as truth
until Phase C fixtures confirm it.** A later agent should mark rows
green only after a fixture actually exercises them.

---

## 5. Suggested remediation sequence

If the next agent wants to close these gaps cleanly, the cheapest
order is:

1. **Fix `account_paths`** (single script edit; kills the one silent-
   failure mode; enables row 25 of `CONFIG_COVERAGE.md` to flip).
2. **Pass over `mapping-suggester/SKILL.md`** to add a second worked
   example from a non-auto domain (Homeowners / Commercial Property /
   Workers' Comp — any). Don't remove the auto examples; add
   alongside. Single PR, no logic change.
3. **Pass over `html-to-velocity/SKILL.md`** — fix the "Iterable
   synonyms" table caption to make its product-scoping explicit, and
   add a second example row. Optionally split into a per-product
   `terminology.yaml` if doing so in concert with Phase E.
4. **Docstring/comment sweep** across both scripts. Pure cosmetic.
   Group with any other drive-by edit, don't PR standalone.
5. **Before the first non-auto Leg 1/2 run:** author the first Phase C
   fixture that exercises a refusal flag. Makes the refusal path a
   regression-tested contract instead of a contractual claim.

Items 1–3 can land before Phase C starts and would measurably reduce
the chance of an agent mis-applying the skill to a new product.
Items 4–5 are Phase-C-or-later housekeeping.

---

## 6. What is NOT a concern (explicitly listed so no one re-panics)

- The `Samples/Output/*.mapping.yaml` files being all-auto. Those are
  fixtures of a specific product, not shared infrastructure.
- `path-registry.yaml` being CommercialAuto-shaped. It's regenerated
  per-product; the shape is a function of the input config.
- `PIPELINE_EVOLUTION_PLAN.md` and `PIPELINE_IMPROVEMENTS_PLAN.md`
  both mentioning CommercialAuto extensively. Those are plan
  documents for the current build phase; no rules depend on them.
- The `singularize()` rough heuristic (see §4.2). Good enough; human
  reviewer catches the misses.
- The 8 `system_paths` hardcoding (see §4.3). Those ARE universal.
- Rule 1's coverage-loop special case being phrased around vehicles.
  It IS generic logic; just rephrase per §3.1.

---

## 7. Change log

- **2026-04-22** — Initial audit written mid-Phase-C-prep. Author:
  opus-class agent investigating a user concern that the skill had
  over-fit to CommercialAuto. Conclusion: no architecture problem;
  one real gap (§2); a batch of cosmetic prose bias (§3); plus a
  handful of watchpoints (§4). Suggested remediation sequence in §5.
  No code changes made by this audit — file is observational only.
