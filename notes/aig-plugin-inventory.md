# AIG reference config — plugin inventory (2026-07-16)

Scope: `workspace-prod/reference/socotra-config/` + `workspace-prod/reference/build/`,
question = what must ship for quote-create + document-render on a fresh EC sandbox tenant.

## 1. Plugin implementations shipped with the config

**None.** There is no `plugins/` directory anywhere under
`workspace-prod/reference/socotra-config/` — no `.java` sources, no plugin jars.
The config is data-only: product tree (`products/BlanketSpecialRisk`), 79 charge
dirs, 196 lookup `tables/`, `rangeTables/`, `constraintTables/`, coverages,
exposures, documents, automations (schemas only), uiConfigs, plans.

`build/customer-config.jar` (3.9 MB) contains **only generated SDK interfaces**
(`com.socotra.deployment.customer.*`) — zero `*Impl` classes. Interfaces present
(all with no-op `default` methods + a `*PluginStub`):

Rate, Validation, Underwriting, PreCommit, Cancellation, Renewal, Installments,
Autopay, PaymentPostProcessing, ConfigMigration, DelinquencyEvent,
WorkplanExecution, WorkplanSelection, DocumentDataSnapshot, DocumentSelection,
DocumentConsolidationSnapshot, DocumentConsolidationSelection, plus five
automation plugin interfaces (AccountUtility, MdmParty, MdmProducer,
NgeUpdateSubmission, NgplsBroker, QuoteClearance, StateConfiguration).

**Stale leftovers, ignore:** `build/classes/java/main/` holds a compiled
`RatePluginImpl` + `CglRater` + `PersonalAutoRater` from a *different* product
(PersonalAuto / CommercialGeneralLiability — not BlanketSpecialRisk). Its source
is not in the tree and it will not compile against this config's generated
interfaces. Do not deploy it.

## 2. (a) RatePlugin — is one required for quote create?

No implementation exists, and **quote create/price will not fail without one**.
The generated `RatePlugin` interface defaults every overload to
`RatingSet.builder().ok(true).ratingItems(Collections.emptyList()).build()` —
i.e. rating succeeds with zero charges. All 79 charges are
`category: premium, handling: normal, invoicing: scheduled`; nothing in the
charge config forces a rater at quote-create time. Consequence: quotes price to
$0 until a real RatePlugin is written (the 196 rate tables + rangeTables are
in-config and ready for one, but the rater itself was never delivered with this
reference).

## 3. (b) DocumentDataSnapshotPlugin collision?

**No collision.** The `DocumentDataSnapshotPlugin` interface exists in the jar
(quote + policy/segment + invoice overloads) with default renderingData =
the raw quote/segment entity, but no customer implementation is present anywhere.
The Leg 4 generated `*DocumentDataSnapshotPluginImpl.java` will be the first and
only implementation on the tenant. (Same story for DocumentSelectionPlugin.)

## 4. (c) External resources / secrets a fresh tenant won't have

- `secrets/Integrations/config.json` declares a **secrets schema** (values are
  NOT in the config — they must be set on the tenant after deploy): `mdmUrl`,
  `mdmAuthUrl`, `mdmAuthIssuerId`, `mdmClientId`, `mdmClient_secret`,
  `mdmGrant_type`, `mdmScope`, `ofacBaseUrl`, `ngplsBaseUrl`, `ngeBaseUrl`,
  `originatingUser`, plus `mdmMockEnabled` / `ngplsMockEnabled` booleans.
- Seven `automations/` (AccountUtility, MdmParty, MdmProducer,
  NgeUpdateSubmission, NgplsBroker, QuoteClearance, StateConfiguration) are
  request/response **schemas only** — the AutomationPlugin impls that would call
  those AIG endpoints (MDM party/producer search, OFAC, NGPLS broker, NGE
  submission sync) were never in this drop. On a fresh sandbox they are inert;
  nothing in the core quote lifecycle invokes them.
- ~40 `documents/` entries are `rendering: prerendered` PDFs (OFAC notice,
  per-state Guaranty notices, Policy_Packet…) triggered on `issued` — the
  prerendered assets are not needed for quote-create or for our ad-hoc render
  path, which bypasses deployed document config entirely.
- All rating/constraint tables are in-config (`tables/`, `rangeTables/`,
  `constraintTables/`) — no external table source.

## 5. Datamodel version pin

`build/` carries three generations: core-datamodel **v1.7.50**, **v1.7.68**, and
**v1.7.71** (+ sources/javadoc jars each). `customer-config.jar` and
`core-datamodel-v1.7.71.jar` share the same build date (24 Jun) — treat
**v1.7.71 as the pin** for compiling any plugin against this config. Note the
main repo's test config uses v1.7.61 (`build/core-datamodel-v1.7.61.jar`) — do
not mix them; Leg 4 `--datamodel-jar` for AIG work must point at the reference
v1.7.71 jar. A fresh EC sandbox will hand back its own datamodel on config
deploy; regenerate/re-download `customer-config.jar` from the tenant rather than
assuming this jar stays valid if the platform version differs.

Deps in `build/` (slf4j 1.7.36, jackson 2.19.2, protobuf 4.33.2) are compile-time
only; the tenant supplies its own runtime.

## What must be true before quote-create works (checklist)

1. Deploy `workspace-prod/reference/socotra-config/` as-is — it is data-complete
   (tables in-config, no plugin sources to compile). Expect the platform to
   compile only the generated interfaces.
2. Set the `Integrations` secret values on the tenant (or at minimum the two
   mock flags) — required only if/when the Mdm/Ngpls/Nge/OFAC automations get
   implementations; core quote-create does not touch them.
3. Create an account of the config's account type; then create a
   BlanketSpecialRisk quote satisfying the product's structural requirements:
   at least one `Risk` exposure (`Risk+`) and the required elements
   (`PolicyAdjustmentFactor!`, `GeneralExclusions!`, `Limitations!`, `Injury!`,
   `RightToTermination!`, `BeneficiaryDetails!`) with their required fields.
4. Accept that pricing returns $0: no RatePlugin impl exists and the default
   stub returns an empty-OK RatingSet. Ship a RatePlugin only when real premiums
   are needed — it is NOT a quote-create gate.
5. For rendering: deploy the Leg 4 generated DocumentDataSnapshotPluginImpl —
   no existing impl collides. Compile it against the tenant's regenerated
   customer-config.jar + core-datamodel v1.7.71.
6. Ignore/delete `build/classes/java/main/*` (stale PersonalAuto/CGL rater from
   another project).
