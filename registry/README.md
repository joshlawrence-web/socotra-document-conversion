# registry/

Pipeline registry and co-located Leg 2 configuration for the bundled ItemCare demo config.

| File | Role |
|---|---|
| `path-registry.yaml` | Pre-generated Socotra path registry (from `socotra-config/` via `extract_paths.py`) |
| `terminology.yaml` | Optional per-tenant synonym layer for Leg 2 name matching |
| `skill-lessons.yaml` | Optional lessons ledger — accumulated pattern observations across runs |

Regenerate the registry after changing `socotra-config/`:

```bash
python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py \
  --config-dir socotra-config/
```

See [docs/SCHEMA.md](../docs/SCHEMA.md) for artifact contracts.
