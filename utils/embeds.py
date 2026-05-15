from __future__ import annotations

import discord

from salesforce.cli import DeployResult

_GREEN = 0x2ECC71
_BLUE = 0x3498DB
_ORANGE = 0xE67E22
_RED = 0xE74C3C


def _test_field(test_classes: list[str]) -> str:
    return ", ".join(f"`{t}`" for t in test_classes) if test_classes else "RunLocalTests"


def started_embed(filename: str, test_classes: list[str], check_only: bool) -> discord.Embed:
    e = discord.Embed(title="Salesforce Deployment Pipeline", color=_BLUE)
    e.add_field(name="File", value=f"`{filename}`", inline=True)
    e.add_field(name="Mode", value="Validate Only" if check_only else "Deploy", inline=True)
    e.add_field(name="Test Classes", value=_test_field(test_classes), inline=False)
    e.set_footer(text="Starting…")
    return e


def retrieving_embed(filename: str, test_classes: list[str], check_only: bool) -> discord.Embed:
    e = discord.Embed(title="Salesforce Deployment Pipeline", color=_BLUE)
    e.add_field(name="File", value=f"`{filename}`", inline=True)
    e.add_field(name="Mode", value="Validate Only" if check_only else "Deploy", inline=True)
    e.add_field(name="Test Classes", value=_test_field(test_classes), inline=False)
    e.add_field(name="⏳ Step 1 — Retrieve from UAT", value="Retrieving metadata…", inline=False)
    e.set_footer(text="Retrieving from UAT org…")
    return e


def deploying_embed(filename: str, test_classes: list[str], check_only: bool, job_id: str = "") -> discord.Embed:
    action = "Validate (check only)" if check_only else "Deploy"
    e = discord.Embed(title="Salesforce Deployment Pipeline", color=_ORANGE)
    e.add_field(name="File", value=f"`{filename}`", inline=True)
    e.add_field(name="✅ Step 1 — Retrieved from UAT", value="Done", inline=False)
    deploy_value = f"Running, please wait…{chr(10)}`{job_id}`" if job_id else "Running, please wait…"
    e.add_field(name=f"⏳ Step 2 — {action} to Production", value=deploy_value, inline=False)
    e.set_footer(text="This may take a few minutes…")
    return e


def result_embed(result: DeployResult, test_classes: list[str]) -> discord.Embed:
    if result.success:
        color = _GREEN
        title = "✅ Validation Passed" if result.check_only else "✅ Deployment Succeeded"
    else:
        color = _RED
        title = "❌ Validation Failed" if result.check_only else "❌ Deployment Failed"

    e = discord.Embed(title=title, color=color)
    e.add_field(name="Job ID", value=f"`{result.job_id}`", inline=True)
    e.add_field(name="Status", value=result.status, inline=True)
    e.add_field(
        name="Components",
        value=f"Total: {result.total_components} | Deployed: {result.deployed_components} | Failed: {result.failed_components}",
        inline=False,
    )

    if result.total_tests > 0 or test_classes:
        e.add_field(
            name="Tests",
            value=f"Total: {result.total_tests} | Passed: {result.tests_passed} | Failed: {result.tests_failed}",
            inline=False,
        )

    if result.component_failures:
        lines = [f"`{f['file']}` line {f['line']}: {f['problem'][:80]}" for f in result.component_failures[:5]]
        if len(result.component_failures) > 5:
            lines.append(f"…and {len(result.component_failures) - 5} more")
        e.add_field(name="Component Failures", value="\n".join(lines), inline=False)

    if result.test_failures:
        lines = [f"`{f['class']}.{f['method']}`: {f['message'][:80]}" for f in result.test_failures[:5]]
        if len(result.test_failures) > 5:
            lines.append(f"…and {len(result.test_failures) - 5} more")
        e.add_field(name="Test Failures", value="\n".join(lines), inline=False)

    if result.coverage_warnings:
        lines = [f"`{w['name']}`: {w['message'][:100]}" for w in result.coverage_warnings[:5]]
        if len(result.coverage_warnings) > 5:
            lines.append(f"…and {len(result.coverage_warnings) - 5} more")
        e.add_field(name="Coverage Warnings", value="\n".join(lines), inline=False)

    if result.error_message and not result.success:
        e.add_field(name="Error", value=result.error_message[:1000], inline=False)

    e.set_footer(text="Salesforce Deployment Bot v2")
    return e


def error_embed(step: str, error: str) -> discord.Embed:
    e = discord.Embed(title=f"❌ Error at {step}", color=_RED)
    e.add_field(name="Details", value=f"```{error[:1000]}```", inline=False)
    e.set_footer(text="Check bot logs for full traceback")
    return e
