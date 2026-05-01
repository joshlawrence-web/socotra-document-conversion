# mapping-suggester — Full mode supplements (lazy load)

Read this file **once** immediately after the run mode is locked to
**`full`** (after Pre-Step in `SKILL.md`, before Step 0).

Do **not** read this file for `terse`, `delta`, or `batch` (which uses
`terse` internally for each document).

---

## Shape probe — verbatim terminal template

Before building any candidates (Step 2a), inspect both inputs and print
this block **verbatim** to the terminal (substitute angle-bracketed
values). The **rules** for interpreting probe results (missing keys,
feature flags, refusal list) remain in `SKILL.md` Step 2a.

```
Shape probe for <stem>.mapping.yaml (schema <M>.<N>):
  Recognised context keys: <sorted, comma-separated list>
  Unrecognised context keys (preserved, not used): <sorted list or "(none)">
  Required keys present: name, placeholder, type, context, data_source
  Missing expected keys: <sorted list or "(none)">

Shape probe for path-registry.yaml (schema <M>.<N>):
  Top-level sections: <sorted, comma-separated list of top-level keys
                      except schema_version and meta>
  Unrecognised sections (preserved, not used): <sorted list or "(none)">
  Feature flags:
    <flag_name>: <true|false>
    ...
```

---

## Review file — full-mode narrative depth

Follow the section order and tables in `SKILL-output-formats.md`. In
**`full`** mode, add teaching-oriented prose that **`terse`** omits:

### §3 Blockers

After each blocker's bullet list, add **one short paragraph** (2–4
sentences) explaining *why* this item blocks Leg 3 and what the human
should do next. Connect registry facts (scope, quantifier, missing path)
to template structure in plain language.

### §5 Cross-scope warnings

Below the table (or below "No cross-scope warnings."), add a **short
paragraph** summarising the systemic pattern (e.g. "Several fields
assume Vehicle exposure scope but sit outside `#foreach ($vehicle …)`").

### §6 Done

Inside the `<details>` block, after the bullet list of high-confidence
mappings, optionally add **one sentence** noting anything notable (e.g.
"All other placeholders require human or plugin data.").

### §7 Unrecognised inputs

Before the four-column table, include this introductory paragraph when
the table has at least one row:

> These keys were preserved in `<stem>.suggested.yaml` but the suggester
> did not use them. Extend the skill's recognised-signal vocabulary (see
> `SKILL.md`) or remove the key from Leg 1 before promoting it to a
> contract.

When the section is empty ("No unrecognised inputs."), omit the intro.
