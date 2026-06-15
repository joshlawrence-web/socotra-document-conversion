# SCHEMA.md — Pipeline artifact contract

**Status:** Living document. Every PR that changes artifact shape MUST
update the relevant table below and bump the relevant `schema_version`,
or the mapping-suggester's shape probe will fire and block the run.

## Purpose

The HTML → Velocity pipeline flows data between four skills:

1. `html-to-velocity` (Leg 1) — reads an HTML mockup, writes
   `<stem>.vm`, `<stem>.mapping.yaml`, `<stem>.report.md`.
2. `extract_paths.py` (Leg 2a) — reads a `socotra-config/` tree, writes
   `registry/path-registry.yaml` by default (or `--output`).
3. `mapping-suggester` (Leg 2) — reads the mapping YAML + the registry,
   writes `<stem>.suggested.yaml`, `<stem>.review.md`.
4. `leg4_generate_plugin.py` (Leg 4) — reads `<stem>.suggested.yaml` + JARs,
   writes `{Product}DocumentDataSnapshotPluginImpl.java` and
   `<stem>.plugin-report.md`. No `schema_version` — Java output is not a
   versioned YAML artifact.

Each of the four YAML/Markdown artifacts (mapping, registry, suggested,
review) carries a `schema_version` string at its root. The fifth
artifact — the per-run telemetry `<stem>.suggester-log.jsonl` landed in
Phase D session D1 — is JSON Lines, so its contract is expressed as a
JSON Schema at `conformance/schemas/suggester-log.schema.json` instead. The
sixth artifact — the repo-level lessons ledger `skill-lessons.yaml`
landed in Phase D session D2 — is a YAML file and carries a
`schema_version` root key like the first four. The seventh artifact —
the per-tenant synonym layer `terminology.yaml` landed in Phase E — is
a YAML file and carries a `schema_version` root key like the other
YAML artifacts. It is **optional**: the mapping-suggester's Step 0c
skips silently when the file is absent. The string-or-schema
versioning is the pipeline-wide contract; consumers refuse to run when
their supported MAJOR does not match the producer's MAJOR.

## Compatibility rules

- `schema_version` is a `'MAJOR.MINOR'` string (YAML quoted to force
  string parsing — `'1.0'`, not `1.0`).
- **MAJOR** bumps on breaking shape changes: removed keys, renamed
  keys, changed value types, or moved sections. Consumers supporting an
  older MAJOR MUST halt before writing any output and print the
  upgrade-path message documented in the relevant SKILL.md.
- **MINOR** bumps on additive changes: new optional keys, new values
  in an enum, new top-level sections. Consumers supporting an older
  MINOR MUST proceed with a warning and MUST preserve any unrecognised
  keys verbatim on pass-through.
- **Unrecognised keys** at any level are always preserved. The mapping
  suggester's Step 2a shape probe records them under "Unrecognised
  inputs" in `<stem>.review.md` with `next_action: needs-skill-update`;
  the substitution writer (Leg 3) must do the same when it arrives.
- The first release of the contract is `1.0`. Subsequent versions append
  a row to the "Change log" at the bottom of this file.

## Artifact: `path-registry.yaml`

Produced by: `extract_paths.py`. Current version: **1.1** (MINOR bump: `meta.source_config_sha256`).

Canonical location in this repository: **`registry/path-registry.yaml`** (not at the repo root).

### Top-level sections (recognised in v1.1)

| Key | Type | Description |
|---|---|---|
| `schema_version` | string | `'1.1'`. First key in the file. |
| `meta` | map | Generation metadata (config_dir, product, display_name, generated_at, note). Always present. |
| `feature_support` | map | Boolean flags reporting which Socotra config features the structural scan saw (Phase B, session B1). Ten flags today; see the dedicated table below. Always present in registries produced by the current `extract_paths.py`. |
| `iterables` | list of map | Flat index of every foreach-able element. One row per `+`/`*`-quantified exposure; coverages and data-extension arrays will join here when Phase B lands. |
| `system_paths` | list of map | `$data.<field>` entries that exist on every policy (locator, productName, currency, timestamps, …). |
| `account_paths` | list of map | `$data.account.data.<field>` entries. |
| `policy_data` | list of map | `$data.data.<field>` entries declared in the product's `data:` block. |
| `policy_charges` | list of map | `$data.charges.<ChargeName>` entries. |
| `exposures` | list of map | One block per exposure (Vehicle, Driver, …), each with nested `fields`, `coverages`, `system_fields`. |

### `meta` keys (v1.0)

| Key | Type | Description |
|---|---|---|
| `config_dir` | string | Absolute path to the source `socotra-config/`. |
| `product` | string | First product directory name (e.g. `CommercialAuto`). |
| `display_name` | string | `displayName` from the product's `config.json`. |
| `generated_at` | string | ISO-8601 UTC timestamp of the run. |
| `source_config_sha256` | string | **v1.1+** Deterministic SHA-256 (lowercase hex) over the Socotra config inputs Leg 2a consumed; see **Registry config fingerprint** below. |
| `note` | string | Free-form human-readable explanation of the conventions in use. |

### Registry config fingerprint (`meta.source_config_sha256`, v1.1+)

Implemented in `velocity_converter/socotra_config_fingerprint.py` and invoked from `extract_paths.py` and Leg 2 tooling.

- **Root:** resolved `socotra-config/` directory.
- **Files:** every `config.json` under `products/`, `exposures/`, `coverages/`, `charges/`, `accounts/`, `customDataTypes/`, and `perils/` (recursive), sorted by relative POSIX path.
- **Payload:** for each file, append `relative_path + "\n" + utf8_text + "\n"` to a running SHA-256 (UTF-8 decode with replacement on invalid bytes).
- **Output:** lowercase hex digest of the final hash.

Leg 2 (`velocity_converter/leg2_fill_mapping.py` and the mapping-suggester skill) may recompute the same digest from `--config-dir` and **refuse to run** when it disagrees with `meta.source_config_sha256` unless an explicit escape hatch is used (see provenance keys `registry_config_check` / `registry_config_verified` on `<stem>.suggested.yaml` and JSONL summaries).

### `feature_support` keys (v1.0)

Emitted by `extract_paths.py → detect_features()` via a structural scan
of `socotra-config/`. Every flag is derived from live config contents
— not from file or directory presence alone. See `CONFIG_COVERAGE.md`
in this directory for the authoritative matrix of what each flag means,
which configs have it today, and whether the mapping-suggester has a
matching rule for it.

| Key | Type | Description |
|---|---|---|
| `nested_iterables` | bool | `true` iff any data-extension field has type `<CDT>+` or `<CDT>*` (an array of a custom data type). |
| `custom_data_types` | bool | `true` iff any `customDataTypes/<Name>/config.json` parses successfully. |
| `recursive_cdts` | bool | `true` iff any CDT's `data` map references its own name via `type: <Self>` (optionally quantified). |
| `jurisdictional_scopes` | bool | `true` iff any coverage or the product config carries `qualification`, `appliesTo`, or `exclusive`. |
| `peril_based` | bool | `true` iff a `perils/` directory exists with at least one subdirectory. |
| `multi_product` | bool | `true` iff `products/` has more than one subdirectory. |
| `coverage_terms` | bool | `true` iff any coverage has a non-empty `coverageTerms: [...]` array. |
| `default_option_prefix` | bool | `true` iff any coverage-term option starts with `*` (marks the default). |
| `auto_elements` | bool | `true` iff any `!` suffix appears on a `contents` token or a data-extension `type`. |
| `array_data_extensions` | bool | `true` iff any data-extension `type` ends in `+` or `*` (primitive or CDT). |

Consumers read these flags to decide whether a feature-dependent
matching rule may safely run. The mapping-suggester enforces a refusal
rule (see `.cursor/skills/mapping-suggester/SKILL.md` Step 2a, Feature-
support refusal rule): flags whose name is not on the skill's current
"rule-supported flags" whitelist surface a `needs-skill-update:` row in
`<stem>.review.md` §7 whenever they are `true`. CommercialAuto today
carries all ten flags `false`; no refusal fires in the current
regression.

Adding a new flag requires (a) extending `detect_features()`, (b)
adding a row here, (c) adding a matching row in `CONFIG_COVERAGE.md`
§3, and (d) updating the SKILL's refusal whitelist. The four edits
must land in the same PR or the contract is broken.

### Entry keys (v1.0) — any `system_paths` / `account_paths` / `policy_data` / exposure `fields` / coverage `fields` / `system_fields` row

| Key | Type | Description |
|---|---|---|
| `field` | string | Canonical field name (matches the mapping YAML's `name` for high-confidence matches). |
| `display_name` | string | Human-readable label (`displayName` from config, or fallback to `field`). |
| `type` | string | Raw type token including quantifier suffix (e.g. `string+`, `Vehicle`, `decimal?`). |
| `base_type` | string | Same as `type` with the quantifier stripped. |
| `quantifier` | enum | One of `''`, `'!'`, `'?'`, `'+'`, `'*'`. |
| `cardinality` | enum | `exactly_one`, `exactly_one_auto`, `zero_or_one`, `one_or_more`, `any`. |
| `iterable` | bool | `true` iff `quantifier in {'+', '*'}`. |
| `category` | enum | `system`, `account`, `policy_data`, `exposure_data`, `exposure_system`, `coverage_data`. |
| `velocity` | string | Full Velocity dot-notation path (e.g. `$vehicle.data.year`). |
| `requires_scope` | list of map | Ordered list (outermost first) of `#foreach` steps that must be active for `velocity` to resolve. Empty list when none are required. |
| `options` | list of string? | Enum options when the config declared `options: [...]`. Omitted otherwise. |
| `custom_type_ref` | string? | Present when `base_type` refers to a custom data type rather than a primitive. Omitted otherwise. |

### Charge-entry keys (`policy_charges`, coverage `charges`)

| Key | Type | Description |
|---|---|---|
| `name` | string | Charge name (directory under `charges/`). |
| `category` | string | `category` from the charge's own config.json, or `"unknown"`. |
| `velocity_amount` | string | `$…charges.<Name>.amount` path. |
| `velocity_object` | string | `$…charges.<Name>` (use when iterating the charge object itself). |
| `requires_scope` | list of map | Same shape as above. |

### Iterables-index keys

| Key | Type | Description |
|---|---|---|
| `name` | string | Canonical name (e.g. `Vehicle`). |
| `display_name` | string | `displayName` from the exposure's config. |
| `kind` | enum | `exposure` (Phase B will add `data_extension_array`, etc.). |
| `list_velocity` | string | Path to the iterable collection (`$data.vehicles`). |
| `iterator` | string | `#foreach` iterator variable (`$vehicle`). |
| `foreach` | string | Literal `#foreach (…)` directive to copy into templates. |
| `quantifier` / `cardinality` | enum | As above. |

### Exposure-block keys

| Key | Type | Description |
|---|---|---|
| `name` | string | Exposure name (e.g. `Vehicle`). |
| `display_name` | string | From config. |
| `list_velocity` | string | `$data.<plural>`. |
| `iterator` | string | Derived iterator stem (without `$`). |
| `foreach` | string | Literal `#foreach (…)` directive. |
| `raw_contents` | list of string | Raw `contents:` tokens from the exposure config (quantifiers intact). |
| `system_fields` | list of map | Exposure `locator`, `name`, etc. |
| `fields` | list of map | Data-extension fields on the exposure. |
| `coverages` | list of map | Nested coverage blocks. |
| `quantifier` / `cardinality` / `iterable` | enum | Same as entry-level. |

### Coverage-block keys

| Key | Type | Description |
|---|---|---|
| `name` | string | Coverage name (e.g. `Coll`). |
| `display_name` | string | From config. |
| `velocity` | string | `$<iterator>.<Coverage>`. |
| `note` | string | Human guidance about the `#if` guard. |
| `requires_scope` | list of map | Inherited from parent exposure. |
| `fields` | list of map | Coverage data-extension fields. |
| `charges` | list of map | Coverage-level charges. |
| `quantifier` / `cardinality` / `iterable` | enum | Same as entry-level. |

### `requires_scope` step shape

| Key | Type | Description |
|---|---|---|
| `iterator` | string | Velocity reference (e.g. `$vehicle`). |
| `foreach` | string | Literal `#foreach (…)` directive. |

## Artifact: `<stem>.mapping.yaml`

Produced by: `html-to-velocity/velocity_converter/convert.py` (Leg 1).
Current version: **1.0**.

### Top-level sections

| Key | Type | Description |
|---|---|---|
| `schema_version` | string | `'1.0'`. First key in the file. |
| `source` | string | Basename of the source HTML file. |
| `generated_at` | string | ISO-8601 UTC timestamp. |
| `variables` | list of map | Top-level placeholders. |
| `loops` | list of map | Detected loops, each with nested `fields`. |
| `warnings` | list of string? | Optional list of loop-conversion warnings. Omitted when empty. |

### Variable-entry keys

| Key | Type | Description |
|---|---|---|
| `name` | string | Placeholder identifier. |
| `placeholder` | string | Full `$TBD_*` token. |
| `type` | enum | `variable` or `loop_field`. |
| `context` | map | See context keys below. |
| `data_source` | string | Empty at Leg 1. Filled by Leg 2 / human review. |
| `occurrence` | enum? | `required` (default) / `optional` / `one_or_more` / `zero_or_more`. Declared in the source document by an occurrence symbol prefixing the placeholder name — `{x}` required, `{$x}` optional, `{+x}` one or more, `{*x}` zero or more (mirrors the registry quantifier vocabulary). The symbol never reaches the `$TBD_*` token; it is normalised here at Leg 0. Leg 4 turns `required`/`one_or_more` into plugin-side null/empty guards that throw `IllegalStateException` when the data is missing — the template carries no null-safety logic. |

### `context` keys (v1.0 contract)

| Key | Type | Description |
|---|---|---|
| `parent_tag` | string | HTML parent element (`p`, `td`, `li`, …). |
| `nearest_label` | string | Closest label / heading text. |
| `line` | int | Line number in source HTML (BeautifulSoup `sourceline`). |
| `loop` | string? | Enclosing loop name (set on every loop field). |
| `loop_hint` | string? | Canonical iterable `name` implied by variable prefix. Top-level variables only. |
| `column_header` | string? | Table column header (for `<td>` context). |
| `container` | string? | Container element (`ul`, `tbody`, …). Set on loop entries. |
| `detection` | enum? | How Leg 1 detected the loop (`mustache`, `liquid`, `heuristic`, `auto`, `explicit`). |

Any other keys under `context:` are **preserved but unused** —
mapping-suggester reports them under "Unrecognised inputs" in
`<stem>.review.md`.

### Loop-entry keys

| Key | Type | Description |
|---|---|---|
| `name` | string | Loop name. |
| `placeholder` | string | `$TBD_<name>`. |
| `iterator` | string | `$<iterator>` (e.g. `$vehicle`). |
| `detection` | enum | `mustache` / `auto` (Leg 1) / `marker` (Leg 0 `[Name]`…`[/Name]` sections). |
| `context` | map | See context keys above (`container`, `nearest_heading`, `line`). |
| `data_source` | string | Empty at Leg 1. |
| `fields` | list of map | Loop-scoped variables (each has the variable-entry shape with `type: loop_field`). |

## Artifact: `<stem>.suggested.yaml`

Produced by: `mapping-suggester` (Leg 2). Current version: **2.0** (MAJOR: per-(placeholder × rendering-root) verdicts grounded in the compiled JARs).

> **MAJOR break (2.0).** The scalar `data_source` / `confidence` / `reasoning`
> on each variable/loop is **replaced** by a root-independent `candidate` plus a
> per-root `verdicts` map, and a new top-level `rendering_roots` list is added.
> Confidence is now decided by introspecting `build/*.jar` (`javap`) per
> rendering root — the JARs are the authority (Leg2 plan D1/D4). Downstream
> consumers that only support `1.x` (Leg 3, Leg 4) MUST halt with an
> upgrade-path message until the §14 harmonisation lands; until then they read a
> 2.0 file as having no high-confidence scalar fields. Output modes
> (`full`/`terse`/`delta`/`batch`) were removed in 2026-06 — Leg 2 has a
> single output behaviour (the former `terse`).

### Rendering roots (2.0)

A document renders against the root(s) declared in its source filename brackets
(`<stem>(<root>[,<root>...]).html`, e.g. `Simple-form(segment).html`). Leg 2
parses this from the mapping's `source:` value; absence is a hard blocker
surfaced in `<stem>.review.md` (no verdicts written). Allowed roots: `quote`,
`segment`, `invoice` (invoice is enumerable but **not resolved** in the first
cut — D5). The first listed root is primary.

### Top-level sections

| Key | Type | Description |
|---|---|---|
| `schema_version` | string | `'2.0'`. First key. |
| `run_id` | string | UUID for this run; matches JSONL `run_id`. |
| `generated_at` | string | ISO-8601 UTC timestamp. |
| `input_mapping_sha256` | string | SHA-256 of mapping file bytes read. |
| `input_registry_sha256` | string | SHA-256 of registry file bytes read. |
| `registry_schema_version` | string | Registry root `schema_version`. |
| `registry_generated_at` | string | From registry `meta.generated_at`. |
| `registry_config_dir` | string | From registry `meta.config_dir` (tree the registry claimed). |
| `registry_source_config_sha256` | string? | From registry `meta.source_config_sha256` when present. |
| `live_source_config_sha256` | string? | Recomputed from `--config-dir` when supplied. |
| `registry_config_verified` | bool | `true` only when embedded and live fingerprints matched. |
| `registry_config_check` | string | `matched` \| `skipped_no_config_dir` \| `skipped_escape_hatch` \| `skipped_missing_registry_fingerprint` \| `failed_mismatch`. |
| `input_mapping_version` | string | `schema_version` read from `<stem>.mapping.yaml`. |
| `input_registry_version` | string | `schema_version` read from `path-registry.yaml`. |
| `source` | string | Copied from mapping (carries the `(root)` bracket Leg 2 parses). |
| `path_registry` | string | Path to the registry file used (relative to suggested output when under the repo, else absolute). |
| `product` | string | `meta.product` from the registry. |
| `rendering_roots` | list of map | **2.0** — declared roots: `{id, java_type, request, primary}`. `java_type` is `null` for invoice (deferred). |
| `tooling` | map? | Optional `{ mapping_suggester: { version, ruleset_id } }`. |
| `variables` | list of map | Variable entries (see below). |
| `loops` | list of map | Loop entries. |

Every key from the input mapping YAML is preserved verbatim. Any
unrecognised keys pass through unchanged.

### `rendering_roots` entry keys (2.0)

| Key | Type | Description |
|---|---|---|
| `id` | enum | `quote` \| `segment` \| `invoice`. |
| `java_type` | string? | Fully-qualified `renderingData` type (e.g. `com.socotra.deployment.customer.ItemCareSegment`); `null` for invoice (D5). |
| `request` | string | Plugin request type simple name (`ItemCareRequest`, `ItemCareQuoteRequest`, `InvoiceDetailsRequest`). |
| `primary` | bool | `true` for the first declared root. |

### Variable-entry keys (suggested 2.0)

Superset of the mapping entry. The scalar `data_source`/`confidence`/`reasoning`
of 1.x is replaced by `candidate` + `verdicts`:

| Key | Type | Description |
|---|---|---|
| `name` / `placeholder` / `type` / `context` | — | Copied from mapping, verbatim. |
| `candidate` | map | Root-independent name-match: `{path, match_step, registry_field}`. `path` is the registry `velocity` (empty when no single match). `match_step` ∈ `exact` \| `ci` \| `terminology` \| `fuzzy` \| `none`. |
| `verdicts` | map | One entry per root id in `rendering_roots`. Each verdict is the per-root grading below. |

#### Verdict shape (per root, 2.0)

| Key | Type | Description |
|---|---|---|
| `data_source` | string | The candidate path **only when `sdk_status: verified`**; empty otherwise (no invented paths). |
| `confidence` | enum | `high` / `medium` / `low`. Graded by `confidence_grade(match_step, sdk_status)`. |
| `sdk_status` | enum | `verified` \| `not_found` \| `sibling_only` \| `not_navigable` \| `skipped` (see table below). |
| `sibling_hint` | string? | Present on `sibling_only` — e.g. `Policy.policyNumber()` (the request-reachable sibling that exposes the field). |
| `reasoning` | string | Prose; carries exactly one next-action for non-`high` verdicts. |

#### `sdk_status` enum + grading (2.0)

| `sdk_status` | Meaning | Confidence given `match_step` |
|---|---|---|
| `verified` | path navigable on this root via `javap` | `high` if exact/ci/terminology; `medium` if fuzzy |
| `not_found` | no such accessor on the root, nor on a sibling | `low` + `supply-from-plugin` |
| `sibling_only` | absent on root, present on `Policy`/`Transaction` (request sibling) | `low` + `supply-from-plugin` (+ `sibling_hint`) |
| `not_navigable` | a path segment returns a scalar/`java.*` and can't be walked further | `low` + `confirm-assumption` |
| `skipped` | invoice root (D5), or no candidate path to check | `low` |

**The JAR can only demote** (D8): a `fuzzy` name-match that happens to be
`verified` stays `medium`; SDK truth never promotes a weak match to `high`.
Method resolution is case-insensitive to mirror Velocity property access
(`$item.Accessories` → `accessories()`).

### Loop-entry keys (suggested 2.0)

Superset of the mapping loop entry plus:

| Key | Type | Description |
|---|---|---|
| `iterator` | string | Copied from the registry iterables index. |
| `foreach` | string | Literal `#foreach (…)` directive. |
| `candidate` | map | `{list_velocity, match_step}` (root-independent). |
| `verdicts` | map | Per-root verdict for the loop list root (`list_velocity` validated against each root's Java type). |
| `available_coverages` | list of map? | Emitted on exposure loops. Lists the coverages on the exposure with their `velocity`, `quantifier`, `cardinality`. |
| `fields` | list of map | Each loop field carries `candidate: {velocity, match_step}` + per-root `verdicts`, validated against the **iterator element type** resolved from the root via `javap` (e.g. `ItemCareSegment.items()` → `ItemPolicy`). |

### Next-action vocabulary (used inside `reasoning`)

Closed vocabulary — exactly one per `low`/`medium` variable or loop
entry. See `.cursor/skills/mapping-suggester/SKILL.md` → "Ambiguity
bubble-up" for semantics.

- `pick-one`
- `supply-from-plugin`
- `restructure-template`
- `delete-from-template`
- `confirm-assumption`
- `needs-skill-update` — used exclusively in the review file's
  "Unrecognised inputs" section, never on a variable or loop entry.

## Artifact: `<stem>.review.md`

Produced by: `mapping-suggester` (Leg 2). Current version: **2.0** (per-root rendering, tracks the `.suggested.yaml` MAJOR bump).

### Required layout

| Position | Content | Description |
|---|---|---|
| Line 1 | `<!-- schema_version: 2.0 -->` | HTML comment carrying the **review document** version. Parseable without loading the body. |
| Line 2 | (blank) | |
| Section 1 | `# Mapping review — <stem>` | Metadata bullets, incl. a `Rendering roots:` bullet and a `Schema:` bullet `2.0 (mapping <M>.<N>, registry <M>.<N>)`. |
| Section 2 | `## Summary (per rendering root)` | Per-root high/medium/low table + next-action breakdown (primary root). |
| Section 3 | `## Blockers (low confidence, per root)` | One row per `(placeholder × root)` low verdict, with `sdk_status` + next-action. A field can be a blocker on one root and `Done` on another. |
| Section 4 | `## Assumptions to confirm (medium confidence, per root)` | Per-root medium verdicts. |
| Section 5 | `## Cross-scope warnings` | Table of name-match-but-scope-wrong variables (primary root). |
| Section 6 | `## Done (high confidence, per root)` | Collapsed `<details>` list of high-confidence `(placeholder × root)` verdicts. |
| Section 7 | `## Unrecognised inputs` | Table of keys the shape probe flagged. Always render; print "No unrecognised inputs." when empty. |

A missing/invalid rendering-root declaration short-circuits to a `## Blockers`
review with no verdicts (Leg2 plan §8).

**v1.1 extensions (tool-emitted; optional in frozen conformance goldens):**
between Section 1 and `## Summary`, `velocity_converter/leg2_fill_mapping.py` may emit
provenance bullets (`run_id`, paths, hashes, registry lineage,
`registry_config_check`), a `---` separator, and
`## State summary`. Hand-authored `conformance/fixtures/*/golden/review.md`
files may omit those blocks until refreshed from a live run; they must still
use the line-1 HTML comment and a correct `Schema:` bullet for the paired
mapping and registry versions.

## Artifact: `<stem>.suggester-log.jsonl`

Produced by: `mapping-suggester` (Leg 2). Current version: **1.0**
(landed session D1, 2026-04-22). Per-run telemetry in the JSON Lines
format — one JSON object per line. Append-only across runs; each
invocation adds a fresh batch of `kind: placeholder` records (one per
mapping `variables` entry, then one per `loops` entry) terminated by
exactly one `kind: summary` record. The authoritative contract is the
JSON Schema at `conformance/schemas/suggester-log.schema.json`; the tables
below mirror that schema.

Note: the log file is JSON Lines, not YAML, so `schema_version` does
not appear as a top-level key. Instead, every record is validated
against `conformance/schemas/suggester-log.schema.json`; the schema carries
its own `$id` and is version-stamped in the change log below. Breaking
changes to the log shape bump the schema file's `$id` minor/major
marker AND add a `schema_version` hint to the summary record in the
next release (deferred until a real breaking change is proposed).

### Shared fields (every record)

| Key | Type | Description |
|---|---|---|
| `ts` | string | UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ` (fractional seconds optional). |
| `run_id` | string (UUID) | Shared across every record from the same invocation. |
| `kind` | enum | `placeholder` or `summary`. |

### `kind: placeholder` — one per mapping entry

| Key | Type | Description |
|---|---|---|
| `name` | string | `name:` field from the mapping entry. |
| `placeholder` | string | Full `$TBD_*` token (scope-prefixed when applicable). |
| `type` | enum | `variable` / `loop` / `loop_field`. |
| `context` | object | Verbatim copy of the mapping entry's `context:` block, including unrecognised keys. |
| `chosen_match` | string \| null | Velocity path chosen (matches `data_source:` in the suggested YAML); `null` when no match. |
| `confidence` | enum | `high` / `medium` / `low`. |
| `next_action` | enum \| null | Closed vocabulary — `pick-one`, `supply-from-plugin`, `restructure-template`, `delete-from-template`, `confirm-assumption`, `needs-skill-update`; `null` only on `high` rows that need no follow-up. |
| `rejected_candidates` | array | Candidate paths considered but rejected. Each item is `{velocity: string, reason: enum}` where `reason` ∈ `scope_violation | quantifier_mismatch | cardinality_mismatch | type_mismatch | display_name_mismatch | charge_form_mismatch | feature_refused | ambiguous_tiebreak | no_label_context | other`. |
| `unknown_context_keys` | array<string> | Context keys on this entry NOT in the v1.0 recognised vocabulary. |

### `kind: summary` — exactly one per run

| Key | Type | Description |
|---|---|---|
| `source` | string | Original HTML filename (mapping YAML's `source:` key). |
| `product` | string | Product name (registry `meta.product`). |
| `totals` | object | `{variables: int, loops: int}`. |
| `confidence_counts` | object | `{high: int, medium: int, low: int}`. |
| `next_actions` | object | Count per next-action code observed this run; codes with zero occurrences may be omitted. |
| `dead_registry_paths` | array<string> | Registry entries that matched zero placeholders this run. Sort lexicographically; consumers MAY truncate for readability. |
| `hot_registry_paths` | array<string> | Registry entries matched by ≥ 2 placeholders this run (candidates for terminology promotion). |
| `unknown_context_keys_seen` | array<string> | Union of every placeholder record's `unknown_context_keys`, sorted. |

**v1.1 summary extensions (optional, additive):**
`input_mapping_sha256`, `input_registry_sha256`,
`registry_schema_version`, `registry_generated_at`,
`registry_config_dir`, `registry_source_config_sha256`,
`live_source_config_sha256`, `registry_config_verified`,
`registry_config_check`, and `result_suggested_sha256`.
Older logs may also carry `mode`, `base_suggested_sha256`,
`previous_run_id`, and `delta_changes` (object) — these keys are no
longer emitted (modes removed 2026-06). Logs may omit any of these
keys; validators MUST treat them all as optional.

### Emission rules

- Log written in Step 4c of the `mapping-suggester` SKILL.md "How to
  run" sequence, in the same in-memory pass that writes
  `<stem>.suggested.yaml` and `<stem>.review.md`.
- File is append-only. Successive runs add records without rewriting.
- Absence of the log after a run that produced `.suggested.yaml` and
  `.review.md` is a bug, not a feature.
- Step 0 MAJOR halts produce no log (nothing ran).

## Artifact: `skill-lessons.yaml`

Produced by: human seed (Phase D session D2, 2026-04-22) + incremental
updates from `mapping-suggester` (Leg 2) Step 4d. Lives alongside the
path registry (e.g. `registry/skill-lessons.yaml`). Current version: **1.0**. Optional — older checkouts may not
have it; the suggester's Step 0b skips silently when absent.

The ledger accumulates patterns that keep surfacing across customers
and documents so a human reviewer can decide whether the pattern
deserves a first-class rule in `mapping-suggester/SKILL.md`. Agents
append and bump; promotion is human-only (see "Lesson workflow
(Phase D)" in the SKILL and the Phase D §7 hard constraint).

### Top-level sections

| Key | Type | Description |
|---|---|---|
| `schema_version` | string | `'1.0'`. First key in the file. |
| `lessons` | list of map | One entry per observed pattern. Order is insertion order; rows are never reordered. |

### Lesson-entry keys (v1.0)

| Key | Type | Description |
|---|---|---|
| `id` | string | Short kebab-case identifier, unique within the file. Used by the SKILL's per-lesson matcher table. |
| `first_seen` | string (date) | ISO `YYYY-MM-DD` of the first run that observed the pattern. Never edited after creation. |
| `last_seen` | string (date) | ISO `YYYY-MM-DD` of the most recent run that observed the pattern. Bumped by agents on every matching run. |
| `seen_count` | int | Number of runs (not placeholders) in which the pattern fired. Incremented by agents by exactly 1 per matching run. |
| `observed_in` | array<string> | Source stems (e.g. `claim-form`, `renewal-notice`) where the pattern was observed. Agents append new stems; never deduplicate an existing entry. |
| `pattern` | string | Prose description of the phenomenon. Agent-immutable after creation. |
| `current_rule` | string | The confidence-level + next-action code the suggester currently applies for this pattern (e.g. `"medium, confirm-assumption"`). Agent-immutable after creation. |
| `candidate_promotion` | string \| null | Concrete promoted rule proposed by a human reviewer. `null` until a reviewer writes it. Agents MUST leave this field untouched. |
| `status` | enum | `observed` \| `proposed` \| `promoted` \| `rejected`. Agent-immutable on existing rows; new rows are born as `observed`. |

### State machine

```
observed  ──┐
            ├──► proposed  ──►  promoted
            │         │
            │         └────►  rejected
            │
            └── (stays at observed until a human acts)
```

Transitions are human-only. Agents MUST NOT write any transition. See
the SKILL's "Lesson workflow (Phase D)" section for the authoritative
division-of-responsibility table.

### Agent-auto-promotion prohibition

This is a hard constraint (test failure, not style guideline). The
constraint lives in two places for redundancy:

- `.cursor/skills/mapping-suggester/SKILL.md` → "Important
  constraints" → "Do not auto-promote lessons".
- `.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md` §7 ("Hard constraints") → "Do not
  auto-promote lessons".

Any run that sets `status: promoted` (or edits `candidate_promotion`
from `null`) without a human review is a test failure.

### Emission rules

- Read in Step 0b of the `mapping-suggester` SKILL.md "How to run"
  sequence; written in Step 4d of the same sequence.
- Writes preserve existing comments and the seed's key order on
  untouched rows.
- When no lesson matches and no new pattern is observed this run,
  Step 4d is a no-op — the file is not rewritten.
- Absent file is legitimate — Step 0b skips silently. The file is
  never auto-created; seeding is a human-initiated act.

## Artifact: `terminology.yaml`

Produced by: human hand-authoring (Phase E, 2026-04-23). Read by:
`mapping-suggester` (Leg 2) Step 0c. **Resolution order:** (1) sibling
of the registry file being used (e.g. `registry/terminology.yaml` next to
`registry/path-registry.yaml`); (2) path from `--terminology <path>`.
Current version: **1.0**. Optional — checkouts without the file skip
synonym matching silently.

The per-tenant synonym layer lets customer-specific vocabulary
(Vehicle vs Unit vs Asset, Liability vs BI-PD, etc.) resolve to the
canonical Socotra config names the registry emits, without bleeding
tenant data into `.cursor/skills/`. Matching is exact-string only;
fuzzy / stemming / regex synonyms are explicitly out of scope (see
`.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md` §10).

### Top-level sections

| Key | Type | Description |
|---|---|---|
| `schema_version` | string | `'1.0'`. First key in the file. |
| `tenant` | string | Free-text identifier. Separate tenants MUST live in separate files; the suggester refuses to merge two terminology files (see below). |
| `synonyms` | map | Three sub-maps (`exposures`, `coverages`, `fields`), each keyed by canonical registry name → list of alias strings. |
| `display_name_aliases` | map | Free-text `display_name` strings → list of aliases. Used when the placeholder's `nearest_label` / `nearest_heading` matches a display string rather than a canonical field name. |

### `synonyms` sub-maps (v1.0)

| Sub-map | Canonical keys resolve against | Alias list |
|---|---|---|
| `exposures` | `iterables[].name` where `kind: exposure` | Strings a Leg 1 mapping may use for the loop `name`, `context.nearest_heading`, or a top-level variable's `context.loop_hint`. |
| `coverages` | `exposures[].coverages[].name` (any exposure) | Strings that may appear on coverage loops or coverage-scoped variables. |
| `fields` | Any registry `field` key — `system_paths`, `account_paths`, `policy_data`, exposure `fields`, coverage `fields`, `system_fields`, coverage `charges[].name`. | Strings that may appear as a variable `name` or its `nearest_label`. |

Missing sub-maps are legitimate — the suggester reads a sub-map as
empty when the key is absent or `null`.

### `display_name_aliases` (v1.0)

| Key | Type | Description |
|---|---|---|
| (any quoted string) | list of string | Aliases a placeholder's `context.nearest_label` / `context.nearest_heading` may use for the keyed display string. Quoted to preserve spaces and casing. |

### Matching precedence

See `.cursor/skills/mapping-suggester/SKILL.md` → "Name-match
precedence (Phase E — terminology layer)". Brief summary:

1. Exact match against the registry.
2. Case-insensitive match against the registry.
3. **Terminology synonym lookup** — the alias must appear verbatim in
   a `synonyms.*` or `display_name_aliases[*]` list. Match is
   case-insensitive string equality; the map key is the canonical
   name. Every terminology-sourced match carries the reasoning line
   `matched via terminology.yaml synonym <alias> → canonical <name>`.
4. Fuzzy / obvious-synonym fallback (last resort).

### Hard constraints

- **Single file per run.** The suggester MUST NOT merge two
  terminology files. If `--terminology <path>` is passed AND the
  sibling-of-registry default resolves, the flag wins and the sibling
  is ignored — the sibling is not read, not validated, and not
  unioned. Cross-tenant contamination is a test failure (see
  `.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md` §6.3 / §7 and
  `.cursor/skills/mapping-suggester/SKILL.md` → "Important
  constraints").
- **Canonicals must exist in the registry.** Unknown canonical
  names surface a `needs-skill-update: terminology canonical name
  <X> not found in registry` row in `<stem>.review.md` §7 at
  shape-probe time and the entry is dropped from the active synonym
  map for that run (it is not used for matching).
- **No storage under `.cursor/skills/`.** The file lives alongside the
  registry (or a project-specific registry folder) so tenant data stays out of the skill.
- **No auto-promotion from lessons.** Synonyms enter this file
  through user hand-editing or through a human reviewer promoting a
  `skill-lessons.yaml` row; agents never add a synonym without a
  prior human-written `candidate_promotion` on the underlying lesson
  row.

### Emission rules

- Read in Step 0c of the `mapping-suggester` SKILL.md "How to run"
  sequence.
- Agents MUST NOT edit this file as part of a suggester run; all
  edits are human-authored.
- Absent file is legitimate — Step 0c skips silently. The file is
  never auto-created; seeding is a human-initiated act.

## Artifact: `<stem>.final.vm`

Produced by: `substitution-writer` (Leg 3). Current version: **1.0**.

This is the production-ready Velocity template. It is the terminal artifact of
the pipeline — the file that gets deployed to Socotra.

### Generation rules

- Read from `<stem>.vm` (Leg 1) and `<stem>.suggested.yaml` (Leg 2).
- Written to `workspace/output/<stem>/<stem>.final.vm` (same directory as all
  other per-document artifacts). The Leg 1 `<stem>.vm` is **never overwritten**.
- Every `$TBD_<NAME>` token where `data_source` is non-empty is replaced
  with the `data_source` value verbatim.
- Every `$TBD_<NAME>` token where `data_source` is empty is preserved
  as-is (design decision DD-2 — see below).
- `#if($TBD_<NAME>)` opener lines and their matching `#end` closer lines are
  stripped (design decision DD-1 — see below).
- `#foreach` lines whose collection is a `$TBD_*` token are replaced with the
  real `foreach` directive from the loop's suggested entry when one is present
  and resolved.

### Design decisions

| Code | Decision | Rationale |
|---|---|---|
| DD-1 | `#if($TBD_*)...#end` guards stripped from all variables in the final output | Leg 1 adds guards for template validity during review. The final Velocity template does not need them — their presence would double-wrap every field. Readability was prioritised over null-safety; guards can be added manually or by a future leg. |
| DD-2 | Unresolved `$TBD_*` tokens preserved as-is | Keeps the template syntactically parseable; makes unresolved tokens immediately visible in the output file. |
| DD-3 | Lenient mode — substitute every resolved token, report the rest | Never abort on low-confidence or empty `data_source`. Partial output is always better than no output for incremental workflows. |

No `schema_version` key is emitted in the `.final.vm` file itself — it is a
Velocity template, not a YAML artifact. The version of the substitution logic
is tracked via `<stem>.leg3-report.md`.

---

## Artifact: `<stem>.leg3-report.md`

Produced by: `substitution-writer` (Leg 3). Current version: **1.0**.

The remedy form. Lists every token in the template alongside its resolution
status. Designed to be human-readable and editable: when tokens remain
unresolved, the reviewer fills in the YAML snippet provided for each one,
updates `<stem>.suggested.yaml`, and re-runs Leg 3.

### Required layout

| Position | Content |
|---|---|
| Line 1 | `<!-- leg3_schema_version: 1.0 -->` |
| Section 1 | Status header table (Status, Source template, Mapping used, Output template, Generated) |
| Section 2 | `## Resolved (N)` — table of substituted tokens (type, placeholder, label, velocity path, confidence) |
| Section 3 | `## Unresolved (N)` — one sub-section per unresolved token with label, source line, action needed, Leg 2 note, action guidance prose, and a YAML fill-in block |
| Section 4 | `## Next steps` — exact `RUN_PIPELINE` command(s) to re-run after fixes |

### Unresolved token sub-section shape

Each unresolved entry contains:
- A metadata table: label, source line, type (variable/loop), action needed, Leg 2 note
- An `_ACTION_GUIDANCE` prose block explaining what the reviewer must do
- A YAML snippet pre-populated with `name`, `placeholder`, and an empty `data_source` field

The YAML snippet is not machine-parseable by the pipeline; it is a human aid.
After editing, the reviewer copies the `data_source` value into the
`.suggested.yaml` file and re-runs Leg 3.

---

## Artifact: `<stem>.conditional-registry.yaml`

Produced by: `leg0_ingest.py --parse-conditional-form` (after the customer
returns the filled conditional form). Consumed by: Leg 2 (automatically when
present beside the mapping), Leg 3 (optional enrichment — warns and ignores
an invalid file), Leg 4 (required when present — halts on an invalid file).

**Unversioned**: the document is a bare YAML list with no `schema_version`
key. The contract is enforced by `velocity_converter/models.py`
(`ConditionalBlock` / `ConditionalRegistry`).

### Block entry shape

| Key | Type | Required | Description |
|---|---|---|---|
| `id` | int | **yes** | Unique block id; `$doc.condN` markers reference it |
| `source_text` | string | **yes** | The conditional text shown to the customer (with `{field}` tokens) |
| `conditions` | list of string | no (default `[]`) | Condition expressions, e.g. `quoteNumber != null`; blank entries are dropped |
| `operator` | string | no (default `AND`) | Combinator for multiple conditions; normalised to upper case |
| `parent_id` | int or null | no | Enclosing block id for nested blocks |
| `depth` | int | no (default 0) | Nesting depth |
| `render` | enum | no (default `plugin`) | `plugin` — Leg 4 bakes the text into the plugin's conditional string; the template prints `${data.condN}`. `template` — the content stays in the `.vm` inside `#if($data.condN)`…`#end` and the plugin puts a Boolean. Set by Leg 0 when the block contains a `[Name]`…`[/Name]` loop section. |

```yaml
- id: 1
  source_text: Accidental Damage cover is included in your plan.
  conditions:
  - quoteNumber != null
  operator: AND
```

## Change log

- **(enforcement) — 2026-06-11 — Typed contract models.**
  `velocity_converter/models.py` now enforces this document's contracts at
  every pipeline read/write boundary (pydantic v2, unknown keys preserved
  via `extra="allow"`). The MAJOR-halt / MINOR-warn rule above is enforced
  by `check_contract_version`; structural violations raise a `ContractError`
  naming the offending entries. Models are validators only — output YAML is
  always dumped from the original dict, never from a model, so key order
  and bytes are unchanged. Telemetry records are validated against
  `conformance/schemas/suggester-log.schema.json` in the test suite. No
  schema_version bumps: shapes are unchanged; this entry records the
  enforcement mechanism only.
- **2.0 — 2026-06-03 — Root-aware, SDK-grounded confidence (MAJOR on
  `.suggested.yaml` + `.review.md`).** Leg 2 now grades confidence per
  **(placeholder × rendering root)** by introspecting the compiled
  `build/*.jar` via `javap` — the JARs are the authority for which `$data.*`
  paths exist on the quote / segment / invoice root a document renders against
  (Leg2 plan D1). The scalar `data_source`/`confidence`/`reasoning` on each
  variable/loop is **replaced** by a root-independent `candidate` plus a per-root
  `verdicts` map; a new top-level `rendering_roots` list is added; the rendering
  root is declared in the source filename brackets `<stem>(<root>).html` (D2,
  no inference — missing brackets are a hard blocker). New `sdk_status` enum
  (`verified` / `not_found` / `sibling_only` / `not_navigable` / `skipped`) with
  a "JAR can only demote" grading rule (D8). The canonical fix: `$data.policyNumber`
  on the `ItemCare` segment root is now `low` + `sibling_only` +
  `Policy.policyNumber()` instead of a false `high`. Added shared
  `velocity_converter/sdk_introspect.py` (factored from Leg 4's `javap` helpers; Leg 4
  imports them back, behaviour unchanged). `--mode delta` is blocked on 2.0
  (D10). Invoice-root resolution is out of the first cut (D5). **Downstream
  impact:** Leg 3 / Leg 4 support only `1.x` and MUST halt with an upgrade
  message until the §14 harmonisation lands; until then they read a 2.0 file as
  having no high-confidence scalar fields. Conformance `suggested`/`review`
  goldens for products **without** build JARs cannot be regenerated to true 2.0
  (SDK grounding requires the compiled product JARs) — they remain at 1.x and
  the conformance runner does not auto-run Leg 2, so the registry checks are
  unaffected. See `.cursor/plans/pipeline-improvements/Leg2-root-aware-confidence/`.
- **1.0 — 2026-04-22 — Initial contract.** Introduced `schema_version`
  on all artifacts, the recognised context-signal vocabulary, the
  Step 2a shape probe, and the `needs-skill-update` next-action code.
  Downstream consumers (mapping-suggester) added a Step 0 version
  check with MAJOR-halt / MINOR-warn semantics. `SCHEMA.md` created
  at the repo root.
- **1.0 — 2026-04-22 — Phase D session D1 (additive, new artifact).**
  Introduced `<stem>.suggester-log.jsonl` as the fifth pipeline
  artifact (JSON Lines telemetry, append-only across runs).
  `mapping-suggester` SKILL.md gained a mandatory Step 4c that
  appends one `kind: placeholder` record per mapping entry plus one
  `kind: summary` record per run. Authoritative JSON Schema lives at
  `conformance/schemas/suggester-log.schema.json` (Draft 2020-12). No
  existing artifact's shape changed — the evolution-plan Phase A
  version contract still reads `1.0` on every existing file. The log
  is observational (no downstream step consumes it yet); Phase D
  session D2 will wire it into `skill-lessons.yaml` promotion.
- **1.0 — 2026-04-22 — Phase D session D2 (additive, new artifact).**
  Introduced `skill-lessons.yaml` at the repo root as the sixth
  pipeline artifact (repo-level lessons ledger, human-curated,
  agent-incremented via `mapping-suggester` Step 4d). Added the
  corresponding `Artifact: skill-lessons.yaml` section above with the
  full top-level + lesson-entry key tables, the
  `observed / proposed / promoted / rejected` state machine, and the
  authoritative restatement of the agent-auto-promotion hard
  constraint. `mapping-suggester/SKILL.md` gained three coordinated
  additions in the same session: a Step 0b that reads the ledger on
  startup, a Step 4d that bumps `seen_count` / `last_seen` /
  `observed_in` on matched rows (and appends new `observed` rows for
  new patterns) in the same in-memory pass as Step 4c, and a new
  top-level "Lesson workflow (Phase D)" section that documents the
  state machine + per-lesson matcher table. The new "Do not
  auto-promote lessons" bullet in "Important constraints" mirrors
  the Phase D §7 hard constraint. No existing artifact's shape
  changed — the D1 telemetry contract and the Phase A v1.0 contract
  still read `1.0` on every file. Demonstrated end-to-end with two
  live Leg 2 runs on `claim-form`: `seen_count` on the
  `claimant-eq-policyholder` lesson grew from the §5.2 seed value of
  2 to 4 across the two runs; `vehicle-scope-violation` grew from 1
  to 3.
- **1.1 — 2026-04-26 — State linking + delta audit (MINOR registry,
  MINOR suggested, additive JSONL).** Canonical
  `registry/path-registry.yaml` (root copy removed). `extract_paths.py`
  emits `meta.source_config_sha256` (registry **1.1**). Leg 2
  provenance (`run_id`, input hashes, registry lineage, optional
  `--config-dir` hash gate with escape hatches) stamped on
  `<stem>.suggested.yaml`, `<stem>.review.md`, and JSONL summaries;
  delta runs carry `delta_changes` + `registry_or_config_changed`.
  Added `velocity_converter/socotra_config_fingerprint.py`,
  `velocity_converter/suggester_state.py`, `velocity_converter/suggester_inspect.py`, and
  extended `velocity_converter/leg2_fill_mapping.py` + `emit_telemetry.py`.
  Conformance runner rejects a stray root-level `path-registry.yaml`.
  `html-to-velocity` auto-discovery checks `registry/path-registry.yaml`
  before `path-registry.yaml` per directory.
- **1.0 — 2026-04-22 — Phase B session B1 (additive, no version bump).**
  Added the `feature_support` top-level block to `path-registry.yaml`
  (emitted by `extract_paths.py → detect_features()`) with ten
  structural-scan flags. No key removals, no renames; consumers that
  don't know about `feature_support` see it as an unrecognised
  top-level section and the Step 2a shape probe reports it as such.
  Because the change is purely additive — new optional top-level
  section, all new keys default to `false` for CommercialAuto — it
  stays within MINOR-compatibility and does NOT bump the registry
  version. `CONFIG_COVERAGE.md` at the repo root became the
  authoritative matrix of features the pipeline tracks, and the
  mapping-suggester SKILL.md gained a refusal rule that fires when a
  flag is `true` but the skill has no matching rule.
- **1.0 — 2026-04-23 — Phase E (additive, new artifact).** Introduced
  `terminology.yaml` at the repo root as the seventh pipeline artifact
  (per-tenant synonym layer, human-curated, optional). Added the
  corresponding `Artifact: terminology.yaml` section above with the
  `schema_version` / `tenant` / `synonyms` / `display_name_aliases`
  top-level tables and the single-file-per-run hard constraint.
  `mapping-suggester/SKILL.md` gained three coordinated additions in
  the same session: a new `Name-match precedence` subsection in the
  Matching strategy (exact → case-insensitive → terminology synonym
  → fuzzy) with a standard reasoning line for terminology-sourced
  matches, a new Step 0c that reads the file at startup with MAJOR-
  halt / MINOR-warn semantics and resolves canonicals against the
  registry, and a new "Do not merge multiple terminology files"
  bullet in "Important constraints" mirroring the `PIPELINE_
  EVOLUTION_PLAN.md` §6.3 / §7 hard constraint. Step 5's terminal
  block and the "After output" checklist both grew a terminology-
  layer line (never suppressed — downstream agents pattern-match on
  the line to notice the layer is plumbed). No existing artifact's
  shape changed — the v1.0 contracts on mapping / registry /
  suggested / review / suggester-log.jsonl / skill-lessons.yaml all
  still read `1.0`. Phase E is exercised end-to-end by the
  `conformance/fixtures/custom-naming/` fixture, which now carries a
  `terminology.yaml` that lifts the `octopuses` loop from `low` +
  `supply-from-plugin` to `high` via an exposure alias `Octopus →
  [octopuses, octopi]`.
- **1.0 — 2026-06-02 — Leg 4 / plugin-builder (additive, two new
  artifacts).** Introduced `{Product}DocumentDataSnapshotPluginImpl.java`
  and `<stem>.plugin-report.md` as the tenth and eleventh pipeline
  artifacts. Added `velocity_converter/leg4_generate_plugin.py` (deterministic Java
  codegen via `javap` introspection) and
  `.cursor/skills/plugin-builder/SKILL.md` (skill registration). Java
  output is not a versioned YAML artifact — no `schema_version` key.
  `CLAUDE.md` updated with Leg 4 trigger phrases. No existing artifact's
  shape changed.
- **1.0 — 2026-05-01 — Leg 3 / substitution-writer (additive, two new
  artifacts).** Introduced `<stem>.final.vm` and `<stem>.leg3-report.md`
  as the eighth and ninth pipeline artifacts. Added
  `velocity_converter/leg3_substitute.py` (core substitution logic),
  `.cursor/skills/substitution-writer/SKILL.md` (skill registration),
  and extended `velocity_converter/agent.py` + `velocity_converter/agent_tools.py` to support
  `leg3` and `leg1+leg2+leg3` pipeline operations. `CLAUDE.md` updated
  with leg3 trigger phrases and the full-pipeline default changed to
  `leg1+leg2+leg3`. Three design decisions recorded (DD-1: strip
  `#if($TBD_*)` guards; DD-2: preserve unresolved `$TBD_*` as-is;
  DD-3: lenient mode). No existing artifact's shape changed.
