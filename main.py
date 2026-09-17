import discord
from discord.ext import commands
import asyncio
import sys
import os

from ercy_scanner import ErcyScanner

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

scanner = None
bot_token = os.getenv("MTU1MDI2Njg4OTIxNTY3MjM4Mg.GzKERo.EX0tSiEXpOJTJ6oQVLhM1Bvp76kRNYtIC4UiYc")

@bot.event
async def on_ready():
    print(f"🟣 Ercy Bot online — {bot.user}")
    await bot.tree.sync()

@bot.tree.command(name="scan", description="Start / stop / status the Roblox scanner")
async def scan(interaction: discord.Interaction, action: str = "start", universe_id: str = "5946282691"):
    global scanner

    if action.lower() in ("new", "start"):
        if scanner and scanner.running:
            await interaction.response.send_message("Scanner is already running.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        class CustomGUI(ErcyScanner):
            async def log_msg(self, msg, level="info"):
                await interaction.channel.send(f"[{level.upper()}] {msg}")

            async def set_status(self, text, color=None):
                await interaction.channel.send(text)

        scanner = CustomGUI(sys.argv)
        await interaction.followup.send("🟣 Scanner started. Watching SHINJUKU 1988...", ephemeral=True)
        return

    elif action.lower() == "stop":
        if not scanner or not scanner.running:
            await interaction.response.send_message("Nothing to stop.", ephemeral=True)
            return
        scanner.running = False
        await interaction.response.send_message("🟣 Scanner stopped.", ephemeral=True)
        return

    elif action.lower() == "status":
        status = "🟢 Running" if (scanner and scanner.running) else "🔴 Stopped"
        await interaction.response.send_message(f"Ercy Scanner: {status}", ephemeral=True)
        return

    await interaction.response.send_message("Unknown action. Use: /scan new, /scan status, /scan stop", ephemeral=True)

bot.run(bot_token)
