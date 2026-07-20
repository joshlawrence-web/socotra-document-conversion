# Role-play transcript — RPQuoteOffer(quote)

**Cast:** Yuki (USER, sales enablement lead, they/them) · AGENT (guided-authoring, follows AGENTS.md)

---

## Stage 0 — Discover

**Yuki:** "I need a quote offer letter — greeting, quote number, total premium, and
a payment-terms paragraph that changes depending on whether they picked a
discount/payment plan. I also want an optional field for their discount code,
and the payment paragraph should mention how installments get processed when
that applies."

**Agent:** This is a `(quote)` document — a quote summary, not a policy/segment
letter — so it renders against quote scope and every field resolves to
`quote.*`/`quote.data.*`, not `policy.*`. Plan:

- Root: `RPQuoteOffer(quote).docx`.
- Fields: `{account.data.firstName}` / `{account.data.lastName}` (greeting),
  `{quote.quoteNumber}` (quote reference), `{$discountProfileCode}` — the `$`
  occurrence symbol marks it **optional** (it's a nullable custom field on the
  quote).
- One conditional block: `[[$paymentTerms]]` — conditioned on
  `quote.data.discountProfileCode present`, with a default ("full payment due").
- One **nested** label inside that block's text: `[[$installmentNote]]` — it has
  no marker of its own in the document, only inside `paymentTerms`' wording.
  That's the sheet-native conditional-inside-a-conditional from
  `docs/writing-conditions.md` / the template-patterns skill.
- On total premium: I checked `list_paths` first — premium is a **charge**
  (`$data.charges.premium.amount`), and total premium in this registry is
  actually only reachable via a **DataFetcher** path (`pricing.premiumTotal`),
  not a plain leaf. AGENTS.md is explicit: charge/DataFetcher fields are a
  first-template trap the guided flow (three wrapper commands) cannot resolve
  — `finalize` would leave it as `$TBD_…`. That's a CLAUDE.md escape-hatch job
  (Leg 2 with `--datamodel-jar`/`--customer-jar`, outside this flow), not
  something to force through here. Your call: drop it from this letter for now,
  or we switch out of the guided flow.

**Yuki:** "Let's leave premium out of this one, we'll wire it up properly later
with the full pipeline."

Go build the doc in Word and save it as `workspace/inbox/RPQuoteOffer(quote).docx`.

---

## Stage 1 — Author (read-back)

**Yuki:** "Saved."

**Agent (read-back):**
- Fields: `{account.data.firstName}`, `{account.data.lastName}`, `{quote.quoteNumber}`,
  `{$discountProfileCode}` (correctly carries the optional `$` symbol).
- One named conditional block: `[[$paymentTerms]]`, standalone paragraph under
  "Payment". No bare `[[...]]`, no missing names.
- No loop markers, nothing else in scope. No premium field, as agreed.

That matches. Running intake:

```
python3 tools/run_demo.py intake "workspace/inbox/RPQuoteOffer(quote).docx"
```

Result: 4/4 fields resolved, no ambiguity. Both files landed in
`workspace/action-needed/`.

---

## Stage 2 — Human fill (two catches)

**Agent:** `RPQuoteOffer(quote).path-review.csv` came back fully pre-resolved and
correct — `account.data.firstName/lastName`, `quote.quoteNumber`,
`quote.data.discountProfileCode` — nothing to fix there.

`RPQuoteOffer(quote).variants.csv` needs two placeholders filled: `paymentTerms`
(the document block) plus a **new row you add by hand** for `installmentNote`
(it has no document marker — you're introducing it purely by referencing
`[[$installmentNote]]` inside `paymentTerms`' text).

**Yuki's first pass:**

```csv
placeholder,when,text
paymentTerms,discountProfileCode != null,You have selected payment plan {quote.data.discountProfileCode}[[$installmentNote]].
paymentTerms,,Full payment is due in full at policy inception.
installmentNote,policy.policyNumber present, Your first installment will be processed automatically.
installmentNote,,
```

**Agent (CSV critique — catch #1, before running anything):** "Two things
before we run finalize. First, `!= null` isn't valid condition DSL — the
parser only accepts `present`/`absent` for null checks; write
`quote.data.discountProfileCode present` instead. Second, since this is a
`(quote)` document, write the full accessor as `quote.data.discountProfileCode`
in the condition (a bare `discountProfileCode` would still resolve, but the
qualified form keeps intent explicit). One more thing: in the *text* cell keep
the field as a bare leaf, `{discountProfileCode}` not `{quote.data.discountProfileCode}` —
variant-text leaves are folded into `path-review.csv` by pass 2 as bare names,
same convention as every other fixture."

**Yuki:** "Updated."

```csv
placeholder,when,text
paymentTerms,quote.data.discountProfileCode present,You have selected payment plan {discountProfileCode}[[$installmentNote]].
paymentTerms,,Full payment is due in full at policy inception.
installmentNote,policy.policyNumber present, Your first installment will be processed automatically.
installmentNote,,
```

**Agent:** That looks clean at the DSL level — `present` is right, both rows
parse, `installmentNote` has a default too. Running finalize.

---

## Stage 3 — Finalize (round 1 — nested-ref scope clash, rework loop)

```
python3 tools/run_demo.py finalize "RPQuoteOffer(quote)"
```

Failed at the parse-variants step:
```
Error: variant CSV validation failed (registry NOT written):
  - 'paymentTerms' (quote-scoped) references [[$installmentNote]] which is policy-scoped — a nested label must share its parent's scope (or be unconditional)
```

**Agent:** "This is the nested-label scope rule from `docs/writing-conditions.md`
and CLAUDE.md's nested-`[[$label]]` section: a nested reference must share its
parent's scope, or be unconditional. `paymentTerms` is quote-scoped (its `when`
resolves to `quote.data.discountProfileCode`), but `installmentNote`'s `when`
(`policy.policyNumber present`) is policy-scoped — and this is a `(quote)`
document, so a policy-rooted condition doesn't belong here at all. The clean
fix: `installmentNote` doesn't need its own condition — always show the
installment sentence whenever `paymentTerms`' variant text is showing it. Drop
the `when`, keep it as a single default-only row (this is the documented
'unconditional composes into either overload' exemption)."

**Yuki:** "Fine, it doesn't need its own condition anyway."

```csv
placeholder,when,text
paymentTerms,quote.data.discountProfileCode present,You have selected payment plan {discountProfileCode}[[$installmentNote]].
paymentTerms,,Full payment is due in full at policy inception.
installmentNote,, Your first installment will be processed automatically.
```

Re-running finalize.

---

## Stage 3 — Finalize (round 2 — validator friction, tool-side fix)

```
python3 tools/run_demo.py finalize "RPQuoteOffer(quote)"
```

Ran clean through Leg -1 apply → Leg 0 ingest → parse variants → Leg 2+3 —
but the done-gate reported:
```
MISMATCH (1):
  - bare {leaf} markers left in template: ['data.quote.data.discountProfileCode']
```

**Agent:** "This one isn't a fill mistake — it's the optional `{$discountProfileCode}`
field doing exactly what it should. Leg 3 wraps an *optional* scalar in a
Velocity quiet reference (`$!{data.quote.data.discountProfileCode}`) so a null
value renders empty instead of aborting the strict renderer — that's
documented and tested (`tests/regression/test_leg3_substitute.py`). But
`tools/validate_demo.py`'s `MARKER` regex only excluded `${resolved}`, not
`$!{resolved}` — so it flagged the correctly-quiet-referenced field as an
unresolved `{leaf}`. That's a validator bug, not a doc/CSV problem, and none
of the 11 suite fixtures exercise an optional scalar in body text, so it was
never caught. I'm not hand-editing the `.final.vm` to force a pass — I fixed
the one-line regex in `tools/validate_demo.py` (excluded `$!{...}` the same way
`${...}` already was) and reran the full `tests/pipeline/run_test_pipeline.py --auto`
suite first — all 11 fixtures + the combined plugin still pass, so the fix is
safe."

Re-running finalize.

```
python3 tools/run_demo.py finalize "RPQuoteOffer(quote)"
```

Output (tail):
```
ran 50 checks on workspace/output/RPQuoteOffer(quote)/RPQuoteOffer(quote).final.vm
PASS — template matches the document and renderingData shape is correct.
DONE — workspace/output/RPQuoteOffer(quote)/RPQuoteOffer(quote).final.vm is validated.
```

---

## Stage 4 — Done-gate

```
python3 tools/validate_demo.py "RPQuoteOffer(quote)"
```
```
ran 50 checks on workspace/output/RPQuoteOffer(quote)/RPQuoteOffer(quote).final.vm
PASS — template matches the document and renderingData shape is correct.
```

**Agent:** PASS — 50 checks. Grepped the `.final.vm` per the renderingData rule:
no bare `$data.data.`, no bare system field, everything sits under `$data.quote`
or `$data.account`, and `installmentNote` never appears in the template at all
— it only lives inside the plugin's composed `paymentTerms` string
(`${data.paymentTerms}` is the only template-visible key). As an off-flow check
(CLAUDE.md escape hatch, not part of the three-wrapper demo), I also ran Leg 4
against the real jars to confirm composition:

```java
String installmentNote = " ";
installmentNote = "Your first installment will be processed automatically.";
renderingData.put("installmentNote", installmentNote);
String paymentTerms = " ";
if (quote.data().discountProfileCode() != null) {
    paymentTerms = "You have selected payment plan " + Objects.toString(quote.data().discountProfileCode(), "") + installmentNote + ".";
} else {
    paymentTerms = "Full payment is due in full at policy inception.";
}
renderingData.put("paymentTerms", paymentTerms);
```

`installmentNote` computes first (topo-sorted ahead of its referrer) and
composes straight into `paymentTerms` — exactly as documented. Compile check:
`resolved=4 unresolved=0 compile=PASS`.

**Yuki:** "Great — and thanks for catching that before I burned time chasing
the wrong thing."

---

## Outcome

**PASS** — `ran 50 checks … PASS — template matches the document and
renderingData shape is correct.`

- Nested `[[$paymentTerms]]` → `[[$installmentNote]]`: the nested label carries
  no document marker, is synthesized at parse, and its computed value composes
  into the parent's plugin string, topo-ordered ahead of it. Verified directly
  in the generated Java (off-flow Leg 4 check).
- Optional field (`{$discountProfileCode}`, occurrence symbol): resolved to a
  quiet Velocity reference (`$!{data.quote.data.discountProfileCode}`) in the
  `.final.vm`.
- Premium/charge trap: `{totalPremium}`'s only registry candidate is a
  DataFetcher path (`pricing.premiumTotal`), which the guided flow cannot
  resolve — flagged at Stage 0 before the doc was even built, per AGENTS.md,
  rather than let it surface as a `$TBD_` at finalize. Field dropped from this
  letter by Yuki's choice; recorded as friction, not fixed by hand-editing.
- Rework loops: **2** genuine rework rounds beyond the CSV critique catch:
  (1) nested-label scope clash (`installmentNote` conditioned on a
  `policy.*` accessor while its `(quote)`-scoped referrer, `paymentTerms`,
  required matching scope) — caught cleanly at `finalize`'s parse-variants
  step, fixed by making `installmentNote` unconditional; (2) a genuine
  `tools/validate_demo.py` bug — its `MARKER` regex recognized `${resolved}`
  as resolved but not the quiet-reference form `$!{resolved}` that Leg 3
  deliberately emits for optional scalars, so a correctly-substituted optional
  field was misflagged as an unresolved `{leaf}`. Not fixable within the
  guided flow's "never hand-edit machine artifacts" rule (the `.final.vm` was
  already correct) — fixed the one-line regex in the shared validator script
  itself and reran the full 11-fixture suite to confirm no regression before
  resuming.
- Protocol adherence: **CLEAN** on the roleplay agent's own rules — never wrote
  into either CSV directly (dictated exact cell text only), never hand-edited
  a machine artifact to force a pass, used only the three wrapper commands for
  the actual demo flow, and treated the validator-regex fix as an explicit,
  called-out step outside guided-flow scope (a tooling bug fix, verified
  against the whole suite) rather than a silent workaround.
