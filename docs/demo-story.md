  ---
  The Tale of Priya and the ZenCover Welcome Letter
  
  Priya runs customer comms at ZenCover, a gadget-insurance startup. She's never written a line of code. But today she's been handed a job that used to take the engineering team two
  weeks: turn her Word letter into a living template that fills itself in for every customer.
  
  Her implementation contact, Sam, told her one thing before she started:
  
  ▎ "Just write the letter like you'd write it to a real person. Wherever a real value goes, leave me a little marker. I'll teach you four markers. That's the whole job."
  
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
  Marker 2 — The double bracket: "only show this sometimes"
  
  Priya's letter has a line that should only appear for new customers:

  ▎ [[As a new ZenCover customer, a welcome discount has been applied to your first premium payment.]]
  
  She wraps the whole sentence in double square brackets. That tells the pipeline: this is conditional text — someone will decide later when it shows.
  
  She does the same for the accidental-damage line:

  ▎ [[Your plan includes Accidental Damage cover from day one — no waiting period applies.]]
  
  She does not have to write the rule herself. After she sends the document in, the pipeline hands her back a single spreadsheet — ZenCoverWelcomeLetter(quote).variants.csv — one
  row per conditional. Each binary [[…]] block comes back with its text already filled in from her letter; she only writes the when:

  placeholder,when,text
  cond1,,"As a new ZenCover customer, a welcome discount has been applied..."
  cond2,,"Your plan includes Accidental Damage cover from day one..."

  Priya (or Sam, if it's technical) fills the blank when cell in plain dot-notation (the condition language uses present / absent, not "!= null"):

  cond1,"quoteNumber present","As a new ZenCover customer..."
  cond2,"state == ""CA""","Your plan includes Accidental Damage cover..."

  The lesson: double brackets = "maybe show this." She writes the text in Word; she fills the when in the one CSV that comes back. That same CSV carries every kind of conditional — binary lines, repeat-this-section blocks, and the pick-one-of-many variants below.
  
  ▎ A conditional can even contain its own values: [[A loyalty discount of {discountAmount} applies (type: {discountType}).]] — curly braces nest happily inside double brackets.
  
  ---
  Marker 3 — The named section: "repeat this for every item"
  
  ZenCover policies can cover many gadgets. Priya wants one table row per insured item. She builds a normal Word table with a header row, then wraps the data row in matching tags
  named after the thing being listed:
  
  ┌────────────────┬────────────────┬─────────────────┬────────────────┐
  │   Item Type    │ Purchase Date  │      Price      │     Serial     │
  ├────────────────┼────────────────┼─────────────────┼────────────────┤
  │ [Item]         │                │                 │                │
  ├────────────────┼────────────────┼─────────────────┼────────────────┤
  │ {itemTypeCode} │ {purchaseDate} │ {purchasePrice} │ {serialNumber} │
  ├────────────────┼────────────────┼─────────────────┼────────────────┤
  │ [/Item]        │                │                 │                │
  └────────────────┴────────────────┴─────────────────┴────────────────┘
  
  [Item] … [/Item] is an open/close pair. The header stays put; the row between the tags repeats once per gadget. (The name Item has to match what ZenCover calls its item list — Sam
  confirms that part.)

  The lesson: [Name] … [/Name] = "loop this region for each one." Header once, body per item.
  
  ▎ Advanced flourish for the demo: you can put a loop inside a conditional — [[Here are your free gifts: [Item]…[/Item]]] — and the whole gift section (list and all) appears only 
  ▎ when the condition holds.   

  ---
  Marker 4 — The dollar-token: "pick one of several versions"
  
  ZenCover operates in many states, and each state needs a different legal disclosure. Priya does not paste 50 paragraphs. She writes a single placeholder:

  ▎ Applicable Disclosure:
  ▎ [[$disclosureClause]]

  The $ inside double brackets means: "this is a variant slot — I'll supply the versions in a spreadsheet." Those versions go in the same .variants.csv the pipeline already handed her:
  
  placeholder,when,text
  disclosureClause,"discountType == ""FLAT""","Policy {policyNumber}: a flat discount of {discountAmount} applies."
  disclosureClause,"discountType == ""PERCENT""","Policy {policyNumber}: a percentage discount applies."
  disclosureClause,,"Policy {policyNumber}: no discount applies."

  Each row is a version: a when rule and the text to show. The blank when is the default — the fallback when nothing else matches. Notice the text can hold its own {curly} values
  too.

  The lesson: [[$token]] = "one of many versions." One marker in Word; the versions go in the CSV.
  
  ---
  How the demo flows (the part you say out loud)

  Here's the arc to narrate when you present it:
  
  1. "I wrote a normal letter." Show the Word doc with the four markers — curly braces, double brackets, an [Item] loop, one [[$token]].
  2. "I hand it to the pipeline once." Run intake:
  python3 -m velocity_converter.agent --yes "RUN_PIPELINE intake input=workspace/inbox/ZenCoverWelcomeLetter(quote).docx registry=registry/path-registry.yaml
  output=workspace/output"
  3. "It hands me back two fill-in-the-blank files" — both in workspace/action-needed/:
    - …path-review.md → confirm each field name maps to the right path.
    - …variants.csv → ONE file for ALL conditional text: write the when for each double-bracket block (its text is pre-filled), and the versions for each [[$token]].
  4. "I fill those in like a form — no code." Confirm paths, write conditions, fill variant rows.
  5. "The pipeline turns my letter into a self-filling template." Run Leg -1 apply → Leg 0 → Leg 2+3+4, and out comes the production .final.vm plus the Java plugin.

  The moral Priya learned: write the document for a human; leave four kinds of markers; answer the forms that come back. That's the whole customer job.
  
  ---
  Cheat sheet (hand this to whoever fills the doc)

  ┌────────────────────────────┬─────────────────────────────────────────────┬────────────────────────────────────┐
  │           Marker           │                    Means                    │              Example               │
  ├────────────────────────────┼─────────────────────────────────────────────┼────────────────────────────────────┤
  │ {field}                    │ drop a real value in                        │ Dear {firstName},                  │
  ├────────────────────────────┼─────────────────────────────────────────────┼────────────────────────────────────┤
  │ {$field} {+field} {*field} │ optional / one-or-more / zero-or-more       │ {$middleName}                      │
  ├────────────────────────────┼─────────────────────────────────────────────┼────────────────────────────────────┤
  │ [[ text ]]                 │ show only when a condition holds            │ [[New customer discount applied.]] │
  ├────────────────────────────┼─────────────────────────────────────────────┼────────────────────────────────────┤
  │ [Name]…[/Name]             │ repeat for each one in a list               │ [Item]…[/Item] table row           │
  ├────────────────────────────┼─────────────────────────────────────────────┼────────────────────────────────────┤
  │ [[$token]]                 │ pick one of several versions (fill the CSV) │ [[$disclosureClause]]              │
  └────────────────────────────┴─────────────────────────────────────────────┴────────────────────────────────────┘
  
  ---
  Want me to actually run this end to end on a sample doc so the demo has real output files to show? I can spin up a ZenCoverWelcomeLetter walkthrough and produce the two fill-in
  files live.