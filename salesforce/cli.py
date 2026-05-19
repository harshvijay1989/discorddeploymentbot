from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_SF_BIN = os.getenv("SF_CLI_PATH", "sf")


@dataclass
class DeployResult:
    job_id: str
    status: str
    success: bool
    check_only: bool
    total_components: int = 0
    deployed_components: int = 0
    failed_components: int = 0
    total_tests: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    component_failures: list[dict] = field(default_factory=list)
    test_failures: list[dict] = field(default_factory=list)
    coverage_warnings: list[dict] = field(default_factory=list)
    error_message: str = ""


async def _run(*args: str, cwd: str | None = None) -> dict:
    """Run SF CLI with --json; raise on non-zero exit."""
    cmd = [_SF_BIN, *args, "--json"]
    logger.info("CMD: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    raw = stdout.decode().strip()
    err = stderr.decode().strip()
    logger.info("EXIT CODE: %s", proc.returncode)
    if err:
        logger.info("STDERR: %s", err)
    logger.info("STDOUT: %s", raw[:2000] if raw else "(empty)")
    if not raw:
        raise RuntimeError(f"SF CLI produced no output.\nstderr: {err[:500]}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"SF CLI output is not JSON:\n{raw[:500]}")
    if data.get("status", 0) not in (0, 1):
        msg = data.get("message") or data.get("name") or err
        raise RuntimeError(f"SF CLI error: {msg}")
    return data


async def setup_auth(alias: str, auth_url: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".url", delete=False) as f:
        f.write(auth_url.strip())
        tmp_path = f.name
    try:
        await _run(
            "org", "login", "sfdx-url",
            "--sfdx-url-file", tmp_path,
            "--alias", alias,
            "--no-prompt",
        )
        logger.info("Auth stored for org alias: %s", alias)
    finally:
        os.unlink(tmp_path)


async def retrieve(
    manifest: str,
    org_alias: str,
    cwd: str,
    wait_minutes: int = 30,
) -> None:
    await _run(
        "project", "retrieve", "start",
        "--manifest", manifest,
        "--target-org", org_alias,
        "--wait", str(wait_minutes),
        cwd=cwd,
    )
    logger.info("Retrieve from %s completed", org_alias)


async def deploy_start(
    manifest: str,
    org_alias: str,
    test_classes: list[str],
    cwd: str,
    check_only: bool = False,
) -> tuple[str, str]:
    """Start deployment asynchronously; returns (job_id, deploy_url)."""
    args = [
        "project", "deploy", "start",
        "--manifest", manifest,
        "--target-org", org_alias,
        "--async",
    ]
    if check_only:
        args.append("--dry-run")
    if test_classes:
        args += ["--test-level", "RunSpecifiedTests", "--tests", *test_classes]
    else:
        args += ["--test-level", "RunLocalTests"]

    data = await _run(*args, cwd=cwd)
    result = data.get("result", {})
    job_id = result.get("id", "")
    deploy_url = result.get("deployUrl", "")
    if not job_id:
        raise RuntimeError("Deploy started but no job ID returned")
    logger.info("Deploy started, job ID: %s", job_id)
    return job_id, deploy_url


async def deploy_report(
    job_id: str,
    org_alias: str,
    cwd: str,
    wait_minutes: int = 60,
) -> DeployResult:
    """Poll until deployment completes; returns final result."""
    data = await _run(
        "project", "deploy", "report",
        "--job-id", job_id,
        "--target-org", org_alias,
        "--wait", str(wait_minutes),
        cwd=cwd,
    )
    logger.info("DEPLOY REPORT: %s", json.dumps(data.get("result", {}), indent=2)[:3000])
    return _parse_result(data.get("result", {}))


def _parse_result(r: dict) -> DeployResult:
    details = r.get("details", {})
    run_test = details.get("runTestResult", {})

    comp_failures = [
        {
            "file": f.get("fileName", ""),
            "name": f.get("fullName", ""),
            "problem": f.get("problem", ""),
            "line": str(f.get("lineNumber", "")),
        }
        for f in details.get("componentFailures", [])
    ]

    test_failures = [
        {
            "class": f.get("name", ""),
            "method": f.get("methodName", ""),
            "message": f.get("message", ""),
        }
        for f in run_test.get("failures", [])
    ]

    coverage_warnings = [
        {
            "name": w.get("name", ""),
            "message": w.get("message", ""),
        }
        for w in run_test.get("codeCoverageWarnings", [])
    ]

    total_tests = int(run_test.get("numTestsRun", 0))
    failed_tests = int(run_test.get("numFailures", 0))

    return DeployResult(
        job_id=r.get("id", "unknown"),
        status=r.get("status", "Unknown"),
        success=r.get("success", False),
        check_only=r.get("checkOnly", False),
        total_components=int(r.get("numberComponentsTotal", 0)),
        deployed_components=int(r.get("numberComponentsDeployed", 0)),
        failed_components=int(r.get("numberComponentErrors", 0)),
        total_tests=total_tests,
        tests_passed=total_tests - failed_tests,
        tests_failed=failed_tests,
        component_failures=comp_failures,
        test_failures=test_failures,
        coverage_warnings=coverage_warnings,
        error_message=r.get("errorMessage", "") or r.get("errorStatusCode", ""),
    )
