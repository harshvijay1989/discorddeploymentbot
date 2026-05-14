import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from salesforce import cli as sf

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    logger.info("Bot ready as %s", bot.user)


async def _auth_orgs() -> None:
    """Authenticate UAT and PROD orgs from SFDX auth URLs at startup."""
    pairs = [
        (os.getenv("UAT_SF_ORG_ALIAS", "uat"), os.environ["UAT_SFDX_AUTH_URL"]),
        (os.getenv("PROD_SF_ORG_ALIAS", "prod"), os.environ["PROD_SFDX_AUTH_URL"]),
    ]
    for alias, url in pairs:
        try:
            await sf.setup_auth(alias, url)
            logger.info("Authenticated org: %s", alias)
        except Exception as exc:
            logger.error("Failed to authenticate org %s: %s", alias, exc)
            raise SystemExit(1) from exc


async def main() -> None:
    async with bot:
        await _auth_orgs()
        await bot.load_extension("commands.deploy")
        await bot.start(os.environ["DISCORD_BOT_TOKEN"])


if __name__ == "__main__":
    asyncio.run(main())
