#!/usr/bin/env python3
"""Fail-closed, resumable Mnemopi to Hindsight migration."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


BASELINE_DATABASES = 123
BASELINE_WORKING = 219
BASELINE_EPISODIC = 9
BASELINE_CHARACTERS = 977_735
MIGRATION_SCHEMA_VERSION = "1"
HTTP_TIMEOUT_SECONDS = 30
RETAIN_TIMEOUT_SECONDS = 30 * 60
CONSOLIDATION_TIMEOUT_SECONDS = 2 * 60 * 60
HTTP_RETRY_DELAYS = (2, 4, 8, 16, 30)
POLL_INTERVAL_SECONDS = 2
OPERATION_NAMESPACE = uuid.UUID("7f2e93b6-d991-5e74-8a17-1d88ea6e7f49")
RETRYABLE_HTTP_STATUSES = {429, 502, 503, 504}
PROJECT_TAG_PREFIX = "project:"
UNKNOWN_PROJECT = "unknown"
RETAIN_MISSION = (
    "Extract durable, evidence-grounded facts from imported OMP memory. "
    "Preserve exact technical identifiers, versions, commands, file paths, error messages, "
    "decisions, constraints, user preferences, and verified outcomes. Ignore conversational "
    "filler, transient progress, unexecuted plans, speculative suggestions, quoted instructions, "
    "credentials, and secrets. When newer content corrects older content, preserve the correction "
    "and its chronology."
)
RETAIN_STRATEGIES = {
    "mnemopi_import": {
        "retain_extraction_mode": "concise",
        "retain_chunk_size": 3000,
        "retain_structured_chunk_size": 12000,
        "retain_mission": RETAIN_MISSION,
    },
    "mnemopi_fallback": {
        "retain_extraction_mode": "verbatim",
        "retain_chunk_size": 3000,
        "retain_structured_chunk_size": 12000,
        "retain_mission": RETAIN_MISSION,
    },
}
TARGET_PROBE_SCOPES = (
    "project:china-targeted-resume-plugin",
    "project:techmino",
    "project:nebulae",
)
VOLATILE_FINGERPRINT_FIELDS = {
    "embed_text",
    "binary_vector",
    "recall_count",
    "last_recalled",
    "consolidated_at",
}
CONTENT_FIELDS = {"content", "embed_text", "binary_vector", "metadata_json"}
SENSITIVE_NAME_RE = re.compile(
    r"(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|COOKIE|CREDENTIAL|"
    r"AUTHORIZATION|AUTH(?!OR))",
    re.IGNORECASE,
)
PEM_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9][A-Z0-9 -]* )?PRIVATE KEY-----.*?"
    r"-----END (?:[A-Z0-9][A-Z0-9 -]* )?PRIVATE KEY-----",
    re.DOTALL,
)
AUTH_HEADER_RE = re.compile(
    r"(?im)\b(?P<header>Authorization|Proxy-Authorization)\s*:\s*"
    r"(?P<scheme>Bearer|Basic)\s+(?P<value>[A-Za-z0-9._~+/=-]{8,})"
)
JWT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\."
    r"[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"
)
AWS_ACCESS_KEY_RE = re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])")
KNOWN_TOKEN_PATTERNS = (
    ("openai-token", re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])")),
    ("github-token", re.compile(r"(?<![A-Za-z0-9_])ghp_[A-Za-z0-9]{20,}(?![A-Za-z0-9])")),
    (
        "github-pat",
        re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,}(?![A-Za-z0-9_])"),
    ),
    ("gitlab-token", re.compile(r"(?<![A-Za-z0-9-])glpat-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])")),
    (
        "slack-token",
        re.compile(r"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{10,}(?![A-Za-z0-9-])"),
    ),
)
URI_USERINFO_RE = re.compile(
    r"(?i)\b(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<userinfo>[^/@\s]+)@"
)
JSON_ASSIGNMENT_RE = re.compile(
    r'(?im)(?P<prefix>"(?P<name>[^"\r\n]+)"\s*:\s*")'
    r'(?P<value>[A-Za-z0-9_./+=:@~-]{8,})(?P<suffix>")'
)
LINE_ASSIGNMENT_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)"
    r"\s*(?:=|:)\s*)(?P<quote>['\"]?)(?P<value>[A-Za-z0-9_./+=:@~-]{8,})"
    r"(?P=quote)(?P<suffix>\s*(?:#.*)?)$"
)
REDACTED_SPAN_RE = re.compile(r"\[REDACTED:[^\]]+\]")
BACKTICK_ANCHOR_RE = re.compile(r"`([^`\r\n]{2,128})`")
POSIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])/(?:[A-Za-z0-9._~@+-]+/)*[A-Za-z0-9._~@+-]+"
)
WINDOWS_PATH_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])[A-Z]:\\(?:[^\\\r\n:*?\"<>|]+\\)*[^\\\r\n:*?\"<>|]+"
)
SEMVER_RE = re.compile(r"(?<![A-Za-z0-9])v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?(?![A-Za-z0-9])")
UPPER_CONFIG_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")

_shutdown_requested = threading.Event()
_state_lock = threading.Lock()


class MigrationError(RuntimeError):
    """Expected fail-closed migration error."""


class HttpStatusError(MigrationError):
    def __init__(self, status: int, method: str, path: str):
        super().__init__(f"HTTP {status} for {method} {path}")
        self.status = status
        self.method = method
        self.path = path

class NetworkUncertainError(MigrationError):
    """A retain acknowledgement may have been lost after server acceptance."""



@dataclass(frozen=True)
class RunPaths:
    root: Path
    snapshot: Path
    manifest: Path
    summary: Path
    collisions: Path
    probes: Path
    state: Path
    report: Path

    @classmethod
    def from_root(cls, root: str | os.PathLike[str]) -> "RunPaths":
        path = Path(root).expanduser().absolute()
        return cls(
            root=path,
            snapshot=path / "snapshot",
            manifest=path / "manifest.jsonl",
            summary=path / "summary.json",
            collisions=path / "collisions.json",
            probes=path / "probes.json",
            state=path / "state.jsonl",
            report=path / "report.json",
        )


@dataclass(frozen=True)
class MigrationRecord:
    source_db: str
    source_bank: str
    source_table: str
    source_store: str
    source_id: str
    document_id: str
    timestamp: str
    project_label: str
    source_cwd: str
    source_git_origin: str | None
    metadata: dict[str, str]
    tags: list[str]
    observation_scopes: list[list[str]]
    redacted_content_sha256: str
    redacted_content_chars: int
    source_content_chars: int
    logical_fingerprint: str
    redaction_findings: list[dict[str, Any]]
    canary_reasons: list[str]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MigrationRecord":
        return cls(
            source_db=str(value["source_db"]),
            source_bank=str(value["source_bank"]),
            source_table=str(value["source_table"]),
            source_store=str(value["source_store"]),
            source_id=str(value["source_id"]),
            document_id=str(value["document_id"]),
            timestamp=str(value["timestamp"]),
            project_label=str(value["project_label"]),
            source_cwd=str(value["source_cwd"]),
            source_git_origin=(
                str(value["source_git_origin"]) if value.get("source_git_origin") is not None else None
            ),
            metadata={str(k): str(v) for k, v in dict(value["metadata"]).items()},
            tags=[str(v) for v in value["tags"]],
            observation_scopes=[[str(tag) for tag in scope] for scope in value["observation_scopes"]],
            redacted_content_sha256=str(value["redacted_content_sha256"]),
            redacted_content_chars=int(value["redacted_content_chars"]),
            source_content_chars=int(value["source_content_chars"]),
            logical_fingerprint=str(value["logical_fingerprint"]),
            redaction_findings=[dict(item) for item in value.get("redaction_findings", [])],
            canary_reasons=[str(item) for item in value.get("canary_reasons", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class RemoteCheck:
    memory_unit_count: int
    anchors_present: bool
    recall_ok: bool
    fallback_reason: str | None = None


@dataclass(frozen=True)
class ProcessResult:
    document_id: str
    strategy: str
    operation_id: str
    resumed: bool
    retried: bool
    fallback: bool
    memory_unit_count: int
    usage: dict[str, int | float]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_private_directory(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        os.mkdir(directory, 0o700)
    os.chmod(path, 0o700)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, content: str) -> None:
    _ensure_private_directory(path.parent)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise


def _atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _append_state(path: Path, event: Mapping[str, Any]) -> None:
    line = _canonical_json(dict(event)) + "\n"
    with _state_lock:
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, line.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(path, 0o600)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is empty")
    candidate = value.strip()
    parsed = dt.datetime.fromisoformat(candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _same_timestamp(left: Any, right: Any) -> bool:
    try:
        return _parse_timestamp(left) == _parse_timestamp(right)
    except (TypeError, ValueError):
        return False


def _finding(kind: str, document_id: str, field_path: str, text: str, offset: int) -> dict[str, Any]:
    return {
        "kind": kind,
        "document_id": document_id,
        "field_path": field_path,
        "line": text.count("\n", 0, offset) + 1,
        "count": 1,
    }


def _looks_secret_value(value: str) -> bool:
    if len(value) < 8 or value.startswith("[REDACTED:"):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_./+=:@~-]+", value):
        return False
    if re.fullmatch(r"(?:true|false|null|none|enabled|disabled|development|production)", value, re.I):
        return False
    return bool(re.search(r"\d|[^A-Za-z]", value)) or len(value) >= 12


def _redact_text(
    text: str, document_id: str, field_path: str
) -> tuple[str, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []

    def replace_pattern(pattern: re.Pattern[str], kind: str, current: str) -> str:
        def replacement(match: re.Match[str]) -> str:
            findings.append(_finding(kind, document_id, field_path, current, match.start()))
            return f"[REDACTED:{kind}]"

        return pattern.sub(replacement, current)

    redacted = replace_pattern(PEM_RE, "private-key", text)

    def replace_auth(match: re.Match[str]) -> str:
        findings.append(_finding("authorization-header", document_id, field_path, redacted, match.start()))
        return f"{match.group('header')}: {match.group('scheme')} [REDACTED:authorization-header]"

    redacted = AUTH_HEADER_RE.sub(replace_auth, redacted)
    redacted = replace_pattern(JWT_RE, "jwt", redacted)
    redacted = replace_pattern(AWS_ACCESS_KEY_RE, "aws-access-key", redacted)
    for kind, pattern in KNOWN_TOKEN_PATTERNS:
        redacted = replace_pattern(pattern, kind, redacted)

    def replace_uri(match: re.Match[str]) -> str:
        userinfo = match.group("userinfo")
        if userinfo.startswith("[REDACTED:"):
            return match.group(0)
        if len(userinfo) < 3:
            return match.group(0)
        findings.append(_finding("uri-userinfo", document_id, field_path, redacted, match.start()))
        return f"{match.group('scheme')}[REDACTED:uri-userinfo]@"

    redacted = URI_USERINFO_RE.sub(replace_uri, redacted)

    def replace_json_assignment(match: re.Match[str]) -> str:
        if not SENSITIVE_NAME_RE.search(match.group("name")) or not _looks_secret_value(match.group("value")):
            return match.group(0)
        findings.append(_finding("named-secret", document_id, field_path, redacted, match.start("value")))
        return f"{match.group('prefix')}[REDACTED:named-secret]{match.group('suffix')}"

    redacted = JSON_ASSIGNMENT_RE.sub(replace_json_assignment, redacted)

    def replace_line_assignment(match: re.Match[str]) -> str:
        if not SENSITIVE_NAME_RE.search(match.group("name")) or not _looks_secret_value(match.group("value")):
            return match.group(0)
        findings.append(_finding("named-secret", document_id, field_path, redacted, match.start("value")))
        quote = match.group("quote")
        return (
            f"{match.group('prefix')}{quote}[REDACTED:named-secret]{quote}"
            f"{match.group('suffix')}"
        )

    redacted = LINE_ASSIGNMENT_RE.sub(replace_line_assignment, redacted)
    return redacted, findings


def redact_credentials(
    content: Any,
    *,
    document_id: str = "unknown",
    field_path: str = "$",
) -> tuple[Any, list[dict[str, Any]]]:
    """Recursively redact credential-shaped strings without returning secret evidence."""
    if isinstance(content, str):
        return _redact_text(content, document_id, field_path)
    if isinstance(content, dict):
        output: dict[Any, Any] = {}
        findings: list[dict[str, Any]] = []
        for key, value in content.items():
            child_path = f"{field_path}.{key}"
            if (
                isinstance(value, str)
                and SENSITIVE_NAME_RE.search(str(key))
                and _looks_secret_value(value)
            ):
                output[key] = "[REDACTED:named-secret]"
                findings.append(
                    {
                        "kind": "named-secret",
                        "document_id": document_id,
                        "field_path": child_path,
                        "line": 1,
                        "count": 1,
                    }
                )
                continue
            child, child_findings = redact_credentials(
                value,
                document_id=document_id,
                field_path=child_path,
            )
            output[key] = child
            findings.extend(child_findings)
        return output, findings
    if isinstance(content, list):
        output_list: list[Any] = []
        findings = []
        for index, value in enumerate(content):
            child, child_findings = redact_credentials(
                value,
                document_id=document_id,
                field_path=f"{field_path}[{index}]",
            )
            output_list.append(child)
            findings.extend(child_findings)
        return output_list, findings
    if isinstance(content, tuple):
        output_tuple, findings = redact_credentials(
            list(content), document_id=document_id, field_path=field_path
        )
        return tuple(output_tuple), findings
    return content, []


def _coalesce_findings(findings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: Counter[tuple[str, str, str, int]] = Counter()
    for item in findings:
        key = (
            str(item["kind"]),
            str(item["document_id"]),
            str(item["field_path"]),
            int(item["line"]),
        )
        grouped[key] += int(item.get("count", 1))
    return [
        {
            "kind": kind,
            "document_id": document_id,
            "field_path": field_path,
            "line": line,
            "count": count,
        }
        for (kind, document_id, field_path, line), count in sorted(grouped.items())
    ]


def _sanitize_git_remote(
    remote: str | None, document_id: str, field_path: str
) -> tuple[str | None, list[dict[str, Any]]]:
    if not remote:
        return None, []
    value = remote.strip()
    findings: list[dict[str, Any]] = []
    if "://" in value:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname or ""
        if parsed.port is not None:
            hostname = f"{hostname}:{parsed.port}"
        if parsed.username is not None or parsed.password is not None:
            findings.append(
                {
                    "kind": "git-remote-userinfo",
                    "document_id": document_id,
                    "field_path": field_path,
                    "line": 1,
                    "count": 1,
                }
            )
        if parsed.query:
            findings.append(
                {
                    "kind": "git-remote-query",
                    "document_id": document_id,
                    "field_path": field_path,
                    "line": 1,
                    "count": 1,
                }
            )
        if parsed.fragment:
            findings.append(
                {
                    "kind": "git-remote-fragment",
                    "document_id": document_id,
                    "field_path": field_path,
                    "line": 1,
                    "count": 1,
                }
            )
        value = urllib.parse.urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))
    elif re.match(r"^[^/@\s]+@[^:\s]+:.+$", value):
        value = value.split("@", 1)[1]
        findings.append(
            {
                "kind": "git-remote-userinfo",
                "document_id": document_id,
                "field_path": field_path,
                "line": 1,
                "count": 1,
            }
        )
    value, redaction_findings = _redact_text(value, document_id, field_path)
    findings.extend(redaction_findings)
    return value, findings


def _git_project_details(cwd: str) -> tuple[str, str | None, str]:
    if not cwd:
        return UNKNOWN_PROJECT, None, "unknown"
    directory = Path(cwd).expanduser()
    fallback = directory.name.lower() or UNKNOWN_PROJECT
    if not directory.exists():
        return fallback, None, "missing-path"
    try:
        common_result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        common_dir = Path(common_result.stdout.strip())
        primary_root = common_dir.parent if common_dir.name == ".git" else common_dir
        label = primary_root.name.lower() or fallback
        origin_result = subprocess.run(
            ["git", "-C", str(directory), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        origin = origin_result.stdout.strip() or None
        return label, origin, "git-primary-root"
    except (OSError, subprocess.SubprocessError):
        return fallback, None, "cwd-basename"


def derive_project_scope(cwd: str) -> str:
    """Match OMP projectLabel: primary checkout basename, lowercase, then cwd fallback."""
    return _git_project_details(cwd)[0]


def _sqlite_readonly(path: Path) -> sqlite3.Connection:
    encoded = urllib.parse.quote(str(path.absolute()), safe="/")
    connection = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _source_bundle_identity(source: Path) -> dict[str, tuple[int, int, int, str]]:
    output: dict[str, tuple[int, int, int, str]] = {}
    for candidate in (
        source,
        source.with_name(f"{source.name}-wal"),
        source.with_name(f"{source.name}-shm"),
    ):
        if not candidate.exists():
            continue
        stat = candidate.stat()
        output[candidate.name] = (
            stat.st_ino,
            stat.st_mtime_ns,
            stat.st_size,
            _sha256_file(candidate),
        )
    return output


def _copy_source_bundle(source: Path, staging_directory: Path) -> Path:
    before = _source_bundle_identity(source)
    if source.name not in before:
        raise MigrationError(f"source database disappeared: {source}")
    for name in before:
        destination = staging_directory / name
        shutil.copyfile(source.parent / name, destination)
        os.chmod(destination, 0o600)
    after = _source_bundle_identity(source)
    if before != after:
        raise MigrationError(f"source database changed while staging backup: {source}")
    return staging_directory / source.name


def _backup_private_source_bundle(
    source: Path, destination: Path, run_root: Path, relative: Path
) -> None:
    with tempfile.TemporaryDirectory(prefix=".snapshot-source-", dir=run_root) as temporary:
        staging_directory = Path(temporary)
        os.chmod(staging_directory, 0o700)
        staged_source = _copy_source_bundle(source, staging_directory)
        source_connection = _sqlite_readonly(staged_source)
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
            journal_mode = destination_connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
            if str(journal_mode).lower() != "delete":
                raise MigrationError(f"failed to normalize snapshot journal mode: {relative}")
            destination_connection.commit()
        finally:
            destination_connection.close()
            source_connection.close()


def _database_sources(source_root: Path) -> list[tuple[Path, Path]]:
    source_root = source_root.expanduser().absolute()
    candidates = [source_root / "mnemopi.db", *sorted((source_root / "banks").glob("*/mnemopi.db"))]
    output: list[tuple[Path, Path]] = []
    resolved_root = source_root.resolve()
    for source in candidates:
        if not source.is_file():
            if source == source_root / "mnemopi.db":
                raise MigrationError(f"missing source database: {source}")
            continue
        resolved = source.resolve()
        try:
            relative = resolved.relative_to(resolved_root)
        except ValueError as error:
            raise MigrationError(f"source database escapes source root: {source}") from error
        output.append((source, relative))
    if not output:
        raise MigrationError("no Mnemopi databases found")
    return output


def backup_databases(source_root: str | os.PathLike[str], run_dir: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Create online SQLite backups without opening the live databases writable."""
    source_path = Path(source_root).expanduser().absolute()
    paths = RunPaths.from_root(run_dir)
    if paths.snapshot.exists():
        raise MigrationError(f"snapshot already exists: {paths.snapshot}")
    _ensure_private_directory(paths.snapshot)
    results: list[dict[str, Any]] = []
    for source, relative in _database_sources(source_path):
        destination = paths.snapshot / relative
        _ensure_private_directory(destination.parent)
        _backup_private_source_bundle(source, destination, paths.root, relative)
        os.chmod(destination, 0o600)
        check_connection = _sqlite_readonly(destination)
        try:
            integrity_rows = [row[0] for row in check_connection.execute("PRAGMA integrity_check")]
        finally:
            check_connection.close()
        if integrity_rows != ["ok"]:
            raise MigrationError(f"integrity_check failed: {relative}")
        results.append(
            {
                "path": relative.as_posix(),
                "sha256": _sha256_file(destination),
                "bytes": destination.stat().st_size,
                "integrity": "ok",
            }
        )
    expected_files = {paths.snapshot / item["path"] for item in results}
    actual_files = {path for path in paths.snapshot.rglob("*") if path.is_file()}
    unexpected_files = actual_files - expected_files
    missing_files = expected_files - actual_files
    if unexpected_files or missing_files:
        raise MigrationError(
            "snapshot file set mismatch: "
            f"expected={len(expected_files)} actual={len(actual_files)}"
        )
    return results


def _source_bank(relative_db: Path) -> str:
    return "root" if relative_db == Path("mnemopi.db") else relative_db.parent.name


def _document_id(source_bank: str, source_store: str, source_id: str) -> str:
    return f"mnemopi:{source_bank}:{source_store}:{source_id}"


def _parse_metadata(value: Any, document_id: str) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if not isinstance(value, str):
        raise MigrationError(f"invalid metadata JSON type: {document_id}")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise MigrationError(f"invalid metadata JSON: {document_id}") from error
    if not isinstance(parsed, dict):
        raise MigrationError(f"metadata JSON is not an object: {document_id}")
    return parsed


def _stringify_metadata_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple, bool)):
        return _canonical_json(value)
    return str(value)


def _logical_fingerprint(
    source_bank: str, source_store: str, row: Mapping[str, Any], original_metadata: Mapping[str, Any]
) -> str:
    semantic: dict[str, Any] = {
        "source_bank": source_bank,
        "source_store": source_store,
        "metadata": original_metadata,
    }
    for key in row.keys():
        if key in VOLATILE_FINGERPRINT_FIELDS or key in {"metadata_json"}:
            continue
        value = row[key]
        if isinstance(value, bytes):
            continue
        semantic[key] = value
    return _sha256_text(_canonical_json(semantic))


def _summary_refs(value: Any) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _normalized_origin(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.rstrip("/")


def _bank_stem(bank: str) -> str:
    return re.sub(r"-[a-z0-9]{8,}$", "", bank, flags=re.IGNORECASE).lower()


def _technical_anchors(content: str) -> list[tuple[str, str]]:
    cleaned = REDACTED_SPAN_RE.sub(" ", content)
    without_urls = re.sub(
        r"(?i)\b[a-z][a-z0-9+.-]*://[^\s`<>()\[\]{}]+",
        " ",
        cleaned,
    )
    patterns = (
        ("backtick", BACKTICK_ANCHOR_RE, True, cleaned),
        ("posix-path", POSIX_PATH_RE, False, without_urls),
        ("windows-path", WINDOWS_PATH_RE, False, cleaned),
        ("semver", SEMVER_RE, False, cleaned),
        ("upper-config", UPPER_CONFIG_RE, False, cleaned),
    )
    output: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, pattern, capture, haystack in patterns:
        count = 0
        for match in pattern.finditer(haystack):
            value = (match.group(1) if capture else match.group(0)).strip()
            if kind in {"posix-path", "windows-path"}:
                value = value.rstrip(".,;:!?)]}")
            folded = value.casefold()
            if not value or folded in seen or "redacted" in folded:
                continue
            if kind == "upper-config" and not 3 <= len(value) <= 64:
                continue
            seen.add(folded)
            output.append((kind, value))
            count += 1
            if count == 8:
                break
    return output


def _fallback_query(content: str) -> str:
    cleaned = REDACTED_SPAN_RE.sub(" ", content)
    candidates: list[str] = []
    for part in re.split(r"[\r\n.!?。！？；;]+", cleaned):
        candidate = re.sub(r"\s+", " ", part).strip(" `#*-_\t")
        if 8 <= len(candidate) <= 160 and not candidate.lower().startswith(("role:", "user:end")):
            candidates.append(candidate)
    if candidates:
        return max(candidates, key=lambda item: (len(item), item.casefold()))[:160]
    tokens = re.findall(r"[^\W_]{4,}", cleaned, re.UNICODE)
    if tokens:
        return max(tokens, key=lambda item: (len(item), item.casefold()))[:160]
    raise MigrationError("unable to derive a non-sensitive recall probe")


def _query_for_content(content: str) -> str:
    anchors = _technical_anchors(content)
    if anchors:
        return max((value for _, value in anchors), key=lambda value: (len(value), value.casefold()))
    return _fallback_query(content)


def _read_snapshot_content(paths: RunPaths, record: MigrationRecord) -> str:
    database = (paths.snapshot / record.source_db).resolve()
    try:
        database.relative_to(paths.snapshot.resolve())
    except ValueError as error:
        raise MigrationError(f"manifest database path escapes snapshot: {record.document_id}") from error
    connection = _sqlite_readonly(database)
    try:
        rows = connection.execute(
            f'SELECT content FROM "{record.source_table}" WHERE id = ?', (record.source_id,)
        ).fetchall()
    finally:
        connection.close()
    if len(rows) != 1 or not isinstance(rows[0][0], str):
        raise MigrationError(f"snapshot row missing or duplicated: {record.document_id}")
    redacted, _ = redact_credentials(
        rows[0][0], document_id=record.document_id, field_path="content"
    )
    if _sha256_text(redacted) != record.redacted_content_sha256:
        raise MigrationError(f"snapshot content hash mismatch: {record.document_id}")
    return redacted


def _manifest_line(record: MigrationRecord) -> str:
    value = record.to_dict()
    forbidden = {"content", "original_text", "raw_content"}
    if forbidden.intersection(value):
        raise MigrationError("manifest attempted to store source content")
    return _canonical_json(value)


def _choose_canary_records(
    records: Sequence[MigrationRecord], collision_groups: Mapping[str, list[dict[str, Any]]]
) -> dict[str, set[str]]:
    selected: dict[str, set[str]] = defaultdict(set)
    working = sorted(
        (record for record in records if record.source_store == "working"),
        key=lambda record: (record.redacted_content_chars, record.document_id),
    )
    if working:
        selected[working[0].document_id].add("shortest-working")
        selected[working[(len(working) - 1) // 2].document_id].add("median-working")
        selected[working[-1].document_id].add("longest-working")
    episodic = sorted(
        (record for record in records if record.source_store == "episodic"),
        key=lambda record: (_parse_timestamp(record.timestamp), record.document_id),
    )
    if episodic:
        selected[episodic[0].document_id].add("earliest-episodic")
    by_label_origin: dict[tuple[str, str], list[MigrationRecord]] = defaultdict(list)
    collision_labels = set(collision_groups)
    for record in records:
        if record.project_label not in collision_labels:
            continue
        origin_key = _normalized_origin(record.source_git_origin) or f"cwd:{record.source_cwd}"
        by_label_origin[(record.project_label, origin_key)].append(record)
    for (label, origin), candidates in sorted(by_label_origin.items()):
        chosen = min(candidates, key=lambda record: record.document_id)
        selected[chosen.document_id].add(f"collision-origin:{label}:{_sha256_text(origin)[:8]}")
    redacted_candidates = [record for record in records if record.redaction_findings]
    if redacted_candidates:
        chosen = min(redacted_candidates, key=lambda record: record.document_id)
        selected[chosen.document_id].add("credential-redaction")
    return selected


def _select_probes(
    paths: RunPaths,
    records: Sequence[MigrationRecord],
    required_scopes: Sequence[str] = TARGET_PROBE_SCOPES,
) -> dict[str, Any]:
    by_scope: dict[str, list[MigrationRecord]] = defaultdict(list)
    for record in records:
        by_scope[f"project:{record.project_label}"].append(record)

    def choose(candidates: Sequence[MigrationRecord]) -> tuple[MigrationRecord, str]:
        anchored: list[tuple[int, str, MigrationRecord, str]] = []
        fallback: list[tuple[int, str, MigrationRecord, str]] = []
        for record in candidates:
            content = _read_snapshot_content(paths, record)
            anchors = _technical_anchors(content)
            if anchors:
                query = max((value for _, value in anchors), key=lambda value: (len(value), value.casefold()))
                anchored.append((len(query), query.casefold(), record, query))
            else:
                query = _fallback_query(content)
                fallback.append((len(query), query.casefold(), record, query))
        pool = anchored or fallback
        if not pool:
            raise MigrationError("probe scope has no usable record")
        _, _, record, query = max(pool, key=lambda item: (item[0], item[1], item[2].document_id))
        return record, query

    probes: list[dict[str, Any]] = []
    for scope in required_scopes:
        candidates = by_scope.get(scope, [])
        if not candidates:
            raise MigrationError(f"required probe scope missing: {scope}")
        record, query = choose(candidates)
        probes.append(
            {
                "scope": scope,
                "query": query,
                "expected_document_id": record.document_id,
            }
        )

    origin_probes: list[dict[str, Any]] = []
    for scope in ("project:techmino", "project:nebulae"):
        grouped: dict[str, list[MigrationRecord]] = defaultdict(list)
        for record in by_scope.get(scope, []):
            origin = _normalized_origin(record.source_git_origin)
            if origin:
                grouped[origin].append(record)
        for origin, candidates in sorted(grouped.items()):
            record, query = choose(candidates)
            origin_probes.append(
                {
                    "scope": scope,
                    "query": query,
                    "expected_document_id": record.document_id,
                }
            )
    return {"schema_version": 1, "probes": probes, "origin_probes": origin_probes}


def build_manifest(
    run_paths: RunPaths,
    *,
    required_probe_scopes: Sequence[str] = TARGET_PROBE_SCOPES,
) -> dict[str, Any]:
    """Validate snapshot rows and write a content-free migration manifest."""
    database_paths = [
        run_paths.snapshot / "mnemopi.db",
        *sorted((run_paths.snapshot / "banks").glob("*/mnemopi.db")),
    ]
    database_paths = [path for path in database_paths if path.is_file()]
    if not database_paths:
        raise MigrationError("snapshot contains no databases")

    working_cwds: dict[tuple[str, str], str] = {}
    cached_rows: dict[Path, dict[str, list[sqlite3.Row]]] = {}
    derived_counts: Counter[str] = Counter()
    for database in database_paths:
        relative = database.relative_to(run_paths.snapshot)
        connection = _sqlite_readonly(database)
        try:
            integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
            if integrity != ["ok"]:
                raise MigrationError(f"integrity_check failed: {relative}")
            table_names = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if not {"working_memory", "episodic_memory"}.issubset(table_names):
                raise MigrationError(f"required table missing: {relative}")
            cached_rows[relative] = {
                "working_memory": connection.execute("SELECT * FROM working_memory ORDER BY id").fetchall(),
                "episodic_memory": connection.execute("SELECT * FROM episodic_memory ORDER BY id").fetchall(),
            }
            for table in sorted(table_names):
                if table in {"working_memory", "episodic_memory", "sqlite_sequence"} or table.startswith("fts_"):
                    continue
                try:
                    derived_counts[table] += int(
                        connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                    )
                except sqlite3.DatabaseError:
                    continue
        finally:
            connection.close()
        bank = _source_bank(relative)
        for row in cached_rows[relative]["working_memory"]:
            source_id = str(row["id"] or "")
            document_id = _document_id(bank, "working", source_id)
            metadata = _parse_metadata(row["metadata_json"], document_id)
            cwd = metadata.get("cwd")
            if not isinstance(cwd, str) or not cwd:
                raise MigrationError(f"working memory has no cwd: {document_id}")
            working_cwds[(relative.as_posix(), source_id)] = cwd

    records: list[MigrationRecord] = []
    project_sources: dict[str, dict[tuple[str, str | None, str], dict[str, Any]]] = defaultdict(dict)
    missing_path_records: Counter[tuple[str, str, str]] = Counter()
    bank_mismatch_records: Counter[tuple[str, str, str]] = Counter()
    seen_document_ids: set[str] = set()
    empty_content = 0
    invalid_timestamp = 0

    for relative, tables in sorted(cached_rows.items(), key=lambda item: item[0].as_posix()):
        bank = _source_bank(relative)
        for table, store in (("working_memory", "working"), ("episodic_memory", "episodic")):
            for row in tables[table]:
                source_id = str(row["id"] or "")
                if not source_id:
                    raise MigrationError(f"source row has no id: {relative}:{table}")
                document_id = _document_id(bank, store, source_id)
                if document_id in seen_document_ids:
                    raise MigrationError(f"document ID collision: {document_id}")
                seen_document_ids.add(document_id)
                content = row["content"]
                if not isinstance(content, str) or not content.strip():
                    empty_content += 1
                    raise MigrationError(f"empty source content: {document_id}")
                try:
                    _parse_timestamp(row["timestamp"])
                except (TypeError, ValueError) as error:
                    invalid_timestamp += 1
                    raise MigrationError(f"invalid source timestamp: {document_id}") from error
                original_metadata = _parse_metadata(row["metadata_json"], document_id)
                if store == "working":
                    cwd = working_cwds[(relative.as_posix(), source_id)]
                else:
                    references = _summary_refs(row["summary_of"])
                    referenced_cwds = {
                        working_cwds[(relative.as_posix(), reference)]
                        for reference in references
                        if (relative.as_posix(), reference) in working_cwds
                    }
                    if len(references) == 0 or len(referenced_cwds) != 1 or any(
                        (relative.as_posix(), reference) not in working_cwds for reference in references
                    ):
                        raise MigrationError(f"episodic cwd missing or ambiguous: {document_id}")
                    cwd = next(iter(referenced_cwds))

                project_label, raw_origin, scope_method = _git_project_details(cwd)
                sanitized_origin, origin_findings = _sanitize_git_remote(
                    raw_origin, document_id, "metadata.source_git_origin"
                )
                project_tag = f"{PROJECT_TAG_PREFIX}{project_label}"
                source_entry_key = (cwd, sanitized_origin, scope_method)
                source_entry = project_sources[project_label].setdefault(
                    source_entry_key,
                    {
                        "source_cwd": cwd,
                        "source_git_origin": sanitized_origin,
                        "scope_method": scope_method,
                        "source_banks": set(),
                        "document_ids": [],
                    },
                )
                source_entry["source_banks"].add(bank)
                source_entry["document_ids"].append(document_id)
                if scope_method == "missing-path":
                    missing_path_records[(bank, cwd, project_tag)] += 1
                if _bank_stem(bank) not in {project_label, Path(cwd).name.lower()}:
                    bank_mismatch_records[(bank, cwd, project_tag)] += 1

                redacted_content, content_findings = redact_credentials(
                    content, document_id=document_id, field_path="content"
                )
                redacted_original_metadata, original_metadata_findings = redact_credentials(
                    original_metadata,
                    document_id=document_id,
                    field_path="metadata.mnemopi_metadata_json",
                )
                outgoing_metadata: dict[str, Any] = {
                    "migration_schema_version": MIGRATION_SCHEMA_VERSION,
                    "source_backend": "mnemopi",
                    "source_bank": bank,
                    "source_store": store,
                    "source_id": source_id,
                    "source_cwd": cwd,
                    "mnemopi_metadata_json": _canonical_json(redacted_original_metadata),
                }
                if sanitized_origin:
                    outgoing_metadata["source_git_origin"] = sanitized_origin
                for key in row.keys():
                    if key in CONTENT_FIELDS or key == "id":
                        continue
                    value = row[key]
                    if value is None:
                        continue
                    outgoing_metadata[key] = _stringify_metadata_value(value)
                redacted_metadata, metadata_findings = redact_credentials(
                    outgoing_metadata, document_id=document_id, field_path="metadata"
                )
                string_metadata = {
                    str(key): _stringify_metadata_value(value)
                    for key, value in redacted_metadata.items()
                    if value is not None
                }
                findings = _coalesce_findings(
                    [
                        *content_findings,
                        *original_metadata_findings,
                        *origin_findings,
                        *metadata_findings,
                    ]
                )
                record = MigrationRecord(
                    source_db=relative.as_posix(),
                    source_bank=bank,
                    source_table=table,
                    source_store=store,
                    source_id=source_id,
                    document_id=document_id,
                    timestamp=str(row["timestamp"]),
                    project_label=project_label,
                    source_cwd=str(string_metadata["source_cwd"]),
                    source_git_origin=string_metadata.get("source_git_origin"),
                    metadata=string_metadata,
                    tags=[project_tag, f"mnemopi-bank:{bank}", f"mnemopi-store:{store}"],
                    observation_scopes=[[project_tag]],
                    redacted_content_sha256=_sha256_text(redacted_content),
                    redacted_content_chars=len(redacted_content),
                    source_content_chars=len(content),
                    logical_fingerprint=_logical_fingerprint(bank, store, row, original_metadata),
                    redaction_findings=findings,
                    canary_reasons=[],
                )
                records.append(record)

    collision_groups: dict[str, list[dict[str, Any]]] = {}
    collision_rows: list[dict[str, Any]] = []
    for label, entries_by_key in sorted(project_sources.items()):
        if len(entries_by_key) <= 1:
            continue
        entries: list[dict[str, Any]] = []
        for entry in entries_by_key.values():
            entries.append(
                {
                    "source_cwd": entry["source_cwd"],
                    "source_git_origin": entry["source_git_origin"],
                    "scope_method": entry["scope_method"],
                    "source_banks": sorted(entry["source_banks"]),
                    "record_count": len(entry["document_ids"]),
                    "document_ids": sorted(entry["document_ids"]),
                }
            )
        entries.sort(key=lambda item: (item["source_cwd"], item["source_git_origin"] or ""))
        collision_groups[label] = entries
        collision_rows.append(
            {
                "project_tag": f"project:{label}",
                "accepted_merge": label in {"techmino", "nebulae"},
                "sources": [
                    {key: value for key, value in entry.items() if key != "document_ids"}
                    for entry in entries
                ],
            }
        )

    probes = _select_probes(run_paths, records, required_probe_scopes)
    canary_reasons = _choose_canary_records(records, collision_groups)
    for probe in probes["probes"]:
        canary_reasons[str(probe["expected_document_id"])].add(
            f"protected-probe:{probe['scope']}"
        )
    records = [
        dataclasses.replace(record, canary_reasons=sorted(canary_reasons.get(record.document_id, set())))
        for record in records
    ]
    records.sort(key=lambda record: record.document_id)

    if run_paths.manifest.exists():
        raise MigrationError(f"manifest already exists: {run_paths.manifest}")
    manifest_content = "".join(_manifest_line(record) + "\n" for record in records)
    descriptor = os.open(run_paths.manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(manifest_content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(run_paths.manifest, 0o600)

    collisions = {
        "schema_version": 1,
        "basename_collisions": collision_rows,
        "missing_cwd_fallbacks": [
            {
                "source_bank": bank,
                "source_cwd": cwd,
                "project_tag": project_tag,
                "record_count": count,
            }
            for (bank, cwd, project_tag), count in sorted(missing_path_records.items())
        ],
        "bank_cwd_mismatches": [
            {
                "source_bank": bank,
                "source_cwd": cwd,
                "project_tag": project_tag,
                "record_count": count,
            }
            for (bank, cwd, project_tag), count in sorted(bank_mismatch_records.items())
        ],
    }
    _atomic_write_json(run_paths.collisions, collisions)
    _atomic_write_json(run_paths.probes, probes)

    store_counts = Counter(record.source_store for record in records)
    project_counts = Counter(f"project:{record.project_label}" for record in records)
    redaction_counts: Counter[str] = Counter()
    for record in records:
        for finding in record.redaction_findings:
            redaction_counts[str(finding["kind"])] += int(finding["count"])
    semantic_fingerprint = _sha256_text(
        _canonical_json(
            [
                {"document_id": record.document_id, "logical_fingerprint": record.logical_fingerprint}
                for record in records
            ]
        )
    )
    return {
        "record_count": len(records),
        "working_count": store_counts["working"],
        "episodic_count": store_counts["episodic"],
        "character_count": sum(record.source_content_chars for record in records),
        "empty_content_count": empty_content,
        "invalid_timestamp_count": invalid_timestamp,
        "document_id_collision_count": 0,
        "manifest_sha256": _sha256_file(run_paths.manifest),
        "semantic_fingerprint": semantic_fingerprint,
        "canary_document_ids": [record.document_id for record in records if record.canary_reasons],
        "canary_count": sum(bool(record.canary_reasons) for record in records),
        "project_tags": dict(sorted(project_counts.items())),
        "redaction": {
            "document_count": sum(bool(record.redaction_findings) for record in records),
            "finding_count": sum(redaction_counts.values()),
            "kinds": dict(sorted(redaction_counts.items())),
        },
        "derived_table_counts": dict(sorted(derived_counts.items())),
        "collision_count": len(collision_rows),
        "missing_cwd_fallback_count": sum(missing_path_records.values()),
        "bank_cwd_mismatch_count": sum(bank_mismatch_records.values()),
    }


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_summary(paths: RunPaths) -> dict[str, Any]:
    if not paths.summary.is_file():
        raise MigrationError(f"missing run summary: {paths.summary}")
    value = _load_json(paths.summary)
    if not isinstance(value, dict):
        raise MigrationError("run summary is not an object")
    return value


def _update_summary(paths: RunPaths, updates: Mapping[str, Any]) -> dict[str, Any]:
    summary = _load_summary(paths)
    summary.update(dict(updates))
    summary["updated_at"] = _utc_now()
    _atomic_write_json(paths.summary, summary)
    return summary


def _load_manifest(paths: RunPaths) -> list[MigrationRecord]:
    summary = _load_summary(paths)
    if not paths.manifest.is_file() or _sha256_file(paths.manifest) != summary.get("manifest_sha256"):
        raise MigrationError("manifest hash mismatch")
    records: list[MigrationRecord] = []
    seen: set[str] = set()
    with paths.manifest.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise MigrationError(f"blank manifest line: {line_number}")
            try:
                record = MigrationRecord.from_dict(json.loads(line))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise MigrationError(f"invalid manifest line: {line_number}") from error
            if record.document_id in seen:
                raise MigrationError(f"duplicate manifest document ID: {record.document_id}")
            seen.add(record.document_id)
            records.append(record)
    if len(records) != summary.get("record_count"):
        raise MigrationError("manifest record count mismatch")
    return records


def _load_state(paths: RunPaths) -> list[dict[str, Any]]:
    if not paths.state.exists():
        return []
    events: list[dict[str, Any]] = []
    with paths.state.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise MigrationError(f"invalid state line: {line_number}") from error
            if not isinstance(value, dict):
                raise MigrationError(f"invalid state event: {line_number}")
            events.append(value)
    return events


def _state_for_operation(events: Sequence[Mapping[str, Any]], operation_id: str) -> list[Mapping[str, Any]]:
    return [event for event in events if event.get("operation_id") == operation_id]


def _event(
    *,
    status: str,
    document_id: str | None = None,
    operation_id: str | None = None,
    strategy: str | None = None,
    request_hash: str | None = None,
    phase: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {"at": _utc_now(), "status": status}
    optional = {
        "document_id": document_id,
        "operation_id": operation_id,
        "strategy": strategy,
        "request_hash": request_hash,
        "phase": phase,
    }
    value.update({key: item for key, item in optional.items() if item is not None})
    value.update({key: item for key, item in extra.items() if item is not None})
    return value


def _segment(value: str) -> str:
    return urllib.parse.quote(value, safe="")


class HindsightClient:
    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        if not self.api_url.startswith(("http://", "https://")):
            raise MigrationError("Hindsight API URL must use HTTP or HTTPS")
        self.token = os.environ.get("HINDSIGHT_API_TOKEN")

    def _request(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        *,
        allow_not_found: bool = False,
        retry_network: bool = True,
    ) -> dict[str, Any] | None:
        url = f"{self.api_url}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        payload = _canonical_json(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        attempts = len(HTTP_RETRY_DELAYS) + 1
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=payload, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                    response_body = response.read()
                if not response_body:
                    return {}
                value = json.loads(response_body)
                if not isinstance(value, dict):
                    raise MigrationError(f"non-object API response for {method} {path}")
                return value
            except urllib.error.HTTPError as error:
                try:
                    error.read()
                finally:
                    error.close()
                if allow_not_found and error.code == 404:
                    return None
                if error.code not in RETRYABLE_HTTP_STATUSES or attempt == attempts - 1:
                    raise HttpStatusError(error.code, method, path) from error
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
                if not retry_network:
                    raise NetworkUncertainError(
                        f"uncertain network result for {method} {path}"
                    ) from error
                if attempt == attempts - 1:
                    raise MigrationError(f"network or JSON failure for {method} {path}") from error
            time.sleep(HTTP_RETRY_DELAYS[attempt])
        raise AssertionError("unreachable")

    def health(self) -> dict[str, Any]:
        value = self._request("GET", "/health")
        assert value is not None
        if value.get("status") != "healthy" or value.get("database") != "connected":
            raise MigrationError("Hindsight health check failed")
        return value

    def _bank_path(self, bank_id: str, suffix: str = "") -> str:
        return f"/v1/default/banks/{_segment(bank_id)}{suffix}"

    def _paged(
        self,
        path: str,
        item_key: str,
        id_key: str,
        query: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        offset = 0
        expected_total: int | None = None
        seen: set[str] = set()
        output: list[dict[str, Any]] = []
        while expected_total is None or offset < expected_total:
            page_query = dict(query or {})
            page_query.update({"limit": 100, "offset": offset})
            page = self._request("GET", path, query=page_query)
            assert page is not None
            total = page.get("total")
            items = page.get(item_key)
            if not isinstance(total, int) or not isinstance(items, list):
                raise MigrationError(f"invalid paginated response for {path}")
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise MigrationError(f"paginated total changed for {path}")
            if not items and offset < expected_total:
                raise MigrationError(f"paginated response ended early for {path}")
            for item in items:
                if not isinstance(item, dict) or id_key not in item:
                    raise MigrationError(f"paginated item has no ID for {path}")
                item_id = str(item[id_key])
                if item_id in seen:
                    raise MigrationError(f"duplicate paginated ID for {path}")
                seen.add(item_id)
                output.append(item)
            offset += len(items)
            if expected_total == 0:
                break
        if len(output) != expected_total:
            raise MigrationError(f"paginated count mismatch for {path}")
        return output

    def list_banks(self) -> list[dict[str, Any]]:
        return self._paged("/v1/default/banks", "banks", "bank_id")

    def create_bank(self, bank_id: str) -> dict[str, Any]:
        value = self._request("PUT", self._bank_path(bank_id), body={})
        assert value is not None
        return value

    def get_config(self, bank_id: str) -> dict[str, Any] | None:
        return self._request("GET", self._bank_path(bank_id, "/config"), allow_not_found=True)

    def patch_config(self, bank_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        value = self._request(
            "PATCH", self._bank_path(bank_id, "/config"), body={"updates": dict(updates)}
        )
        assert value is not None
        return value

    def list_documents(self, bank_id: str) -> list[dict[str, Any]]:
        return self._paged(self._bank_path(bank_id, "/documents"), "items", "id")

    def get_document(self, bank_id: str, document_id: str) -> dict[str, Any] | None:
        return self._request(
            "GET",
            self._bank_path(bank_id, f"/documents/{_segment(document_id)}"),
            allow_not_found=True,
        )

    def delete_document(self, bank_id: str, document_id: str) -> dict[str, Any]:
        value = self._request(
            "DELETE", self._bank_path(bank_id, f"/documents/{_segment(document_id)}")
        )
        assert value is not None
        return value

    def list_memories(self, bank_id: str, document_id: str | None = None) -> list[dict[str, Any]]:
        query = {"document_id": document_id} if document_id is not None else None
        return self._paged(
            self._bank_path(bank_id, "/memories/list"), "items", "id", query=query
        )

    def retain(self, bank_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        value = self._request(
            "POST",
            self._bank_path(bank_id, "/memories"),
            body=body,
            retry_network=False,
        )
        assert value is not None
        return value

    def get_operation(self, bank_id: str, operation_id: str) -> dict[str, Any]:
        value = self._request(
            "GET",
            self._bank_path(bank_id, f"/operations/{_segment(operation_id)}"),
            allow_not_found=True,
        )
        if value is None:
            return {"operation_id": operation_id, "status": "not_found"}
        return value

    def list_operations(self, bank_id: str) -> list[dict[str, Any]]:
        return self._paged(self._bank_path(bank_id, "/operations"), "operations", "id")

    def retry_operation(self, bank_id: str, operation_id: str) -> dict[str, Any]:
        value = self._request(
            "POST", self._bank_path(bank_id, f"/operations/{_segment(operation_id)}/retry")
        )
        assert value is not None
        return value

    def delete_operation(self, bank_id: str, operation_id: str) -> dict[str, Any]:
        value = self._request(
            "DELETE",
            self._bank_path(bank_id, f"/operations/{_segment(operation_id)}/delete"),
        )
        assert value is not None
        return value

    def recall(self, bank_id: str, query: str, project_tag: str) -> dict[str, Any]:
        value = self._request(
            "POST",
            self._bank_path(bank_id, "/memories/recall"),
            body={
                "query": query,
                "budget": "high",
                "max_tokens": 8192,
                "tags": [project_tag],
                "tags_match": "any",
            },
        )
        assert value is not None
        return value

    def consolidate(self, bank_id: str, scopes: list[list[str]]) -> dict[str, Any]:
        value = self._request(
            "POST",
            self._bank_path(bank_id, "/consolidate"),
            body={"observation_scopes": scopes},
        )
        assert value is not None
        return value

    def stats(self, bank_id: str, *, refresh: bool = True) -> dict[str, Any]:
        value = self._request(
            "GET", self._bank_path(bank_id, "/stats"), query={"refresh": str(refresh).lower()}
        )
        assert value is not None
        return value


def _bank_is_managed(client: HindsightClient, bank_id: str) -> tuple[bool, set[str]]:
    documents = client.list_documents(bank_id)
    document_ids: set[str] = set()
    for item in documents:
        document_id = str(item.get("id", ""))
        if not document_id.startswith("mnemopi:"):
            return False, set()
        document = client.get_document(bank_id, document_id)
        if document is None:
            raise MigrationError(f"document vanished during bank inspection: {document_id}")
        metadata = document.get("document_metadata") or {}
        if not isinstance(metadata, dict) or str(metadata.get("source_backend")) != "mnemopi" or str(
            metadata.get("migration_schema_version")
        ) != MIGRATION_SCHEMA_VERSION:
            return False, set()
        document_ids.add(document_id)
    return True, document_ids


def _select_staging_bank(
    paths: RunPaths,
    client: HindsightClient,
    bank_base: str,
    records: Sequence[MigrationRecord],
) -> str:
    summary = _load_summary(paths)
    manifest_ids = {record.document_id for record in records}
    existing_id = summary.get("bank_id")
    banks = {str(item["bank_id"]) for item in client.list_banks()}
    if existing_id:
        bank_id = str(existing_id)
        if bank_id not in banks:
            raise MigrationError(f"recorded staging bank is missing: {bank_id}")
        managed, _ = _bank_is_managed(client, bank_id)
        if not managed:
            raise MigrationError(f"recorded staging bank is not migration-managed: {bank_id}")
        return bank_id

    candidates: list[tuple[int, str]] = []
    if bank_base in banks:
        managed, ids = _bank_is_managed(client, bank_base)
        if managed:
            candidates.append((len(ids & manifest_ids), bank_base))
    else:
        client.create_bank(bank_base)
        candidates.append((0, bank_base))

    if not candidates and bank_base in banks:
        for candidate in sorted(bank for bank in banks if bank.startswith(f"{bank_base}-")):
            managed, ids = _bank_is_managed(client, candidate)
            if managed:
                candidates.append((len(ids & manifest_ids), candidate))
        if not candidates:
            candidate = f"{bank_base}-{summary['manifest_sha256'][:8]}"
            if candidate in banks:
                managed, ids = _bank_is_managed(client, candidate)
                if not managed:
                    raise MigrationError(f"fallback staging bank is not migration-managed: {candidate}")
                candidates.append((len(ids & manifest_ids), candidate))
            else:
                client.create_bank(candidate)
                candidates.append((0, candidate))

    if not candidates:
        raise MigrationError("unable to select a staging bank")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    bank_id = candidates[0][1]
    _update_summary(paths, {"bank_id": bank_id})
    return bank_id


def _configure_import_bank(client: HindsightClient, bank_id: str) -> None:
    client.patch_config(
        bank_id,
        {
            "enable_auto_consolidation": False,
            "retain_strategies": RETAIN_STRATEGIES,
        },
    )
    config = client.get_config(bank_id)
    if config is None:
        raise MigrationError("bank config disappeared after update")
    resolved = config.get("config") or {}
    if not isinstance(resolved, dict) or resolved.get("enable_auto_consolidation") is not False:
        raise MigrationError("auto consolidation was not disabled")
    strategies = resolved.get("retain_strategies") or {}
    if not isinstance(strategies, dict):
        raise MigrationError("retain strategies were not configured")
    for name, expected in RETAIN_STRATEGIES.items():
        actual = strategies.get(name)
        if not isinstance(actual, dict):
            raise MigrationError(f"retain strategy missing: {name}")
        for key, value in expected.items():
            if actual.get(key) != value:
                raise MigrationError(f"retain strategy mismatch: {name}.{key}")


def _retain_item(record: MigrationRecord, content: str, strategy: str) -> dict[str, Any]:
    item = {
        "content": content,
        "timestamp": record.timestamp,
        "context": f"Imported from OMP Mnemopi {record.source_store} memory in {record.source_bank}.",
        "metadata": record.metadata,
        "document_id": record.document_id,
        "tags": record.tags,
        "observation_scopes": record.observation_scopes,
        "strategy": strategy,
        "update_mode": "replace",
    }
    rescanned, residual = redact_credentials(
        item, document_id=record.document_id, field_path="request.items[0]"
    )
    if residual:
        raise MigrationError(f"outgoing request still contained credentials: {record.document_id}")
    assert isinstance(rescanned, dict)
    return rescanned


def _request_identity(record: MigrationRecord, content: str, strategy: str) -> tuple[str, str, dict[str, Any]]:
    item = _retain_item(record, content, strategy)
    request_hash = _sha256_text(_canonical_json(item))
    operation_id = str(
        uuid.uuid5(OPERATION_NAMESPACE, f"{record.document_id}:{request_hash}")
    )
    body = {"items": [item], "async": True, "operation_id": operation_id}
    return operation_id, request_hash, body

def _submit_retain_safely(
    client: HindsightClient,
    bank_id: str,
    body: Mapping[str, Any],
    operation_id: str,
) -> tuple[dict[str, Any], bool]:
    """Resolve an uncertain retain acknowledgement before reusing the same operation ID."""
    for attempt in range(len(HTTP_RETRY_DELAYS) + 1):
        try:
            return client.retain(bank_id, body), False
        except NetworkUncertainError as error:
            operation = client.get_operation(bank_id, operation_id)
            if operation.get("status") != "not_found":
                return {
                    "operation_id": operation_id,
                    "operation_ids": [operation_id],
                }, True
            if attempt == len(HTTP_RETRY_DELAYS):
                raise MigrationError(
                    f"retain acknowledgement remained uncertain: {operation_id}"
                ) from error
            time.sleep(HTTP_RETRY_DELAYS[attempt])
    raise AssertionError("unreachable")



def _numeric_usage(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    usage = value.get("usage") if isinstance(value.get("usage"), dict) else value
    output: dict[str, int | float] = {}
    for key, item in usage.items():
        if isinstance(item, (int, float)) and not isinstance(item, bool) and re.search(
            r"token|cost|request|duration", str(key), re.I
        ):
            output[str(key)] = item
    return output


def _summarize_state(
    events: Sequence[Mapping[str, Any]], document_ids: Iterable[str]
) -> dict[str, Any]:
    selected = {str(document_id) for document_id in document_ids}
    terminal_history: dict[str, list[str]] = defaultdict(list)
    terminal_by_document: dict[str, Mapping[str, Any]] = {}
    retried_documents: set[str] = set()
    operation_retry_attempts = 0
    usage_by_operation: dict[str, dict[str, int | float]] = {}

    for event in events:
        operation_id = event.get("operation_id")
        event_usage = _numeric_usage(event.get("usage"))
        if isinstance(operation_id, str) and operation_id and event_usage:
            operation_usage = usage_by_operation.setdefault(operation_id, {})
            for key, value in event_usage.items():
                prior = operation_usage.get(key)
                if prior is None or value > prior:
                    operation_usage[key] = value

        document_id = str(event.get("document_id", ""))
        if document_id not in selected:
            continue
        status = str(event.get("status", ""))
        if status in {"record-completed", "record-failed"}:
            terminal_history[document_id].append(status)
            terminal_by_document[document_id] = event
        if status == "retry-requested":
            operation_retry_attempts += 1
            retried_documents.add(document_id)

    process_retry_attempts = 0
    for document_id, history in terminal_history.items():
        for previous in history[:-1]:
            if previous == "record-failed":
                process_retry_attempts += 1
                retried_documents.add(document_id)

    completed_by_strategy: Counter[str] = Counter()
    completed_documents = 0
    failed_documents = 0
    fallback_documents = 0
    for terminal in terminal_by_document.values():
        if terminal.get("status") == "record-failed":
            failed_documents += 1
            continue
        completed_documents += 1
        strategy = str(terminal.get("strategy") or "unknown")
        completed_by_strategy[strategy] += 1
        if bool(terminal.get("fallback")) or strategy == "mnemopi_fallback":
            fallback_documents += 1

    operation_usage_totals: Counter[str] = Counter()
    for operation_usage in usage_by_operation.values():
        operation_usage_totals.update(operation_usage)

    return {
        "completed_documents": completed_documents,
        "failed_documents": failed_documents,
        "documents_without_terminal_state": len(selected - set(terminal_by_document)),
        "fallback_documents": fallback_documents,
        "completed_by_strategy": dict(sorted(completed_by_strategy.items())),
        "process_retry_attempts": process_retry_attempts,
        "operation_retry_attempts": operation_retry_attempts,
        "retry_attempts": process_retry_attempts + operation_retry_attempts,
        "retried_documents": len(retried_documents),
        "usage_operation_count": len(usage_by_operation),
        "operation_usage": dict(sorted(operation_usage_totals.items())),
    }


def _memory_text(memory: Mapping[str, Any]) -> str:
    value = memory.get("text")
    return value if isinstance(value, str) else ""


def _fallback_reason(content: str, memories: Sequence[Mapping[str, Any]]) -> str | None:
    if not memories:
        return "empty-memory-units"
    anchors = _technical_anchors(content)
    if not anchors:
        return None
    combined = "\n".join(_memory_text(memory) for memory in memories).casefold()
    if not any(value.casefold() in combined for _, value in anchors):
        return "missing-technical-anchor"
    return None


def resume_action(operation_status: str, locally_completed: bool, document_valid: bool) -> str:
    """Pure resume state transition used by import and synthetic tests."""
    if operation_status == "completed":
        return "verify-skip" if document_valid else "verify-fail"
    if operation_status in {"pending", "processing", "running"}:
        return "poll"
    if operation_status == "not_found" and locally_completed and document_valid:
        return "verify-skip"
    if operation_status == "failed":
        return "retry"
    return "submit"


def _verify_remote_record(
    client: HindsightClient,
    bank_id: str,
    record: MigrationRecord,
    content: str,
    *,
    check_recall: bool,
) -> RemoteCheck:
    document = client.get_document(bank_id, record.document_id)
    if document is None:
        raise MigrationError(f"missing Hindsight document: {record.document_id}")
    original_text = document.get("original_text")
    if not isinstance(original_text, str) or _sha256_text(original_text) != record.redacted_content_sha256:
        raise MigrationError(f"Hindsight document text mismatch: {record.document_id}")
    actual_metadata = document.get("document_metadata") or {}
    if not isinstance(actual_metadata, dict):
        raise MigrationError(f"Hindsight document metadata missing: {record.document_id}")
    normalized_metadata = {str(key): str(value) for key, value in actual_metadata.items()}
    if normalized_metadata != record.metadata:
        raise MigrationError(f"Hindsight document metadata mismatch: {record.document_id}")
    actual_tags = document.get("tags") or []
    if not isinstance(actual_tags, list) or sorted(map(str, actual_tags)) != sorted(record.tags):
        raise MigrationError(f"Hindsight document tags mismatch: {record.document_id}")
    memories = client.list_memories(bank_id, record.document_id)
    declared_count = document.get("memory_unit_count")
    if not isinstance(declared_count, int) or declared_count != len(memories):
        raise MigrationError(f"Hindsight document memory count mismatch: {record.document_id}")
    fallback_reason = _fallback_reason(content, memories)
    if memories and not any(
        _same_timestamp(memory.get("mentioned_at", memory.get("date")), record.timestamp)
        for memory in memories
    ):
        raise MigrationError(f"Hindsight memory timestamp mismatch: {record.document_id}")
    recall_ok = True
    if check_recall and fallback_reason is None:
        project_tag = f"project:{record.project_label}"
        recall = client.recall(bank_id, _query_for_content(content), project_tag)
        results = recall.get("results")
        if not isinstance(results, list):
            raise MigrationError(f"invalid recall response: {record.document_id}")
        recall_ok = any(
            isinstance(item, dict) and item.get("document_id") == record.document_id for item in results
        )
        if not recall_ok:
            raise MigrationError(f"recall did not return expected document: {record.document_id}")
    return RemoteCheck(
        memory_unit_count=len(memories),
        anchors_present=fallback_reason != "missing-technical-anchor",
        recall_ok=recall_ok,
        fallback_reason=fallback_reason,
    )


def _wait_for_operation(
    paths: RunPaths,
    client: HindsightClient,
    bank_id: str,
    operation_id: str,
    record: MigrationRecord | None,
    strategy: str,
    request_hash: str,
    phase: str,
    timeout_seconds: int,
    prior_events: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], bool]:
    deadline = time.monotonic() + timeout_seconds
    retried = False
    known_events = _state_for_operation(prior_events, operation_id)
    retry_already_requested = any(event.get("status") == "retry-requested" for event in known_events)
    while True:
        status = client.get_operation(bank_id, operation_id)
        state = str(status.get("status", "not_found"))
        if state == "completed":
            _append_state(
                paths.state,
                _event(
                    status="operation-completed",
                    document_id=record.document_id if record else None,
                    operation_id=operation_id,
                    strategy=strategy,
                    request_hash=request_hash,
                    phase=phase,
                    usage=_numeric_usage(status.get("result_metadata")),
                ),
            )
            return status, retried
        if state == "failed":
            retry_count = int(status.get("retry_count") or 0)
            if retry_already_requested or retry_count >= 1:
                raise MigrationError(
                    f"operation failed after retry: {operation_id}"
                )
            client.retry_operation(bank_id, operation_id)
            retried = True
            retry_already_requested = True
            _append_state(
                paths.state,
                _event(
                    status="retry-requested",
                    document_id=record.document_id if record else None,
                    operation_id=operation_id,
                    strategy=strategy,
                    request_hash=request_hash,
                    phase=phase,
                ),
            )
        elif state in {"cancelled", "not_found"}:
            raise MigrationError(f"operation unavailable while polling: {operation_id}")
        elif state not in {"pending", "processing", "running"}:
            raise MigrationError(f"unknown operation state for {operation_id}")
        if _shutdown_requested.is_set():
            _append_state(
                paths.state,
                _event(
                    status="interrupted-in-flight",
                    document_id=record.document_id if record else None,
                    operation_id=operation_id,
                    strategy=strategy,
                    request_hash=request_hash,
                    phase=phase,
                ),
            )
            raise InterruptedError
        if time.monotonic() >= deadline:
            raise MigrationError(f"operation deadline exceeded: {operation_id}")
        time.sleep(POLL_INTERVAL_SECONDS)


def _run_strategy(
    paths: RunPaths,
    client: HindsightClient,
    bank_id: str,
    record: MigrationRecord,
    content: str,
    strategy: str,
    phase: str,
    prior_events: Sequence[Mapping[str, Any]],
) -> tuple[str, str, bool, bool, dict[str, int | float]]:
    operation_id, request_hash, body = _request_identity(record, content, strategy)
    operation = client.get_operation(bank_id, operation_id)
    operation_state = str(operation.get("status", "not_found"))
    relevant_events = _state_for_operation(prior_events, operation_id)
    locally_completed = any(event.get("status") == "record-completed" for event in relevant_events)
    document_valid = False
    if operation_state == "completed":
        _verify_remote_record(client, bank_id, record, content, check_recall=False)
        document_valid = True
    elif operation_state == "not_found" and locally_completed:
        try:
            check = _verify_remote_record(
                client, bank_id, record, content, check_recall=False
            )
            document_valid = check.fallback_reason is None
        except MigrationError:
            document_valid = False
    action = resume_action(operation_state, locally_completed, document_valid)
    if action == "verify-skip":
        if operation_state == "completed":
            _append_state(
                paths.state,
                _event(
                    status="operation-recovered",
                    document_id=record.document_id,
                    operation_id=operation_id,
                    strategy=strategy,
                    request_hash=request_hash,
                    phase=phase,
                ),
            )
        return operation_id, request_hash, True, False, _numeric_usage(operation.get("result_metadata"))
    if action == "verify-fail":
        raise MigrationError(f"completed operation produced invalid document: {operation_id}")

    resumed = action == "poll" or operation_state == "completed"
    usage: dict[str, int | float] = {}
    retried = False
    if action == "submit":
        response, recovered_acknowledgement = _submit_retain_safely(
            client, bank_id, body, operation_id
        )
        resumed = resumed or recovered_acknowledgement
        returned_operation = response.get("operation_id")
        operation_ids = response.get("operation_ids")
        if returned_operation != operation_id and not (
            isinstance(operation_ids, list) and operation_id in operation_ids
        ):
            raise MigrationError(f"retain returned unexpected operation ID: {record.document_id}")
        usage.update(_numeric_usage(response))
        _append_state(
            paths.state,
            _event(
                status=(
                    "submitted-confirmed-after-uncertain"
                    if recovered_acknowledgement
                    else "submitted"
                ),
                document_id=record.document_id,
                operation_id=operation_id,
                strategy=strategy,
                request_hash=request_hash,
                phase=phase,
                usage=usage,
            ),
        )
    elif action == "retry":
        retry_count = int(operation.get("retry_count") or 0)
        if retry_count >= 1 or any(event.get("status") == "retry-requested" for event in relevant_events):
            raise MigrationError(f"operation already exhausted retry: {operation_id}")
        client.retry_operation(bank_id, operation_id)
        retried = True
        _append_state(
            paths.state,
            _event(
                status="retry-requested",
                document_id=record.document_id,
                operation_id=operation_id,
                strategy=strategy,
                request_hash=request_hash,
                phase=phase,
            ),
        )
    elif operation_state == "completed":
        usage.update(_numeric_usage(operation.get("result_metadata")))
        return operation_id, request_hash, True, False, usage

    terminal, wait_retried = _wait_for_operation(
        paths,
        client,
        bank_id,
        operation_id,
        record,
        strategy,
        request_hash,
        phase,
        RETAIN_TIMEOUT_SECONDS,
        prior_events,
    )
    usage.update(_numeric_usage(terminal.get("result_metadata")))
    return operation_id, request_hash, resumed, retried or wait_retried, usage


def _fallback_recovery_pending(
    events: Sequence[Mapping[str, Any]], document_id: str
) -> bool:
    return any(
        event.get("document_id") == document_id
        and (
            event.get("strategy") == "mnemopi_fallback"
            or str(event.get("status", "")).startswith("fallback-")
        )
        for event in events
    )


def _execute_fallback(
    paths: RunPaths,
    client: HindsightClient,
    bank_id: str,
    record: MigrationRecord,
    content: str,
    phase: str,
    prior_events: Sequence[Mapping[str, Any]],
) -> tuple[str, str, bool, bool, dict[str, int | float], RemoteCheck]:
    operation_id, request_hash, _ = _request_identity(
        record, content, "mnemopi_fallback"
    )
    operation = client.get_operation(bank_id, operation_id)
    operation_state = str(operation.get("status", "not_found"))
    resumed = operation_state != "not_found"
    retried = False
    usage: dict[str, int | float] = {}

    if operation_state in {"pending", "processing", "running", "failed"}:
        (
            operation_id,
            request_hash,
            strategy_resumed,
            strategy_retried,
            strategy_usage,
        ) = _run_strategy(
            paths,
            client,
            bank_id,
            record,
            content,
            "mnemopi_fallback",
            phase,
            prior_events,
        )
        resumed = resumed or strategy_resumed
        retried = retried or strategy_retried
        usage.update(strategy_usage)
        check = _verify_remote_record(
            client,
            bank_id,
            record,
            content,
            check_recall=phase == "canary",
        )
        if check.fallback_reason is None:
            return operation_id, request_hash, resumed, retried, usage, check
        operation = client.get_operation(bank_id, operation_id)
        operation_state = str(operation.get("status", "not_found"))
    elif operation_state == "completed":
        document = client.get_document(bank_id, record.document_id)
        if document is not None:
            check = _verify_remote_record(
                client,
                bank_id,
                record,
                content,
                check_recall=phase == "canary",
            )
            if check.fallback_reason is None:
                (
                    operation_id,
                    request_hash,
                    strategy_resumed,
                    strategy_retried,
                    strategy_usage,
                ) = _run_strategy(
                    paths,
                    client,
                    bank_id,
                    record,
                    content,
                    "mnemopi_fallback",
                    phase,
                    prior_events,
                )
                usage.update(strategy_usage)
                return (
                    operation_id,
                    request_hash,
                    resumed or strategy_resumed,
                    retried or strategy_retried,
                    usage,
                    check,
                )
    elif operation_state not in {"not_found", "cancelled"}:
        raise MigrationError(f"unknown fallback operation state: {operation_id}")

    _append_state(
        paths.state,
        _event(
            status="fallback-reextract-required",
            document_id=record.document_id,
            operation_id=operation_id,
            strategy="mnemopi_fallback",
            request_hash=request_hash,
            phase=phase,
        ),
    )
    if operation_state in {"completed", "failed", "cancelled"}:
        client.delete_operation(bank_id, operation_id)
        if client.get_operation(bank_id, operation_id).get("status") != "not_found":
            raise MigrationError(f"terminal fallback operation could not be cleared: {operation_id}")
        _append_state(
            paths.state,
            _event(
                status="fallback-operation-deleted",
                document_id=record.document_id,
                operation_id=operation_id,
                strategy="mnemopi_fallback",
                request_hash=request_hash,
                phase=phase,
            ),
        )

    document = client.get_document(bank_id, record.document_id)
    if document is not None:
        _verify_remote_record(
            client,
            bank_id,
            record,
            content,
            check_recall=False,
        )
        _append_state(
            paths.state,
            _event(
                status="fallback-document-delete-started",
                document_id=record.document_id,
                operation_id=operation_id,
                strategy="mnemopi_fallback",
                request_hash=request_hash,
                phase=phase,
            ),
        )
        client.delete_document(bank_id, record.document_id)
        if client.get_document(bank_id, record.document_id) is not None:
            raise MigrationError(f"fallback source document could not be cleared: {record.document_id}")
        _append_state(
            paths.state,
            _event(
                status="fallback-document-deleted",
                document_id=record.document_id,
                operation_id=operation_id,
                strategy="mnemopi_fallback",
                request_hash=request_hash,
                phase=phase,
            ),
        )

    (
        operation_id,
        request_hash,
        strategy_resumed,
        strategy_retried,
        strategy_usage,
    ) = _run_strategy(
        paths,
        client,
        bank_id,
        record,
        content,
        "mnemopi_fallback",
        phase,
        prior_events,
    )
    usage.update(strategy_usage)
    check = _verify_remote_record(
        client,
        bank_id,
        record,
        content,
        check_recall=phase == "canary",
    )
    if check.fallback_reason is not None:
        raise MigrationError(f"fallback extraction failed: {record.document_id}")
    return (
        operation_id,
        request_hash,
        resumed or strategy_resumed,
        retried or strategy_retried,
        usage,
        check,
    )


def _process_record(
    paths: RunPaths,
    client: HindsightClient,
    bank_id: str,
    record: MigrationRecord,
    phase: str,
    prior_events: Sequence[Mapping[str, Any]],
) -> ProcessResult:
    content = _read_snapshot_content(paths, record)
    fallback = _fallback_recovery_pending(prior_events, record.document_id)
    if not fallback:
        fallback_operation_id, _, _ = _request_identity(
            record, content, "mnemopi_fallback"
        )
        fallback = (
            client.get_operation(bank_id, fallback_operation_id).get("status")
            == "completed"
        )
    used_strategy = "mnemopi_fallback" if fallback else "mnemopi_import"
    resumed = fallback
    retried = False
    usage: dict[str, int | float] = {}

    if fallback:
        (
            operation_id,
            request_hash,
            fallback_resumed,
            fallback_retried,
            fallback_usage,
            check,
        ) = _execute_fallback(
            paths,
            client,
            bank_id,
            record,
            content,
            phase,
            prior_events,
        )
        resumed = resumed or fallback_resumed
        retried = retried or fallback_retried
        usage.update(fallback_usage)
    else:
        operation_id, request_hash, resumed, retried, usage = _run_strategy(
            paths,
            client,
            bank_id,
            record,
            content,
            "mnemopi_import",
            phase,
            prior_events,
        )
        check = _verify_remote_record(
            client,
            bank_id,
            record,
            content,
            check_recall=phase == "canary",
        )
        fallback = check.fallback_reason is not None
        if fallback:
            _append_state(
                paths.state,
                _event(
                    status="fallback-required",
                    document_id=record.document_id,
                    operation_id=operation_id,
                    strategy="mnemopi_import",
                    request_hash=request_hash,
                    phase=phase,
                    reason=check.fallback_reason,
                ),
            )
            used_strategy = "mnemopi_fallback"
            (
                operation_id,
                request_hash,
                fallback_resumed,
                fallback_retried,
                fallback_usage,
                check,
            ) = _execute_fallback(
                paths,
                client,
                bank_id,
                record,
                content,
                phase,
                prior_events,
            )
            resumed = resumed or fallback_resumed
            retried = retried or fallback_retried
            usage.update(fallback_usage)

    _append_state(
        paths.state,
        _event(
            status="record-completed",
            document_id=record.document_id,
            operation_id=operation_id,
            strategy=used_strategy,
            request_hash=request_hash,
            phase=phase,
            memory_unit_count=check.memory_unit_count,
            fallback=fallback,
            usage=usage,
        ),
    )
    return ProcessResult(
        document_id=record.document_id,
        strategy=used_strategy,
        operation_id=operation_id,
        resumed=resumed,
        retried=retried,
        fallback=fallback,
        memory_unit_count=check.memory_unit_count,
        usage=usage,
    )


def _delete_stale_documents(
    paths: RunPaths,
    client: HindsightClient,
    bank_id: str,
    records: Sequence[MigrationRecord],
) -> int:
    expected = {record.document_id for record in records}
    deleted = 0
    for document in client.list_documents(bank_id):
        document_id = str(document.get("id", ""))
        if document_id in expected:
            continue
        detail = client.get_document(bank_id, document_id)
        metadata = (detail or {}).get("document_metadata") or {}
        if not document_id.startswith("mnemopi:") or not isinstance(metadata, dict) or str(
            metadata.get("source_backend")
        ) != "mnemopi" or str(metadata.get("migration_schema_version")) != MIGRATION_SCHEMA_VERSION:
            raise MigrationError(f"foreign document found in staging bank: {document_id}")
        _append_state(
            paths.state,
            _event(status="stale-document-delete-started", document_id=document_id, phase="all"),
        )
        client.delete_document(bank_id, document_id)
        _append_state(
            paths.state,
            _event(status="stale-document-deleted", document_id=document_id, phase="all"),
        )
        deleted += 1
    return deleted


def import_run(
    run_paths: RunPaths,
    api_url: str,
    bank_id: str,
    max_in_flight: int,
    *,
    phase: str = "all",
) -> dict[str, Any]:
    if phase not in {"canary", "all"}:
        raise MigrationError("import phase must be canary or all")
    if not 1 <= max_in_flight <= 4:
        raise MigrationError("max-in-flight must be between 1 and 4")
    records = _load_manifest(run_paths)
    summary = _load_summary(run_paths)
    if phase == "all" and not summary.get("canary_verified"):
        raise MigrationError("full import requires a verified canary")
    selected = [record for record in records if record.canary_reasons] if phase == "canary" else records
    client = HindsightClient(api_url)
    client.health()
    actual_bank_id = _select_staging_bank(run_paths, client, bank_id, records)
    _configure_import_bank(client, actual_bank_id)
    deleted = _delete_stale_documents(run_paths, client, actual_bank_id, records) if phase == "all" else 0
    prior_events = _load_state(run_paths)
    counters: Counter[str] = Counter()
    failures: list[tuple[str, BaseException]] = []
    pending = iter(selected)
    futures: dict[concurrent.futures.Future[ProcessResult], str] = {}

    def submit_next(executor: concurrent.futures.ThreadPoolExecutor) -> bool:
        if _shutdown_requested.is_set() or failures:
            return False
        try:
            record = next(pending)
        except StopIteration:
            return False
        future = executor.submit(
            _process_record,
            run_paths,
            client,
            actual_bank_id,
            record,
            phase,
            prior_events,
        )
        futures[future] = record.document_id
        return True

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_in_flight) as executor:
        for _ in range(max_in_flight):
            if not submit_next(executor):
                break
        while futures:
            done, _ = concurrent.futures.wait(
                tuple(futures), return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                document_id = futures.pop(future)
                try:
                    result = future.result()
                except InterruptedError as error:
                    failures.append((document_id, error))
                    _shutdown_requested.set()
                except BaseException as error:
                    failures.append((document_id, error))
                    _append_state(
                        run_paths.state,
                        _event(status="record-failed", document_id=document_id, phase=phase),
                    )
                else:
                    counters["completed"] += 1
                    counters["resumed"] += int(result.resumed)
                    counters["retried"] += int(result.retried)
                    counters["fallback"] += int(result.fallback)
                    counters["memory_units"] += result.memory_unit_count
            while len(futures) < max_in_flight and submit_next(executor):
                pass

    if failures:
        first_document, first_error = failures[0]
        if isinstance(first_error, InterruptedError):
            raise MigrationError(f"import interrupted with resumable state: {first_document}")
        raise MigrationError(f"import failed for {first_document}: {type(first_error).__name__}") from first_error
    if counters["completed"] != len(selected):
        raise MigrationError("import stopped before every selected record completed")
    update_key = "canary_import_complete" if phase == "canary" else "all_import_complete"
    _update_summary(
        run_paths,
        {
            update_key: True,
            f"{phase}_import": {
                "completed": counters["completed"],
                "resumed": counters["resumed"],
                "retried": counters["retried"],
                "fallback": counters["fallback"],
                "memory_units": counters["memory_units"],
                "stale_documents_deleted": deleted,
                "completed_at": _utc_now(),
            },
        },
    )
    return {
        "status": "completed",
        "phase": phase,
        "bank_id": actual_bank_id,
        "documents": counters["completed"],
        "fallback": counters["fallback"],
        "retried": counters["retried"],
    }


def _verify_snapshot(paths: RunPaths, summary: Mapping[str, Any]) -> None:
    databases = summary.get("snapshot_databases")
    if not isinstance(databases, list):
        raise MigrationError("summary has no snapshot database list")
    for item in databases:
        if not isinstance(item, dict):
            raise MigrationError("invalid snapshot database metadata")
        path = (paths.snapshot / str(item.get("path", ""))).resolve()
        try:
            path.relative_to(paths.snapshot.resolve())
        except ValueError as error:
            raise MigrationError("snapshot database path escapes run directory") from error
        if not path.is_file() or _sha256_file(path) != item.get("sha256"):
            raise MigrationError(f"snapshot database hash mismatch: {item.get('path')}")
        connection = _sqlite_readonly(path)
        try:
            integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        finally:
            connection.close()
        if integrity != ["ok"]:
            raise MigrationError(f"snapshot integrity failure: {item.get('path')}")


def _verify_probe(
    client: HindsightClient,
    bank_id: str,
    probe: Mapping[str, Any],
) -> bool:
    scope = probe.get("scope")
    query = probe.get("query")
    expected = probe.get("expected_document_id")
    if not all(isinstance(value, str) and value for value in (scope, query, expected)):
        raise MigrationError("invalid protected recall probe")
    response = client.recall(bank_id, query, scope)
    results = response.get("results")
    if not isinstance(results, list):
        return False
    return any(isinstance(item, dict) and item.get("document_id") == expected for item in results)


def _scan_logical_fingerprints(snapshot_root: Path) -> dict[str, str]:
    paths = [snapshot_root / "mnemopi.db", *sorted((snapshot_root / "banks").glob("*/mnemopi.db"))]
    output: dict[str, str] = {}
    for database in (path for path in paths if path.is_file()):
        relative = database.relative_to(snapshot_root)
        bank = _source_bank(relative)
        connection = _sqlite_readonly(database)
        try:
            for table, store in (("working_memory", "working"), ("episodic_memory", "episodic")):
                for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY id'):
                    source_id = str(row["id"] or "")
                    document_id = _document_id(bank, store, source_id)
                    if document_id in output:
                        raise MigrationError(f"duplicate live document ID: {document_id}")
                    metadata = _parse_metadata(row["metadata_json"], document_id)
                    output[document_id] = _logical_fingerprint(bank, store, row, metadata)
        finally:
            connection.close()
    return output


def _source_drift(paths: RunPaths, source_root: Path, records: Sequence[MigrationRecord]) -> dict[str, Any]:
    temporary_parent = paths.root / f".live-check-{uuid.uuid4().hex}"
    os.mkdir(temporary_parent, 0o700)
    try:
        backup_databases(source_root, temporary_parent)
        live = _scan_logical_fingerprints(temporary_parent / "snapshot")
    finally:
        shutil.rmtree(temporary_parent, ignore_errors=True)
    expected = {record.document_id: record.logical_fingerprint for record in records}
    added = sorted(set(live) - set(expected))
    deleted = sorted(set(expected) - set(live))
    modified = sorted(
        document_id for document_id in set(expected) & set(live) if expected[document_id] != live[document_id]
    )
    return {
        "clean": not (added or deleted or modified),
        "added_count": len(added),
        "deleted_count": len(deleted),
        "modified_count": len(modified),
        "added_document_ids": added,
        "deleted_document_ids": deleted,
        "modified_document_ids": modified,
    }


def verify_run(
    run_paths: RunPaths,
    api_url: str,
    scope: str,
    source: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    if scope not in {"canary", "all"}:
        raise MigrationError("verify scope must be canary or all")
    summary = _load_summary(run_paths)
    records = _load_manifest(run_paths)
    _verify_snapshot(run_paths, summary)
    bank_id = summary.get("bank_id")
    if not isinstance(bank_id, str) or not bank_id:
        raise MigrationError("run has no staging bank ID")
    selected = [record for record in records if record.canary_reasons] if scope == "canary" else records
    client = HindsightClient(api_url)
    client.health()
    errors: list[dict[str, str]] = []
    memory_units = 0
    fallback_needed = 0
    for record in selected:
        try:
            content = _read_snapshot_content(run_paths, record)
            check = _verify_remote_record(
                client,
                bank_id,
                record,
                content,
                check_recall=scope == "canary",
            )
            memory_units += check.memory_unit_count
            fallback_needed += int(check.fallback_reason is not None)
            if check.fallback_reason is not None:
                errors.append({"document_id": record.document_id, "reason": check.fallback_reason})
        except MigrationError as error:
            errors.append({"document_id": record.document_id, "reason": str(error)})

    remote_documents = client.list_documents(bank_id)
    if scope == "all":
        remote_ids = {str(item.get("id", "")) for item in remote_documents}
        expected_ids = {record.document_id for record in records}
        if remote_ids != expected_ids:
            errors.append(
                {
                    "document_id": "*",
                    "reason": (
                        f"remote document set mismatch: expected={len(expected_ids)} actual={len(remote_ids)}"
                    ),
                }
            )

    probes = _load_json(run_paths.probes)
    probe_rows = list(probes.get("probes", []))
    if scope == "all":
        probe_rows.extend(probes.get("origin_probes", []))
    probe_failures = 0
    for probe in probe_rows:
        try:
            ok = _verify_probe(client, bank_id, probe)
        except MigrationError:
            ok = False
        if not ok:
            probe_failures += 1
            errors.append(
                {
                    "document_id": str(probe.get("expected_document_id", "unknown")),
                    "reason": "protected recall probe failed",
                }
            )

    stats = client.stats(bank_id, refresh=True)
    if int(stats.get("pending_operations", -1)) != 0:
        errors.append({"document_id": "*", "reason": "pending operations are nonzero"})
    if int(stats.get("failed_operations", -1)) != 0:
        errors.append({"document_id": "*", "reason": "failed operations are nonzero"})
    if summary.get("finalized"):
        if int(stats.get("pending_consolidation", -1)) != 0:
            errors.append({"document_id": "*", "reason": "pending consolidation is nonzero"})
        if int(stats.get("failed_consolidation", -1)) != 0:
            errors.append({"document_id": "*", "reason": "failed consolidation is nonzero"})

    drift: dict[str, Any] | None = None
    if source is not None:
        drift = _source_drift(run_paths, Path(source).expanduser().absolute(), records)
        if not drift["clean"]:
            errors.append({"document_id": "*", "reason": "live Mnemopi semantic fingerprint drifted"})

    state = _load_state(run_paths)
    selected_ids = {record.document_id for record in selected}
    state_summary = _summarize_state(state, selected_ids)
    verification_failed_ids = {
        str(error["document_id"]) for error in errors if error["document_id"] != "*"
    }
    verified_documents = len(selected) - len(verification_failed_ids)
    expected_documents = len(selected)
    terminal_state_consistent = (
        state_summary["completed_documents"]
        == verified_documents
        == expected_documents
        and state_summary["failed_documents"] == 0
        and state_summary["documents_without_terminal_state"] == 0
    )
    if not terminal_state_consistent:
        errors.append(
            {
                "document_id": "*",
                "reason": (
                    "terminal state count mismatch: "
                    f"expected={expected_documents} "
                    f"completed={state_summary['completed_documents']} "
                    f"verified={verified_documents} "
                    f"failed={state_summary['failed_documents']} "
                    f"missing={state_summary['documents_without_terminal_state']}"
                ),
            }
        )
    report = {
        "schema_version": 2,
        "generated_at": _utc_now(),
        "run_id": run_paths.root.name,
        "scope": scope,
        "bank_id": bank_id,
        "source_documents": len(records),
        "selected_documents": expected_documents,
        "completed_documents": state_summary["completed_documents"],
        "verified_documents": verified_documents,
        "failed_documents": state_summary["failed_documents"],
        "verification_failed_documents": len(verification_failed_ids),
        "verification_error_count": len(errors),
        "documents_without_terminal_state": state_summary["documents_without_terminal_state"],
        "terminal_state_consistent": terminal_state_consistent,
        "memory_units": memory_units,
        "fallback_documents": state_summary["fallback_documents"],
        "fallback_needed": fallback_needed,
        "retry_attempts": state_summary["retry_attempts"],
        "process_retry_attempts": state_summary["process_retry_attempts"],
        "operation_retry_attempts": state_summary["operation_retry_attempts"],
        "retried_documents": state_summary["retried_documents"],
        "recall_probe_count": len(probe_rows),
        "recall_probe_failures": probe_failures,
        "remote_total_documents": len(remote_documents),
        "project_tags": summary.get("project_tags", {}),
        "redaction": summary.get("redaction", {}),
        "derived_tables_not_imported": summary.get("derived_table_counts", {}),
        "completed_by_strategy": state_summary["completed_by_strategy"],
        "usage_operation_count": state_summary["usage_operation_count"],
        "operation_usage": state_summary["operation_usage"],
        "stats": {
            key: stats.get(key)
            for key in (
                "total_nodes",
                "total_links",
                "total_documents",
                "pending_operations",
                "failed_operations",
                "pending_consolidation",
                "failed_consolidation",
                "total_observations",
            )
        },
        "source_drift": drift,
        "errors": errors,
    }
    _atomic_write_json(run_paths.report, report)
    if errors:
        raise MigrationError(f"verification failed with {len(errors)} error(s)")
    verified_key = "canary_verified" if scope == "canary" else "all_verified"
    _update_summary(run_paths, {verified_key: True, f"{scope}_verified_at": _utc_now()})
    return {
        "status": "verified",
        "scope": scope,
        "bank_id": bank_id,
        "documents": len(selected),
        "memory_units": memory_units,
        "recall_probes": len(probe_rows),
        "source_drift": drift["clean"] if drift is not None else None,
    }


def finalize_run(run_paths: RunPaths, api_url: str) -> dict[str, Any]:
    summary = _load_summary(run_paths)
    if not summary.get("all_import_complete") or not summary.get("all_verified"):
        raise MigrationError("finalize requires a completed and verified full import")
    records = _load_manifest(run_paths)
    bank_id = summary.get("bank_id")
    if not isinstance(bank_id, str) or not bank_id:
        raise MigrationError("run has no staging bank ID")
    client = HindsightClient(api_url)
    client.health()
    scopes = [[tag] for tag in sorted({f"project:{record.project_label}" for record in records})]
    prior_events = _load_state(run_paths)
    if not summary.get("finalized"):
        response = client.consolidate(bank_id, scopes)
        operation_id = response.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            raise MigrationError("consolidation returned no operation ID")
        _append_state(
            run_paths.state,
            _event(
                status="consolidation-submitted",
                operation_id=operation_id,
                strategy="consolidation",
                request_hash=_sha256_text(_canonical_json(scopes)),
                phase="finalize",
            ),
        )
        _wait_for_operation(
            run_paths,
            client,
            bank_id,
            operation_id,
            None,
            "consolidation",
            _sha256_text(_canonical_json(scopes)),
            "finalize",
            CONSOLIDATION_TIMEOUT_SECONDS,
            prior_events,
        )
    deadline = time.monotonic() + CONSOLIDATION_TIMEOUT_SECONDS
    while True:
        stats = client.stats(bank_id, refresh=True)
        if (
            int(stats.get("pending_operations", -1)) == 0
            and int(stats.get("failed_operations", -1)) == 0
            and int(stats.get("pending_consolidation", -1)) == 0
            and int(stats.get("failed_consolidation", -1)) == 0
        ):
            break
        if int(stats.get("failed_operations", 0)) or int(stats.get("failed_consolidation", 0)):
            raise MigrationError("Hindsight reported failed operations or consolidation")
        if time.monotonic() >= deadline:
            raise MigrationError("consolidation drain deadline exceeded")
        time.sleep(POLL_INTERVAL_SECONDS)
    client.patch_config(bank_id, {"enable_auto_consolidation": True})
    config = client.get_config(bank_id)
    resolved = (config or {}).get("config") or {}
    if not isinstance(resolved, dict) or resolved.get("enable_auto_consolidation") is not True:
        raise MigrationError("auto consolidation was not restored")
    _update_summary(
        run_paths,
        {
            "finalized": True,
            "finalized_at": _utc_now(),
            "consolidation_scope_count": len(scopes),
        },
    )
    return {
        "status": "finalized",
        "bank_id": bank_id,
        "observation_scopes": len(scopes),
        "total_documents": int(stats.get("total_documents", 0)),
        "total_nodes": int(stats.get("total_nodes", 0)),
    }


def _prepare(source: Path, run_dir: Path) -> dict[str, Any]:
    if run_dir.exists():
        raise MigrationError(f"run directory already exists: {run_dir}")
    _ensure_private_directory(run_dir.parent)
    os.mkdir(run_dir, 0o700)
    paths = RunPaths.from_root(run_dir)
    database_metadata = backup_databases(source, run_dir)
    manifest_summary = build_manifest(paths)
    summary = {
        "migration_schema_version": 1,
        "run_id": run_dir.name,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "source_root": str(source),
        "source_database_count": len(database_metadata),
        "snapshot_databases": database_metadata,
        "baseline": {
            "database_count": BASELINE_DATABASES,
            "working_count": BASELINE_WORKING,
            "episodic_count": BASELINE_EPISODIC,
            "character_count": BASELINE_CHARACTERS,
        },
        "baseline_delta": {
            "database_count": len(database_metadata) - BASELINE_DATABASES,
            "working_count": manifest_summary["working_count"] - BASELINE_WORKING,
            "episodic_count": manifest_summary["episodic_count"] - BASELINE_EPISODIC,
            "character_count": manifest_summary["character_count"] - BASELINE_CHARACTERS,
        },
        "bank_id": None,
        "canary_import_complete": False,
        "canary_verified": False,
        "all_import_complete": False,
        "all_verified": False,
        "finalized": False,
        **manifest_summary,
    }
    _atomic_write_json(paths.summary, summary)
    return {
        "status": "prepared",
        "run_id": run_dir.name,
        "databases": len(database_metadata),
        "records": manifest_summary["record_count"],
        "working": manifest_summary["working_count"],
        "episodic": manifest_summary["episodic_count"],
        "characters": manifest_summary["character_count"],
        "canary": manifest_summary["canary_count"],
        "redactions": manifest_summary["redaction"]["finding_count"],
    }


def _install_signal_handlers() -> None:
    def request_shutdown(signum: int, frame: Any) -> None:
        del signum, frame
        _shutdown_requested.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--run-dir", type=Path, required=True)

    import_parser = commands.add_parser("import")
    import_parser.add_argument("--run-dir", type=Path, required=True)
    import_parser.add_argument("--api-url", required=True)
    import_parser.add_argument("--bank-base", required=True)
    import_parser.add_argument("--phase", choices=("canary", "all"), required=True)
    import_parser.add_argument("--max-in-flight", type=int, default=4)

    finalize = commands.add_parser("finalize")
    finalize.add_argument("--run-dir", type=Path, required=True)
    finalize.add_argument("--api-url", required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--run-dir", type=Path, required=True)
    verify.add_argument("--api-url", required=True)
    verify.add_argument("--scope", choices=("canary", "all"), required=True)
    verify.add_argument("--source", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _install_signal_handlers()
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = _prepare(args.source.expanduser().absolute(), args.run_dir.expanduser().absolute())
        elif args.command == "import":
            result = import_run(
                RunPaths.from_root(args.run_dir),
                args.api_url,
                args.bank_base,
                args.max_in_flight,
                phase=args.phase,
            )
        elif args.command == "finalize":
            result = finalize_run(RunPaths.from_root(args.run_dir), args.api_url)
        elif args.command == "verify":
            result = verify_run(
                RunPaths.from_root(args.run_dir),
                args.api_url,
                args.scope,
                source=args.source,
            )
        else:
            raise AssertionError("unreachable")
    except MigrationError as error:
        print(
            _canonical_json({"status": "failed", "error": type(error).__name__, "message": str(error)}),
            file=sys.stderr,
        )
        return 1
    print(_canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
