from __future__ import annotations

import logging
import os
import tempfile
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
        await interaction.response.defer(thinking=True)

        test_list = [t.strip() for t in test_classes.split(",") if t.strip()]
        xml_bytes = await package_xml.read()

        msg = await interaction.followup.send(
            embed=embeds.started_embed(package_xml.filename, test_list, check_only),
            wait=True,
        )

        with tempfile.TemporaryDirectory(prefix="sfbot_") as tmp:
            # SF CLI requires a valid SFDX project in the working directory
            (Path(tmp) / "sfdx-project.json").write_text(
                '{"packageDirectories":[{"path":"retrieved","default":true}],"sourceApiVersion":"59.0"}'
            )
            pkg_xml_path = Path(tmp) / "package.xml"
            pkg_xml_path.write_bytes(xml_bytes)
            retrieved_dir = "retrieved"  # relative to tmp

            # ── Step 1: Retrieve from UAT ──────────────────────────────────────
            await msg.edit(embed=embeds.retrieving_embed(package_xml.filename, test_list, check_only))
            try:
                await sf.retrieve(str(pkg_xml_path), retrieved_dir, UAT_ALIAS, cwd=tmp)
            except Exception as exc:
                logger.error("Retrieve failed:\n%s", traceback.format_exc())
                await msg.edit(embed=embeds.error_embed("Retrieve (UAT)", str(exc)))
                return

            # ── Step 2: Deploy to Production ───────────────────────────────────
            await msg.edit(embed=embeds.deploying_embed(package_xml.filename, test_list, check_only))
            try:
                result = await sf.deploy(retrieved_dir, PROD_ALIAS, test_list, cwd=tmp, check_only=check_only)
            except Exception as exc:
                logger.error("Deploy failed:\n%s", traceback.format_exc())
                await msg.edit(embed=embeds.error_embed("Deploy (Production)", str(exc)))
                return

        await msg.edit(embed=embeds.result_embed(result, test_list))
        logger.info("Deployment %s finished: %s", result.job_id, result.status)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DeployCog(bot))
