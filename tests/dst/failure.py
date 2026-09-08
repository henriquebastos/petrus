"""Retain, replay, and promote bounded deterministic simulation failures."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal, cast

from hypothesis import Phase, find, settings, strategies as st
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from petrus.testing.dst import (
    Disposition,
    ScenarioArtifact,
    decode_artifact,
    encode_artifact,
)
from tests.dst.generated_runtime_qualification import (
    build_livelock_failure_artifact,
    semantic_labels,
)
from tests.dst.replay_world import replay_path

BUNDLE_FORMAT = "petrus-dst-failure-bundle"
BUNDLE_VERSION = 1
MANIFEST_BYTES = 262_144
BUNDLE_BYTES = 4_456_448
ARTIFACT_FILE = "scenario.json"
MANIFEST_FILE = "manifest.json"
REPLAY_BUNDLE_ARGUMENT = "{bundle}"
REPLAY_COMMAND = ["uv", "run", "python", "-m", "tests.dst.failure", "replay", REPLAY_BUNDLE_ARGUMENT]
FAILURE_PROPERTY = "fair phase must not repeat an unchanged eligible frontier until action exhaustion"
PROMOTED_FIXTURE = Path("tests/dst/fixtures/generated-runtime-minimized-fair-regression-v4.json")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "dsn",
    "password",
    "private_key",
    "refresh_token",
    "secret",
}
_SENSITIVE_VALUES = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"(?:gh[pousr]_|github_pat_)\S+"),
    re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/@\s]+:[^/@\s]+@"),
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DependencyIdentity(_StrictModel):
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=256)


class RuntimeIdentity(_StrictModel):
    commit: str
    dirty: bool
    python: str = Field(min_length=1, max_length=128)
    dependencies: list[DependencyIdentity] = Field(min_length=1, max_length=16)

    @field_validator("commit")
    @classmethod
    def valid_commit(cls, value: str) -> str:
        if not _COMMIT.fullmatch(value):
            raise ValueError("failure bundle commit must be 40 lowercase hexadecimal characters")
        return value


class ShrinkEvidence(_StrictModel):
    parent_scenario_id: str = Field(min_length=1, max_length=256)
    parent_artifact_digest: str
    parent_operations: int = Field(ge=1, le=100_000)
    parent_prefix_operations: int = Field(ge=1, le=100_000)
    parent_bytes: int = Field(ge=1, le=4_194_304)
    minimized_operations: int = Field(ge=1, le=100_000)
    minimized_prefix_operations: int = Field(ge=1, le=100_000)
    minimized_bytes: int = Field(ge=1, le=4_194_304)
    removed_retry: bool
    removed_perturbations: list[str] = Field(max_length=64)

    @field_validator("parent_artifact_digest")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if not _DIGEST.fullmatch(value):
            raise ValueError("failure bundle artifact digest must be sha256:<64 lowercase hex>")
        return value


class ArtifactEvidence(_StrictModel):
    path: Literal["scenario.json"]
    bytes: int = Field(ge=1, le=4_194_304)
    digest: str
    format: Literal["petrus-dst-world"]
    version: Literal[4]
    api: Literal["petrus.testing.dst/v4"]
    scenario_id: str = Field(min_length=1, max_length=256)
    disposition: Literal["budget_exhausted", "invariant_failure"]
    failure: JsonValue

    @field_validator("digest")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if not _DIGEST.fullmatch(value):
            raise ValueError("failure bundle artifact digest must be sha256:<64 lowercase hex>")
        return value


class ReplayInstruction(_StrictModel):
    cwd: Literal["repository-root"]
    command: list[str] = Field(min_length=7, max_length=7)

    @field_validator("command")
    @classmethod
    def valid_command(cls, value: list[str]) -> list[str]:
        if value != REPLAY_COMMAND:
            raise ValueError("failure bundle replay command must use the repository-owned replay route")
        return value


class PromotionEvidence(_StrictModel):
    status: Literal["ordinary-green-regression"]
    path: str = Field(min_length=1, max_length=512)
    digest: str
    scenario_id: str = Field(min_length=1, max_length=256)
    disposition: Literal["quiescent"]

    @field_validator("digest")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if not _DIGEST.fullmatch(value):
            raise ValueError("failure bundle promotion digest must be sha256:<64 lowercase hex>")
        return value


class FailureManifest(_StrictModel):
    format: Literal["petrus-dst-failure-bundle"]
    version: Literal[1]
    property: str = Field(min_length=1, max_length=512)
    discovery_seed: int = Field(ge=0, le=2**53 - 1)
    runtime: RuntimeIdentity
    shrink: ShrinkEvidence
    artifact: ArtifactEvidence
    replay: ReplayInstruction
    semantic_coverage: dict[str, list[str]]
    promotion: PromotionEvidence


def retain_failure_bundle(
    destination: Path,
    artifact: ScenarioArtifact,
    *,
    parent: ScenarioArtifact,
    property_name: str,
    removed_retry: bool,
    removed_perturbations: tuple[str, ...],
    promoted_path: Path = PROMOTED_FIXTURE,
) -> FailureManifest:
    """Validate and atomically retain one exact failed artifact and manifest."""

    if destination.exists():
        raise ValueError(f"DST failure bundle destination already exists: {destination}")
    if (
        artifact.expected.disposition
        not in {
            Disposition.BUDGET_EXHAUSTED.value,
            Disposition.INVARIANT_FAILURE.value,
        }
        or artifact.expected.failure is None
    ):
        raise ValueError("DST failure bundle requires one exact failed v4 artifact")
    if artifact.origin is None:
        raise ValueError("DST failure bundle requires exact discovery provenance")

    artifact_bytes = encode_artifact(artifact)
    parent_bytes = encode_artifact(parent)
    promoted_bytes = _canonical_file(promoted_path)
    promoted = decode_artifact(promoted_bytes)
    if not isinstance(promoted, ScenarioArtifact):
        raise ValueError("DST promoted regression must use the current v4 artifact")
    if promoted.expected.disposition != Disposition.QUIESCENT.value or promoted.expected.failure is not None:
        raise ValueError("DST promoted regression must be an ordinary green quiescent artifact")

    _assert_retention_safe(artifact.model_dump(mode="json"), "artifact")
    coverage = {name: sorted(values) for name, values in semantic_labels(artifact).items()}
    manifest = FailureManifest(
        format=BUNDLE_FORMAT,
        version=BUNDLE_VERSION,
        property=property_name,
        discovery_seed=artifact.origin.seed,
        runtime=_runtime_identity(),
        shrink=ShrinkEvidence(
            parent_scenario_id=parent.scenario_id,
            parent_artifact_digest=_digest(parent_bytes),
            parent_operations=len(parent.operations),
            parent_prefix_operations=_fair_prefix_operations(parent),
            parent_bytes=len(parent_bytes),
            minimized_operations=len(artifact.operations),
            minimized_prefix_operations=_fair_prefix_operations(artifact),
            minimized_bytes=len(artifact_bytes),
            removed_retry=removed_retry,
            removed_perturbations=list(removed_perturbations),
        ),
        artifact=ArtifactEvidence(
            path=ARTIFACT_FILE,
            bytes=len(artifact_bytes),
            digest=_digest(artifact_bytes),
            format=artifact.format,
            version=artifact.version,
            api=artifact.api,
            scenario_id=artifact.scenario_id,
            disposition=cast(Literal["budget_exhausted", "invariant_failure"], artifact.expected.disposition),
            failure=artifact.expected.failure.model_dump(mode="json"),
        ),
        replay=ReplayInstruction(
            cwd="repository-root",
            command=REPLAY_COMMAND,
        ),
        semantic_coverage=coverage,
        promotion=PromotionEvidence(
            status="ordinary-green-regression",
            path=promoted_path.as_posix(),
            digest=_digest(promoted_bytes),
            scenario_id=promoted.scenario_id,
            disposition=Disposition.QUIESCENT.value,
        ),
    )
    manifest_value = manifest.model_dump(mode="json")
    _assert_retention_safe(manifest_value, "manifest")
    manifest_bytes = json.dumps(
        manifest_value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    if len(manifest_bytes) > MANIFEST_BYTES:
        raise ValueError(f"DST failure manifest has {len(manifest_bytes)} bytes; limit is {MANIFEST_BYTES}")
    total = len(artifact_bytes) + len(manifest_bytes) + 2
    if total > BUNDLE_BYTES:
        raise ValueError(f"DST failure bundle has {total} bytes; limit is {BUNDLE_BYTES}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".petrus-dst-failure-", dir=destination.parent))
    try:
        (temporary / ARTIFACT_FILE).write_bytes(artifact_bytes + b"\n")
        (temporary / MANIFEST_FILE).write_bytes(manifest_bytes + b"\n")
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def replay_failure_bundle(bundle: Path) -> dict[str, JsonValue]:
    """Verify bundle integrity, replay its failure, and verify its promotion."""

    expected_files = {ARTIFACT_FILE, MANIFEST_FILE}
    if not bundle.is_dir() or {path.name for path in bundle.iterdir()} != expected_files:
        raise ValueError("DST failure bundle must contain exactly manifest.json and scenario.json")
    manifest_path = bundle / MANIFEST_FILE
    if manifest_path.stat().st_size > MANIFEST_BYTES + 1:
        raise ValueError(f"DST failure manifest exceeds {MANIFEST_BYTES} bytes")
    manifest = FailureManifest.model_validate(_load_strict_json(manifest_path.read_bytes()), strict=True)
    _assert_retention_safe(manifest.model_dump(mode="json"), "manifest")

    artifact_path = bundle / ARTIFACT_FILE
    artifact_bytes = _canonical_file(artifact_path)
    if len(artifact_bytes) != manifest.artifact.bytes or _digest(artifact_bytes) != manifest.artifact.digest:
        raise ValueError("DST failure artifact does not match its retained byte identity")
    if sum(path.stat().st_size for path in bundle.iterdir()) > BUNDLE_BYTES:
        raise ValueError(f"DST failure bundle exceeds {BUNDLE_BYTES} bytes")
    artifact = decode_artifact(artifact_bytes)
    if not isinstance(artifact, ScenarioArtifact):
        raise ValueError("DST failure bundle requires a current v4 artifact")
    _assert_retention_safe(artifact.model_dump(mode="json"), "artifact")
    if (
        artifact.format != manifest.artifact.format
        or artifact.version != manifest.artifact.version
        or artifact.api != manifest.artifact.api
        or artifact.scenario_id != manifest.artifact.scenario_id
        or artifact.expected.disposition != manifest.artifact.disposition
        or artifact.expected.failure is None
        or artifact.expected.failure.model_dump(mode="json") != manifest.artifact.failure
        or artifact.origin is None
        or artifact.origin.seed != manifest.discovery_seed
        or len(artifact.operations) != manifest.shrink.minimized_operations
        or _fair_prefix_operations(artifact) != manifest.shrink.minimized_prefix_operations
        or manifest.semantic_coverage != {name: sorted(values) for name, values in semantic_labels(artifact).items()}
    ):
        raise ValueError("DST failure artifact does not match its manifest expectations")

    failed = replay_path(artifact_path)
    if (
        failed.outcome != "pass"
        or failed.disposition != manifest.artifact.disposition
        or failed.failure != artifact.expected.failure
        or failed.journal_digest != artifact.expected.journal_digest
    ):
        raise ValueError("DST failure replay did not reproduce its exact retained outcome")

    promoted_path = _repository_path(manifest.promotion.path)
    promoted_bytes = _canonical_file(promoted_path)
    if _digest(promoted_bytes) != manifest.promotion.digest:
        raise ValueError("DST promoted regression does not match its retained identity")
    promoted = replay_path(promoted_path)
    if (
        promoted.outcome != "pass"
        or promoted.scenario_id != manifest.promotion.scenario_id
        or promoted.disposition != manifest.promotion.disposition
        or promoted.failure is not None
    ):
        raise ValueError("DST promoted regression did not replay green")

    return cast(
        dict[str, JsonValue],
        {
            "artifact_digest": manifest.artifact.digest,
            "failure": manifest.artifact.failure,
            "failure_disposition": failed.disposition,
            "failure_journal_digest": failed.journal_digest,
            "format": "petrus-dst-failure-replay-result",
            "outcome": "pass",
            "promoted_scenario_id": promoted.scenario_id,
            "promotion_disposition": promoted.disposition,
            "scenario_id": failed.scenario_id,
            "version": 1,
        },
    )


def demonstrate_failure_bundle(destination: Path) -> FailureManifest:
    """Rehearse reproduce, replay, shrink, retain, replay, and promotion."""

    if destination.exists():
        raise ValueError(f"DST failure bundle destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="petrus-dst-failure-demo-", dir=destination.parent) as directory:
        root = Path(directory)
        parent = build_livelock_failure_artifact(
            root / "parent",
            retry=True,
            perturbations=("observe", "crash_reload", "observe"),
        )
        _replay_artifact(parent, root / "parent-replay.json")
        counter = iter(range(1_000))

        def reproduces(candidate: tuple[bool, tuple[str, ...]]) -> bool:
            retry, perturbations = candidate
            artifact = build_livelock_failure_artifact(
                root / f"shrink-{next(counter)}",
                retry=retry,
                perturbations=perturbations,
            )
            return artifact.expected.disposition == Disposition.BUDGET_EXHAUSTED.value

        strategy = st.tuples(
            st.booleans(),
            st.lists(st.sampled_from(("observe", "crash_reload")), max_size=3).map(tuple),
        )
        minimized = find(
            strategy,
            reproduces,
            settings=settings(
                max_examples=20,
                derandomize=True,
                database=None,
                deadline=None,
                phases=(Phase.generate, Phase.shrink),
            ),
        )
        if minimized != (False, ()):
            raise AssertionError(f"DST failure demonstration did not reach the accepted minimum: {minimized!r}")
        artifact = build_livelock_failure_artifact(
            root / "minimized",
            retry=minimized[0],
            perturbations=minimized[1],
        )
        _replay_artifact(artifact, root / "minimized-replay.json")
        manifest = retain_failure_bundle(
            destination,
            artifact,
            parent=parent,
            property_name=FAILURE_PROPERTY,
            removed_retry=True,
            removed_perturbations=("observe", "crash_reload", "observe"),
        )
    replay_failure_bundle(destination)
    return manifest


def _replay_artifact(artifact: ScenarioArtifact, path: Path) -> None:
    path.write_bytes(encode_artifact(artifact) + b"\n")
    result = replay_path(path)
    if (
        result.outcome != "pass"
        or result.disposition != artifact.expected.disposition
        or result.failure != artifact.expected.failure
        or result.journal_digest != artifact.expected.journal_digest
    ):
        raise ValueError("DST generated failure did not replay exactly")


def _runtime_identity() -> RuntimeIdentity:
    root = _repository_root()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    return RuntimeIdentity(
        commit=commit,
        dirty=dirty,
        python=sys.version.split()[0],
        dependencies=[
            DependencyIdentity(name="hypothesis", version=importlib.metadata.version("hypothesis")),
            DependencyIdentity(name="petrus-runtime", version=importlib.metadata.version("petrus-runtime")),
        ],
    )


def _assert_retention_safe(value: JsonValue, subject: str) -> None:
    def visit(item: JsonValue, path: str) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
                if normalized in _SENSITIVE_KEYS or any(
                    normalized.endswith(f"_{sensitive}") for sensitive in _SENSITIVE_KEYS
                ):
                    raise ValueError(f"DST {subject} has a credential-like field at {path}.{key}")
                visit(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")
        elif isinstance(item, str) and any(pattern.search(item) for pattern in _SENSITIVE_VALUES):
            raise ValueError(f"DST {subject} has a credential-like value at {path}")

    visit(value, "$")


def _canonical_file(path: Path) -> bytes:
    payload = path.read_bytes()
    return payload[:-1] if payload.endswith(b"\n") else payload


def _repository_root() -> Path:
    return Path(__file__).parents[2]


def _repository_path(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("DST promoted regression path must remain within the repository")
    return _repository_root() / relative


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _fair_prefix_operations(artifact: ScenarioArtifact) -> int:
    try:
        operation = next(operation for operation in artifact.operations if operation.kind == "begin_fair")
    except StopIteration:
        raise ValueError("DST fair-liveness failure has no fair-phase operation") from None
    return operation.position + 1


def _load_strict_json(payload: bytes) -> object:
    def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    def refuse_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value}")

    try:
        return json.loads(payload, object_pairs_hook=strict_object, parse_constant=refuse_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid strict DST failure manifest: {error}") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demonstrate = commands.add_parser("demonstrate", help="rehearse failure through promotion")
    demonstrate.add_argument("--output", required=True, type=Path)
    replay = commands.add_parser("replay", help="verify and replay one retained bundle")
    replay.add_argument("bundle", type=Path)
    arguments = parser.parse_args()

    if arguments.command == "demonstrate":
        manifest = demonstrate_failure_bundle(arguments.output)
        result: dict[str, JsonValue] = {
            "bundle": str(arguments.output),
            "failure_artifact_digest": manifest.artifact.digest,
            "outcome": "pass",
            "promoted_scenario_id": manifest.promotion.scenario_id,
            "replay_command": [
                "uv",
                "run",
                "python",
                "-m",
                "tests.dst.failure",
                "replay",
                str(arguments.output),
            ],
        }
    else:
        result = replay_failure_bundle(arguments.bundle)
    print(json.dumps(result, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
