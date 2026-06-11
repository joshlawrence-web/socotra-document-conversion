---
name: plugin-builder
description: >
  Given a Leg 2 `.suggested.yaml` (with a `product:` key and high-confidence
  `data_source` paths), runs `velocity_converter/leg4_generate_plugin.py` to emit a
  Socotra `DocumentDataSnapshotPlugin` Java implementation and a
  `<stem>.plugin-report.md` validation summary.
  Use when the user wants to generate the snapshot plugin, build the Java
  plugin class, run Leg 4, or wire up `renderingData` for a document template.
  Trigger on phrases like "generate the plugin", "build the snapshot plugin",
  "run leg 4", "create the DocumentDataSnapshotPlugin", or "wire up renderingData".
---

# plugin-builder

## What this skill does

Leg 4 of the HTML → Velocity pipeline. Takes one upstream artifact:

1. **`<stem>.suggested.yaml`** — produced by `mapping-suggester` (Leg 2).
   Must contain a `product:` key (e.g. `ItemCare`) and at least one
   `confidence: high` variable with a non-empty `data_source`.

Outputs (written to `--output-dir`, default = directory of the suggested file):

- **`{Product}DocumentDataSnapshotPluginImpl.java`** — a compile-correct
  Socotra plugin class. Implements `DocumentDataSnapshotPlugin` with three
  overloads: quote (pass full quote object), policy/segment (fail loud if
  segment absent — `orElseThrow` + SLF4J ERROR), and invoice (stub + `log.warn`).

- **`<stem>.plugin-report.md`** — path-validation summary. High-confidence
  `data_source` paths walked against the segment type via `javap`; medium/low
  entries listed as ignored; optional compile-check result appended.

---

## How to run

```bash
# Minimal (from repo root)
python3 -m velocity_converter.leg4_generate_plugin \
  --suggested samples/output/<stem>/<stem>.suggested.yaml \
  --customer-jar build/customer-config.jar

# With compile check (recommended)
python3 -m velocity_converter.leg4_generate_plugin \
  --suggested samples/output/Simple-form/Simple-form.suggested.yaml \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --compile-check

# Custom output directory
python3 -m velocity_converter.leg4_generate_plugin \
  --suggested samples/output/<stem>/<stem>.suggested.yaml \
  --customer-jar build/customer-config.jar \
  --output-dir /path/to/socotra-config/plugins/java
```

---

## CLI reference

| Flag | Required | Default | Notes |
|------|----------|---------|-------|
| `--suggested` | yes | — | Path to `<stem>.suggested.yaml` |
| `--customer-jar` | yes | — | `build/customer-config.jar` |
| `--output-dir` | no | directory of `--suggested` | Where to write the `.java` and report |
| `--datamodel-jar` | no | newest `build/core-datamodel-v*.jar` | Override core model jar |
| `--compile-check` | no | off | Run `javac` after generation; non-zero exit on failure |

---

## Design decisions

| Code | Decision | Rationale |
|------|----------|-----------|
| D2 | One plugin per product | All document templates for a product share one implementation |
| D3 | `renderingData` = full platform object | Velocity navigates (`$data.policyNumber`); no per-field extraction needed |
| D5 | High-confidence paths only | Medium/low are ignored; lower bar to ship something correct |
| D6 | Output to `samples/output/<stem>/` | No automatic copy to `socotra-config/` — human deploy step |
| D10 | Missing segment → fail loud | `orElseThrow` + SLF4J ERROR so operators see the failure immediately |

---

## Output shape

### `{Product}DocumentDataSnapshotPluginImpl.java`

```java
package com.socotra.deployment.customer;
// imports …

public class ItemCareDocumentDataSnapshotPluginImpl implements DocumentDataSnapshotPlugin {
    @Override
    public DocumentDataSnapshot dataSnapshot(ItemCareQuoteRequest request) { … }

    @Override
    public DocumentDataSnapshot dataSnapshot(ItemCareRequest request) { … } // orElseThrow

    @Override
    public DocumentDataSnapshot dataSnapshot(InvoiceDetailsRequest request) { … } // stub
}
```

### `<stem>.plugin-report.md`

Sections:
1. **Header** — product, source file, generated Java, timestamp
2. **Rendering strategy** — which object is passed as `renderingData`
3. **High-confidence paths** — each `data_source` walked via `javap` (ok / warning)
4. **Ignored (medium / low)** — listed for visibility; not in Java output
5. **Compile check** — pass/fail + `javac` command (if `--compile-check` used)

---

## After generation

The generated `.java` file lives in `samples/output/<stem>/` (or `--output-dir`).
**Manual deploy:** copy it to `socotra-config/plugins/java/` and upload config.
Pipeline integration (`RUN_PIPELINE leg4`) is planned for Phase 3 — see
`.cursor/plans/pipeline-improvements/Leg4-document-snapshot-plugin/00-plan.md`.

---

## Important constraints

- **JAR required at generation time.** `velocity_converter/leg4_generate_plugin.py` calls
  `javap` to verify the plugin interface and nested request types. It exits 1
  if `build/customer-config.jar` is absent or the expected types are missing.
- **Never copy to `socotra-config/` automatically.** Deployment is a human step
  until Phase 4.
- **Product name is case-sensitive.** The `product:` value in `.suggested.yaml`
  must match the Pascal-case name in the JAR (`ItemCare`, not `itemcare`).
- **No LLM in Leg 4.** The Java is emitted deterministically from a template +
  `javap` introspection — no AI calls needed or made.
