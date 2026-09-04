from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    path = SKILL_ROOT / "scripts" / "validate_extension.py"
    spec = importlib.util.spec_from_file_location("modly_extension_validator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


def source(source_id: str, destination: str, repo_id: str = "owner/model") -> dict:
    return {
        "id": source_id,
        "provider": "huggingface",
        "repo_id": repo_id,
        "revision": "0123456789abcdef0123456789abcdef01234567",
        "destination": destination,
        "checks": ["model.safetensors"],
    }


class ModelContractValidationTests(unittest.TestCase):
    def audit(self):
        return VALIDATOR.Audit(Path.cwd())

    def test_accepts_valid_model_sources(self) -> None:
        audit = self.audit()
        node = {"model_sources": [source("primary", "."), source("encoder", "auxiliary/encoder")]}
        VALIDATOR.validate_model_weight_contract(audit, {}, [node], "model-sources")
        self.assertEqual(audit.issues, [])

    def test_rejects_mixed_contract_and_wrong_target(self) -> None:
        audit = self.audit()
        node = {
            "hf_repo": "owner/legacy",
            "download_check": "model.safetensors",
            "model_sources": [source("primary", ".")],
        }
        VALIDATOR.validate_model_weight_contract(audit, {}, [node], "legacy")
        codes = {issue.code for issue in audit.issues}
        self.assertIn("MODEL_CONTRACT_MIXED", codes)
        self.assertIn("MODEL_CONTRACT_TARGET", codes)

    def test_rejects_unsafe_paths_duplicate_ids_and_check_collisions(self) -> None:
        audit = self.audit()
        first = source("primary", ".")
        second = source("PRIMARY", ".", "owner/encoder")
        second["checks"] = ["MODEL.safetensors"]
        third = source("unsafe", "aux/CON", "owner/third")
        VALIDATOR.validate_model_sources(
            audit,
            {"model_sources": [first, second, third]},
            0,
        )
        codes = {issue.code for issue in audit.issues}
        self.assertIn("MODEL_SOURCE_ID_DUPLICATE", codes)
        self.assertIn("MODEL_SOURCE_CHECK_COLLISION", codes)
        self.assertIn("MODEL_SOURCE_DESTINATION", codes)

    def test_rejects_checks_excluded_by_filters(self) -> None:
        audit = self.audit()
        entry = source("primary", ".")
        entry["include_prefixes"] = ["weights/"]
        VALIDATOR.validate_model_sources(audit, {"model_sources": [entry]}, 0)
        self.assertIn("MODEL_SOURCE_CHECK_NOT_INCLUDED", {issue.code for issue in audit.issues})

    def test_rejects_unimplemented_github_provider(self) -> None:
        audit = self.audit()
        entry = source("primary", ".")
        entry["provider"] = "github"
        VALIDATOR.validate_model_sources(audit, {"model_sources": [entry]}, 0)
        self.assertIn("MODEL_SOURCE_PROVIDER", {issue.code for issue in audit.issues})


class ScaffoldContractTests(unittest.TestCase):
    def scaffold(self, target: Path, *contract_args: str) -> dict:
        command = [
            sys.executable,
            str(SKILL_ROOT / "scripts" / "scaffold_extension.py"),
            "--kind", "model",
            "--id", "contract-test",
            "--name", "Contract Test",
            "--author", "DrHepa",
            "--source", "https://github.com/DrHepa/contract-test",
            "--description", "Exercise model contract scaffolding.",
            "--upstream", "https://github.com/upstream/project",
            "--license-name", "MIT",
            "--upstream-license", "MIT",
            "--weights-license", "MIT",
            *contract_args,
            "--output-dir", str(target),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads((target / "manifest.json").read_text(encoding="utf-8"))

    def test_legacy_remains_default(self) -> None:
        with tempfile.TemporaryDirectory(prefix="modly-skill-legacy-") as tmp:
            target = Path(tmp) / "extension"
            manifest = self.scaffold(
                target,
                "--hf-repo", "owner/model",
                "--download-check", "model.safetensors",
            )
            node = manifest["nodes"][0]
            self.assertEqual(node["hf_repo"], "owner/model")
            self.assertNotIn("model_sources", node)
            self.assertIn("REQUIRED_MODEL_FILES = ['model.safetensors']", (target / "generator.py").read_text())

    def test_scaffolds_multiple_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="modly-skill-sources-") as tmp:
            target = Path(tmp) / "extension"
            manifest = self.scaffold(
                target,
                "--model-contract", "model-sources",
                "--model-source", json.dumps(source("primary", ".")),
                "--model-source", json.dumps(source("encoder", "auxiliary/encoder", "owner/encoder")),
            )
            node = manifest["nodes"][0]
            self.assertNotIn("hf_repo", node)
            self.assertEqual([item["id"] for item in node["model_sources"]], ["primary", "encoder"])
            generator = (target / "generator.py").read_text(encoding="utf-8")
            self.assertIn("auxiliary/encoder/model.safetensors", generator)
            for path in target.rglob("*"):
                if path.is_file():
                    self.assertNotIn("@@", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
