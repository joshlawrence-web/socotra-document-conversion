# Additive Plugin Parser / Validator

**Status:** Done
**Completed:** 2026-06-09
**When done:** set `Status: Done`, add `Completed:` date, move folder to `CompletedPlans/` (§6).
**Created:** 2026-06-09
**Item:** Plan-for-plans #1

## START HERE (implementing agent)

Add a standalone validator that parses an existing `DocumentDataSnapshotPluginImpl.java` before Leg 4's additive update runs — catching conflicts, duplicate keys, and malformed structure before writing any bytes.

**Read in this order:**
1. This file — §2 (decisions), §3 (task list)
2. `scripts/leg4_generate_plugin.py` lines 280–400 — existing additive mode (`_parse_existing_plugin`, `_insert_additive_keys`)
3. `tests/integration/` — existing IT pattern to follow

---

## 1. Background

Leg 4's additive mode (`additive_mode = java_path.exists()`) reads an existing `.java` file and inserts missing `put()` calls before the builder return. The current flow:

1. Write `.java.bak`
2. Parse existing file via regex to find existing keys
3. Compute `new_keys = suggested_keys - existing_keys`
4. Insert new `put()` lines

**Gap:** There is no pre-flight check. If the existing Java file is malformed (missing builder pattern, mismatched braces, manually edited put-calls with wrong types), the insertion silently produces broken Java that only surfaces at compile time (if `--compile-check` is passed). There is also no way to ask "what keys does this plugin already have?" without running Leg 4.

**This plan adds:**
- `scripts/validate_plugin.py` — standalone parser/validator
- `--validate-only` flag on `leg4_generate_plugin.py`
- A `parse_plugin_keys(java_path)` utility in the existing `leg4_generate_plugin.py` (extracted from the inline regex)

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | Parser approach | Regex-based (not a full Java AST). The plugin is a generated template with a known structure; a full parser is overkill and adds no dependency. If structure is unrecognisable, emit a clear error and exit 1. |
| D2 | Validation checks | (1) Builder pattern present (`renderingData.builder()` + `.build()`); (2) At least one `put(` call found; (3) No duplicate string literal keys in put-calls; (4) All `put()` calls have exactly two args; (5) File is valid UTF-8. |
| D3 | Output format | Human-readable summary to stdout. Machine-readable `--json` flag for pipeline integration. Exit 0 = valid, exit 1 = invalid. |
| D4 | `parse_plugin_keys()` extraction | Factor the existing inline regex in `_merge_additive()` into a public function `parse_plugin_keys(java_path: Path) -> dict` returning `{existing_keys: set[str], cond_high_water: int, is_valid: bool, errors: list[str]}`. Used by both the validator and the additive merge. |
| D5 | `--validate-only` flag | When passed to `leg4_generate_plugin.py`, runs `parse_plugin_keys()` + validation checks and exits without writing any files. Useful in CI. |
| D6 | Pipeline report | Add a "Pre-flight validation" section to `<stem>.plugin-report.md` when additive mode runs — shows existing key count and any warnings found. |
| D7 | No dependency on JARs | `validate_plugin.py` must work with only the `.java` file — no JARs, no registry. |

---

## 3. Task list

### T1 — Extract `parse_plugin_keys()`

**Goal:** Factor the key-extraction regex out of the additive merge into a reusable function.

```python
def parse_plugin_keys(java_path: Path) -> dict:
    """Parse an existing SnapshotPlugin .java file.
    Returns:
      existing_keys: set[str]        — string literals from put("key", ...) calls
      cond_high_water: int           — highest condN index found
      is_valid: bool                 — False if structure is unrecognisable
      errors: list[str]              — human-readable validation errors
    """
```

**Validation checks inside this function** (D2):
1. `renderingData.builder()` present
2. `.build()` present
3. At least 1 `put(` found
4. No duplicate keys
5. All `put(` calls match `put\s*\(\s*"([^"]+)"\s*,` (two-arg form)

**Files:** `scripts/leg4_generate_plugin.py`

---

### T2 — `scripts/validate_plugin.py` CLI

**Goal:** Standalone validator script.

```
python3 scripts/validate_plugin.py samples/output/ZenCover/ZenCoverDocumentDataSnapshotPluginImpl.java

# Output (valid):
# Plugin: ZenCoverDocumentDataSnapshotPluginImpl.java
# Keys: 42
# Highest condN: 7
# Status: VALID

# Output (invalid):
# Plugin: ...java
# ERROR: Duplicate key "policyNumber" on lines 34 and 67
# ERROR: put() call on line 91 has wrong argument count
# Status: INVALID (2 errors)
```

**Flags:**
- `--json` — machine-readable output
- `--keys` — list all existing keys (one per line)

**Files:** `scripts/validate_plugin.py` (new)

---

### T3 — `--validate-only` flag on `leg4_generate_plugin.py`

**Goal:** Add pre-flight-only mode.

```
python3 scripts/leg4_generate_plugin.py \
  --suggested samples/output/ZenCover/ZenCover.suggested.yaml \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --validate-only
```

Runs `parse_plugin_keys()` on the existing `.java` if present; prints result; exits 0/1. Does not generate or write any files.

**Files:** `scripts/leg4_generate_plugin.py`

---

### T4 — Pre-flight section in plugin report

**Goal:** When additive mode runs, prepend a "Pre-flight validation" section to `.plugin-report.md`.

```markdown
## Pre-flight validation (additive mode)

| Check | Result |
|-------|--------|
| Builder pattern found | ✓ |
| Duplicate keys | None |
| Existing keys | 42 |
| Highest condN | 7 |
```

**Files:** `scripts/leg4_generate_plugin.py` (report writer)

---

### T5 — Tests

**Goal:** Unit tests for `parse_plugin_keys()` and the validator.

Test cases:
- Valid plugin → `is_valid=True`, correct key count
- Duplicate key → `is_valid=False`, error message names the key
- Missing builder pattern → `is_valid=False`
- Empty file → `is_valid=False`
- `--validate-only` exit code 0/1

**Files:** `tests/regression/test_validate_plugin.py` (new)

---

## 4. Definition of done

```bash
# Validate an existing plugin
python3 scripts/validate_plugin.py \
  samples/output/ZenCover/ZenCoverDocumentDataSnapshotPluginImpl.java

# Pre-flight only via leg4
python3 scripts/leg4_generate_plugin.py \
  --suggested samples/output/ZenCover/ZenCover.suggested.yaml \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --validate-only
```

| Check | Expected |
|-------|----------|
| `validate_plugin.py` exits 0 on valid file | ✓ |
| `validate_plugin.py` exits 1 on duplicate key | ✓ |
| `--validate-only` exits 0 without writing files | ✓ |
| `parse_plugin_keys()` used in additive merge path | ✓ (no duplicate logic) |
| Plugin report includes pre-flight section in additive mode | ✓ |
| All T5 tests pass | ✓ |

---

## 5. Files touched

| File | Change |
|------|--------|
| `scripts/leg4_generate_plugin.py` | Extract `parse_plugin_keys()`; add `--validate-only`; add pre-flight report section |
| `scripts/validate_plugin.py` | **New** — standalone CLI validator |
| `tests/regression/test_validate_plugin.py` | **New** — unit tests |

---

## 6. Self-certification (completing agent — required)

When every item in §4 Definition of done is satisfied:

1. Edit this file: change `**Status:** Open` → `**Status:** Done` and add `**Completed:** <date>`.
2. Move this folder: `mv .cursor/plans/pipeline-improvements/01-additive-plugin-validator/ .cursor/plans/pipeline-improvements/CompletedPlans/`
3. Commit both changes with your implementation (or in a follow-up commit).

**Do not skip this step.** Plans left "Open" after completion create false signals about remaining work.
