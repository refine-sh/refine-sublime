#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_ROOTS = {".git", "__pycache__"}
EXCLUDED_FILES = {"manifest.json", ".DS_Store"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def kind(path: Path) -> str:
    first = path.parts[0]
    if first in {"schema", "spec", "registry", "vectors", "runner", "reference"}:
        return first
    if path.name == "LICENSE":
        return "license"
    return "documentation"


def case_ids(paths: List[Path]) -> List[str]:
    identifiers = [
        case["id"]
        for path in paths
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]
    ]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("vector case IDs must be unique within their inventory")
    return identifiers


def main() -> None:
    existing_manifest = {}
    manifest_path = ROOT / "manifest.json"
    if manifest_path.exists():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if relative.parts[0] in EXCLUDED_ROOTS or path.name in EXCLUDED_FILES:
            continue
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError("shipped artifacts must be regular files: %s" % relative)
        if not path.is_file():
            continue
        paths.append(relative)
    paths.sort(key=lambda item: item.as_posix())

    artifacts: List[Dict[str, str]] = []
    aggregate = hashlib.sha256()
    base_aggregate = hashlib.sha256()
    for relative in paths:
        digest = sha256(ROOT / relative)
        normalized = relative.as_posix()
        artifact_kind = kind(relative)
        artifacts.append({"path": normalized, "sha256": digest, "kind": artifact_kind})
        digest_line = (normalized + "\0" + digest + "\n").encode("utf-8")
        aggregate.update(digest_line)
        if artifact_kind in {"schema", "spec", "vectors"}:
            base_aggregate.update(digest_line)

    generated_inventories = {
        "jsonPositiveCaseIds": case_ids(sorted((ROOT / "vectors" / "json" / "positive").glob("*.json"))),
        "jsonNegativeCaseIds": case_ids(sorted((ROOT / "vectors" / "json" / "negative").glob("*.json"))),
        "frameCaseIds": case_ids(sorted((ROOT / "vectors" / "frames").glob("*.json"))),
        "stateScenarioIds": [
        json.loads(path.read_text(encoding="utf-8"))["id"]
        for path in sorted((ROOT / "vectors" / "state").glob("*.json"))
        ],
    }
    inventories = {
        name: existing_manifest.get(name, generated)
        for name, generated in generated_inventories.items()
    }
    manifest = {
        "formatVersion": 1,
        "releaseCandidate": "1.0.0-rc.5",
        "protocol": {"major": 1, "minor": 0},
        "artifactDigest": aggregate.hexdigest(),
        "baseArtifactDigest": base_aggregate.hexdigest(),
        "capabilityRegistryDigest": sha256(ROOT / "registry" / "capabilities.json"),
        **inventories,
        "artifacts": artifacts,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
