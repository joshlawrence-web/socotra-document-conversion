# RenderingData ⇄ Velocity paths — how `$data.…` resolves

A config-agnostic helper. It answers one question: **when a template writes
`$data.<a>.<b>.<c>`, what is each segment, and where does the value come from?**

The rules here hold for any Socotra product. The ZenCover capture at the bottom is just
one worked illustration — ignore the specific field names, keep the shape.

---

## The chain (every product, same shape)

```
socotra-config/*.json          ← source of truth for custom field NAMES + TYPES
      │  (Socotra codegen at config build)
      ▼
customer-config.jar             ← generated typed records, one per config entity;
                                  one accessor per config field, SAME name
      │  + core-datamodel-*.jar  (platform types: the entity's system fields,
      │                            QuotePricing, Charge, Account, Policy, …)
      ▼
<Product>DocumentDataSnapshotPluginImpl.java   ← you write this (Leg 4 generates it).
                                  Pulls typed records + DataFetcher + computes derived
                                  values, puts them on a Map<String,Object> renderingData.
      │  (platform serializes renderingData: records → nested plain Maps)
      ▼
$data  in the template          ← every entity is now a java.util.LinkedHashMap,
                                  keyed by the SAME names as the config fields.
```

**Through-line:** a custom field's config name *is* its record accessor name *is* its
`$data` map key. That identity is why a Velocity path is predictable from the config.

---

## A Velocity path, segment by segment

`$data` is a `Map<String,Object>`. Every `.segment` after it is a **map-key lookup at
render time** — even though the plugin assembled it from strongly typed records. So:

```
$data    .quote        .data         .coolingOffPeriod
 ▲         ▲             ▲             ▲
 the map   a top-level   the custom-   one custom field
           key the       field sub-    (config field name)
           plugin put    map every
           on the map    entity has
```

Four kinds of segment you will see:

| Segment shape | What it is | Comes from |
|---------------|-----------|------------|
| `$data.<key>` | a top-level renderingData entry | **whatever the plugin `.put(...)`** — naming is the plugin's choice (`quote`, `account`, `pricing`, `productType`, `policy`, `segment`, `transaction`, …) |
| `.<systemField>` directly on an entity | platform/system field | core-datamodel (not your config): `locator`, `accountLocator`, `quoteState`, `productName`, `startTime`, `endTime`, `currency`, `quoteNumber`, … |
| `.data.<field>` | a **custom** config field | the entity's `data:` block in `socotra-config/` (this is the part you author) |
| `.<Child>` / `.<collection>` | a nested config entity | `contents:` of the parent (exposures, coverages) — a sub-object or a collection you `#foreach` over |

So the **shape of the path tells you the origin**:
- `.data.<x>` → a custom field, defined in some `config.json` `data:` block.
- a bare `.<x>` on the entity → a system field from the data model JAR.
- a collection / sub-object → a `contents:` relationship in the config.

---

## ⭐ The rendering-root entity key — the rule a demo must enforce

The registry stores a field's velocity **root-relative**: `$data.policyNumber`,
`$data.data.coolingOffPeriod`, `$data.items` — **no entity key**. But renderingData
never exposes a bare `$data.<field>`: the plugin `.put()`s the rendering-root entity
under a **named key**, so the real template path is `$data.<key>.<field>`. Emitting the
registry's root-relative form verbatim (`$data.data.x`, `$data.policyNumber`) points at
a key that does not exist → the reference resolves to nothing at render time.

**The key is the field's verified Java local** (`leg4 _CATEGORY_WIRING`), so the template
path always mirrors the accessor the plugin wires:

| Document root | Field kind | Registry velocity | renderingData / template path | Java local |
|---|---|---|---|---|
| `(quote)` | system **and** custom | `$data.quoteNumber` / `$data.data.x` | `$data.quote.quoteNumber` / `$data.quote.data.x` | `quote` |
| `(segment)` | **system** (core Policy field) | `$data.policyNumber` | `$data.policy.policyNumber` | `policy` |
| `(segment)` | **custom** (typed Segment data) | `$data.data.x` | `$data.segment.data.x` | `segment` |
| `(segment)` | **loop list / exposure** | `$data.items` | `$data.segment.items` | `segment` |
| any | **account** (DataFetcher) | `$data.account.data.x` | `$data.account.data.x` *(own key — unchanged)* | `account` |

The subtlety that bites: a **segment document splits across two keys** — system fields
come off core `Policy` (`$data.policy.*`), custom fields and exposure lists off the typed
`Segment` (`$data.segment.*`). A quote document keeps everything on the single `quote`
key. Account / pricing / DataFetcher paths already name their own key and are left alone.

In the pipeline this splice is `agent_tools.render_root_velocity(velocity, root)` (Leg 0
pre-fill) / `leg2_fill_mapping._reprefix` (Leg 2 JAR verdict). **When generating a demo,
verify it:** no resolved path may be a bare `$data.<field>` or `$data.data.<field>` —
every rendering-root-entity field must carry its `$data.policy` / `$data.segment` /
`$data.quote` key. See the demo checklist in CLAUDE.md § "renderingData shape".

---

## ⚠️ The gotcha: typed records in the plugin → plain Maps in `$data`

In the plugin you hold typed records and call them like methods:
`quote.data().coolingOffPeriod()` → returns a typed `int`. But the plugin puts the whole
record on the map, and the platform **serializes it to a nested `LinkedHashMap`** before
the template runs. Verified over the wire: `$data.get("quote").getClass()` is
`java.util.LinkedHashMap`, not the record type.

Consequences, true for every product:

1. **In the template you do map navigation, not method calls** — `$data.quote.data.x`,
   never `$data.quote.data().x()`. The dots are key lookups.
2. **The record's component names become the map keys**, and those are generated 1:1 from
   config field names. That is *why* the config governs what you can type after `$data.`.
3. **Optionality and typing disappear at the template boundary.** A `type: "string?"`
   field that is unset is simply an absent (or empty) key in the Map. The plugin still
   sees `Optional.empty()`; the template sees nothing. Hence `$!{data.…}` (quiet
   reference) for anything that can be absent — see below.

---

## Velocity syntax notes that bite

| Syntax | Use it for |
|--------|-----------|
| `$data.x.y` | a key you are sure exists; prints the literal `$data.x.y` if it doesn't |
| `$!{data.x.y}` | **quiet reference** — prints empty string when the key is missing/null. Default choice for any optional/`?`-typed field |
| `#if($data.x) … #end` | presence test on an optional sub-object before diving in |
| `#foreach($item in $data.<collection>) … #end` | iterate a collection key (an exposure array); inside, `$item.data.<field>` and `$item.<Coverage>.data.<field>` |
| `${data.x}` | formal/brace form, same as `$data.x`; needed when adjacent text would otherwise glue onto the reference |

The plugin can also flatten things to **plain top-level string keys** (e.g. a computed
`disclosureClause`). Those are just `$data.disclosureClause` — no `.data.` segment,
because they were never a config field; the plugin invented the key.

---

## Where a path's *value* actually originates (3 sources)

The path shape tells you the **name's** origin (config vs system). It does **not** tell
you how the value got populated. Three possibilities, all landing on the same map:

1. **Pass-through from the request** — the plugin received the entity (`request.quote()`,
   `request.policy()`, `request.segment()`) and put it on the map as-is. Most
   `$data.quote.*` / `$data.policy.*` / `$data.segment.*` paths.
2. **DataFetcher fetch** — the plugin called `DataFetcherFactory.get().getX(...)` for data
   not in the request (e.g. the `Account`, or `QuotePricing` for charges) and put the
   result on the map.
3. **Plugin-computed** — the plugin derived a value (summed charges, formatted a date,
   built a conditional string) and put it under a key it named itself. These have **no
   config field** behind them; don't go looking in `socotra-config/` for `pricing` or
   `coolingOff`.

---

## How to discover the paths for ANY product

Three independent ways, in order of effort:

1. **The registry / path catalog** (static, no tenant) — the config-agnostic field list:
   ```
   python3 -m velocity_converter.list_paths --registry registry/path-registry.yaml
   ```
   Grouped: System → Account → Policy custom → charges → per-exposure (system/custom/
   coverages/terms) → DataFetcher paths. This is the catalog of *legal* `$data.…` paths.

2. **Read the config** — for a custom field, open the entity's `config.json` `data:`
   block; the keys there are exactly your `.data.<field>` segments. `contents:` tells you
   the nested entities (collections to `#foreach`, coverage sub-objects).

3. **Dump the live `renderingData`** (proves what the deployed plugin *actually* put on
   the map, including computed keys). The render API returns a *document*, not the map —
   so render a **probe template** that dumps `$data`, asking for `format: html` so the
   body is readable text:

   ```velocity
   <pre>
   #foreach($k in $data.keySet())
   - $k  (class: $data.get($k).getClass().getName())
   #end
   ## then $!{data.<key>} on any key prints its full nested Map via toString()
   </pre>
   ```
   ```
   python3 -m velocity_converter.render_preview \
     --template probe.vm \
     --reference-type <quote|policy|segment|…> --reference-locator <locator> \
     --document-config probe-config-html.json \
     --out probe-out.html
   ```
   The rendered HTML body **is** the renderingData for that entity. (Prereqs: the
   product's `DocumentDataSnapshotPlugin` deployed to the tenant, and `.env.ai-documents`
   filled — see CLAUDE.md § "Ad-hoc rendering preview".)

---

## Worked illustration (ZenCover — names are incidental)

Live `renderingData` captured for a ZenCover quote shows all four segment kinds and all
three value sources at once:

| Velocity path | Segment kind | Value source | Config origin (if any) |
|---------------|--------------|--------------|------------------------|
| `$data.quote.locator` | system field | request pass-through | — (data-model JAR) |
| `$data.quote.data.coolingOffPeriod` | `.data.<field>` | request pass-through | `products/ZenCover` → `data.coolingOffPeriod` |
| `$data.account.data.firstName` | `.data.<field>` | **DataFetcher** (`getAccount`) | `accounts/PersonalAccount` → `data.firstName` |
| `$data.quote.items` (#foreach) | collection | request pass-through | product `contents: ["Item+"]` → exposure `Item` |
| `$item.data.purchasePrice` | `.data.<field>` | request pass-through | `exposures/Item` → `data.purchasePrice` |
| `$item.AccidentalDamage.data.labourCovered` | nested coverage | request pass-through | exposure `contents` → `coverages/AccidentalDamage` |
| `$data.pricing.totalBillable` | top-level invented key | **plugin-computed** | none — sum of `QuotePricing` charges |
| `$data.disclosureClause` | top-level invented key | **plugin-computed** | none — conditional string (reads `newBusinessWaitPeriod`) |
| `$data.productType` | top-level invented key | plugin literal `"ZenCover"` | none |

Every top-level entity (`quote`, `account`, `pricing`) came back as
`java.util.LinkedHashMap` at render time — confirming the records-become-Maps rule above.

---

### See also
- `docs/CONFIG_COVERAGE.md` — what the registry/config models
- `docs/writing-conditions.md` — the condition DSL used by conditional `$data` keys
- CLAUDE.md § "Listing available Velocity paths" and § "Ad-hoc rendering preview"
