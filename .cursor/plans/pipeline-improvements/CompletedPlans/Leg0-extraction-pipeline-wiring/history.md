# History — Leg 0 Extraction + Pipeline Wiring

Append-only. One entry per session. Most recent at top.

---

## 2026-06-08 — Implementation complete

All tasks E-T1 through E-T8 implemented in a single session.

- **E-T1**: `extract_fields()` (regex `\{([a-zA-Z_]…)\}`, dedup) + `annotate_fields()` in `leg0_ingest.py`
- **E-T2**: `extract_conditionals()` (regex `\[\[(.+?)\]\]`, sequential IDs) + `annotate_conditionals()` in `leg0_ingest.py`
- **E-T3**: `write_fields_yaml()` (simplified `token` format, `{stem}.fields.yaml`) + `_normalise_for_leg2()` + `write_leg2_mapping()` (proper `placeholder` format, `{stem}.mapping.yaml`) — both written by `main()`. Format confirmed against `leg2_fill_mapping.py`; normaliser writes `schema_version: 1.0`, `source`, `generated_at`, `placeholder`, `type`, `context` to satisfy leg2.
- **E-T4**: `write_conditional_form()` — markdown with numbered blocks and `Condition:` lines.
- **E-T5**: `parse_conditional_form()` + `write_conditional_registry()` — `--parse-conditional-form` CLI mode writes `{stem}.conditional-registry.yaml` matching `load_conditional_registry()` in leg4.
- **E-T6**: `run_leg0()` in `agent_tools.py` — subprocess call, collects artifacts.
- **E-T7**: `agent.py` updated — `leg0` and `leg0+leg2+leg3` added to VALID_OPS, regex, REFUSAL, validate_inputs, mode defaults, and run() dispatch. `leg0+leg2+leg3` wires leg0 mapping → leg2 → leg3.
- **E-T8**: `CLAUDE.md` updated with Leg 0 trigger phrases, customer workflow, and `--parse-conditional-form` step.

---

## 2026-06-08 — Plan created

Plan drafted from guided discovery session. Decisions E1–E8 locked. Tasks E-T1 through
E-T8 defined. No implementation started. Depends on Leg0-document-ingestion completing first.
