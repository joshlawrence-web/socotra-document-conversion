# Sanity report — policy-template.html

30 findings across 6 categories. Review before mapping; this skill never auto-fixes what it flags.

## Cross-scope variable name reuse

- `{{coverage_name}}` appears inside 3 loop scopes: `coverages`, `general_coverages`, `vehicles`. Each will need its own data source during mapping.
- `{{deductible}}` appears inside 3 loop scopes: `coverages`, `general_coverages`, `vehicles`. Each will need its own data source during mapping.
- `{{first_name}}` appears inside 4 loop scopes: `discount_drivers`, `driver_filings`, `drivers`, `named_insureds`. Each will need its own data source during mapping.
- `{{last_name}}` appears inside 4 loop scopes: `discount_drivers`, `driver_filings`, `drivers`, `named_insureds`. Each will need its own data source during mapping.
- `{{limits}}` appears inside 3 loop scopes: `coverages`, `general_coverages`, `vehicles`. Each will need its own data source during mapping.
- `{{limits_detail}}` appears inside 3 loop scopes: `coverages`, `general_coverages`, `vehicles`. Each will need its own data source during mapping.
- `{{premium}}` appears inside 3 loop scopes: `coverages`, `general_coverages`, `vehicles`. Each will need its own data source during mapping.

## Fragile single-variable blocks

- **L108** — `<h6>` content is the single variable `{{financial_responsibility_phone}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L167** — `<span>` content is the single variable `{{filing_type}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L169** — `<span>` content is the single variable `{{filing_state}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L171** — `<span>` content is the single variable `{{case_number}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L251** — `<span>` content is the single variable `{{policy_number}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L266** — `<span>` content is the single variable `{{year}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L267** — `<span>` content is the single variable `{{make}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L268** — `<span>` content is the single variable `{{model}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L302** — `<span>` content is the single variable `{{lienholder_name}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L305** — `<span>` content is the single variable `{{lienholder_address}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L308** — `<span>` content is the single variable `{{lienholder_city}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L311** — `<span>` content is the single variable `{{lienholder_state}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L314** — `<span>` content is the single variable `{{lienholder_zip}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.
- **L319** — `<span>` content is the single variable `{{additional_interest}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.

## Potentially hardcoded dollar amounts

- **L329** — Found `$3,000` in static text. Consider making this a variable if product/state dependent.
- **L330** — Found `$3,000,` in static text. Consider making this a variable if product/state dependent.
- **L331** — Found `$500` in static text. Consider making this a variable if product/state dependent.
- **L335** — Found `$3,000` in static text. Consider making this a variable if product/state dependent.

## Structural

- **L71** — Loop `{{#named_insureds}}` body contains `<li>` but has no `<ul>`/`<ol>` ancestor; it will render as loose list items.

## Suspicious placeholder tokens

- **L280** — `XXXX` appears in static text: `<li>Company claims history (XXXX)</li>`

## Unlabeled variables

- **L5** — `{{policy_number}}` has no preceding label/strong within its block. Confirm the label is conveyed by layout, or add one.
- **L5** — `{{insured_first_name}}` has no preceding label/strong within its block. Confirm the label is conveyed by layout, or add one.
- **L5** — `{{insured_last_name}}` has no preceding label/strong within its block. Confirm the label is conveyed by layout, or add one.
