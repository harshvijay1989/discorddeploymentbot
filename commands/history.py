from __future__ import annotations

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

import db


def _fmt_time(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso[:16]


def _status_icon(row) -> str:
    s = row["status"] or ""
    if s == "Succeeded":
        return "✅"
    if s in ("Failed", "Errored"):
        return "❌"
    if s == "Running":
        return "⏳"
    return "•"


class HistoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="history", description="Show recent deployment runs")
    @app_commands.describe(limit="How many runs to show (default 10, max 25)")
    async def history(self, interaction: discord.Interaction, limit: int = 10) -> None:
        limit = max(1, min(limit, 25))
        rows = db.recent_runs(limit)

        if not rows:
            await interaction.response.send_message("No deployments yet.", ephemeral=True)
            return

        e = discord.Embed(title=f"Recent Deployments (last {len(rows)})", color=0x3498DB)
        for r in rows:
            icon = _status_icon(r)
            time_str = _fmt_time(r["created_at"])
            test_count = len((r["test_classes"] or "").split(",")) if r["test_classes"] else 0
            line = f"`#{r['id']}` {icon} **{r['status'] or 'Unknown'}** • {time_str}"
            details = f"File: `{r['package_filename'] or '—'}` • Tests: {test_count}"
            if r["job_id"]:
                if r["deploy_url"]:
                    details += f" • [`{r['job_id']}`]({r['deploy_url']})"
                else:
                    details += f" • `{r['job_id']}`"
            e.add_field(name=line, value=details, inline=False)

        e.set_footer(text=f"Use /run <id> to see details")
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="run", description="Show details of a specific deployment run")
    @app_commands.describe(run_id="The run ID (see /history)")
    async def run(self, interaction: discord.Interaction, run_id: int) -> None:
        rows = [r for r in db.recent_runs(1000) if r["id"] == run_id]
        if not rows:
            await interaction.response.send_message(f"Run #{run_id} not found.", ephemeral=True)
            return
        r = rows[0]

        e = discord.Embed(title=f"Deployment Run #{r['id']}", color=0x3498DB)
        e.add_field(name="Status", value=f"{_status_icon(r)} {r['status'] or 'Unknown'}", inline=True)
        e.add_field(name="Started", value=_fmt_time(r["created_at"]), inline=True)
        e.add_field(name="Completed", value=_fmt_time(r["completed_at"]), inline=True)
        e.add_field(name="User", value=r["discord_user"] or "—", inline=True)
        e.add_field(name="File", value=f"`{r['package_filename']}`", inline=True)
        e.add_field(name="Mode", value="Validate" if r["check_only"] else "Deploy", inline=True)

        if r["job_id"]:
            link = f"[`{r['job_id']}`]({r['deploy_url']})" if r["deploy_url"] else f"`{r['job_id']}`"
            e.add_field(name="Job ID", value=link, inline=False)

        if r["test_classes"]:
            e.add_field(name="Test Classes", value=", ".join(f"`{t}`" for t in r["test_classes"].split(",")), inline=False)

        if r["components_total"] is not None:
            e.add_field(
                name="Components",
                value=f"Total: {r['components_total']} | Deployed: {r['components_deployed']} | Failed: {r['components_failed']}",
                inline=False,
            )

        if r["tests_run"] is not None and r["tests_run"] > 0:
            e.add_field(
                name="Tests",
                value=f"Run: {r['tests_run']} | Passed: {r['tests_passed']} | Failed: {r['tests_failed']}",
                inline=False,
            )

        if r["error_message"]:
            e.add_field(name="Error", value=r["error_message"][:1000], inline=False)

        e.set_footer(text=f"package.xml stored at: {r['package_xml_path']}")
        await interaction.response.send_message(embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HistoryCog(bot))
