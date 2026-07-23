"""Regression: no-config loop-root synthesis (Pet → $data.pets) vs strict match."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
from velocity_converter.leg2_fill_mapping import (  # noqa: E402
    build_registry_index,
    suggest_loop_root,
)


def _load_run_demo():
    """tools/ is not a package — load run_demo.py by file path."""
    spec = importlib.util.spec_from_file_location(
        "run_demo", REPO / "tools" / "run_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestNoConfigLoopSynthesis(unittest.TestCase):
    def setUp(self) -> None:
        reg_path = REPO / "registry" / "path-registry.yaml"
        self.reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
        self.idx = build_registry_index(self.reg)

    def test_pet_synthesized_in_no_config(self) -> None:
        list_vel, step, _reason, iterator, foreach, _cov = suggest_loop_root(
            "Pet", self.idx, None, self.reg, no_config=True
        )
        self.assertEqual(list_vel, "$data.pets")
        self.assertEqual(iterator, "$pet")
        self.assertEqual(foreach, "#foreach ($pet in $data.pets)")
        self.assertEqual(step, "synthesized")

    def test_unmatched_loop_empty_without_no_config(self) -> None:
        # Real-config path: strict resolution unchanged — no synthesis.
        list_vel, step, _reason, iterator, foreach, _cov = suggest_loop_root(
            "Pet", self.idx, None, self.reg
        )
        self.assertEqual(list_vel, "")
        self.assertEqual(step, "none")
        self.assertIsNone(iterator)
        self.assertIsNone(foreach)

    def test_exact_registry_match_wins_even_in_no_config(self) -> None:
        # `Item` exists in the registry → exact match, never synthesized.
        list_vel, step, _reason, iterator, _fe, _cov = suggest_loop_root(
            "Item", self.idx, None, self.reg, no_config=True
        )
        self.assertEqual(list_vel, "$data.items")
        self.assertEqual(step, "exact")
        self.assertEqual(iterator, "$item")

    def test_plural_edge_cases(self) -> None:
        # -y → -ies, sibilant → -es, already-plural left alone.
        self.assertEqual(
            suggest_loop_root("Party", self.idx, None, self.reg, no_config=True)[0],
            "$data.parties",
        )
        self.assertEqual(
            suggest_loop_root("Box", self.idx, None, self.reg, no_config=True)[0],
            "$data.boxes",
        )
        # Already-plural loop word is left alone (ceiling: a singular ending in
        # -s like "Bus" is indistinguishable and also passes through unchanged).
        self.assertEqual(
            suggest_loop_root("Pets", self.idx, None, self.reg, no_config=True)[0],
            "$data.pets",
        )


class TestNoConfigLoopBodyFill(unittest.TestCase):
    """_fill_loop_roots_no_jar must resolve the loop BODY fields too, so no
    $TBD_ token survives into the template for a synthesized (no-config) loop."""

    def setUp(self) -> None:
        self.rd = _load_run_demo()
        self._cwd = os.getcwd()
        os.chdir(REPO)  # module-level REGISTRY is a repo-relative path

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def test_pet_body_fields_resolved_no_tbd(self) -> None:
        import tempfile
        stem = "PetDemo(segment)"
        mapping = {
            "source": "PetDemo(segment)",
            "variables": [],
            "loops": [{
                "name": "Pet", "type": "loop", "placeholder": "$TBD_Pet",
                "data_source": "",
                "fields": [
                    {"name": "pet.data.petName", "type": "loop_field",
                     "placeholder": "$TBD_pet.data.petName",
                     "data_source": "UNRESOLVED:pet.data.petName"},
                    {"name": "pet.data.species", "type": "loop_field",
                     "placeholder": "$TBD_pet.data.species",
                     "data_source": "UNRESOLVED:pet.data.species"},
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / f"{stem}.mapping.yaml").write_text(
                yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
            self.rd._fill_loop_roots_no_jar(stem, d)
            out = yaml.safe_load((Path(d) / f"{stem}.mapping.yaml").read_text())

        loop = out["loops"][0]
        self.assertEqual(loop["data_source"], "$data.segment.pets")
        self.assertTrue(loop.get("no_config_synthesized"))
        srcs = [f["data_source"] for f in loop["fields"]]
        self.assertEqual(srcs, ["$pet.data.petName", "$pet.data.species"])
        self.assertFalse(any(s.startswith("UNRESOLVED:") for s in srcs))


if __name__ == "__main__":
    unittest.main()
