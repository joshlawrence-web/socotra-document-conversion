# registry/

This directory holds all registry files used by the pipeline. Each file has a distinct role.

## `path-registry.yaml`

Hand-curated map of every Velocity path available in this product config, organised by entity type (policy, exposure, coverage, etc.). Updated whenever coverages or fields are added to the Socotra config. Used by Leg 2 as the candidate pool when matching `$TBD_*` tokens to real paths.

## `sdk-schema-index.yaml`

Generated artefact. Produced by `scripts/build_schema_index.py` from the compiled customer and datamodel JARs. Contains entity-type → field name → return type mappings. Regenerate whenever the JARs change. Used by Leg 2's strict lookup step (`match_token`) to resolve tokens against the exact schema exposed by the deployed config.

## `terminology.yaml`

Synonym table: plain-English aliases → canonical registry field names. Hand-maintained. For example, mapping customer vocabulary ("Unit") to the Socotra field name ("Vehicle"). Used by Leg 2 Step 3 fuzzy matching (suggestions from this file are capped at `confidence: medium`).

## `skill-lessons.yaml`

Leg 2 feedback log. Captures confirmed good and bad path suggestions to improve future matches. Written by the pipeline automatically after a Leg 2 run; do not hand-edit. Over time this file accumulates signal that steers the AI matcher away from previously rejected suggestions.

---

Regenerate the path registry after changing `socotra-config/`:

```bash
python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py \
  --config-dir socotra-config/
```

See [docs/SCHEMA.md](../docs/SCHEMA.md) for artifact contracts.
