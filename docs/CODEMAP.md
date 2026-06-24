# Code Map — `velocity_converter/`

**Purpose:** a navigation index so an agent can read the *right* 150 lines instead of a
1,000–2,000-line module. Find the function below, then open that file at the line number
(`file_path:line` is clickable). For *how a leg works internally* (control-flow diagrams),
see [leg-internals.md](leg-internals.md). For the end-to-end artifact flow, see
[pipeline-dataflow.md](pipeline-dataflow.md).

Line numbers reflect the state of the tree when this map was written — they drift as code
changes. If a number looks off, `grep -n 'def <name>'` the file; treat this as a "which
file + roughly where" index, not a source of truth.

---

## Pipeline legs

### Leg -1 — `legminus1_resolve_paths.py` (758 lines) — bare `{leaf}` → accessor path
Registry-only resolution; emits a customer-fill `.path-review.csv` (field / suggested /
final) + a canonical `.path-review.md` before Leg 0.

| Symbol | Line | Role |
|---|---|---|
| `collect_placeholders()` | 110 | Scan doc text for `{leaf}` placeholders + loop scope |
| `_loop_spans()` / `_loop_for_position()` | 90 / 103 | Map `[Item]…[/Item]` spans → which loop a position is in |
| `resolve_fields()` | 141 | Match each leaf against registry candidates |
| `run_suggest()` | 378 | **Suggest mode** entry — writes CSV + review + map + changes |
| `write_path_review/map/changes()` | 167 / 301 / 329 | The canonical artifacts |
| `write_path_review_csv()` | 236 | Customer-fill CSV view (field / suggested / final) |
| `read_path_review_csv()` / `_patch_review_finals()` | 258 / 277 | Fold the filled CSV's `final` column back onto the md |
| `parse_path_review()` | 464 | Parse the (folded) `Final:` lines back out |
| `run_apply()` | 570 | **Apply mode** entry (md) — final map + resolved doc copy |
| `run_apply_csv()` | 662 | **Apply mode** entry (csv) — fold CSV → md, then `run_apply()` |
| `_rewrite_docx()` / `write_resolved_doc()` | 503 / 537 | Bake accessors into a `.resolved.docx` |
| `main()` | 701 | CLI: `--parse-path-review[-csv]` vs suggest |

### Leg 0 — `leg0_ingest.py` — `.docx`/`.pdf` → HTML + mapping + variants CSV
| Symbol | Line | Role |
|---|---|---|
| `convert_docx()` / `convert_pdf()` | 74 / 137 | Document → raw HTML |
| `extract_fields()` | 225 | `{field}` + occurrence symbols → token list |
| `annotate_fields()` | 359 | `{field}` → `$TBD_field` in HTML |
| `extract_conditionals()` | 432 | `[[…]]` blocks (incl. `[[$variant]]`), nesting, block IDs |
| `annotate_conditionals()` | 518 | Conditional blocks → `$doc.condN` |
| `extract_loops()` | 596 | `[Name]…[/Name]` → `#foreach` scaffold; moves fields into loop |
| `write_leg2_mapping()` | 793 | Emit `.mapping.yaml` (Leg 2 contract) |
| `write_variants_csv()` | 835 | Single human-fill `.variants.csv` for ALL conditional text (binary / template / N-way) |
| `write_conditional_blocks()` | 899 | Machine sidecar `.conditional-blocks.yaml` (per-block metadata the CSV can't carry) |
| `load_conditional_blocks()` | 925 | Read the sidecar back at parse time |
| `parse_conditional_form()` | 943 | **legacy `--parse-conditional-form` mode** — in-flight form → blocks |
| `parse_variants_csv_to_blocks()` | 1050 | **`--parse-variants-csv` mode** — filled CSV + sidecar → blocks |
| `write_conditional_registry()` | 1129 | Emit `.conditional-registry.yaml` |
| `main()` | 1256 | CLI: default ingest vs `--parse-variants-csv` (legacy `--parse-conditional-form`) |

### Leg 1 — `convert.py` (1358 lines) — HTML mockup → `.vm` + `.mapping.yaml`
| Symbol | Line | Role |
|---|---|---|
| `convert()` | 1166 | Core pipeline (called by `main()`) |
| `_collect_mustache_tokens()` | 435 | Find `[name]`/`[/name]` loop markers in DOM |
| `_find_innermost_pair()` / `_process_mustache_pair()` | 452 / 477 | Convert loops innermost-first → `#foreach` |
| `auto_detect_loops()` | 653 | Optional: infer loops from sibling repetition |
| `rewrite_vars_in_subtree()` | 368 | `{{var}}` → `$TBD_var` outside loops |
| `_record_var()` | 300 | Label a var via nearest label/heading/column header |
| `nearest_label/heading/column_header()` | 131 / 143 / 148 | Label-inference heuristics |
| `wrap_conditionals()` | 689 | Wrap `$TBD_*`-bearing blocks in `#if` guards |
| `extract_conditional_blocks()` | 1065 | `[prose]` → `$doc.condN`, link nesting |
| `build_sanity_report()` | 788 | Suspicious-token / unlabeled-var report |
| `dump_yaml()` | 1035 | Serialize `Mapping` → YAML |
| `load_iterables()` / `_match_loop_hint()` | 198 / 254 | Registry iterable lookup for loop hints |
| `main()` | 1248 | CLI entry |

### Leg 2 — `leg2_fill_mapping.py` (1674 lines) — suggest accessor paths, grade confidence
| Symbol | Line | Role |
|---|---|---|
| `annotate_mapping()` | 1284 | **Main enrichment loop** (per variable / loop / loop-field) |
| `build_registry_index()` | 252 | Index registry by field / display name |
| `parse_rendering_roots()` | 538 | Extract root_ids + product from filename brackets |
| `match_token()` | 450 | Strict `Entity.field` lookup (exact / ci / terminology) |
| `derive_variable_candidate()` | 604 | Root-independent candidate for one token |
| `_quote_accessor_candidate()` | 379 | Direct `quote.data.*` match (no reprefix) |
| `check_scope()` | 321 | Validate `#foreach` scope requirement |
| `variable_verdict_for_root()` | 877 | Per-root JAR probe + grade |
| `suggest_loop_root()` / `loop_root_verdict_for_root()` | 988 / 1210 | Iterable → list velocity + verdict |
| `suggest_loop_field()` / `_match_coverage_field()` | 1109 / 1048 | Loop field → exposure/coverage path |
| `loop_field_verdict_for_root()` | 1240 | Per-root loop field verdict (elem-type cache) |
| `_datafetcher_verdict()` | 744 | DataFetcher lifecycle gate + probe |
| `apply_feature_gate()` / `feature_gate_violation()` | 850 / 824 | Demote feature-gated paths |
| `confidence_grade()` | 589 | high = exact + verified; else low/none |
| `load_schema_index()` / `load_terminology()` | 480 / 1407 | Optional inputs |
| `main()` | 1444 | CLI entry |

`leg2_review_writer.py` (389 lines) — `_write_review_md()` (59) builds `.review.md` from verdicts.

### Leg 3 — `leg3_substitute.py` (804 lines) — `.mapping.yaml` → `.final.vm`
| Symbol | Line | Role |
|---|---|---|
| `process_vm()` | 338 | Strip `#if($TBD_*)` guards, substitute tokens, resolve foreach |
| `build_substitution_map()` | 265 | `$TBD_*` → data_source path |
| `build_foreach_map()` | 292 | Loop placeholder → `#foreach` directive |
| `build_cond_map()` | 102 | `$doc.condN` → `${data.condN}` |
| `apply_cond_substitutions()` | 115 | Innermost-first conditional-block resolution |
| `split_delegated()` | 175 | Separate plugin-owned vs template-resolved tokens |
| `_flatten_to_primary_root()` | 230 | Schema 2.0 per-root verdicts → flat fields |
| `write_report()` | 451 | `.leg3-report.md` |
| `main()` | 691 | CLI entry |

### Leg 4 — `leg4_generate_plugin.py` (2092 lines) — `.mapping.yaml` → `SnapshotPlugin.java`
| Symbol | Line | Role |
|---|---|---|
| `_process_form()` | 1729 | **Per-form orchestrator** (called once per `--suggested`) |
| `render_java()` | 1383 | Assemble the full `.java` (fresh mode) |
| `_flatten_to_segment_root()` | 582 | Schema 2.0 → segment root |
| `_collect_datafetcher_calls()` | 975 | Extract DataFetcher vars per scope |
| `load_conditional_registry()` | 1049 | Load + validate `.conditional-registry.yaml` |
| `_build_cond_field_lookup()` | 205 | Variable name → Java wiring |
| `_augment_field_lookup_for_variants()` | 320 | Add field tokens from variant text |
| `_analyse_cond_fields()` | 400 | Classify unresolved (hard-fail) / unsupported / mixed-scope |
| `render_conditional_puts()` | 1324 | Binary + variant `if/else-if/else` chains (binary routes through the variant generator) |
| `_render_variant_puts()` | 1209 | N-way + binary variant chain (first match wins) |
| `_render_template_put()` | 1269 | Template (`render: template`) block → Boolean from `when` AST (or legacy `conditions[]`) |
| `condition_to_java()` | *(condition_dsl.py:546)* | Condition AST → Java boolean expr |
| `render_occurrence_guards()` | 482 | Null/empty guards for required / one_or_more |
| `_parse_existing_plugin_keys()` / `parse_plugin_keys()` | 742 / 749 | **Additive mode** — read existing `.java` |
| `_diff_keys()` / `_append_to_plugin()` | 873 / 898 | Additive merge + conditional-id renumber |
| `validate_path()` | *(sdk_introspect.py:228)* | javap-walk a path against the root |
| `compile_check()` | 1666 | `javac` against customer + datamodel JARs |
| `write_report()` | 1428 | `.plugin-report.md` |
| `main()` | 1691 | CLI entry (multi-form loop) |

---

## Orchestration & entry points

### `agent.py` (593 lines) — `RUN_PIPELINE` orchestrator
| Symbol | Line | Role |
|---|---|---|
| `parse_invocation()` | 76 | Parse `RUN_PIPELINE leg…+leg… input=… registry=…` |
| `run()` | 148 | Dispatch the requested leg chain |
| `_derive_leg2_paths()` / `_derive_leg3_paths()` | 124 / 110 | Infer artifact paths between legs |
| `guided_mode()` | 468 | Interactive prompt flow |
| `main()` | 570 | CLI entry (`--yes` to skip confirm) |

### `agent_tools.py` (890 lines) — leg runners + preflight (shared by agent.py & MCP)
| Symbol | Line | Role |
|---|---|---|
| `run_legminus1()` / `run_legminus1_apply()` | 401 / 438 | Leg -1 |
| `run_leg0()` … `run_leg4()` | 366 / 467 / 539 / 505 / 612 | Per-leg runners |
| `validate_inputs()` | 65 | Preflight validation |
| `build_preflight()` | 293 | Preflight summary table |
| `_predict_writes()` | 189 | Predict output files before running |
| `_warn_missing_cond_registry()` | 581 | The mandatory conditional-registry preflight |
| `build_velocity_lookup()` / `build_velocity_meta_lookup()` | 731 / 782 | Velocity-path lookups for downstream legs |
| `run_list_paths()` | 880 | Path catalog |

### `mcp_server.py` (375 lines) — Claude Code MCP tool surface
Tool fns: `convert_html_to_velocity()` (58), `extract_velocity_tokens()` (116),
`suggest_velocity_paths()` (153), `write_final_template()` (199), `ingest_document()` (236),
`generate_snapshot_plugin()` (281), `list_velocity_paths()` (336). `main()` (370).

---

## Registry & SDK introspection

### `extract_paths.py` (798 lines) — Socotra config → `path-registry.yaml`
| Symbol | Line | Role |
|---|---|---|
| `build_registry()` | 594 | Top-level registry build |
| `extract_exposure()` / `extract_coverage()` | 269 / 209 | Per-exposure / per-coverage fields |
| `extract_data_fields()` | 154 | Custom data fields |
| `extract_policy_charges()` | 526 | Policy-level charges |
| `detect_features()` | 383 | Feature-support flags |
| `_tag_feature_gates()` | 561 | Tag gated entries |
| `parse_quantified_token()` / `quantifier_fields()` | 90 / 103 | Occurrence quantifiers |
| `main()` | 734 | CLI entry |

> **Caution:** the on-disk `registry/path-registry.yaml` is ahead of this extractor; do not
> blind-regenerate (drops `quote_system`). See repo memory `registry-generator-staleness`.

### `registry_match.py` (238 lines) — leaf-name matching (used by Leg -1)
`build_candidate_index()` (56) — flatten registry to candidates; `match_leaf()` (168) — match one leaf, with loop scope.

### `sdk_introspect.py` (472 lines) — javap-based JAR introspection
`validate_path()` (228) — walk a path against a root type; `classify_path()` (419) — verified/sibling/missing;
`build_schema_index()` (337) — precompute schema; `datafetcher_return_type()` (175); `roots_for_product()` (272).

### `list_paths.py` (275 lines) — render the human path catalog
`render_catalog()` (116) — grouped Markdown; `main()` (252).

### `build_schema_index.py` (91 lines) — write `sdk-schema-index.yaml`. `main()` (34).

---

## Contracts & condition DSL

### `models.py` (502 lines) — Pydantic contracts for every artifact
Mapping side: `VariableContext` (57), `Candidate` (70), `Verdict` (88), `MappingVariable` (116),
`MappingLoop` (130), `MappingDoc` (147), `SuggestedDoc` (158). Registry side: `RegistryEntry` (196),
`IterableEntry` (236), `CoverageEntry` (249), `ExposureEntry` (264), `PathRegistry` (293).
Conditionals: `Variant` (315), `ConditionalBlock` (328), `ConditionalRegistry` (398), `block_key()` (386).
Helpers: `validate_contract()` (446), `load_contract()` (474), `check_contract_version()` (411).

### `condition_dsl.py` (788 lines) — variant `when:` condition language → Java
| Symbol | Line | Role |
|---|---|---|
| `parse_condition()` | 156 | Text → `ConditionAST` |
| `validate_condition()` | 347 | Validate against registry index (scope, types) |
| `condition_to_java()` | 546 | AST → null-safe Java boolean expr |
| `parse_variants_csv()` | 694 | `.variants.csv` → `VariantParseResult` |
| `build_registry_index()` | 302 | Index for leaf → accessor resolution |
| `_resolve_path()` | 637 | Bare leaf → full accessor |
| `ast_to_dict()` / `ast_from_dict()` | 588 / 603 | Serialize AST in registry |

---

## State & misc

| Module | Lines | Key symbols |
|---|---|---|
| `suggester_state.py` | 125 | `evaluate_registry_config_gate()` (37) — registry/config staleness gate |
| `socotra_config_fingerprint.py` | 62 | `compute_source_config_sha256()` (50) |
| `workspace.py` | 86 | `action_needed_dir()` (50), `action_needed_file()` (62) — routes human-fill files |
| `render_preview.py` | 282 | `render_template()` (126) — live-tenant ad-hoc render; `load_env()` (69) |
