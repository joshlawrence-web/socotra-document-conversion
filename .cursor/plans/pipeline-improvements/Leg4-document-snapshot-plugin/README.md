# Leg 4 — Document snapshot plugin

**Implementing agents: start here.**

| Read first | Purpose |
|------------|---------|
| [00-plan.md](./00-plan.md) | Full spec, golden Java, javap cookbook, task checklist, definition of done |
| [history.md](./history.md) | Session log — append when you finish work |

**Status:** Phase 1 complete (2026-06-02) · script + pilot pass §12 · Phase 2–4 deferred

**Pilot command:**

```bash
python3 scripts/leg4_generate_plugin.py \
  --suggested samples/output/Simple-form/Simple-form.suggested.yaml \
  --output-dir samples/output/Simple-form \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --compile-check
```

**Do not** expand scope beyond [00-plan.md §3](./00-plan.md#3-decision-history-locked) without user approval.
