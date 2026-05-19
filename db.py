from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PACKAGES_DIR = DATA_DIR / "packages"
DB_PATH = DATA_DIR / "deployments.db"


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    PACKAGES_DIR.mkdir(exist_ok=True)


def _conn() -> sqlite3.Connection:
    _ensure_dirs()
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                discord_user TEXT,
                discord_channel TEXT,
                package_filename TEXT,
                package_xml_path TEXT,
                test_classes TEXT,
                check_only INTEGER,
                job_id TEXT,
                deploy_url TEXT,
                status TEXT,
                success INTEGER,
                error_message TEXT,
                components_total INTEGER,
                components_deployed INTEGER,
                components_failed INTEGER,
                tests_run INTEGER,
                tests_passed INTEGER,
                tests_failed INTEGER,
                coverage_warnings TEXT,
                test_failures TEXT
            )
        """)


def save_package(run_id: int, xml_bytes: bytes) -> str:
    _ensure_dirs()
    path = PACKAGES_DIR / f"{run_id}_package.xml"
    path.write_bytes(xml_bytes)
    return str(path)


def create_run(
    discord_user: str,
    discord_channel: str,
    package_filename: str,
    test_classes: list[str],
    check_only: bool,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO deployments
               (created_at, discord_user, discord_channel, package_filename,
                test_classes, check_only, status)
               VALUES (?, ?, ?, ?, ?, ?, 'Started')""",
            (now, discord_user, discord_channel, package_filename,
             ",".join(test_classes), int(check_only)),
        )
        return cur.lastrowid


def update_package_path(run_id: int, path: str) -> None:
    with _conn() as c:
        c.execute("UPDATE deployments SET package_xml_path=? WHERE id=?", (path, run_id))


def update_job(run_id: int, job_id: str, deploy_url: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE deployments SET job_id=?, deploy_url=?, status='Running' WHERE id=?",
            (job_id, deploy_url, run_id),
        )


def update_result(run_id: int, result) -> None:
    """Save final deploy result. `result` is a DeployResult dataclass."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute(
            """UPDATE deployments SET
               completed_at=?, status=?, success=?, error_message=?,
               components_total=?, components_deployed=?, components_failed=?,
               tests_run=?, tests_passed=?, tests_failed=?,
               coverage_warnings=?, test_failures=?
               WHERE id=?""",
            (
                now, result.status, int(result.success), result.error_message,
                result.total_components, result.deployed_components, result.failed_components,
                result.total_tests, result.tests_passed, result.tests_failed,
                json.dumps(result.coverage_warnings), json.dumps(result.test_failures),
                run_id,
            ),
        )


def mark_failed(run_id: int, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute(
            "UPDATE deployments SET completed_at=?, status='Errored', success=0, error_message=? WHERE id=?",
            (now, error[:1000], run_id),
        )


def recent_runs(limit: int = 10) -> list[sqlite3.Row]:
    with _conn() as c:
        return list(c.execute(
            "SELECT * FROM deployments ORDER BY id DESC LIMIT ?", (limit,),
        ))
