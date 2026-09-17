import discord
from discord.ext import commands, tasks
import os
import asyncio
from datetime import datetime, timezone
import aiohttp
import requests
from urllib.parse import urlparse, parse_qs
import re

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
UPDATE_INTERVAL = 15

class ErcyScanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.webhook_url = WEBHOOK_URL
        self.place_id = ""
        self.universe_id = ""
        self.game_name = "Unknown"
        self.running = False
        self.last_message_id = None
        self.last_servers_hash = None
        self.scan_task.start()

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"✓ Logged in as {self.bot.user}")
        try:
            await self.bot.tree.sync()
            print("✓ Commands synced")
        except Exception as e:
            print(f"✗ Command sync failed: {e}")

    def extract_place_id(self, url_or_id):
        """Extract place ID from Roblox URL or return if already ID"""
        # if it's just a number, return it
        if url_or_id.isdigit():
            return url_or_id
        
        # try to extract from URL
        match = re.search(r'/games/(\d+)', url_or_id)
        if match:
            return match.group(1)
        
        return None

    async def get_universe_id(self, place_id):
        """Get universe ID from place ID"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://apis.roblox.com/universes/v1/places/{place_id}/universe", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        return str(data.get("universeId"))
        except Exception as e:
            print(f"Universe lookup error: {e}")
        return None

    async def get_game_data(self, universe_id):
        """Get game data from universe ID"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://games.roblox.com/v1/games?universeIds={universe_id}", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("data"):
                            return data["data"][0]
        except Exception as e:
            print(f"Game data error: {e}")
        return None

    async def get_game_icon(self, universe_id):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://thumbnails.roblox.com/v1/games/icons?universeIds={universe_id}&size=512x512&format=Png", timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("data"):
                            return data["data"][0].get("imageUrl")
        except Exception:
            pass
        return None

    async def get_server_list(self, place_id, limit=50):
        if not place_id:
            return []
        servers = []
        cursor = None
        try:
            async with aiohttp.ClientSession() as session:
                for _ in range(3):
                    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?sortOrder=Desc&excludeFullGames=false&limit={min(100, limit)}"
                    if cursor:
                        url += f"&cursor={cursor}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                        if r.status != 200:
                            break
                        data = await r.json()
                        batch = data.get("data") or []
                        servers.extend(batch)
                        cursor = data.get("nextPageCursor")
                        if not cursor or len(servers) >= limit:
                            break
                        await asyncio.sleep(0.25)
        except Exception as e:
            print(f"Server list error: {e}")
        return servers[:limit]

    def delete_old_message(self):
        if not self.last_message_id or not self.webhook_url:
            return
        try:
            requests.delete(f"{self.webhook_url}/messages/{self.last_message_id}", timeout=10)
        except Exception:
            pass
        self.last_message_id = None

    def send_webhook(self, playing, server_count, servers, icon, game_name):
        self.delete_old_message()

        lines = []
        for i, s in enumerate(servers[:25], 1):
            sid = (s.get("id") or "?")[:8]
            p = s.get("playing", 0)
            mx = s.get("maxPlayers", 0)
            ping = s.get("ping")
            ping_s = f"  {ping}ms" if ping is not None else ""
            lines.append(f"`{i:02d}`  **{p}/{mx}**{ping_s}  `{sid}…`")
        server_text = "\n".join(lines) if lines else "_No public servers_"
        if len(servers) > 25:
            server_text += f"\n_…and {len(servers) - 25} more_"

        embed = {
            "title": f"{game_name}  •  Ercy Scanner",
            "description": f"**Players Online:** `{playing}`\n**Active Servers:** `{server_count}`",
            "color": 0x9B59B6,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Ercy Scanner • Live"},
            "fields": [{"name": f"Server List ({min(len(servers), 25)} shown)", "value": (server_text[:1020] or "—"), "inline": False}],
        }
        if icon:
            embed["thumbnail"] = {"url": icon}

        payload = {"embeds": [embed]}
        try:
            r = requests.post(f"{self.webhook_url}?wait=true", json=payload, timeout=14)
            if r.status_code == 200:
                data = r.json()
                self.last_message_id = data.get("id")
                return True
        except Exception as e:
            print(f"Webhook send failed: {e}")
        return False

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def scan_task(self):
        if not self.running or not self.place_id or not self.universe_id:
            return

        try:
            game = await self.get_game_data(self.universe_id)
            icon = await self.get_game_icon(self.universe_id)

            if not game:
                return

            playing = game.get("playing", 0) or 0
            servers = await self.get_server_list(self.place_id)
            server_count = len(servers) if servers else (max(1, round(playing / 50)) if playing > 0 else 0)

            servers_hash = (playing, tuple(sorted((s.get("id"), s.get("playing")) for s in servers[:30])))

            if servers_hash != self.last_servers_hash:
                ok = self.send_webhook(playing, server_count, servers, icon, self.game_name)
                self.last_servers_hash = servers_hash
                print(f"✓ Updated: {playing} players, {server_count} servers" if ok else f"✗ Webhook failed")

        except Exception as e:
            print(f"Loop error: {e}")

    @discord.app_commands.command(name="link", description="Paste Roblox game link to start scanning")
    @discord.app_commands.describe(url="Roblox game URL or place ID")
    async def link_command(self, interaction: discord.Interaction, url: str):
        if not self.webhook_url:
            await interaction.response.send_message("❌ WEBHOOK_URL not set in environment", ephemeral=True)
            return

        await interaction.response.defer()

        place_id = self.extract_place_id(url.strip())
        if not place_id:
            await interaction.followup.send("❌ Invalid URL or ID format")
            return

        # get universe ID from place ID
        universe_id = await self.get_universe_id(place_id)
        if not universe_id:
            await interaction.followup.send("❌ Could not find universe ID — invalid game?")
            return

        # fetch game data
        game = await self.get_game_data(universe_id)
        if not game:
            await interaction.followup.send("❌ Could not fetch game data from Roblox API")
            return

        # start scanning
        self.place_id = place_id
        self.universe_id = universe_id
        self.game_name = game.get("name", "Unknown Game")
        self.running = True
        self.last_message_id = None
        self.last_servers_hash = None

        playing = game.get("playing", 0) or 0
        icon = await self.get_game_icon(universe_id)
        servers = await self.get_server_list(place_id)
        server_count = len(servers) if servers else (max(1, round(playing / 50)) if playing > 0 else 0)
        servers_hash = (playing, tuple(sorted((s.get("id"), s.get("playing")) for s in servers[:30])))

        ok = self.send_webhook(playing, server_count, servers, icon, self.game_name)
        self.last_servers_hash = servers_hash

        print(f"✓ Scanner started — {self.game_name} ({universe_id})")
        await interaction.followup.send(f"✓ **Scanning:** {self.game_name}\n**Players:** `{playing}`\n**Servers:** `{server_count}`\n**Place ID:** `{place_id}`")

    @discord.app_commands.command(name="stop", description="Stop the scanner")
    async def stop_command(self, interaction: discord.Interaction):
        if not self.running:
            await interaction.response.send_message("⚠ Scanner not running", ephemeral=True)
            return
        
        self.running = False
        self.delete_old_message()
        print("✗ Scanner stopped")
        await interaction.response.send_message("✓ Scanner stopped & message deleted", ephemeral=True)

    @discord.app_commands.command(name="status", description="Check scanner status")
    async def status_command(self, interaction: discord.Interaction):
        if self.running:
            msg = f"✓ **Running**\n**Game:** {self.game_name}\n**Place ID:** `{self.place_id}`\n**Universe ID:** `{self.universe_id}`"
        else:
            msg = "❌ **Not running** — use `/link` to start"
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.app_commands.command(name="test", description="Test webhook connection")
    async def test_command(self, interaction: discord.Interaction):
        if not self.webhook_url:
            await interaction.response.send_message("❌ WEBHOOK_URL not set", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            r = requests.post(f"{self.webhook_url}?wait=true", json={"embeds": [{"title": "✓ Webhook Test", "description": "Connection successful.", "color": 0x9B59B6, "timestamp": datetime.now(timezone.utc).isoformat()}]}, timeout=10)
            if r.status_code in (200, 204):
                await interaction.followup.send("✓ Webhook test passed")
            else:
                await interaction.followup.send(f"❌ Webhook returned {r.status_code}")
        except Exception as e:
            await interaction.followup.send(f"❌ {e}")

    @discord.app_commands.command(name="help", description="Show all commands")
    async def help_command(self, interaction: discord.Interaction):
        help_text = """
**Ercy Scanner Commands:**

`/link <URL or ID>` — Paste Roblox game URL or place ID to start scanning
Example: `/link https://www.roblox.com/games/17375940438/SHINJUKU-1988`

`/stop` — Stop the scanner

`/status` — Check if scanner is running

`/test` — Test webhook connection

`/help` — Show this message
"""
        await interaction.response.send_message(help_text, ephemeral=True)


async def main():
    async with bot:
        await bot.add_cog(ErcyScanner(bot))
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
