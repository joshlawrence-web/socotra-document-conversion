# Leg 4 — renderingData Alignment (Phase 5)

**Status:** Complete (T1–T5 done 2026-06-03)  
**Created:** 2026-06-03  
**Predecessor:** [Leg4-plugin-enrichment](../Leg4-plugin-enrichment/00-plan.md) — Phase 4 scope (parallel, independent)  
**History:** [history.md](./history.md) (append-only)

---

## START HERE (implementing agent)

This plan corrects the generated Java plugin to match established Socotra practice.
The MVP (Phases 1–3) generates compile-correct code but the `renderingData` shape
deviates from the internal standard in two key ways:

1. **Quote handler** — passes `request.quote()` directly; should be a `HashMap` with
   named keys plus enriched pricing from `DataFetcherFactory`.
2. **Segment handler** — passes `segment` directly; should be a `HashMap` with
   `policy`, `transaction`, `segment`, `todayAsString`, `productType`.

Fixing these requires a **coupled Velocity template change**: generated `.vm` files
use `$data.*` (works with direct passthrough). After this plan, renderingData is a
`HashMap` — templates must use named keys (`$quote.*`, `$segment.*`, `$policy.*` etc.).
Both sides must ship together.

**Read in this order:**

1. This file — §2 (decisions reversed), §3 (new locked decisions), §4 (task list)
2. `scripts/leg4_generate_plugin.py` — `JAVA_TEMPLATE` + `render_java()` to replace
3. `scripts/leg1_extract.py` or `scripts/leg1_*.py` — token naming (Leg 1 coupling)
4. `samples/output/Simple-form(quote)/ItemCareDocumentDataSnapshotPluginImpl.java` — current output
5. `samples/output/Simple-form(quote)/Simple-form(quote).final.vm` — current template (`$data.*` refs)

**Ground-truth reference plugins (from EC-Demo-Product-main):**
- `commercial-auto/plugins/java/CommercialAutoDocumentSnapshotPlugin.java`
- `commercial-auto_127_V1/plugins/java/GlobalDocDataSnapshotPlugin.java` (invoice pattern only)
- `personal-auto_v11/products/PersonalAuto/plugins/java/DocDataSnapshotPlugin.java` (pricing enrichment)

---

## 2. MVP decisions being reversed

| Old # | Topic | Old decision | New decision |
|-------|--------|-------------|--------------|
| D3 | `renderingData` shape | Pass full platform object directly | `HashMap<String, Object>` with named keys |
| D10 | Missing segment | Fail loud — `orElseThrow` | Soft fail — `orElse(null)` + `log.error(...)` |

Rationale: the working internal standard (CommercialAuto) uses named keys so
templates can reference `$segment`, `$policy`, `$transaction` as distinct roots.
Direct passthrough collapses everything under `$data`, which is non-standard and
breaks template portability across products.

---

## 3. Locked decisions for this plan

| # | Topic | Decision |
|---|--------|----------|
| A1 | Metadata | Out of scope — do not add `.metadata()` call |
| A2 | Invoice handler | Out of scope — keep existing stub (`Collections.emptyMap()` + `log.warn`) |
| A3 | Pricing null guard | Wrap `DataFetcherFactory` call in `try/catch`; `pricing` map is empty on null result |
| A4 | Template root keys — quote | `"quote"`, `"pricing"`, `"productType"` |
| A5 | Template root keys — segment | `"todayAsString"`, `"policy"`, `"transaction"`, `"segment"`, `"productType"` |
| A6 | Date format | `MM/dd/yyyy` via `SimpleDateFormat` (matches working example exactly) |
| A7 | Decimal format | `"0.00"` via `DecimalFormat` (matches working example exactly) |
| A8 | Charge split logic | `"premium".equalsIgnoreCase(chargeCategory)` → premiumTotal; `"nonFinancial".equalsIgnoreCase` → skip; else → otherTotal |
| A9 | Coupled Velocity change | Leg 1 token prefix must change from `$data.` to the correct root key for the document type |

---

## 4. Task list

Check boxes when done; append a handoff to [history.md](./history.md).

---

### T1 — Update `JAVA_TEMPLATE` and `render_java()` in `scripts/leg4_generate_plugin.py`

**Quote handler — replace:**
```java
return DocumentDataSnapshot.builder()
        .renderingData(request.quote())
        .build();
```

**With:**
```java
{Product}Quote quote = request.quote();
QuotePricing pricing = null;
try {
    pricing = DataFetcherFactory.get().getQuotePricing(quote.locator());
} catch (Exception e) {
    log.warn("Could not fetch quote pricing for locator={}", quote.locator(), e);
}

HashMap<String, Object> renderingData = new HashMap<>();
DecimalFormat df = new DecimalFormat("0.00");
BigDecimal premiumTotal = BigDecimal.ZERO;
BigDecimal otherTotal = BigDecimal.ZERO;

if (pricing != null && pricing.items() != null) {
    for (Charge item : pricing.items()) {
        if ("premium".equalsIgnoreCase(item.chargeCategory().toString())) {
            premiumTotal = premiumTotal.add(item.amount());
        } else if (!"nonFinancial".equalsIgnoreCase(item.chargeCategory().toString())) {
            otherTotal = otherTotal.add(item.amount());
        }
    }
}

BigDecimal totalBillable = premiumTotal.add(otherTotal);
HashMap<String, Object> enhancedPricing = new HashMap<>();
enhancedPricing.put("premiumTotal", df.format(premiumTotal));
enhancedPricing.put("otherTotal", df.format(otherTotal));
enhancedPricing.put("totalBillable", df.format(totalBillable));

renderingData.put("quote", quote);
renderingData.put("pricing", enhancedPricing);
renderingData.put("productType", "%(product)s");

return DocumentDataSnapshot.builder()
        .renderingData(renderingData)
        .build();
```

**Segment handler — replace:**
```java
{Product}Segment segment = request.segment()
        .orElseThrow(() -> { ... });
return DocumentDataSnapshot.builder()
        .renderingData(segment)
        .build();
```

**With:**
```java
Policy policy = request.policy();
Transaction transaction = request.transaction();
{Product}Segment segment = request.segment().orElse(null);

if (segment == null) {
    log.error("Segment is missing in the %(product)s request");
}

HashMap<String, Object> renderingData = new HashMap<>();
String pattern = "MM/dd/yyyy";
DateFormat dateFormatter = new SimpleDateFormat(pattern);
Date today = Calendar.getInstance().getTime();
String todayAsString = dateFormatter.format(today);

renderingData.put("todayAsString", todayAsString);
renderingData.put("policy", policy);
renderingData.put("transaction", transaction);
renderingData.put("segment", segment);
renderingData.put("productType", "%(product)s");

return DocumentDataSnapshot.builder()
        .renderingData(renderingData)
        .build();
```

**Files:** `scripts/leg4_generate_plugin.py` — `JAVA_TEMPLATE` constant + `render_java()`

---

### T2 — Expand import block in `JAVA_TEMPLATE`

Add to imports (replace the current narrow list):

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DateFormat;
import java.text.DecimalFormat;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.HashMap;
import com.socotra.coremodel.Charge;
import com.socotra.coremodel.QuotePricing;
import com.socotra.deployment.DataFetcherFactory;
```

Remove: `import java.util.Collections;` (no longer needed after T1).
Keep: `Policy`, `Transaction`, `DocumentDataSnapshot`, `Logger`, `LoggerFactory`, plugin interface imports.

**Files:** `scripts/leg4_generate_plugin.py` — `JAVA_TEMPLATE`

---

### T3 — Update generated Velocity template root keys (Leg 1 coupling)

The existing generated templates use `$data.fieldName` because the MVP passes the raw
object as `renderingData`. After T1 the plugin puts named keys into a HashMap, so
templates must reference `$quote.fieldName` (quote docs) or `$segment.fieldName`,
`$policy.fieldName`, `$transaction.fieldName` (policy docs).

**Find where Leg 1 writes `$data.` tokens** — likely in `scripts/leg1_extract.py` or
the Velocity token-emission logic. Change the prefix logic so that:

- For quote-context documents: token root = `$quote`
- For policy/segment-context documents: segment fields → `$segment`, policy fields → `$policy`, transaction fields → `$transaction`

**This also affects Leg 2 and Leg 3** — `data_source` values in `.suggested.yaml`
and path validation in `leg4_generate_plugin.py` use these same roots. Verify that
`validate_path()` in `sdk_introspect.py` is still called against the correct type
(e.g. `{Product}Segment` for segment fields, `{Product}Quote` for quote fields).

**Files:**
- `scripts/leg1_extract.py` (or wherever `$data.` tokens are emitted)
- `registry/path-registry.yaml` — review if root-key hints are stored here
- `scripts/sdk_introspect.py` — confirm `validate_path` target class is still correct

**Definition of done:**
- Running `RUN_PIPELINE leg1+leg2+leg3` on `Simple-form(quote).html` produces a
  `.final.vm` with `$quote.*` references (not `$data.*`)
- Running `RUN_PIPELINE leg1+leg2+leg3` on a segment doc produces `$segment.*`,
  `$policy.*`, `$transaction.*` references as appropriate

---

### T4 — Re-generate and verify pilot output

After T1–T3:

1. Re-run `leg4_generate_plugin.py` on `Simple-form(quote).suggested.yaml`
2. Verify the Java file compiles (`--compile-check`)
3. Re-run `leg1+leg2+leg3` on `Simple-form(quote).html`
4. Verify the `.final.vm` no longer contains `$data.*`
5. Manually inspect that template variable names match renderingData keys

**Files:** `samples/output/Simple-form(quote)/` — regenerated outputs

---

### T5 — Update docstring and report in `leg4_generate_plugin.py`

The module docstring says:
> `renderingData` root (`$data` in Velocity) = the full quote / segment object

Update to reflect the new HashMap shape and named key convention.

Update `write_report()` "Rendering strategy" section (currently says `$data.*`)
to describe the named-key approach and list the standard root keys per request type.

**Files:** `scripts/leg4_generate_plugin.py` — module docstring + `write_report()`

---

## 5. Recommended order

1. **T2** (imports) — mechanical, no logic change, establishes the import baseline
2. **T1** (JAVA_TEMPLATE) — core logic change, depends on T2 for clean compile
3. **T4 partial** — compile-check the new Java before touching Velocity
4. **T3** (Leg 1 Velocity coupling) — changes token naming, affects existing output
5. **T4 full** — end-to-end re-gen and verify
6. **T5** (docstring/report) — cleanup, last

---

## 6. Out of scope (do not implement)

- `.metadata()` on `DocumentDataSnapshot.builder()` — separate concern, deferred
- Invoice handler enrichment — stub stays; full pattern documented in memory
- Per-document branching (P4.3 from Leg4-plugin-enrichment plan)
- YAML `supply-from-plugin` patching (P4.1)

---

## 7. Repo signposting

| Path | Role |
|------|------|
| `scripts/leg4_generate_plugin.py` | `JAVA_TEMPLATE`, `render_java()`, `write_report()` |
| `scripts/leg1_extract.py` | Token emission — find `$data.` prefix source |
| `scripts/sdk_introspect.py` | `validate_path()` — confirm target class unchanged |
| `registry/path-registry.yaml` | Path hints — check root key convention |
| `samples/output/Simple-form(quote)/` | Pilot input + regenerated output |
| `build/customer-config.jar` | Plugin interface + request types |
| `build/core-datamodel-v1.7.61.jar` | `Charge`, `QuotePricing`, `Policy`, `Transaction` |
| `EC-Demo-Product-main/commercial-auto/plugins/java/CommercialAutoDocumentSnapshotPlugin.java` | Quote ground truth |
| `EC-Demo-Product-main/commercial-auto_127_V1/plugins/java/GlobalDocDataSnapshotPlugin.java` | Invoice pattern reference |

---

## Superseded assumption

**2026-06-03 — Wrong assumption corrected.** This plan assumed templates reference named roots
as bare `$quote.*`/`$segment.*` variables. Confirmed via live renderer: all renderingData keys
are exposed under `$data`, so templates must use `$data.quote.*` etc. Fixed in plan
[Leg2-data-root-prefix-fix](../Leg2-data-root-prefix-fix/00-plan.md).
