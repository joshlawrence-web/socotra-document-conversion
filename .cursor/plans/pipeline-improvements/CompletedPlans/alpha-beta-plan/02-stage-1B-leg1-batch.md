# Stage 1B — Agent B: Leg 1 Batch Flag

**Runs in parallel with:** [Stage 1A](01-stage-1A-leg2-run-modes.md)
**Hands off to:** [Stage 2 — Validation](03-stage-2-validation.md) (after Stage 1A also finishes)

---

## Scope

Two files only:

```
.cursor/skills/html-to-velocity/scripts/convert.py
.cursor/skills/html-to-velocity/SKILL.md
```

No other files are touched by this agent.

---

## Change 1 — `convert.py`: add `--batch` flag

**File:** `.cursor/skills/html-to-velocity/scripts/convert.py`

### What to add

The script currently has an `argparse` parser that accepts a single positional `input` argument. Add a `--batch` flag that makes the positional argument optional and instead accepts a list of file paths.

The resulting CLI interface:

```bash
# existing (unchanged)
python3 convert.py samples/input/claim-form.html --output-dir samples/output/claim-form

# new: batch mode — multiple files, output dirs derived automatically
python3 convert.py --batch samples/input/claim-form.html samples/input/renewal-notice.html \
    --output-dir samples/output

# new: batch mode — glob expansion handled by the shell
python3 convert.py --batch samples/input/*.html --output-dir samples/output
```

### Behavioral contract for `--batch`

- When `--batch` is given, the positional `input` argument is ignored.
- Each file in the batch list is processed in order.
- `--output-dir` is treated as a **parent** directory. For each file `<stem>.html` the script writes to `<output-dir>/<stem>/` — identical to the single-file behavior.
- `path-registry.yaml` (if `--registry` is given or auto-located) is loaded **once** before the loop and reused for all files.
- Per-file output: same three files as single-file mode (`.vm`, `.mapping.yaml`, `README.md`).
- Terminal output: one summary line per file, then a combined count at the end:

```
✓ claim-form       → samples/output/claim-form/  (12 vars, 3 loops)
✓ renewal-notice   → samples/output/renewal-notice/  (8 vars, 1 loop)
Batch complete: 2 files, 20 vars, 4 loops
```

### Implementation sketch

```python
# In the argparse setup section:
parser.add_argument(
    "input",
    nargs="?",
    help="Path to the HTML input file (omit when using --batch)"
)
parser.add_argument(
    "--batch",
    nargs="+",
    metavar="FILE",
    help="Process multiple HTML files in one pass. --output-dir is treated as parent dir."
)

# In main():
if args.batch:
    registry = load_registry(args.registry)   # load once
    results = []
    for html_path in args.batch:
        result = convert_file(html_path, args, registry=registry)
        results.append(result)
    print_batch_summary(results)
elif args.input:
    registry = load_registry(args.registry)
    convert_file(args.input, args, registry=registry)
else:
    parser.error("Provide an input file or use --batch.")
```

The existing `convert_file()` logic (or equivalent current structure) is refactored minimally — the only change is accepting a pre-loaded `registry` argument so it doesn't reload the file on each iteration.

---

## Change 2 — `SKILL.md`: document `--batch` in the "How to run" section

**File:** `.cursor/skills/html-to-velocity/SKILL.md`

**Location:** The `## How to run` section, under `### CLI flags`.

Add one entry to the flags table:

```markdown
- `--batch <file1> [file2 ...]` — process multiple HTML files in a single invocation.
  `--output-dir` is treated as the parent directory; each file writes to `<output-dir>/<stem>/`.
  The registry file (if provided) is loaded once and shared across all inputs.
  Incompatible with the single-file positional argument — use one or the other.
```

Also add a batch example under `## How to run`:

```markdown
### Batch example (all files in a folder)

```bash
python3 .cursor/skills/html-to-velocity/scripts/convert.py \
    --batch samples/input/*.html \
    --output-dir samples/output \
    --registry path-registry.yaml
```
```

---

## Acceptance criteria for Stage 1B

- [ ] `convert.py` accepts `--batch <file1> [file2 ...]` without error
- [ ] Running `--batch samples/input/*.html --output-dir samples/output` produces one `<stem>/` subfolder per input file under `samples/output/`
- [ ] Running `--batch` without `--output-dir` falls back to writing next to each input file (existing default behavior)
- [ ] Single-file invocation (no `--batch`) is fully backward-compatible — no behavior change
- [ ] `SKILL.md` flags list includes `--batch` with correct description
- [ ] Registry is loaded once in batch mode (verifiable via a single file-read log line in verbose output or by inspection)
