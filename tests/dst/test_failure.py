"""CV19.DS4 failure retention, replay, credential refusal, and promotion."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue, ValidationError

from petrus.testing.dst import ScenarioArtifact, load_artifact
from tests.dst.failure import (
    ARTIFACT_FILE,
    BUNDLE_BYTES,
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    FAILURE_PROPERTY,
    MANIFEST_FILE,
    REPLAY_COMMAND,
    FailureManifest,
    demonstrate_failure_bundle,
    replay_failure_bundle,
    retain_failure_bundle,
)


@pytest.fixture(scope="module")
def demonstrated_bundle(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, FailureManifest]:
    bundle = tmp_path_factory.mktemp("dst-failure") / "bundle"
    manifest = demonstrate_failure_bundle(bundle)
    return bundle, manifest


def test_deliberate_failure_is_retained_replayed_and_promoted(
    demonstrated_bundle: tuple[Path, FailureManifest],
) -> None:
    bundle, manifest = demonstrated_bundle

    assert {path.name for path in bundle.iterdir()} == {ARTIFACT_FILE, MANIFEST_FILE}
    assert manifest.format == BUNDLE_FORMAT
    assert manifest.version == BUNDLE_VERSION
    assert manifest.property == FAILURE_PROPERTY
    assert manifest.discovery_seed == 19_003
    assert manifest.artifact.version == 4
    assert manifest.artifact.api == "petrus.testing.dst/v4"
    assert manifest.artifact.disposition == "budget_exhausted"
    assert cast(dict[str, JsonValue], manifest.artifact.failure)["kind"] == "budget_exhausted"
    assert manifest.shrink.parent_operations == manifest.shrink.minimized_operations
    assert manifest.shrink.parent_prefix_operations > manifest.shrink.minimized_prefix_operations
    assert manifest.shrink.parent_bytes > manifest.shrink.minimized_bytes
    assert manifest.shrink.removed_retry is True
    assert manifest.shrink.removed_perturbations == ["observe", "crash_reload", "observe"]
    assert manifest.replay.cwd == "repository-root"
    assert manifest.replay.command == REPLAY_COMMAND
    assert manifest.promotion.status == "ordinary-green-regression"
    assert manifest.promotion.disposition == "quiescent"
    assert manifest.semantic_coverage["checker_activations"]
    assert sum(path.stat().st_size for path in bundle.iterdir()) <= BUNDLE_BYTES

    encoded_manifest = (bundle / MANIFEST_FILE).read_bytes()
    assert b'"payload"' not in encoded_manifest
    assert b'"result"' not in encoded_manifest
    assert b"shrinking-livelock-event" not in encoded_manifest
    replayed = replay_failure_bundle(bundle)
    assert replayed["outcome"] == "pass"
    assert replayed["failure_disposition"] == "budget_exhausted"
    assert replayed["promotion_disposition"] == "quiescent"

    completed = subprocess.run(
        [sys.executable, "-m", "tests.dst.failure", "replay", str(bundle)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == replayed


@pytest.mark.parametrize(
    "payload, match",
    [
        ({"provider_password": "not-retainable"}, "credential-like field"),
        ({"message": "failed at postgres://admin:password@provider.invalid/db"}, "credential-like value"),
    ],
)
def test_failure_retention_refuses_credential_shaped_data_before_writing(
    demonstrated_bundle: tuple[Path, FailureManifest],
    tmp_path: Path,
    payload: dict[str, JsonValue],
    match: str,
) -> None:
    bundle, _ = demonstrated_bundle
    artifact = load_artifact(bundle / ARTIFACT_FILE)
    assert isinstance(artifact, ScenarioArtifact)
    value = artifact.model_dump(mode="json")
    for operation in cast(list[dict[str, JsonValue]], value["operations"]):
        if operation["kind"] == "execute":
            cast(dict[str, JsonValue], operation["command"])["payload"] = payload
            break
    unsafe = ScenarioArtifact.model_validate(value, strict=True)
    destination = tmp_path / "unsafe"

    with pytest.raises(ValueError, match=match):
        retain_failure_bundle(
            destination,
            unsafe,
            parent=artifact,
            property_name=FAILURE_PROPERTY,
            removed_retry=False,
            removed_perturbations=(),
        )

    assert not destination.exists()


def test_failure_replay_refuses_tampering_and_extra_files(
    demonstrated_bundle: tuple[Path, FailureManifest],
    tmp_path: Path,
) -> None:
    bundle, _ = demonstrated_bundle
    tampered = tmp_path / "tampered"
    shutil.copytree(bundle, tampered)
    scenario = tampered / ARTIFACT_FILE
    scenario.write_bytes(scenario.read_bytes() + b" ")

    with pytest.raises(ValueError, match="does not match its retained byte identity"):
        replay_failure_bundle(tampered)

    extra = tmp_path / "extra"
    shutil.copytree(bundle, extra)
    (extra / "provider-response.txt").write_text("must not be retained", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly manifest.json and scenario.json"):
        replay_failure_bundle(extra)


def test_failure_replay_refuses_manifest_mismatch_and_bundle_overage(
    demonstrated_bundle: tuple[Path, FailureManifest],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, _ = demonstrated_bundle
    mismatched = tmp_path / "mismatched"
    shutil.copytree(bundle, mismatched)
    manifest_path = mismatched / MANIFEST_FILE
    manifest = json.loads(manifest_path.read_bytes())
    manifest["discovery_seed"] += 1
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match its manifest expectations"):
        replay_failure_bundle(mismatched)

    monkeypatch.setattr("tests.dst.failure.BUNDLE_BYTES", 1)
    with pytest.raises(ValueError, match="bundle exceeds 1 bytes"):
        replay_failure_bundle(bundle)


def test_failure_manifest_refuses_unknown_schema() -> None:
    with pytest.raises(ValidationError):
        FailureManifest.model_validate(
            {
                "format": BUNDLE_FORMAT,
                "version": 2,
            },
            strict=True,
        )
