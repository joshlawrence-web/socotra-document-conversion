# History — Explicit Path Provision at Docx/PDF Stage

Append-only. Newest entry first.

---

## 2026-06-10 — Implemented

### What changed

- **`scripts/agent_tools.py`**: Added `_velocity_to_accessor`, `build_velocity_lookup`, and `resolve_dotted_path`. `build_velocity_lookup` does a recursive walk of the registry YAML, building a flat map with two keys per entry (Pass 1: full suffix, Pass 2: accessor shorthand). Pass 1 wins on collision. Returns `{}` on any load failure.

- **`scripts/leg0_ingest.py`**:
  - `_FIELD_RE` widened to `r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}"` — captures dotted names as a single token
  - `extract_fields(html, registry_path=None)`: deferred import of `build_velocity_lookup`; for each name containing a dot, resolves against the lookup and writes either the velocity path or `UNRESOLVED:<name>` into `data_source`; prints a single stderr warning listing all unresolved names
  - `_normalise_for_leg2`: changed `"data_source": ""` to `"data_source": f.get("data_source", "")` so resolved values flow into the YAML output
  - `main()`: ancestor-walk from `input_path.parent` to find `registry/path-registry.yaml`; passes it into `extract_fields`

- **`.cursor/skills/html-to-velocity/scripts/convert.py`**:
  - Repo-root ancestor search added near top; inserts `scripts/` onto `sys.path` and imports `_build_velocity_lookup` with a silent fallback
  - `Mapping` dataclass: added `velocity_lookup: dict = field(default_factory=dict, repr=False)` (excluded from `to_yaml_dict()` output)
  - `_record_var`: when `mapping.velocity_lookup` is non-empty and name contains a dot, resolves against the lookup; writes velocity path on hit or `UNRESOLVED:<name>` + `mapping.warnings` entry on miss
  - `convert()`: added `velocity_lookup: Optional[dict] = None` parameter; populates `mapping.velocity_lookup` alongside `iterables` using the same registry resolution
  - batch mode: pre-builds lookup once alongside iterables; passes into each `convert()` call

### Verification

- `py_compile` passes on all three changed files ✓
- Functional test: bare `{firstName}` → `data_source: ""`; dotted `{account.data.firstName}` → `data_source: $data.account.data.firstName`; unresolved `{account.data.unknownField}` → `UNRESOLVED:account.data.unknownField` + stderr warning ✓
- Registry accessor forms verified: `account.data.firstName`, `quote.quoteNumber`, `policy.locator` all resolve correctly ✓

---

## 2026-06-10 — Plan created

### Summary

- Identified the gap left by Plan 08: Leg 2's `data_source` preservation hook is wired, but Leg 0 and Leg 1 still always write `data_source: ""`, discarding explicit path intent from docx placeholders like `{account.data.firstName}`.
- Designed two-pass flat velocity-map lookup: Pass 1 full suffix, Pass 2 accessor shorthand.
- Defined `UNRESOLVED:<name>` sentinel for unmatched dotted placeholders.
- Scoped changes to `agent_tools.py`, `leg0_ingest.py`, `convert.py` only.
- Noted follow-on: Leg 3 guard for `UNRESOLVED:*` entries.
