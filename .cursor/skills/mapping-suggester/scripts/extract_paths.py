#!/usr/bin/env python3
"""
extract_paths.py  —  Socotra Config Path Extractor
Leg 2a of the HTML → Velocity template pipeline.

Walks a socotra-config/ directory and emits a path-registry.yaml
containing every valid Velocity access path derived from the product config,
together with the Socotra quantifier metadata (cardinality / iterability)
and a per-entry ``requires_scope`` list that captures which ``#foreach``
loops must be active for the path to be valid.

Velocity path conventions (Socotra dot-notation):
  $data.productName                          top-level system field
  $data.data.fieldName                       policy custom data field
  $data.account.data.name                    account data field
  $data.vehicles                             exposure list (foreach target)
  $vehicle.data.vin                          exposure custom data field
  $vehicle.Coll.data.deductible              coverage custom data field
  $vehicle.Coll.charges.premium.amount       coverage charge amount
  $data.charges.GoodCustomerDiscount.amount  policy-level charge amount

Quantifier suffixes on ``contents`` tokens or data-extension ``type`` values:
  ""   — exactly one required         (not iterable)
  "!"  — exactly one, auto-created    (not iterable; always present)
  "?"  — zero or one                  (not iterable; needs #if guard)
  "+"  — one or more                  (iterable; foreach required)
  "*"  — any number                   (iterable; foreach required)

Usage:
    python3 extract_paths.py --config-dir ./socotra-config [--output path-registry.yaml]

Output: when ``--output`` is omitted, writes ``<parent-of-config-dir>/registry/path-registry.yaml``
(creates ``registry/``). Pass ``--output`` explicitly for conformance fixtures or ad-hoc paths.
"""

import argparse
import copy
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _compute_source_config_sha256(config_dir: Path) -> str:
    """Load ``scripts/socotra_config_fingerprint.py`` from the repo root (any ancestor)."""
    here = Path(__file__).resolve()
    for anc in here.parents:
        mod_path = anc / "scripts" / "socotra_config_fingerprint.py"
        if not mod_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("socotra_config_fingerprint", mod_path)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "compute_source_config_sha256", None)
        if callable(fn):
            return str(fn(config_dir))
    raise RuntimeError(
        "Cannot locate scripts/socotra_config_fingerprint.py above {}".format(here)
    )

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required.  Run: pip install pyyaml --break-system-packages")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Quantifier parsing — single source of truth
# ---------------------------------------------------------------------------

QUANTIFIER_SUFFIXES = ("!", "?", "+", "*")

QUANTIFIER_CARDINALITY = {
    "":  "exactly_one",
    "!": "exactly_one_auto",
    "?": "zero_or_one",
    "+": "one_or_more",
    "*": "any",
}

ITERABLE_QUANTIFIERS = {"+", "*"}

# Primitive base types in Socotra data-extension fields. A field whose
# ``type`` strips to one of these is a scalar (or a scalar array when
# combined with ``+`` / ``*``). Anything else is treated as a reference to
# a custom data type.
PRIMITIVE_TYPES = {
    "string", "text", "int", "number", "decimal", "boolean",
    "date", "datetime", "binary",
}


def parse_quantified_token(token: str) -> tuple[str, str]:
    """
    Split a contents-array token like 'Vehicle+', 'MedPay?', 'Coll' or
    'collision!' into (name, quantifier).
    Returns ('', '') for an empty token.
    """
    if not token:
        return ("", "")
    if token[-1] in QUANTIFIER_SUFFIXES:
        return (token[:-1], token[-1])
    return (token, "")


def quantifier_fields(quantifier: str) -> dict:
    """Uniform dict of ``quantifier`` / ``cardinality`` / ``iterable`` keys."""
    return {
        "quantifier":  quantifier,
        "cardinality": QUANTIFIER_CARDINALITY[quantifier],
        "iterable":    quantifier in ITERABLE_QUANTIFIERS,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def exposure_list_key(exposure_name: str) -> str:
    """
    Derive the Velocity list key for an exposure.
    Socotra lowercases the first character and pluralises with 's'.
    e.g. Vehicle -> vehicles, Driver -> drivers
    """
    name = exposure_name[0].lower() + exposure_name[1:]
    if not name.endswith("s"):
        name += "s"
    return name


def iterator_var(exposure_name: str) -> str:
    """
    Derive the foreach iterator variable name from the exposure name.
    e.g. Vehicle -> vehicle, Driver -> driver
    """
    return exposure_name[0].lower() + exposure_name[1:]


def make_scope_entry(iterator: str, list_velocity: str) -> dict:
    """Build a single scope step (one ``#foreach``) for ``requires_scope``."""
    iter_ref = iterator if iterator.startswith("$") else "${}".format(iterator)
    return {
        "iterator": iter_ref,
        "foreach":  "#foreach ({} in {})".format(iter_ref, list_velocity),
    }


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def extract_data_fields(data_map: dict, dot_prefix: str, category: str,
                        scope: list | None = None) -> list:
    """
    Turn a config 'data' block into path entries using dot notation.

    dot_prefix : Velocity prefix up to (and including) the .data segment,
                 e.g. '$data.data' for policy fields, '$vehicle.data' for
                 exposure fields, '$vehicle.Coll.data' for coverage fields.
    scope      : list of scope steps (outermost first) required to access
                 this prefix. Copied onto every emitted entry as
                 ``requires_scope``.

    Every emitted entry carries quantifier / cardinality / iterable keys
    derived from the raw ``type`` string. Primitive array types
    (``string+``, ``int*``, ``binary?`` …) are flattened into a single
    scalar-array entry; references to custom data types are *not* expanded
    recursively (Socotra config doesn't lean on those in the test
    product — add that pass when a real sample needs it, and wire the
    extra foreach into ``requires_scope`` at the call site).
    """
    scope = list(scope or [])
    entries = []
    for field_name, field_def in data_map.items():
        display_name = field_def.get("displayName", field_name)
        raw_type     = field_def.get("type", "string")
        options      = field_def.get("options")

        base_type, type_q = parse_quantified_token(raw_type)

        velocity = "{}.{}".format(dot_prefix, field_name)

        entry = {
            "field":          field_name,
            "display_name":   display_name,
            "type":           raw_type,
            "base_type":      base_type,
            **quantifier_fields(type_q),
            "category":       category,
            "velocity":       velocity,
            "requires_scope": copy.deepcopy(scope),
        }

        # Flag references to non-primitive (custom) data types so the
        # consumer can tell a scalar/scalar-array apart from an embedded
        # object reference that may need its own foreach. Full recursive
        # expansion is intentionally deferred — see docstring.
        if base_type and base_type not in PRIMITIVE_TYPES:
            entry["custom_type_ref"] = base_type

        if options:
            entry["options"] = options
        entries.append(entry)
    return entries


def extract_coverage(coverage_name: str, config_dir: Path, iterator: str,
                     scope: list) -> dict | None:
    """
    Build a coverage block for a given exposure iterator.
    e.g. iterator='vehicle', coverage_name='Coll'
    -> velocity prefix: $vehicle.Coll

    ``scope`` is the parent exposure's ``requires_scope`` (already includes
    its own foreach). Coverage-scoped fields and charges inherit it
    verbatim — coverages themselves aren't a foreach target, they're
    conditional accessors on the exposure iterator.
    """
    config_path = config_dir / "coverages" / coverage_name / "config.json"
    if not config_path.exists():
        return None

    cfg          = load_json(config_path)
    display_name = cfg.get("displayName", coverage_name)
    data_map     = cfg.get("data", {})
    charge_names = cfg.get("charges", [])

    cov_velocity    = "${}.{}".format(iterator, coverage_name)
    cov_data_prefix = "${}.{}.data".format(iterator, coverage_name)

    fields = extract_data_fields(
        data_map,
        cov_data_prefix,
        category="coverage_data",
        scope=scope,
    )

    charges = []
    for charge_name in charge_names:
        charge_path = config_dir / "charges" / charge_name / "config.json"
        charge_cfg  = load_json(charge_path) if charge_path.exists() else {}
        cat         = charge_cfg.get("category", "unknown")

        charges.append({
            "name":            charge_name,
            "category":        cat,
            "velocity_amount": "${}.{}.charges.{}.amount".format(iterator, coverage_name, charge_name),
            "velocity_object": "${}.{}.charges.{}".format(iterator, coverage_name, charge_name),
            "requires_scope":  copy.deepcopy(scope),
        })

    block = {
        "name":           coverage_name,
        "display_name":   display_name,
        "velocity":       cov_velocity,
        "note":           "#if({}) before accessing — coverage may not be present on every exposure".format(cov_velocity),
        "requires_scope": copy.deepcopy(scope),
    }
    if fields:
        block["fields"] = fields
    if charges:
        block["charges"] = charges

    return block


def extract_exposure(exposure_name: str, config_dir: Path,
                     outer_scope: list | None = None) -> dict | None:
    """
    Build a full exposure block: list path, iterator, data fields, coverages.

    ``outer_scope`` supports future nested iterables (e.g. Driver+ embedded
    as a data-extension on Vehicle). At the top level it's empty, meaning
    the exposure's own foreach is the only required scope.
    """
    config_path = config_dir / "exposures" / exposure_name / "config.json"
    if not config_path.exists():
        return None

    cfg          = load_json(config_path)
    display_name = cfg.get("displayName", exposure_name)
    data_map     = cfg.get("data", {})
    iterator     = iterator_var(exposure_name)
    list_key     = exposure_list_key(exposure_name)

    list_velocity = "$data.{}".format(list_key)

    # Scope required to reference anything under an exposure instance =
    # outer scopes (if any) plus this exposure's own foreach.
    own_step    = make_scope_entry(iterator, list_velocity)
    self_scope  = list(outer_scope or []) + [own_step]

    fields = extract_data_fields(
        data_map,
        "${}.data".format(iterator),
        category="exposure_data",
        scope=self_scope,
    )

    system_fields = [
        {
            "field":          "locator",
            "display_name":   "Exposure locator (system)",
            "type":           "string",
            "base_type":      "string",
            **quantifier_fields(""),
            "category":       "exposure_system",
            "velocity":       "${}.locator".format(iterator),
            "requires_scope": copy.deepcopy(self_scope),
        },
        {
            "field":          "name",
            "display_name":   "Exposure type name (system)",
            "type":           "string",
            "base_type":      "string",
            **quantifier_fields(""),
            "category":       "exposure_system",
            "velocity":       "${}.name".format(iterator),
            "requires_scope": copy.deepcopy(self_scope),
        },
    ]

    raw_contents = cfg.get("contents", [])
    coverage_tokens = [parse_quantified_token(c) for c in raw_contents]

    coverages = []
    for cov_name, cov_q in coverage_tokens:
        cov_block = extract_coverage(cov_name, config_dir, iterator, self_scope)
        if cov_block:
            cov_block.update(quantifier_fields(cov_q))
            coverages.append(cov_block)

    raw_exposure_contents_for_note = (
        # preserved for downstream tooling that wants the raw list
        raw_contents
    )

    block = {
        "name":           exposure_name,
        "display_name":   display_name,
        "list_velocity":  list_velocity,
        "iterator":       iterator,
        "foreach":        "#foreach (${} in {})".format(iterator, list_velocity),
        "raw_contents":   raw_exposure_contents_for_note,
        "system_fields":  system_fields,
        "fields":         fields,
    }
    if coverages:
        block["coverages"] = coverages

    return block


# ---------------------------------------------------------------------------
# Feature-support structural scan
# ---------------------------------------------------------------------------

def _iter_subdir_configs(parent: Path) -> list:
    """
    Yield (subdir_name, parsed_config) pairs for every ``<sub>/config.json``
    beneath ``parent``. Malformed JSON is silently skipped — the feature
    scan is a best-effort structural probe, not a validator.
    """
    out = []
    if not parent.exists():
        return out
    for d in parent.iterdir():
        if not d.is_dir():
            continue
        cfg_path = d / "config.json"
        if not cfg_path.exists():
            continue
        try:
            cfg = load_json(cfg_path)
        except Exception:
            continue
        out.append((d.name, cfg))
    return out


def detect_features(config_dir: Path, product_cfg: dict) -> dict:
    """
    Structural scan of ``config_dir`` that produces the ``feature_support``
    block emitted into ``path-registry.yaml``.

    Every flag is derived from a live inspection of config contents — never
    from file presence alone. ``custom_data_types`` is true only when a
    ``customDataTypes/<Name>/config.json`` actually parses; ``coverage_terms``
    is true only when some coverage config carries a non-empty
    ``coverageTerms: [...]`` array. An empty directory is not a feature.

    Flag vocabulary (PIPELINE_EVOLUTION_PLAN.md §3.2 and CONFIG_COVERAGE.md
    are the authoritative references):

    - nested_iterables        — data-extension field whose type is ``<CDT>+``
                                or ``<CDT>*``.
    - custom_data_types       — ``customDataTypes/<Name>/`` parses.
    - recursive_cdts          — a CDT references itself in its ``data`` map.
    - jurisdictional_scopes   — any coverage / product carries a
                                ``qualification`` / ``appliesTo`` /
                                ``exclusive`` key.
    - peril_based             — ``perils/`` exists with subdirs.
    - multi_product           — ``products/`` has more than one subdir.
    - coverage_terms          — any coverage has a non-empty
                                ``coverageTerms`` array.
    - default_option_prefix   — any coverage-term option starts with ``*``.
    - auto_elements           — any ``!`` suffix on a ``contents`` token or
                                a data-extension ``type``.
    - array_data_extensions   — data-extension ``type`` ending in ``+`` or
                                ``*`` (primitive or CDT).
    """
    flags = {
        "nested_iterables":        False,
        "custom_data_types":       False,
        "recursive_cdts":          False,
        "jurisdictional_scopes":   False,
        "peril_based":             False,
        "multi_product":           False,
        "coverage_terms":          False,
        "default_option_prefix":   False,
        "auto_elements":           False,
        "array_data_extensions":   False,
    }

    products_dir = config_dir / "products"
    if products_dir.exists():
        product_subdirs = [d for d in products_dir.iterdir() if d.is_dir()]
        flags["multi_product"] = len(product_subdirs) > 1

    perils_dir = config_dir / "perils"
    if perils_dir.exists() and any(d.is_dir() for d in perils_dir.iterdir()):
        flags["peril_based"] = True

    cdt_entries = _iter_subdir_configs(config_dir / "customDataTypes")
    if cdt_entries:
        flags["custom_data_types"] = True
        for cdt_name, cdt_cfg in cdt_entries:
            data_map = cdt_cfg.get("data") or {}
            if not isinstance(data_map, dict):
                continue
            for _, field_def in data_map.items():
                if not isinstance(field_def, dict):
                    continue
                raw_type = field_def.get("type")
                if not isinstance(raw_type, str):
                    continue
                base, _q = parse_quantified_token(raw_type)
                if base == cdt_name:
                    flags["recursive_cdts"] = True
                    break
            if flags["recursive_cdts"]:
                break

    coverage_entries = _iter_subdir_configs(config_dir / "coverages")
    for _cov_name, cov_cfg in coverage_entries:
        terms = cov_cfg.get("coverageTerms")
        if isinstance(terms, list) and terms:
            flags["coverage_terms"] = True
            for term in terms:
                if not isinstance(term, dict):
                    continue
                for opt in term.get("options") or []:
                    if isinstance(opt, str) and opt.startswith("*"):
                        flags["default_option_prefix"] = True
                        break
                if flags["default_option_prefix"]:
                    break
        if any(k in cov_cfg for k in ("qualification", "appliesTo", "exclusive")):
            flags["jurisdictional_scopes"] = True

    if isinstance(product_cfg, dict) and any(
        k in product_cfg for k in ("qualification", "appliesTo", "exclusive")
    ):
        flags["jurisdictional_scopes"] = True

    def _scan_data_map(data_map):
        if not isinstance(data_map, dict):
            return
        for _, field_def in data_map.items():
            if not isinstance(field_def, dict):
                continue
            raw_type = field_def.get("type")
            if not isinstance(raw_type, str) or not raw_type:
                continue
            base, q = parse_quantified_token(raw_type)
            if q == "!":
                flags["auto_elements"] = True
            if q in ITERABLE_QUANTIFIERS:
                flags["array_data_extensions"] = True
                if base and base not in PRIMITIVE_TYPES:
                    flags["nested_iterables"] = True

    def _scan_contents(contents):
        if not isinstance(contents, list):
            return
        for tok in contents:
            if not isinstance(tok, str):
                continue
            _, q = parse_quantified_token(tok)
            if q == "!":
                flags["auto_elements"] = True

    if isinstance(product_cfg, dict):
        _scan_data_map(product_cfg.get("data"))
        _scan_contents(product_cfg.get("contents"))

    for _exp_name, exp_cfg in _iter_subdir_configs(config_dir / "exposures"):
        _scan_data_map(exp_cfg.get("data"))
        _scan_contents(exp_cfg.get("contents"))

    for _cov_name, cov_cfg in coverage_entries:
        _scan_data_map(cov_cfg.get("data"))
        _scan_contents(cov_cfg.get("contents"))

    for _acct_name, acct_cfg in _iter_subdir_configs(config_dir / "accounts"):
        _scan_data_map(acct_cfg.get("data"))

    for _cdt_name, cdt_cfg in cdt_entries:
        _scan_data_map(cdt_cfg.get("data"))

    return flags


def extract_policy_charges(product_cfg: dict, config_dir: Path) -> list:
    """Policy-level charges declared on the product (no required scope)."""
    charge_names = product_cfg.get("charges", [])
    entries = []
    for charge_name in charge_names:
        charge_path = config_dir / "charges" / charge_name / "config.json"
        charge_cfg  = load_json(charge_path) if charge_path.exists() else {}
        cat         = charge_cfg.get("category", "unknown")

        entries.append({
            "name":            charge_name,
            "category":        cat,
            "velocity_amount": "$data.charges.{}.amount".format(charge_name),
            "velocity_object": "$data.charges.{}".format(charge_name),
            "requires_scope":  [],
        })
    return entries


# ---------------------------------------------------------------------------
# Registry builder
# ---------------------------------------------------------------------------

def _unscoped_entry(field, display_name, type_, category, velocity) -> dict:
    return {
        "field":          field,
        "display_name":   display_name,
        "type":           type_,
        "base_type":      type_,
        **quantifier_fields(""),
        "category":       category,
        "velocity":       velocity,
        "requires_scope": [],
    }


def build_registry(config_dir: Path) -> dict:
    products_dir = config_dir / "products"
    if products_dir.exists():
        # Sort by name so multi-product configs pick a deterministic product
        # across filesystems (iterdir order is OS/FS-dependent).
        product_dirs = sorted(
            (d for d in products_dir.iterdir() if d.is_dir()),
            key=lambda d: d.name,
        )
        if not product_dirs:
            raise FileNotFoundError("No product subdirectory found under products/")
        product_name     = product_dirs[0].name
        product_cfg_path = product_dirs[0] / "config.json"
    else:
        raise FileNotFoundError(
            "Cannot find products/ directory under {}".format(config_dir)
        )

    if not product_cfg_path.exists():
        raise FileNotFoundError("config.json not found at {}".format(product_cfg_path))

    product_cfg  = load_json(product_cfg_path)
    display_name = product_cfg.get("displayName", product_name)

    # System paths — always available on $data
    system_paths = [
        _unscoped_entry("locator",         "Policy/quote locator",        "string",   "system", "$data.locator"),
        _unscoped_entry("productName",     "Product name",                 "string",   "system", "$data.productName"),
        _unscoped_entry("policyNumber",    "Policy number",                "string",   "system", "$data.policyNumber"),
        _unscoped_entry("currency",        "Currency",                     "string",   "system", "$data.currency"),
        _unscoped_entry("policyStartTime", "Policy start (epoch ms)",      "datetime", "system", "$data.policyStartTime"),
        _unscoped_entry("policyEndTime",   "Policy end (epoch ms)",        "datetime", "system", "$data.policyEndTime"),
        _unscoped_entry("created",         "Created timestamp",            "datetime", "system", "$data.created"),
        _unscoped_entry("updated",         "Last updated timestamp",       "datetime", "system", "$data.updated"),
    ]

    # Account paths — $data.account.data.<field>
    account_paths = [
        _unscoped_entry("name",         "Account name",   "string", "account", "$data.account.data.name"),
        _unscoped_entry("addressLine1", "Address line 1", "string", "account", "$data.account.data.addressLine1"),
        _unscoped_entry("addressLine2", "Address line 2", "string", "account", "$data.account.data.addressLine2"),
        _unscoped_entry("city",         "City",           "string", "account", "$data.account.data.city"),
        _unscoped_entry("state",        "State",          "string", "account", "$data.account.data.state"),
        _unscoped_entry("postalCode",   "Postal code",    "string", "account", "$data.account.data.postalCode"),
        _unscoped_entry("country",      "Country",        "string", "account", "$data.account.data.country"),
        _unscoped_entry("email",        "Email",          "string", "account", "$data.account.data.email"),
        _unscoped_entry("phone",        "Phone",          "string", "account", "$data.account.data.phone"),
    ]

    # Policy custom data fields: $data.data.<field>  (no enclosing scope)
    policy_data_map = product_cfg.get("data", {})
    policy_fields   = extract_data_fields(
        policy_data_map, "$data.data", category="policy_data", scope=[],
    )

    # Policy-level charges
    policy_charges = extract_policy_charges(product_cfg, config_dir)

    # Exposures
    raw_contents     = product_cfg.get("contents", [])
    exposure_tokens  = [parse_quantified_token(c) for c in raw_contents]
    exposure_quants  = {name: q for name, q in exposure_tokens if name}
    exposure_names   = [name for name, _ in exposure_tokens if name]

    # Also catch any exposures/ subdirectories not listed in contents
    # (treated as quantifier-less, i.e. cardinality exactly_one).
    exposures_dir = config_dir / "exposures"
    if exposures_dir.exists():
        for d in exposures_dir.iterdir():
            if d.is_dir() and d.name not in exposure_names:
                exposure_names.append(d.name)
                exposure_quants[d.name] = ""

    exposures = []
    iterables_index = []
    for exp_name in exposure_names:
        block = extract_exposure(exp_name, config_dir, outer_scope=[])
        if not block:
            continue
        q = exposure_quants.get(exp_name, "")
        block.update(quantifier_fields(q))
        exposures.append(block)

        if q in ITERABLE_QUANTIFIERS:
            iterables_index.append({
                "name":          exp_name,
                "display_name":  block["display_name"],
                "kind":          "exposure",
                "list_velocity": block["list_velocity"],
                "iterator":      "${}".format(block["iterator"]),
                "foreach":       block["foreach"],
                "quantifier":    q,
                "cardinality":   QUANTIFIER_CARDINALITY[q],
            })

    feature_support = detect_features(config_dir, product_cfg)
    source_fp = _compute_source_config_sha256(config_dir)

    return {
        "schema_version": "1.1",
        "meta": {
            "config_dir":   str(config_dir.resolve()),
            "product":      product_name,
            "display_name": display_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_config_sha256": source_fp,
            "note": (
                "Socotra Velocity dot-notation paths. "
                "Root object is $data (the renderingData from DocumentDataSnapshotPlugin). "
                "Policy custom fields: $data.data.<field>. "
                "Account fields: $data.account.data.<field>. "
                "Exposure lists: $data.<exposurePlural> (e.g. $data.vehicles). "
                "Exposure fields: $<iterator>.data.<field> (e.g. $vehicle.data.vin). "
                "Coverage fields: $<iterator>.<Coverage>.data.<field>. "
                "Charge amounts: $data.charges.<ChargeName>.amount or "
                "$<iterator>.<Coverage>.charges.<ChargeName>.amount. "
                "Every entry carries `quantifier` + `cardinality` + `iterable` flags "
                "plus a `requires_scope` list of #foreach steps (outermost first) "
                "that must be active for the path to be valid. The previous "
                "`optional: true/false` key on coverages has been replaced by "
                "`quantifier: '?'` + `cardinality: zero_or_one`."
            ),
        },
        "feature_support": feature_support,
        "iterables":      iterables_index,
        "system_paths":   system_paths,
        "account_paths":  account_paths,
        "policy_data":    policy_fields,
        "policy_charges": policy_charges,
        "exposures":      exposures,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract Socotra config paths into a Velocity path registry."
    )
    parser.add_argument("--config-dir", required=True, help="Path to socotra-config/ directory")
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: <config-dir>/../registry/path-registry.yaml)",
    )
    args = parser.parse_args()

    config_dir = Path(args.config_dir).resolve()
    if not config_dir.exists():
        print("ERROR: config-dir not found: {}".format(config_dir))
        sys.exit(1)

    print("Extracting paths from: {}".format(config_dir))

    registry    = build_registry(config_dir)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = config_dir.parent / "registry" / "path-registry.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(registry, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    n_system   = len(registry["system_paths"])
    n_account  = len(registry["account_paths"])
    n_policy   = len(registry["policy_data"])
    n_charges  = len(registry["policy_charges"])
    n_exp      = len(registry["exposures"])
    n_iter     = len(registry["iterables"])
    n_exp_f    = sum(len(e.get("fields", [])) for e in registry["exposures"])
    n_cov      = sum(len(e.get("coverages", [])) for e in registry["exposures"])
    n_cov_f    = sum(len(c.get("fields", [])) for e in registry["exposures"] for c in e.get("coverages", []))

    n_features_on = sum(1 for v in registry["feature_support"].values() if v)
    n_features    = len(registry["feature_support"])

    print("\nProduct:          {}".format(registry["meta"]["product"]))
    print("Iterables:        {}".format(n_iter))
    print("System paths:     {}".format(n_system))
    print("Account paths:    {}".format(n_account))
    print("Policy fields:    {}".format(n_policy))
    print("Policy charges:   {}".format(n_charges))
    print("Exposures:        {}".format(n_exp))
    print("  Exposure fields:  {}".format(n_exp_f))
    print("  Coverages:        {}".format(n_cov))
    print("  Coverage fields:  {}".format(n_cov_f))
    print("Feature flags on: {} / {}".format(n_features_on, n_features))
    print("\nTotal paths:      {}".format(n_system + n_account + n_policy + n_charges + n_exp_f + n_cov_f))
    print("\nOutput: {}".format(output_path))


if __name__ == "__main__":
    main()
