# RPWelcomeBasic Roleplay Transcript

**Participants:** Dana (ZenCover PM, USER), Agent (guided authoring facilitator)  
**Start Date:** 2026-07-17  
**Goal:** Create a simple welcome letter with greeting, policy number, premium, and conditional discount paragraph

---

## STAGE 0 — Discovery Conversation

**AGENT:**
Hi Dana! Let's build your welcome letter for new policyholders. Before we jump into Word, let me understand what you want:

- Is this a letter that goes to every customer (a policy document), or a quote summary they see before they buy?
- What's the core story? Greeting them, letting them know their policy is active, some key details?
- You mentioned a discount paragraph — what triggers it? "Only show this when they got a discount"?

**USER (Dana):**
Yes, perfect! So this is definitely for policies, not quotes. New customers get it in the mail. We want to:
1. Greet them by name (first name, casual)
2. Their policy number
3. How much the premium is
4. And then — this is the key bit — if we gave them a discount, we want a paragraph explaining it. Something like "We've applied a 15% discount because you're a returning customer."

**AGENT:**
Got it. So you're building a `(segment)` document — policy-level. Let me pull the field catalog and suggest what you can use:

**Fields we have:**
- **Greeting:** `firstName` (from the policyholder's account)
- **Policy ID:** `policyNumber`
- **Premium:** The `premium` charge amount
- **Discount:** `discountAmount` — and we can make it conditional: "show this paragraph only when `discountAmount` is present"

To keep it simple, I'd suggest:
1. A plain greeting: `Dear {firstName},`
2. Your policy details: policy number and premium on a couple of lines
3. One conditional block `[[$discountNote]]` that wraps the discount paragraph — you fill that in a spreadsheet later

Does that match what you're after?

**USER (Dana):**
Exactly! So I write the marker `[[$discountNote]]` in the document, and then I fill in the actual wording later in a spreadsheet? That sounds right.

**AGENT:**
Yes, exactly. You'll create a Word doc with:
- The greeting using `{firstName}` — bare name, the tool suggests the full path
- `{policyNumber}` and the premium amount (you'll type the field name)
- A paragraph wrapped in `[[$discountNote]]` … `[/$discountNote]]` markers (wait, let me correct that — the markers for a conditional text block are `[[$discountNote]]` in the Word doc, but they're not paired like a loop — the `[[$name]]` just marks a placeholder for text you'll write in the spreadsheet)

Actually, let me clarify the marker syntax: for a conditional **paragraph** like your discount wording, there are two ways:
- **Simpler (you're drafting it):** A `[Name?]` … `[/Name]` region that guards the whole paragraph — you write it in the doc itself
- **Cleaner (you're picking from options later):** A `[[$token]]` placeholder where you fill the wording in the spreadsheet

For a welcome letter, the second is probably better — you keep the doc clean and fill the variant text in a spreadsheet. So you'd write the placeholder `[[$discountNote]]` right where you want that paragraph, then in the spreadsheet, you'll write the condition (`discountAmount present`) and the wording.

**USER (Dana):**
OK so the placeholder is just `[[$discountNote]]`? Not paired? And I put that sentence in the doc where the paragraph should go?

**AGENT:**
Exactly right. It's a single token — just `[[$discountNote]]` in the document, no closing marker. The spreadsheet fills in the wording and the condition.

Now, field names: for the premium, do you know what it's called in your system, or should I just list a few guesses? Common names are `premium`, `totalPremium`, `annualPremium`.

**USER (Dana):**
Let me think... I think we just call it "premium" — it's the main charge. If that's in your system, use that.

**AGENT:**
Perfect, `premium` is there. Now, before you open Word, let me confirm the list of what you'll type:

1. `{firstName}` — greeting
2. `{policyNumber}` — policy ID
3. `{premium}` — the premium charge
4. `[[$discountNote]]` — placeholder for the conditional wording

Does that look right? And one more thing: the filename must end in `(segment)` or `(quote)` before `.docx` — since this is a policy letter, you'll save it as **`RPWelcomeBasic(segment).docx`** in `workspace/inbox/`. Sound good?

**USER (Dana):**
Got it. I'll write it in Word and save it there. Let me draft it now.

---

## STAGE 1 — Authoring (User creates the docx)

*[User creates `workspace/inbox/RPWelcomeBasic(segment).docx` in Word with content]*

Dear {firstName},

Welcome to ZenCover! We're excited to protect your items.

Your policy number is {policyNumber}.
Your premium: {premium}.

[[$discountNote]]

Thank you for choosing ZenCover.

---

**[After user saves the docx, Agent reads it back]**

**AGENT (reading back):**
Great! Let me confirm what I see in your document:

**Fields:**
- ✓ `{firstName}` — greeting
- ✓ `{policyNumber}` — policy number
- ✓ `{premium}` — premium amount

**Conditional blocks:**
- ✓ `[[$discountNote]]` — placeholder for the discount wording

Everything is there and looks right. One quick sanity check: for the `{premium}` field, do you want that to be a number with currency formatting, or just the bare number? The system will give us the number — if you want it prettier, we can tweak that after the template is generated.

**USER (Dana):**
Bare number is fine for now — we'll dress it up later if needed.

**AGENT:**
Perfect. Ready to run the intake?

**USER (Dana):**
Yep!

---

## STAGE 2 — Intake Run

**AGENT:**
Intake ran successfully! The system found your three fields and scanned for conditionals. Now I need to explain the two files you're about to fill.

**File 1: `path-review.csv`** — This lists every field you used and suggests the full accessor path.

Let me show you what arrived:
- `{firstName}` → suggested `account.data.firstName` ✓ Already correct!
- `{policyNumber}` → suggested `policy.policyNumber` ✓ Already correct!
- `{premium}` → suggested `charges.premium.amount` ✓ Already correct!

All three fields were resolved automatically. You just need to **confirm** each one by making sure the `final` column (the rightmost column) has the right path. Here they all look good, so you can leave them as-is.

**File 2: `variants.csv`** — This is where you write the conditional block's wording and condition.

The system found your `[[$discountNote]]` placeholder. Here's what you need to fill:

| placeholder | when | text |
|---|---|---|
| discountNote | `discountAmount present` | *Your discount paragraph here* |
| discountNote | *(leave blank)* | *(leave blank)* |

The first row: you write the **condition** in the `when` column (`discountAmount present` means "only show this if the customer got a discount") and the **wording** in the `text` column — something like "You've received a special discount of {discountAmount}! Thank you for your loyalty."

The second row is the **default** — what appears if the condition is false. If you want nothing to appear when there's no discount, leave both `when` and `text` blank.

Does that make sense?

**USER (Dana):**
Yes! So I confirm the fields are right, and then I write the discount paragraph. The condition is "discountAmount present" — perfect, that's exactly what I want.

For the text, I want: "You've also received a 15% loyalty discount of {discountAmount}. We appreciate your business!"

**AGENT:**
Got it. Two things:
1. You can use bare field names in that text cell — so `{discountAmount}` is fine, the system will pick it up.
2. Your wording sounds great. Let me double-check: is that the **only** variant you want, or do you want something different if the discount is a different amount? (e.g., "5% for some customers, 15% for others")

**USER (Dana):**
No, that one wording is fine for all discounts. It's the same message for everyone who gets a discount.

**AGENT:**
Perfect. Go ahead and fill both CSVs. For `path-review.csv`, just confirm all three fields have the right `final` value (they do). For `variants.csv`, fill the first row and leave the second blank. Then let me know when you're done.

---

**[User Dana fills the CSVs]**

**USER (Dana) — path-review.csv review:**
✓ `{firstName}` → `account.data.firstName` — Confirmed
✓ `{policyNumber}` → `policy.policyNumber` — Confirmed  
✓ `{premium}` → `charges.premium.amount` — Confirmed

All three look right!

**USER (Dana) — variants.csv filled:**
Row 1 (the discount case):
- placeholder: discountNote
- when: `discountAmount present`
- text: `You've also received a 15% loyalty discount of {discountAmount}. We appreciate your business!`

Row 2 (default/no discount):
- placeholder: discountNote
- when: *(blank)*
- text: *(blank)*

**AGENT (reading back Dana's fills):**
Perfect! Let me confirm I see this right:

**Condition DSL check:** `discountAmount present` — yes, that's the right syntax. It means "render this paragraph only when the customer has a discount amount."

**Wording:** You're using a bare field `{discountAmount}` in the text cell — that's exactly right, the system will pick it up and resolve it.

**Default row:** Blank, which means "if there's no discount, don't show anything" — correct.

Everything looks good. Ready to finalize?

**USER (Dana):**
Yes, let's go!

---

## STAGE 3 — Finalize (Pass 1)

**AGENT:**
Running finalize now...

[System output:]
```
Pass 2: 1 net-new variant-text leaf(s): 1 resolved, 0 ambiguous, 0 unmatched.
```

Great news and a small hiccup:
- Good news: All your original fields are ready
- Small thing: You used `{discountAmount}` in the variant text, and the system is asking you to confirm its path

The system already suggested `policy.data.discountAmount`, which is exactly right — that's the policy's discount field. Let me show you the updated path-review.csv:

**New row added:**
- `{discountAmount}` → suggested `policy.data.discountAmount` → `final` = `policy.data.discountAmount` ✓

This is already correct, so you just need to review it and confirm you're happy with it. Once you do, I'll re-run finalize.

**USER (Dana):**
That looks right — it's the discount amount. Confirmed!

---

## STAGE 3 — Finalize (Pass 2 — re-run with the new field confirmed)

**AGENT (running finalize again):**
[System runs through Leg 0 → variants parsing → Leg 2 path resolution → Leg 3 substitution]

MISMATCH detected:

**Result:** The template has one unresolved token: `$TBD_charges.premium.amount`

**What happened:** The `{premium}` field is a charge field (not a plain field), and the pipeline's schema verification can't find it in the compiled SDK index. This is a known limitation — charge fields are tricky because they're registry-only, not schema-verified.

**Fix:** The registry knows about this field as `$data.charges.premium.amount`. I'm going to manually fill that into the mapping and re-run Leg 3.

*[Manually updating the mapping.yaml data_source for charges.premium.amount]*

Re-running Leg 3…

---

## STAGE 4 — Validation (The Done-Gate)

**[Running the validator]**

```
ran 44 checks on workspace/output/RPWelcomeBasic(segment)/RPWelcomeBasic(segment).final.vm
PASS — template matches the document and renderingData shape is correct.
```

**AGENT:**
✓ **PASS!** Your template is done. Let me show you what you've built:

**What the final template does:**
1. Greets the customer by first name: `Dear {firstName},`
2. States their policy number: `{policyNumber}`
3. Shows the premium amount: `{premium}`
4. Conditionally displays the discount paragraph **only when they have a discount** (when `discountAmount` is present), with the exact wording: "You've also received a 15% loyalty discount of {discountAmount}. We appreciate your business!"
5. If there's no discount, that paragraph doesn't appear at all.

**Files created:**
- `workspace/output/RPWelcomeBasic(segment)/RPWelcomeBasic(segment).final.vm` — the production template
- `workspace/output/RPWelcomeBasic(segment)/RPWelcomeBasic(segment).leg3-report.md` — what resolved and what didn't
- Supporting artifacts (path-map, mapping, conditional-registry)

This is ready to deploy to Socotra!

**USER (Dana):**
Fantastic! That was actually pretty straightforward. The only hiccup was the premium field, but once we fixed the mapping, it worked.

**AGENT:**
Right. Premium/charge fields are a known edge case in the pipeline — the registry knows about them, but they require a manual fix in the mapping because they're not in the compiled schema. For your next template, you might want to stick to simpler fields first, or we can handle charge fields the same way. Either way, now you know the pattern!

---

## Summary

**Outcome:** PASS (44 checks)

**Markers exercised:**
- ✓ `{field}` bare placeholders (firstName, policyNumber)
- ✓ `{field}` with dotted registry path (premium)
- ✓ `[[$token]]` conditional text block (discountNote)
- ✓ Bare `{leaf}` inside variant text (discountAmount in the discount paragraph)

**Rework loops:** 1
- **Cause:** Premium field is a charge-level path that requires manual mapping resolution (Leg 2 → Leg 3 handoff)
- **Fix:** Edited the mapping.yaml to supply `$data.charges.premium.amount` and re-ran Leg 3

**Friction points:**
1. **Charge fields not auto-resolved** — The pipeline's schema verification doesn't catch charge fields, leaving them as `$TBD_*` tokens. User guidance should warn against using premium fields in first templates, or flag upfront that manual mapping work is needed.
2. **Pass 2 (variant-text field detection)** — Working as designed. The system correctly detected `{discountAmount}` in the variant text and asked for confirmation. Good UX for catching variant-only fields.

**Files produced:**
- `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverterZenCover/workspace/inbox/RPWelcomeBasic(segment).docx` — source document
- `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverterZenCover/workspace/output/RPWelcomeBasic(segment)/RPWelcomeBasic(segment).final.vm` — production template ✓ PASS
- `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverterZenCover/workspace/output/RPWelcomeBasic(segment)/RPWelcomeBasic(segment).leg3-report.md` — validation report
- `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverterZenCover/workspace/output/RPWelcomeBasic(segment)/RPWelcomeBasic(segment).path-review.md` — canonical field mappings
- `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverterZenCover/workspace/output/RPWelcomeBasic(segment)/RPWelcomeBasic(segment).conditional-registry.yaml` — variant block metadata
- `workspace/action-needed/RPWelcomeBasic(segment).path-review.csv` — reviewed and confirmed ✓
- `workspace/action-needed/RPWelcomeBasic(segment).variants.csv` — filled with discount condition and wording ✓

**Verbatim highlights from transcript:**

1. **Dana's requirement (discovery):**
   > "We want to: 1. Greet them by name (first name, casual) 2. Their policy number 3. How much the premium is 4. And then — this is the key bit — if we gave them a discount, we want a paragraph explaining it. Something like 'We've applied a 15% discount because you're a returning customer.'"

2. **Agent's clarification on conditional syntax:**
   > "For a conditional **paragraph** like your discount wording, there are two ways: ... Cleaner (you're picking from options later): A `[[$token]]` placeholder where you fill the wording in the spreadsheet."

3. **Agent's explanation of the charge-field friction:**
   > "The `{premium}` field is a charge field (not a plain field), and the pipeline's schema verification can't find it in the compiled SDK index. This is a known limitation — charge fields are tricky because they're registry-only, not schema-verified."



