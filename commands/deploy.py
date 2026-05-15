from __future__ import annotations

import logging
import os
import shutil
import traceback
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from salesforce import cli as sf
from utils import embeds

logger = logging.getLogger(__name__)

UAT_ALIAS = os.getenv("UAT_SF_ORG_ALIAS", "uat")
PROD_ALIAS = os.getenv("PROD_SF_ORG_ALIAS", "prod")

SF_PROJECT_DIR = Path(__file__).parent.parent / "sfbot"


class DeployCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="deploy", description="Retrieve from UAT and deploy to Production")
    @app_commands.describe(
        package_xml="Attach your package.xml file",
        test_classes="Comma-separated Apex test classes (e.g. AccountTest,ContactTest)",
        check_only="Validate without deploying (default: false)",
    )
    async def deploy(
        self,
        interaction: discord.Interaction,
        package_xml: discord.Attachment,
        test_classes: str,
        check_only: bool = False,
    ) -> None:
        try:
            await interaction.response.defer(thinking=True)
        except discord.errors.NotFound:
            logger.warning("Interaction expired before defer — bot was likely restarting")
            return

        test_list = [t.strip() for t in test_classes.split(",") if t.strip()]
        xml_bytes = await package_xml.read()

        msg = await interaction.followup.send(
            embed=embeds.started_embed(package_xml.filename, test_list, check_only),
            wait=True,
        )

        manifest = "package.xml"

        try:
            (SF_PROJECT_DIR / manifest).write_bytes(xml_bytes)

            # ── Step 1: Retrieve from UAT ──────────────────────────────────────
            await msg.edit(embed=embeds.retrieving_embed(package_xml.filename, test_list, check_only))
            try:
                await sf.retrieve(manifest, UAT_ALIAS, cwd=str(SF_PROJECT_DIR))
            except Exception as exc:
                logger.error("Retrieve failed:\n%s", traceback.format_exc())
                await msg.edit(embed=embeds.error_embed("Retrieve (UAT)", str(exc)))
                return

            # ── Step 2: Start deploy (async, get job ID) ───────────────────────
            await msg.edit(embed=embeds.deploying_embed(package_xml.filename, test_list, check_only))
            try:
                job_id = await sf.deploy_start(manifest, PROD_ALIAS, test_list, cwd=str(SF_PROJECT_DIR), check_only=check_only)
            except Exception as exc:
                logger.error("Deploy start failed:\n%s", traceback.format_exc())
                await msg.edit(embed=embeds.error_embed("Deploy (Production)", str(exc)))
                return

            await msg.edit(embed=embeds.deploying_embed(package_xml.filename, test_list, check_only, job_id=job_id))

        finally:
            force_app_default = SF_PROJECT_DIR / "force-app" / "main" / "default"
            if force_app_default.exists():
                shutil.rmtree(force_app_default)
                force_app_default.mkdir()
            (SF_PROJECT_DIR / manifest).unlink(missing_ok=True)
            logger.info("Cleaned up force-app/main/default and package.xml")

        # ── Step 3: Wait for result and report ────────────────────────────────
        try:
            result = await sf.deploy_report(job_id, PROD_ALIAS, cwd=str(SF_PROJECT_DIR))
        except Exception as exc:
            logger.error("Deploy report failed:\n%s", traceback.format_exc())
            await msg.edit(embed=embeds.error_embed("Deploy Report", str(exc)))
            return

        await msg.edit(embed=embeds.result_embed(result, test_list))
        logger.info("Deploy %s finished: %s", result.job_id, result.status)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DeployCog(bot))
