# Plan: Fix DataFetcher JAR Probe for Generic Return Types

## Context

`getAccount()` in the `DataFetcher` interface is declared as `<T> T getAccount(ULID)` — a raw generic. `sdk_introspect.py:datafetcher_return_type()` calls `_unwrap_type()` on the return, which returns `None` for bare type params (no dot). This means the JAR probe never runs for any DataFetcher method that returns a generic. The registry falls back to "trusted from registry" (medium confidence, no verification).

This allowed incorrect paths to be hand-authored in the registry without detection:
- `account_paths.name` → `$data.account.data.name` — no `name()` method on `PersonalAccountData`
- `datafetcher_paths.accountName` → `$data.account.data.name` — same non-existent field

The actual `PersonalAccountData` fields (confirmed from `customer-config.jar` and `socotra-config/accounts/PersonalAccount/config.json`) are: `firstName`, `lastName`, `email`, `primaryPhone`.

Many other `account_paths` entries also reference non-existent fields: `addressLine1`, `addressLine2`, `city`, `state`, `postalCode`, `country`, `phone`.

---

## Step 1 — `scripts/sdk_introspect.py`: Resolve generic DataFetcher returns

The concrete customer type IS in `customer-config.jar` — we just need to find it.

**Add `_find_customer_type_for_method(classpath: str, method_name: str) -> str | None`:**

1. Strip `get` prefix from method name → stem (e.g., `getAccount` → `Account`)
2. List classes in `customer-config.jar` using `jar tf`
3. Filter to classes in `com.socotra.deployment.customer` with no `$` (no inner classes)
4. Match class short name containing the stem (case-insensitive, e.g., `PersonalAccount` contains `Account`)
5. Return FQCN of the match; if multiple, prefer shortest name; if none, return `None`

**Modify `datafetcher_return_type(classpath, method_name)`:**

After `_unwrap_type()` returns `None`, call `_find_customer_type_for_method()` as a fallback:
```python
def datafetcher_return_type(classpath: str, method_name: str) -> str | None:
    raw = _method_return_type(classpath, DATAFETCHER_INTERFACE, method_name)
    result = _unwrap_type(raw) if raw else None
    if result is None:
        result = _find_customer_type_for_method(classpath, method_name)
    return result
```

This makes the JAR probe run for ALL generic DataFetcher methods (`getAccount`, `getQuote`, `getSegment`, etc.). No changes to `_datafetcher_verdict` are needed — the existing verified/not_found confidence grading applies once a concrete FQCN is resolved.

---

## Step 2 — `registry/path-registry.yaml`: Fix `account_paths`

Replace the entire `account_paths` section to match the JAR and socotra-config exactly:

| field | velocity | notes |
|---|---|---|
| `firstName` | `$data.account.data.firstName` | replaces `name` |
| `lastName` | `$data.account.data.lastName` | new |
| `email` | `$data.account.data.email` | unchanged |
| `primaryPhone` | `$data.account.data.primaryPhone` | replaces `phone` |

Remove: `name`, `addressLine1`, `addressLine2`, `city`, `state`, `postalCode`, `country`, `phone` — none exist on `PersonalAccountData`.

**Policy (confirmed by user):** `account_paths` — and all account entries in `datafetcher_paths` — must be derived solely from the JARs. No hand-authored fields that aren't verified by `javap` against the concrete customer type.

---

## Step 3 — `registry/path-registry.yaml`: Fix `datafetcher_paths.accountName`

Replace the single `accountName` entry with two entries:

```yaml
- field: accountFirstName
  display_name: Account First Name (DataFetcher)
  source: datafetcher
  datafetcher_method: getAccount
  datafetcher_arg:
    quote: quote.accountLocator()
    segment: policy.accountLocator()
  datafetcher_key: account
  valid_roots: [quote, segment]
  velocity: $data.account.data.firstName
  type: string
  ...

- field: accountLastName
  display_name: Account Last Name (DataFetcher)
  source: datafetcher
  datafetcher_method: getAccount
  datafetcher_arg:
    quote: quote.accountLocator()
    segment: policy.accountLocator()
  datafetcher_key: account
  valid_roots: [quote, segment]
  velocity: $data.account.data.lastName
  type: string
  ...
```

---

## Step 4 — `scripts/leg2_fill_mapping.py`: Tighten `_validate_datafetcher_entry`

Currently validates velocity starts with `$data.{key}` but allows `$data.account.name` (missing `.data.`). After Step 1 the JAR probe catches this at runtime, but add a registry-load-time guard too:

For entries where `datafetcher_key` resolves to a class with a `.data()` sub-object (i.e., account, quote, segment), warn or error if the velocity path doesn't include `.data.` after the key segment.

This is a secondary guard — the JAR probe from Step 1 is the primary fix. Keep this lightweight: add to `_validate_datafetcher_entry` a check that `$data.account.*` paths must use `$data.account.data.*` (similar to the existing prefix check).

---

## Step 5 — Re-run pipeline and verify

After Steps 1–4:
1. Re-run full pipeline on `samples/input/Simple-form(quote).html`
2. Check `Simple-form(quote).leg3-report.md` — `accountFirstName`/`accountLastName` should resolve with high confidence, no `$TBD_*` tokens for account name
3. Re-run Leg 4 — compile check should pass
4. Smoke test: `python3 -c "from scripts.sdk_introspect import datafetcher_return_type; import glob; cp=':'.join(glob.glob('build/*.jar')); print(datafetcher_return_type(cp, 'getAccount'))"` should print `com.socotra.deployment.customer.PersonalAccount`

---

## Files to modify

| File | Change |
|---|---|
| `scripts/sdk_introspect.py` | Add `_find_customer_type_for_method`, modify `datafetcher_return_type` |
| `registry/path-registry.yaml` | Rewrite `account_paths` section, replace `accountName` in `datafetcher_paths` |
| `scripts/leg2_fill_mapping.py` | Tighten `_validate_datafetcher_entry` for `.data.` sub-path pattern |
