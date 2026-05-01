# custom-naming — exposure name that does not pluralise cleanly

## Purpose

Proves that `extract_paths.py`'s naive pluralisation rule
(`name[0].lower() + name[1:] + 's' unless already ends in 's'`) produces
a Velocity list key that **does not match the English plural** for
exposures whose singular form already ends in `s`, and that the
mapping-suggester's Rule 1 name-match is strict — it does **not**
accept the English plural as a synonym without an external terminology
layer.

This is the Phase E terminology-layer anchor. Pre-Phase-E (sessions
C4 and earlier) the `octopuses` loop resolved to `low` +
`supply-from-plugin` because Rule 1's name-match was strict
(case-insensitive equality against `Octopus` / derived plural
`octopus` / obvious synonyms only — "octopuses" fails all three).
Phase E added a fixture-local `terminology.yaml` that declares
`Octopus: [octopuses, octopi]` under `synonyms.exposures`. The
suggester's new name-match precedence (exact → case-insensitive →
terminology synonym → fuzzy) hits step 3 on `octopuses`, resolves it
to canonical `Octopus`, and lifts the loop to `high` with the
standard terminology reasoning line:

> matched via terminology.yaml synonym `octopuses` → canonical `Octopus`

The `low` + `supply-from-plugin` behaviour is still the correct
fallback when `terminology.yaml` is absent; Phase E makes it
configurable rather than hard-coded.

`Octopus` was chosen as the canonical edge case because it is a real
English noun whose natural plural (`octopuses` / `octopi`) differs
from Socotra's derived plural (`octopus` — no suffix appended,
because the singular already ends in `s`). Any noun ending in `s`, `x`,
`z`, `ch`, or `sh` exhibits the same mismatch (`Box` → `$data.boxs`,
`Class` → `$data.class`, etc.); Octopus is simply the most vivid.

## `CONFIG_COVERAGE.md` rows covered

§3.1 — Quantifiers on exposure `contents`:

- **Row 1** — Exposure quantifier `+` — partial (`Octopus+` is a
  `+`-quantified exposure; the `+` quantifier contract itself is
  directly covered by `all-quantifiers/`). This fixture exercises
  the downstream Rule 1 failure mode when the derived list key
  does not match the template author's chosen loop name, which is
  orthogonal to the quantifier itself.

No dedicated `feature_support` flag covers terminology drift —
Phase E added a `terminology.yaml` artifact (not a flag) that
resolves this mismatch. The fixture is therefore a regression on
Rule 1's match strictness plus the post-Phase-E terminology hit, not
on any feature-flag refusal.

## `feature_support` flags expected

Every flag `false`. `custom-naming/` has:

- No `!`, `?`, or `*` suffixes (only `Octopus+`, which flips nothing).
- No `customDataTypes/`, no `perils/`, one product subdir, no
  `qualification` / `appliesTo` / `exclusive`, no `coverageTerms`.
- No data-extension `type` ending in `+` or `*`.

Any flag flipping to `true` on this fixture indicates
`detect_features()` has gained a false positive sensitive to exposure
naming.

## Behaviour proven

1. **Extractor pluralisation is "append `s` unless already ends in
   `s`".** `Octopus` → list key `octopus` (not `octopuses`, not
   `octopi`). The registry emits `list_velocity: $data.octopus` and
   `iterator: $octopus`. This is the deliberate behaviour of
   `exposure_list_key()` — simple and deterministic, at the cost of
   ungrammatical plurals for `s`/`x`/`z`-ending nouns.
2. **Rule 1 match is strict.** The suggester matches the loop `name`
   against the iterable's `name` (`Octopus`), `display_name`
   (`Octopus`), and derived plural (`octopus`) using
   case-insensitive equality plus obvious-synonym acceptance. The
   template's `octopuses` fails all three comparisons — it is not
   `Octopus` case-insensitively, not the derived plural `octopus`,
   and "octopuses" is not an obvious synonym recognised by the
   current SKILL rules.
3. **Terminology resolution (Phase E).** With a fixture-local
   `terminology.yaml` declaring `Octopus: [octopuses, octopi]` under
   `synonyms.exposures`, Rule 1 step 3 matches and the loop lifts to
   `high`. The reasoning block carries the verbatim line
   `matched via terminology.yaml synonym octopuses → canonical
   Octopus` per SKILL.md → "Name-match precedence". Because the
   match is via an alias (not the name / display_name / derived
   plural), `confidence: high` is earned by step 3, not step 1 — but
   the grade is identical: all four iterable fields
   (`list_velocity`, `iterator`, `foreach`, quantifier metadata) are
   copied verbatim from the `Octopus` iterable and no further scope
   or quantifier guard applies to a top-level `contents: "Octopus+"`
   exposure.
4. **Non-affected placeholders stay high.** `policy_number` matches
   the system path `$data.policyNumber` without touching the
   iterables index. Neither Rule 1's naming-mismatch nor the
   terminology layer cascade to variables that have nothing to do
   with the mis-named exposure.
5. **Fallback path still exists.** Removing the fixture-local
   `terminology.yaml` reverts the behaviour to the pre-Phase-E
   contract (low + `supply-from-plugin` per the FIXTURE.md that
   shipped with session C4). The fixture's goldens assume the
   terminology file is present; tests that delete or rename it will
   regress to the session-C4 golden values.

## Inputs

- `socotra-config/products/DeepSeaFleet/config.json` —
  `contents: ["Octopus+"]`, `charges: []`, no policy data.
- `socotra-config/exposures/Octopus/config.json` — 1 data field
  (`tankId: string`), no coverages. The `displayName` is `Octopus`
  (matches the exposure name exactly).
- `mapping.yaml` — 1 variable (`policy_number`), 1 loop
  (`octopuses`, deliberately mis-named relative to Socotra's
  derived plural) with 0 fields.
- `terminology.yaml` — Phase E synonym layer (tenant:
  `DeepSeaFleet`). Declares `synonyms.exposures.Octopus:
  [octopuses, octopi]`. Lives alongside `mapping.yaml` at the
  fixture root (the suggester's Step 0c resolves the sibling-of-
  registry path; for an agent run against the golden registry, that
  sibling is this fixture's root).

## Goldens

- `golden/path-registry.yaml` — 18 total addressable paths (8 system
  + 9 account + 0 policy + 1 exposure field); 1 iterable
  (`Octopus+` with `list_velocity: $data.octopus`); 10 feature
  flags all `false`. Not affected by Phase E — `extract_paths.py`
  does not read `terminology.yaml`.
- `golden/suggested.yaml` — 2 `high` (`policy_number` +
  `octopuses`), 0 `medium`, 0 `low`. The `octopuses` loop resolves
  to `$data.octopus` via the terminology layer; `reasoning` carries
  the standard `matched via terminology.yaml synonym …` line.
- `golden/review.md` — 0 blockers, 0 assumptions, 0 cross-scope
  warnings, 2 done items (with a `(via terminology.yaml synonym
  octopuses → canonical Octopus)` annotation on the `octopuses`
  row), 0 unrecognised-inputs rows. Header carries an extra
  `Terminology:` bullet that names the loaded file, the tenant, the
  active-alias count, and the match count this run.
