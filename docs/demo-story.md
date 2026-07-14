  ---
  The Tale of Priya and the ZenCover Welcome Letter
  
  Priya runs customer comms at ZenCover, a gadget-insurance startup. She's never written a line of code. But today she's been handed a job that used to take the engineering team two
  weeks: turn her Word letter into a living template that fills itself in for every customer.
  
  Her implementation contact, Sam, told her one thing before she started:
  
  ▎ "Just write the letter like you'd write it to a real person. Wherever a real value goes, leave me a little marker. I'll teach you three markers. That's the whole job."
  
  Priya opens Word. Here's what she learns, marker by marker.
  
  ---
  Marker 1 — The curly brace: "put a real value here"

  Priya writes the greeting:
  
  ▎ Dear {firstName} {lastName},

  She doesn't know that firstName lives at account.data.firstName in ZenCover's system — and Sam told her she doesn't have to*. She just wraps the plain field name in curly braces.
  The pipeline's first leg (Leg -1) will hand her back a little review sheet that says "I think {firstName} means account.data.firstName — yes?" and she just confirms it.

  So her quote table becomes:
  
  | Quote Reference | {quoteNumber} |
  | Cover Start Date | {startTime} |
  | Total Monthly Premium | {premiumTotal} |
  
  The lesson: curly braces = "a real value drops in here." Write the name, not the database path.
  
  The little symbols (optional, but great for a demo)
  
  Sam mentions a power-user trick. If a field might be missing, or might repeat, she can put a symbol right after the opening brace:
  
  - {email} — required. Must be there or the system complains loudly.
  - {$middleName} — optional (the $). Fine if it's blank.
  - {+phoneNumber} — one or more.
  - {*nickname} — zero or more.

  Priya marks the customer's middle name {$middleName} because plenty of people don't have one. "Now the document won't break for them," Sam says.
  
  ---
  Marker 2 — The dollar-token: "only show this sometimes — or pick one of several versions"
  
  Priya's letter has a line that should only appear for new customers. Sam's rule: every conditional gets its own name, right in the double brackets — a "$token", not a raw sentence:

  ▎ [[$newCustomerDiscount]]
  
  She does the same for the accidental-damage line:

  ▎ [[$accidentalDamageCover]]
  
  She writes the actual wording later, in a spreadsheet — not in Word. (If she wraps a whole sentence in double brackets *without* a `$name`, the pipeline stops and tells her to
  name it — no auto-naming, no guessing.)

  After she sends the document in, the pipeline hands her back a single spreadsheet — ZenCoverWelcomeLetter(quote).variants.csv — one row group per named token, blank for her to
  fill in both the when and the text:

  placeholder,when,text
  newCustomerDiscount,,
  newCustomerDiscount,,
  accidentalDamageCover,,
  accidentalDamageCover,,

  Priya (or Sam, if it's technical) fills the condition and the wording in plain dot-notation (the condition language uses present / absent, not "!= null"). The second, blank row
  per token is the default — the fallback when nothing else matches:

  newCustomerDiscount,"quoteNumber present","As a new ZenCover customer, a welcome discount has been applied to your first premium payment."
  newCustomerDiscount,,""
  accidentalDamageCover,"state == ""CA""","Your plan includes Accidental Damage cover from day one — no waiting period applies."
  accidentalDamageCover,,""

  The lesson: `[[$token]]` = "maybe show this — the name is mine to pick, the wording and the when both go in the CSV." That same CSV carries every named token in the letter,
  binary or many-way — see the 50-state trick below.
  
  ▎ A conditional's text can even contain its own values: "A loyalty discount of {discountAmount} applies (type: {discountType})." — curly braces nest happily inside a variant's
  ▎ text cell.

  ZenCover also operates in many states, and each state needs a different legal disclosure. Priya does not paste 50 paragraphs — she reuses the very same marker, just with more
  rows:

  ▎ Applicable Disclosure:
  ▎ [[$disclosureClause]]

  Its rows in the same .variants.csv:
  
  placeholder,when,text
  disclosureClause,"discountType == ""FLAT""","Policy {policyNumber}: a flat discount of {discountAmount} applies."
  disclosureClause,"discountType == ""PERCENT""","Policy {policyNumber}: a percentage discount applies."
  disclosureClause,,"Policy {policyNumber}: no discount applies."

  Each row is a version: a when rule and the text to show. The blank when is the default. Notice the text can hold its own {curly} values too. One marker in Word, as many rows in
  the CSV as she needs — one condition or fifty.
  
  ---
  Marker 3 — The named section: "repeat this for every item"
  
  ZenCover policies can cover many gadgets. Priya wants one table row per insured item. She builds a normal Word table with a header row, then wraps the data row in matching tags
  named after the thing being listed — the opening tag gets a trailing slash, so the pipeline knows it's a loop and not a stray bracket:
  
  ┌────────────────┬────────────────┬─────────────────┬────────────────┐
  │   Item Type    │ Purchase Date  │      Price      │     Serial     │
  ├────────────────┼────────────────┼─────────────────┼────────────────┤
  │ [Item/]        │                │                 │                │
  ├────────────────┼────────────────┼─────────────────┼────────────────┤
  │ {itemTypeCode} │ {purchaseDate} │ {purchasePrice} │ {serialNumber} │
  ├────────────────┼────────────────┼─────────────────┼────────────────┤
  │ [/Item]        │                │                 │                │
  └────────────────┴────────────────┴─────────────────┴────────────────┘
  
  [Item/] … [/Item] is an open/close pair. The header stays put; the row between the tags repeats once per gadget. (The name Item has to match what ZenCover calls its item list —
  Sam confirms that part.)

  The lesson: [Name/] … [/Name] = "loop this region for each one." Header once, body per item.
  
  ▎ Advanced flourish for the demo: a loop can be conditional too, without nesting it inside a [[$token]] block. Priya writes a "Free Gifts" section as its own loop —
  ▎ [Gift/]…[/Gift] — and the variants.csv that comes back has a row for it, keyed by the loop's own name, with no text column to fill (the wording stays in the document):
  ▎
  ▎ placeholder,when,text
  ▎ Gift,,
  ▎
  ▎ She leaves it blank and the gift list always shows; she writes a condition — Gift,"loyaltyTier == ""GOLD"""," — and the whole section (list and all) appears only for gold-tier
  ▎ customers.
  
  ---
  How the demo flows (the part you say out loud)

  Here's the arc to narrate when you present it:
  
  1. "I wrote a normal letter." Show the Word doc with the three markers — curly braces, an [Item/] loop, and named [[$token]] blocks (one condition or many).
  2. "I hand it to the pipeline once." Run intake:
  python3 -m velocity_converter.agent --yes "RUN_PIPELINE intake input=workspace/inbox/ZenCoverWelcomeLetter(quote).docx registry=registry/path-registry.yaml
  output=workspace/output"
  3. "It hands me back two fill-in-the-blank files" — both in workspace/action-needed/:
    - …path-review.md → confirm each field name maps to the right path.
    - …variants.csv → ONE file for ALL conditional text: write the when + text for each [[$token]] block (more rows for a many-way token), and just the when for each [Item/]-style
      loop's row.
  4. "I fill those in like a form — no code." Confirm paths, write conditions, fill variant rows.
  5. "The pipeline turns my letter into a self-filling template." Run Leg -1 apply → Leg 0 → Leg 2+3+4, and out comes the production .final.vm plus the Java plugin.

  The moral Priya learned: write the document for a human; leave three kinds of markers; answer the forms that come back. That's the whole customer job.
  
  ---
  Cheat sheet (hand this to whoever fills the doc)

  ┌────────────────────────────┬───────────────────────────────────────────────────┬────────────────────────────────────┐
  │           Marker           │                       Means                        │              Example               │
  ├────────────────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────┤
  │ {field}                    │ drop a real value in                               │ Dear {firstName},                  │
  ├────────────────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────┤
  │ {$field} {+field} {*field} │ optional / one-or-more / zero-or-more              │ {$middleName}                      │
  ├────────────────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────┤
  │ [Name/]…[/Name]            │ repeat for each one in a list                      │ [Item/]…[/Item] table row          │
  ├────────────────────────────┼───────────────────────────────────────────────────┼────────────────────────────────────┤
  │ [[$token]]                 │ name a block: show it sometimes, or pick one       │ [[$disclosureClause]]              │
  │                            │ of several versions — the CSV carries the rest    │                                     │
  └────────────────────────────┴───────────────────────────────────────────────────┴────────────────────────────────────┘

  A bare `[[some sentence]]` with no `$name` is no longer valid — the pipeline stops and lists every unnamed block it finds. Name it and move the wording to the CSV.
  
  ---
  Want me to actually run this end to end on a sample doc so the demo has real output files to show? I can spin up a ZenCoverWelcomeLetter walkthrough and produce the two fill-in
  files live.