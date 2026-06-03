# Problem brief — Root-aware confidence for the Leg 2 mapping-suggester

**Status:** Problem definition only — no plan yet. **For the planning agent.**
**Created:** 2026-06-03
**Author:** handoff from a Leg 4 pilot run that exposed the gap.

> **Planning agent: start here.** This file describes *what is wrong and why*, with
> reproducible SDK evidence. It does **not** prescribe an implementation. Your job is
> to turn this into a plan (locked decisions, design, task list, definition of done)
> following the house style in
> [`../Leg4-document-snapshot-plugin/00-plan.md`](../Leg4-document-snapshot-plugin/00-plan.md).
> Do **not** start coding. Confirm scope and open questions (§7) with the user first.

---

## 1. TL;DR

Leg 2 (the mapping-suggester, a.k.a. the "high-confidence rater") assigns
`high / medium / low` confidence by matching placeholder names against
`registry/path-registry.yaml`, which is extracted **from `socotra-config/` only**
(`extract_paths.py`). That registry models a *single, notional* `$data` root.

But in Socotra, `$data` at render time is the `renderingData` object returned by the
`DocumentDataSnapshotPlugin`, and its **concrete Java type changes depending on which
policy object the document targets** — a quote, a segment (policy), or invoice details.
The rater never consults the compiled SDK (`build/*.jar`) to confirm a field actually
exists on the root the document will render against. **So a path can be rated `high`
and still be broken at runtime.**

The fix: make confidence a function of **(field × rendering root)**, grounded in the
compiled SDK via `javap` — not a scalar derived from config alone. A document may target
**one or multiple** roots, and the verdict can differ per root.

---

## 2. Reproducible evidence — the `Simple-form` pilot

The Leg 2 output `samples/output/Simple-form/Simple-form.suggested.yaml` rated:

```yaml
- name: POLICY_NUMBER
  data_source: $data.policyNumber
  confidence: high
  reasoning: 'exact match: policyNumber → $data.policyNumber'
```

`javap` against the build JARs tells a different story. Reproduce from repo root:

```bash
CP="build/customer-config.jar:build/core-datamodel-v1.7.61.jar"
javap -classpath "$CP" -public com.socotra.deployment.customer.ItemCareQuote   | grep -i number
javap -classpath "$CP" -public com.socotra.deployment.customer.ItemCareSegment | grep -i number
javap -classpath "$CP" -public com.socotra.coremodel.Policy                    | grep -i number
```

| Rendering root (what `$data` *is*) | Document target | Has `policyNumber()`? | Notes |
|---|---|---|---|
| `ItemCareQuote` | Quote documents | **No** | Closest: `quoteNumber()`, `reservedPolicyNumber()` |
| `ItemCareSegment` | **Policy docs — current Leg 4 `renderingData`** | **No** | Only `locator()`, `transactionLocator()`, `data()`, `items()`… |
| `com.socotra.coremodel.Policy` | reachable via `request.policy()` — **not** the rendering root today | **Yes** `Optional<String> policyNumber()` | The field lives *here*, a sibling on the request |
| Invoice details | Invoice documents | n/a | Leg 4 currently stubs invoice with an empty map |

**Consequence:** for the `Simple-form` policy document, Leg 4 emits
`renderingData(segment)`, so `$data.policyNumber` resolves against `ItemCareSegment`,
which has no `policyNumber()`. The `high` verdict was wrong. The data exists, but on
`Policy` — only the plugin can lift it onto the rendering root.

**Note:** Leg 4 *already* detected this. `validate_path()` in
`scripts/leg4_generate_plugin.py` walks the segment type via `javap` and emitted a
**warning** in `Simple-form.plugin-report.md`. The knowledge exists downstream but is
report-only. The fix is to **push that SDK-awareness upstream into the Leg 2 rater.**

### The relevant request shape (policy documents)

```
DocumentDataSnapshotPlugin$ItemCareRequest:
  Policy policy()
  Transaction transaction()
  Optional<ItemCareSegment> segment()
  DocumentConfig config()
```

So a policy document can reach `policy().policyNumber()`, `transaction()`, and the
segment — but the *rendering root* is only one chosen object (today: the segment).

---

## 3. Root cause — two coupled gaps

1. **Confidence is computed against a config abstraction, not the SDK.**
   `path-registry.yaml` is derived from `socotra-config/` (field declarations,
   exposures, charges…). It encodes the *configured* shape, not the *compiled,
   navigable* shape of any rendering root. Config-declared ≠ SDK-accessible-on-a-root.

2. **The model assumes one universal `$data` root.** Confidence is treated as a
   scalar per field. In reality it is a function of **(field × rendering root)**, and a
   document can target **one or several** roots (quote-time vs. policy-time rendering of
   the *same* template; invoice documents differ again). `policyNumber` should plausibly
   be: `high` on a Policy-backed root, `low / supply-from-plugin` on a bare segment root,
   and "use `quoteNumber()` / `reservedPolicyNumber()`" on a quote root.

---

## 4. What the fix must deliver (requirements, not design)

- **Root-aware confidence.** A verdict per `(placeholder, rendering-root)`. The output
  must express one *or multiple* verdicts when a template can render under multiple roots.
- **SDK-grounded matching.** Introspect `build/customer-config.jar` +
  `build/core-datamodel-*.jar` (via `javap`, reusing the `leg4_generate_plugin.py`
  patterns) to confirm a path is actually navigable on the target root type. "High"
  should mean **"verified to exist on the target root in the compiled SDK."**
- **Document → root(s) contract.** Define how a document declares which target(s) it
  renders for (quote / segment / invoice / Policy-backed) and how the rater enumerates
  roots from the `product:` in the `.suggested.yaml`.
- **Registry vs. SDK reconciliation.** When the config registry and the SDK disagree
  (the `policyNumber` case), define precedence and how it is surfaced (e.g. "exists in
  config but not on root X → demote + flag `supply-from-plugin`").
- **Close the loop with Leg 4.** A field that exists only on a sibling
  (`Policy.policyNumber()`) but not the rendering root should drive a concrete Leg 4
  action: have the plugin compute/lift it into `renderingData`, rather than passing the
  raw segment and hoping it resolves.

---

## 5. Repo signposts (what exists today)

| Path | Role |
|---|---|
| `.cursor/skills/mapping-suggester/scripts/extract_paths.py` | Builds `path-registry.yaml` **from `socotra-config/` only** — the config-side source of truth |
| `registry/path-registry.yaml` | Flat catalogue; single notional `$data` root; `meta.note` documents the `$data` convention |
| `scripts/leg2_fill_mapping.py` | The rater — matches placeholders to registry paths, assigns confidence (Rules 1–6) |
| `.cursor/skills/mapping-suggester/SKILL.md` | Skill contract; "Only use paths from the registry" constraint lives here |
| `scripts/leg4_generate_plugin.py` | **Reuse:** `_javap`, `_zero_arg_methods`, `_unwrap_type`, `validate_path` already do SDK introspection per root |
| `build/customer-config.jar` | `{Product}Quote`, `{Product}Segment`, `DocumentDataSnapshotPlugin$*Request` types |
| `build/core-datamodel-v1.7.61.jar` | `Policy`, `Transaction`, `DocumentDataSnapshot`, … |
| `samples/output/Simple-form/` | Pilot: `.suggested.yaml`, `.plugin-report.md` (the warning), `ItemCareDocumentDataSnapshotPluginImpl.java` |
| `../Leg4-document-snapshot-plugin/00-plan.md` | **House style** to mirror for the new plan |

---

## 6. Suggested shape of the plan (for the planning agent to decide)

Two broad implementation directions to weigh (do not pre-commit — present trade-offs):

- **A — Validation layer on top of the existing registry.** Keep `extract_paths.py`
  as-is; add a JAR-aware pass in `leg2_fill_mapping.py` that validates/demotes each
  candidate path against the target root type(s) via `javap`. Less invasive; mirrors
  Leg 4. Registry stays config-only; SDK truth applied at rate-time.
- **B — Root dimension baked into the registry.** Extend `extract_paths.py` (or a new
  introspector) to emit per-root availability so the registry itself knows which fields
  exist on quote / segment / invoice roots. More work; single richer source of truth.

The planning agent should pick one (or a hybrid), justify it, and lock it as a decision.

---

## 7. Open questions to resolve with the user before planning

1. Direction A vs. B (or hybrid) for where SDK truth lives.
2. How a document/template declares its target root(s): inferred from product +
   transaction context, or explicit in the mapping?
3. Where the canonical document→root mapping lives so Leg 2 and Leg 4 share one source.
4. Should the verdict schema change (per-root confidence) — and is that a MAJOR bump to
   the `.suggested.yaml` / registry schema contract in `docs/SCHEMA.md`?
5. Scope: is invoice-root support in or out for the first cut (Leg 4 currently stubs it)?

---

## 8. Definition of done (for the *plan*, not the implementation)

- A plan folder mirroring the Leg 4 layout (`00-plan.md`, `README.md`, `history.md`).
- Locked decisions table answering §7.
- Chosen direction (§6) with rationale.
- Task list with phases + a verifiable definition of done for the implementation.
- A reproducible acceptance check: after implementation, the `Simple-form`
  `POLICY_NUMBER` case is **no longer rated `high` against the segment root** (it is
  demoted/flagged `supply-from-plugin`, or routed to a Policy-backed root), and a
  genuinely segment-resident field still rates `high`.
