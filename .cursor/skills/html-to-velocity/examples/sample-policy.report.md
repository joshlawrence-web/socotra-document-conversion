# Sanity report — sample-policy.html

5 findings across 2 categories. Review before mapping; this skill never auto-fixes what it flags.

## Fragile single-variable blocks

- **L20** — `<strong>` content is the single variable `{{policyNumber}}`. If the data is missing, this element will render empty. Consider a fallback label or wrap with `#if`.

## Unlabeled variables

- **L20** — `{{policyNumber}}` has no label immediately before it. Confirm the label is conveyed by layout, or add `<strong>...:</strong>` style tag.
- **L30** — `{{lastName}}` has no label immediately before it. Confirm the label is conveyed by layout, or add `<strong>...:</strong>` style tag.
- **L31** — `{{location}}` has no label immediately before it. Confirm the label is conveyed by layout, or add `<strong>...:</strong>` style tag.
- **L38** — `{{coverageName}}` has no label immediately before it. Confirm the label is conveyed by layout, or add `<strong>...:</strong>` style tag.
