from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

import migrate_mnemopi as migration


WORKING_SCHEMA = """
CREATE TABLE working_memory (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    source TEXT,
    timestamp TEXT,
    session_id TEXT,
    importance REAL,
    metadata_json TEXT,
    veracity TEXT,
    memory_type TEXT,
    consolidated_at TEXT,
    recall_count INTEGER,
    last_recalled TEXT,
    valid_until TEXT,
    superseded_by TEXT,
    scope TEXT,
    author_id TEXT,
    author_type TEXT,
    channel_id TEXT,
    trust_tier TEXT,
    event_date TEXT,
    event_date_precision TEXT,
    temporal_tags TEXT,
    corrected_by TEXT
)
"""

EPISODIC_SCHEMA = """
CREATE TABLE episodic_memory (
    rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    timestamp TEXT,
    session_id TEXT,
    importance REAL,
    metadata_json TEXT,
    summary_of TEXT,
    veracity TEXT,
    tier INTEGER,
    degraded_at TEXT,
    memory_type TEXT,
    recall_count INTEGER,
    last_recalled TEXT,
    valid_until TEXT,
    superseded_by TEXT,
    scope TEXT,
    author_id TEXT,
    author_type TEXT,
    channel_id TEXT,
    trust_tier TEXT,
    event_date TEXT,
    event_date_precision TEXT,
    temporal_tags TEXT,
    corrected_by TEXT
)
"""


def file_identity(path: Path) -> tuple[int, int, int, str]:
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size, digest


def create_database(
    path: Path,
    *,
    working: list[dict[str, object]] | None = None,
    episodic: list[dict[str, object]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(WORKING_SCHEMA)
    connection.execute(EPISODIC_SCHEMA)
    for row in working or []:
        values = {
            "id": row["id"],
            "content": row["content"],
            "source": row.get("source", "synthetic-test"),
            "timestamp": row.get("timestamp", "2026-01-02T03:04:05Z"),
            "session_id": row.get("session_id", "synthetic-session"),
            "importance": row.get("importance", 0.75),
            "metadata_json": json.dumps(row.get("metadata", {}), sort_keys=True),
            "veracity": row.get("veracity", "verified"),
            "memory_type": row.get("memory_type", "episode"),
            "consolidated_at": None,
            "recall_count": 0,
            "last_recalled": None,
            "valid_until": None,
            "superseded_by": None,
            "scope": "bank",
            "author_id": "synthetic-agent",
            "author_type": "agent",
            "channel_id": "synthetic-channel",
            "trust_tier": "VERIFIED",
            "event_date": None,
            "event_date_precision": "unknown",
            "temporal_tags": "[]",
            "corrected_by": None,
        }
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        connection.execute(
            f"INSERT INTO working_memory ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    for row in episodic or []:
        values = {
            "id": row["id"],
            "content": row["content"],
            "source": row.get("source", "synthetic-test"),
            "timestamp": row.get("timestamp", "2026-01-02T04:05:06Z"),
            "session_id": row.get("session_id", "synthetic-session"),
            "importance": row.get("importance", 0.8),
            "metadata_json": json.dumps(row.get("metadata", {}), sort_keys=True),
            "summary_of": row["summary_of"],
            "veracity": row.get("veracity", "verified"),
            "tier": 1,
            "degraded_at": None,
            "memory_type": row.get("memory_type", "episode"),
            "recall_count": 0,
            "last_recalled": None,
            "valid_until": None,
            "superseded_by": None,
            "scope": "bank",
            "author_id": "synthetic-agent",
            "author_type": "agent",
            "channel_id": "synthetic-channel",
            "trust_tier": "VERIFIED",
            "event_date": None,
            "event_date_precision": "unknown",
            "temporal_tags": "[]",
            "corrected_by": None,
        }
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        connection.execute(
            f"INSERT INTO episodic_memory ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
    connection.commit()
    connection.close()


def prepare_fixture(
    source: Path,
    run: Path,
    required_probe_scopes: tuple[str, ...] = (),
) -> tuple[migration.RunPaths, dict[str, object]]:
    run.mkdir(mode=0o700)
    migration.backup_databases(source, run)
    paths = migration.RunPaths.from_root(run)
    summary = migration.build_manifest(
        paths, required_probe_scopes=required_probe_scopes
    )
    return paths, summary


class MigrationTests(unittest.TestCase):
    def test_snapshot_includes_committed_wal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            database = source / "mnemopi.db"
            connection = sqlite3.connect(database)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA wal_autocheckpoint = 0")
            connection.execute(WORKING_SCHEMA)
            connection.execute(EPISODIC_SCHEMA)
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute(
                "INSERT INTO working_memory (id, content, timestamp, metadata_json) VALUES (?, ?, ?, ?)",
                (
                    "wal-row",
                    "Committed WAL content with `WAL_ANCHOR`.",
                    "2026-01-02T03:04:05Z",
                    json.dumps({"cwd": str(root / "project")}),
                ),
            )
            connection.commit()
            wal = database.with_name("mnemopi.db-wal")
            shm = database.with_name("mnemopi.db-shm")
            self.assertTrue(wal.exists())
            self.assertTrue(shm.exists())
            source_files = (database, wal, shm)
            before = {path: file_identity(path) for path in source_files}

            run = root / "run"
            run.mkdir(mode=0o700)
            migration.backup_databases(source, run)

            after = {path: file_identity(path) for path in source_files}
            self.assertEqual(before, after)
            snapshot_path = run / "snapshot" / "mnemopi.db"
            self.assertEqual(list(snapshot_path.parent.glob("mnemopi.db-*")), [])
            snapshot = sqlite3.connect(snapshot_path)
            try:
                journal_mode = snapshot.execute("PRAGMA journal_mode").fetchone()[0]
                count = snapshot.execute(
                    "SELECT count(*) FROM working_memory WHERE id = 'wal-row'"
                ).fetchone()[0]
            finally:
                snapshot.close()
            self.assertEqual(journal_mode, "delete")
            connection.close()
            self.assertEqual(count, 1)

    def test_manifest_maps_working_and_episodic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            project = root / "sample-project"
            project.mkdir()
            create_database(source / "mnemopi.db")
            create_database(
                source / "banks" / "sample-bank-12345678" / "mnemopi.db",
                working=[
                    {
                        "id": "working-1",
                        "content": "Use `SAMPLE_OPTION` at /tmp/sample.",
                        "metadata": {"cwd": str(project), "context": "synthetic"},
                    }
                ],
                episodic=[
                    {
                        "id": "episodic-1",
                        "content": "A synthetic episodic summary for version 1.2.3.",
                        "summary_of": "working-1",
                    }
                ],
            )
            paths, summary = prepare_fixture(
                source, root / "run", ("project:sample-project",)
            )
            rows = [json.loads(line) for line in paths.manifest.read_text().splitlines()]
            self.assertEqual(summary["record_count"], 2)
            self.assertEqual({row["source_store"] for row in rows}, {"working", "episodic"})
            self.assertEqual(len({row["document_id"] for row in rows}), 2)
            self.assertTrue(all(row["document_id"].startswith("mnemopi:") for row in rows))
            self.assertTrue(all("content" not in row for row in rows))
            self.assertTrue(all(row["observation_scopes"] == [[row["tags"][0]]] for row in rows))
            self.assertEqual(os.stat(paths.manifest).st_mode & 0o777, 0o600)
            snapshot_directories = [
                paths.snapshot,
                *[path for path in paths.snapshot.rglob("*") if path.is_dir()],
            ]
            self.assertTrue(
                all(
                    directory.stat().st_mode & 0o777 == 0o700
                    for directory in snapshot_directories
                )
            )
            probe_data = json.loads(paths.probes.read_text())
            probe = probe_data["probes"][0]
            canary_ids = {
                row["document_id"] for row in rows if row["canary_reasons"]
            }
            probe_ids = {
                item["expected_document_id"] for item in probe_data["probes"]
            }
            self.assertTrue(probe_ids.issubset(canary_ids))
            self.assertTrue(
                all(
                    set(item) == {"scope", "query", "expected_document_id"}
                    for item in [
                        *probe_data["probes"],
                        *probe_data["origin_probes"],
                    ]
                )
            )
            probe_row = next(
                row for row in rows if row["document_id"] == probe["expected_document_id"]
            )
            self.assertIn(
                "protected-probe:project:sample-project", probe_row["canary_reasons"]
            )

    def test_project_label_uses_primary_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary = root / "PrimaryCheckout"
            linked = root / "linked-worktree"
            subprocess.run(["git", "init", str(primary)], check=True, capture_output=True)
            (primary / "tracked.txt").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(primary), "add", "tracked.txt"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(primary),
                    "-c",
                    "user.name=Synthetic Test",
                    "-c",
                    "user.email=synthetic@example.invalid",
                    "commit",
                    "-m",
                    "fixture",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(primary), "worktree", "add", str(linked)],
                check=True,
                capture_output=True,
            )
            self.assertEqual(migration.derive_project_scope(str(linked)), "primarycheckout")

    def test_colliding_basenames_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            cwd_one = root / "one" / "SameName"
            cwd_two = root / "two" / "SameName"
            cwd_one.mkdir(parents=True)
            cwd_two.mkdir(parents=True)
            create_database(source / "mnemopi.db")
            for index, cwd in enumerate((cwd_one, cwd_two), 1):
                create_database(
                    source / "banks" / f"bank-{index}-12345678" / "mnemopi.db",
                    working=[
                        {
                            "id": f"working-{index}",
                            "content": f"Synthetic collision record {index} with `COLLISION_KEY`.",
                            "metadata": {"cwd": str(cwd)},
                        }
                    ],
                )
            paths, _ = prepare_fixture(source, root / "run")
            collisions = json.loads(paths.collisions.read_text())
            labels = {row["project_tag"] for row in collisions["basename_collisions"]}
            self.assertIn("project:samename", labels)
            collision = next(
                row
                for row in collisions["basename_collisions"]
                if row["project_tag"] == "project:samename"
            )
            self.assertEqual(len(collision["sources"]), 2)

    def test_redaction_never_leaks_secret(self) -> None:
        secrets = {
            "pem": "-----BEGIN PRIVATE KEY-----\nSYNTHETICPRIVATEKEYDATA1234567890\n-----END PRIVATE KEY-----",
            "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signatureABC123",
            "authorization": "syntheticBearerValue123456789",
            "uri": "user:syntheticPassword42",
            "aws": "AKIA1234567890ABCDEF",
            "openai": "sk-SyntheticOpenAIToken1234567890",
            "github": "ghp_SyntheticGitHubToken1234567890",
            "github_pat": "github_pat_SyntheticGitHubPAT1234567890",
            "gitlab": "glpat-SyntheticGitLabToken1234567890",
            "slack": "xoxb-1234567890-synthetic-token",
            "named": "correct-horse-42",
            "dict_key": "abcdefghijklmnop",
            "camel_secret": "CamelCaseSecret42",
            "camel_token": "ConcatenatedToken42",
            "joined_secret": "UpperJoinedSecret42",
        }
        content = (
            f"{secrets['pem']}\n"
            f"JWT={secrets['jwt']}\n"
            f"Authorization: Bearer {secrets['authorization']}\n"
            f"remote=https://{secrets['uri']}@example.invalid/repo\n"
            f"AWS_ACCESS_KEY_ID={secrets['aws']}\n"
            f"OPENAI_TOKEN={secrets['openai']}\n"
            f"GITHUB_TOKEN={secrets['github']}\n"
            f"PAT={secrets['github_pat']}\n"
            f"GITLAB_TOKEN={secrets['gitlab']}\n"
            f"SLACK_TOKEN={secrets['slack']}\n"
            f"PASSWORD={secrets['named']}\n"
            f'{{"api_secret":"{secrets["named"]}"}}\n'
            "Ordinary authentication prose must remain."
        )
        redacted, findings = migration.redact_credentials(
            {
                "content": content,
                "nested": [content],
                "api_key": secrets["dict_key"],
                "authentication_note": "Ordinary prose with spaces remains visible",
                "author_id": "coding-agent",
                "author_name": "ordinary-author",
                "authorization": "BasicSyntheticCredential42",
                "apiSecret": secrets["camel_secret"],
                "accessToken": secrets["camel_token"],
                "APISECRET": secrets["joined_secret"],
            },
            document_id="mnemopi:synthetic:working:1",
        )
        serialized = json.dumps(redacted, sort_keys=True)
        for secret in secrets.values():
            self.assertNotIn(secret, serialized)
        self.assertIn("Ordinary authentication prose must remain.", serialized)
        self.assertEqual(redacted["authentication_note"], "Ordinary prose with spaces remains visible")
        self.assertEqual(redacted["author_id"], "coding-agent")
        self.assertEqual(redacted["author_name"], "ordinary-author")
        self.assertEqual(redacted["authorization"], "[REDACTED:named-secret]")
        self.assertGreaterEqual(len(findings), len(secrets))
        for finding in findings:
            self.assertEqual(
                set(finding), {"kind", "document_id", "field_path", "line", "count"}
            )
        redacted_again, second_findings = migration.redact_credentials(
            redacted, document_id="mnemopi:synthetic:working:1"
        )
        self.assertEqual(redacted_again, redacted)
        self.assertEqual(second_findings, [])

    def test_document_and_operation_ids_are_deterministic(self) -> None:
        document_id = migration._document_id("synthetic-bank", "working", "source-id")
        record = migration.MigrationRecord(
            source_db="banks/synthetic-bank/mnemopi.db",
            source_bank="synthetic-bank",
            source_table="working_memory",
            source_store="working",
            source_id="source-id",
            document_id=document_id,
            timestamp="2026-01-02T03:04:05Z",
            project_label="synthetic",
            source_cwd="/tmp/synthetic",
            source_git_origin=None,
            metadata={
                "migration_schema_version": "1",
                "source_backend": "mnemopi",
                "source_bank": "synthetic-bank",
                "source_store": "working",
                "source_id": "source-id",
                "source_cwd": "/tmp/synthetic",
                "mnemopi_metadata_json": "{}",
            },
            tags=["project:synthetic", "mnemopi-bank:synthetic-bank", "mnemopi-store:working"],
            observation_scopes=[["project:synthetic"]],
            redacted_content_sha256=hashlib.sha256(b"content").hexdigest(),
            redacted_content_chars=7,
            source_content_chars=7,
            logical_fingerprint="logical",
            redaction_findings=[],
            canary_reasons=[],
        )
        first = migration._request_identity(record, "content", "mnemopi_import")
        second = migration._request_identity(record, "content", "mnemopi_import")
        changed = migration._request_identity(record, "changed content", "mnemopi_import")
        fallback = migration._request_identity(record, "content", "mnemopi_fallback")
        self.assertEqual(document_id, "mnemopi:synthetic-bank:working:source-id")
        self.assertEqual(first[:2], second[:2])
        self.assertNotEqual(first[0], changed[0])
        self.assertNotEqual(first[0], fallback[0])

    def test_resume_skips_completed_operation(self) -> None:
        self.assertEqual(
            migration.resume_action("completed", locally_completed=False, document_valid=True),
            "verify-skip",
        )
        self.assertEqual(
            migration.resume_action("not_found", locally_completed=True, document_valid=True),
            "verify-skip",
        )
        self.assertNotEqual(
            migration.resume_action("completed", locally_completed=False, document_valid=True),
            "submit",
        )
        state_summary = migration._summarize_state(
            [
                {
                    "status": "operation-completed",
                    "document_id": "doc-a",
                    "operation_id": "op-a",
                    "usage": {"total_tokens": 100},
                },
                {
                    "status": "record-completed",
                    "document_id": "doc-a",
                    "operation_id": "op-a",
                    "strategy": "mnemopi_import",
                    "usage": {"total_tokens": 100},
                },
                {
                    "status": "record-completed",
                    "document_id": "doc-a",
                    "operation_id": "op-a",
                    "strategy": "mnemopi_import",
                    "usage": {"total_tokens": 100},
                },
                {"status": "record-failed", "document_id": "doc-b"},
                {"status": "record-failed", "document_id": "doc-b"},
                {
                    "status": "retry-requested",
                    "document_id": "doc-b",
                    "operation_id": "op-b",
                },
                {
                    "status": "operation-completed",
                    "document_id": "doc-b",
                    "operation_id": "op-b",
                    "usage": {"total_tokens": 50},
                },
                {
                    "status": "record-completed",
                    "document_id": "doc-b",
                    "operation_id": "op-b",
                    "strategy": "mnemopi_fallback",
                    "fallback": True,
                    "usage": {"total_tokens": 50},
                },
                {
                    "status": "operation-completed",
                    "operation_id": "consolidate-op",
                    "usage": {"total_tokens": 25},
                },
            ],
            {"doc-a", "doc-b"},
        )
        self.assertEqual(state_summary["completed_documents"], 2)
        self.assertEqual(state_summary["failed_documents"], 0)
        self.assertEqual(state_summary["documents_without_terminal_state"], 0)
        self.assertEqual(state_summary["fallback_documents"], 1)
        self.assertEqual(
            state_summary["completed_by_strategy"],
            {"mnemopi_fallback": 1, "mnemopi_import": 1},
        )
        self.assertEqual(state_summary["process_retry_attempts"], 2)
        self.assertEqual(state_summary["operation_retry_attempts"], 1)
        self.assertEqual(state_summary["retry_attempts"], 3)
        self.assertEqual(state_summary["retried_documents"], 1)
        self.assertEqual(state_summary["usage_operation_count"], 3)
        self.assertEqual(state_summary["operation_usage"]["total_tokens"], 175)

    def test_missing_anchor_selects_verbatim_fallback(self) -> None:
        content = "Use `EXACT_TOKEN` from /tmp/example with version 1.2.3."
        self.assertEqual(
            migration._fallback_reason(content, [{"text": "A generic summary without identifiers."}]),
            "missing-technical-anchor",
        )
        self.assertIsNone(
            migration._fallback_reason(content, [{"text": "Preserve EXACT_TOKEN exactly."}])
        )
        self.assertEqual(migration._fallback_reason(content, []), "empty-memory-units")
        self.assertIsNone(
            migration._fallback_reason("No technical anchor in this sentence.", [{"text": "Fact"}])
        )
        anchors = migration._technical_anchors(
            "See https://example.invalid/not/a/path and read /tmp/real-path."
        )
        posix_paths = [value for kind, value in anchors if kind == "posix-path"]
        self.assertEqual(posix_paths, ["/tmp/real-path"])


if __name__ == "__main__":
    unittest.main()
