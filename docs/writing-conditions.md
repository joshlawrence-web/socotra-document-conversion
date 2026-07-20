# Writing Conditions — the LLM-assisted authoring guide

**Audience:** whoever (human or model) fills the `when` column of a
`<stem>.variants.csv` or the `when:` field of a `conditional-registry.yaml`.
This is the **one** place in the pipeline that is authored rather than derived —
everything downstream (validation, Java codegen, the compile check) is
prescriptive and runs off code in `velocity_converter/condition_dsl.py`.

> `variants.csv` is one of **two** files the customer fills (the other is
> `path-review.csv`). For how the two relate — which fields go where, and why a field
> on both must agree — see [variants-and-path-review.md](variants-and-path-review.md).

**The single most important rule:** you write *what to test*, in a tiny
data-language. You never write Java, and you never reason about Java types.
`coolingOffPeriod > 0` is the whole condition — the emitter decides whether that
becomes `... > 0` (an `int` field) or `... .compareTo(new BigDecimal("0")) > 0`
(a `decimal` field). If you ever find yourself typing `BigDecimal`, `compareTo`,
`.intValue()`, `==` on a String, or `!= null`, stop: that is the emitter's job,
and writing it yourself is how plugins fail to compile.

---

## Where conditions live

A `variants.csv` has three columns — `placeholder, when, text` — and row order
is priority (first match wins):

```csv
placeholder,when,text
coolingOff,quote.data.coolingOffPeriod > 0,You have a {coolingOffPeriod}-day cooling-off period from your start date.
coolingOff,,No cooling-off period applies to this policy.
disclosureClause,"quote.data.newBusinessWaitPeriod in [7, 14]",A new-business waiting period applies before claims can be made.
disclosureClause,,No new-business waiting period applies to this policy.
```

- A **blank** `when` (or `*` / `else` / `default`) is the **default row**. Each
  placeholder needs **exactly one** default — it renders when nothing else
  matches, so the block never renders empty.
- Every other row's `when` is a condition in the grammar below.
- **A placeholder may carry any number of conditioned rows** (an N-way block —
  e.g. one row per state, first match wins) — you are never limited to one
  condition + default. Add rows; keep the single default last.
- Quote the whole `when` cell if it contains a comma (e.g. an `in [...]` list).

---

## Grammar

```
condition  := comparison (("and" | "or") comparison)*
comparison := path op literal?
path       := identifier ("." identifier)*
op         := == | != | >= | <= | > | < | present | absent | in
literal    := string | number | boolean | "[" literal ("," literal)* "]"
```

- **`and` / `or` may not be mixed** in one condition. Pick one joiner. If you
  need both, split into separate placeholder rows (priority order does the rest).
- `present` / `absent` take no literal. `in` takes a bracketed list.

## Operators

| Operator | Use for | Example |
|---|---|---|
| `==` `!=` | equality (String, enum, number, boolean) | `quote.data.state == "CA"` |
| `>` `>=` `<` `<=` | ordering — **numeric or date fields only** | `quote.data.coolingOffPeriod > 0` |
| `present` | field is non-null | `quote.quoteNumber present` |
| `absent` | field is null | `quote.data.discountCode absent` |
| `in` | value is one of a list | `quote.data.newBusinessWaitPeriod in [7, 14]` |

## Literals

- **String:** double or single quotes — `"CA"`, `'Gold'`. Enums are written as
  their name in quotes (`status == "ACTIVE"`); the emitter compares safely.
- **Number:** bare — `0`, `7`, `12.5`. Do not quote numbers.
- **Boolean:** `true` / `false` (bare, any case).
- **List:** `[7, 14]`, `["CA", "NY"]` — all items the same kind.

## Null handling — never write `!= null`

Use `present` / `absent`. The parser rejects `null` literals on purpose:

```
quote.quoteNumber present      ✅
quote.quoteNumber != null      ❌  -> "use `present`/`absent` for null checks"
```

Every accessor step is null-guarded for you, so a condition can never NPE even
on a deep path.

---

## Paths and scope

A path's **root** picks the scope, and a block is single-scoped:

- `quote.…` — quote-scoped (quote system fields, e.g. `quote.quoteNumber`).
- `policy.…` — policy-scoped.
- **Custom product fields** (anything you defined under a product's `data`) are
  reached as `quote.data.<field>` in a quote document and `policy.data.<field>`
  in a policy document. Use the root that matches the document you are authoring
  (`ZenCoverDemoLetter(quote)` → `quote.data.coolingOffPeriod`).

> **A field's registry category limits which documents can condition on it.** A
> quote-only field (registry category `quote_system`, e.g. `region`) is only
> reachable as `quote.<field>` — a `(segment)` document's conditions cannot use
> it at all (`policy.region` is rejected as an unknown accessor). Before
> building a condition around a field, check it exists under the root your
> document renders against; if it is quote-only and you are writing a policy
> letter, pick a policy-level field as the discriminator instead.

### Bare leaves

You may write just the leaf name when it is unambiguous — `state == "CA"`
instead of `quote.data.state == "CA"`. Resolution rules:

- The leaf must resolve to **exactly one** registry field (in the document's
  scope). If two fields share a leaf name, you get an *ambiguous* error — write
  the full accessor.
- All comparisons in one `when` must resolve to the **same scope**.

### Per-item conditions — the one `item.*` exception

Conditions are **document-scoped**: `item.*` paths are rejected for `[[$token]]`
blocks and document-level regions (there is no single item to test). The one
exception is the `when`-only row of a **`[Name?]` region inside a `[Name/]`
loop** (an in-loop value region): its condition is evaluated **per item**, and
every path must root at the loop's iterator —
`item.Breakdown.data.labourCovered == "true"`. Blank still means always render.

---

## Type rules (what validation enforces)

Validation (`validate_condition`) checks the *shape*, not Java types:

- Ordering (`>` `>=` `<` `<=`) requires a **numeric or date** field.
- A numeric field must be compared to a number (and a number `in` list must be
  all numbers); a boolean field to `true`/`false`; a String/date field not to a
  bare number.
- The path must exist in the registry and be legal for the block's scope.

That is the extent of what you must get right. **Whether the field is `int`,
`decimal`, `Integer`, `BigDecimal`, `Long`, … is irrelevant to you** — the
codegen resolves the real Java return type (via javap) and emits the matching
comparison: autounboxed operators for integer/float leaves, `compareTo` for
`BigDecimal`/`BigInteger`. This is exactly the split that previously broke when a
condition was forced into a hand-written `BigDecimal.compareTo` against an `int`
field; let the emitter own it.

---

## Worked examples (real ZenCover fields)

| Goal | `when` |
|---|---|
| Cooling-off period applies | `quote.data.coolingOffPeriod > 0` |
| Waiting period is 7 or 14 days | `quote.data.newBusinessWaitPeriod in [7, 14]` |
| Issued in California | `quote.data.state == "CA"` |
| A discount code was supplied | `quote.data.discountProfileCode present` |
| Premium over a threshold | `policy.data.premium > 500` |
| Rider selected and not in Texas | `quote.data.hasRider == true and quote.data.state != "TX"` |

### Anti-patterns

| Don't write | Why | Write instead |
|---|---|---|
| `coolingOffPeriod.compareTo(new BigDecimal("0")) > 0` | That's Java; the emitter generates it | `coolingOffPeriod > 0` |
| `state.equals("CA")` | Java again | `state == "CA"` |
| `quoteNumber != null` | `null` literal is rejected | `quoteNumber present` |
| `state == "CA" and premium > 500 or hasRider == true` | mixed `and`/`or` | split into separate rows |
| `coolingOffPeriod > "0"` | numeric field vs string | `coolingOffPeriod > 0` |

---

## When something is wrong

`parse_condition` raises on bad syntax; `validate_condition` returns a list of
human-readable errors (unknown path, wrong scope, type mismatch, ambiguous
leaf). The Leg 4 run surfaces these before any Java is written, and the
`--compile-check` is the backstop. If a condition validates but the plugin still
fails to compile, that is a **codegen bug, not an authoring bug** — file it
against `condition_dsl.py`, do not work around it by hand-writing Java in the
`when`.
