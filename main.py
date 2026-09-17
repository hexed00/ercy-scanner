import discord
from discord.ext import commands, tasks
import os
import time
import asyncio
from datetime import datetime, timezone
import aiohttp
import requests

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
UNIVERSE_ID = os.getenv("UNIVERSE_ID", "5946282691")
UPDATE_INTERVAL = 15

class ErcyScanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.webhook_url = WEBHOOK_URL
        self.universe_id = UNIVERSE_ID
        self.place_id = ""
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

    async def get_game_data(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://games.roblox.com/v1/games?universeIds={self.universe_id}", timeout=aiohttp.ClientTimeout(total=12)) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("data"):
                            g = data["data"][0]
                            playing = g.get("playing", 0) or 0
                            root_place = g.get("rootPlaceId")
                            if root_place and not self.place_id:
                                self.place_id = str(root_place)
                            return playing, g
        except Exception as e:
            print(f"Game data error: {e}")
        return None, None

    async def get_game_icon(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://thumbnails.roblox.com/v1/games/icons?universeIds={self.universe_id}&size=512x512&format=Png", timeout=aiohttp.ClientTimeout(total=10)) as r:
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
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=14)) as r:
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

    def send_webhook(self, playing, server_count, servers, icon):
        self.delete_old_message()

        lines = []
        for i, s in enumerate(servers[:25], 1):
            sid = (s.get("id") or "?")[:8]
            p = s.get("playing", 0)
            mx = s.get("maxPlayers", 0)
            ping = s.get("ping")
            ping_s = f"  {ping}ms" if ping is not None else ""
            lines.append(f"`{i:02d}`  **{p}/{mx}**{ping_s}  `{sid}…`")
        server_text = "\n".join(lines) if lines else "_No public servers returned_"
        if len(servers) > 25:
            server_text += f"\n_…and {len(servers) - 25} more_"

        embed = {
            "title": "SHINJUKU 1988  •  Ercy Scanner",
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
            else:
                print(f"Webhook post {r.status_code}")
        except Exception as e:
            print(f"Webhook send failed: {e}")
        return False

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def scan_task(self):
        if not self.running:
            return

        try:
            playing, game = await self.get_game_data()
            icon = await self.get_game_icon()

            if playing is None:
                return

            place = self.place_id or (str(game.get("rootPlaceId")) if game else None)
            servers = await self.get_server_list(place) if place else []
            server_count = len(servers) if servers else (max(1, round(playing / 50)) if playing > 0 else 0)

            servers_hash = (playing, tuple(sorted((s.get("id"), s.get("playing")) for s in servers[:30])))

            if servers_hash != self.last_servers_hash:
                ok = self.send_webhook(playing, server_count, servers, icon)
                self.last_servers_hash = servers_hash
                print(f"✓ Updated: {playing} players, {server_count} servers" if ok else f"✗ Webhook failed")

        except Exception as e:
            print(f"Loop error: {e}")

    @discord.app_commands.command(name="scan", description="Ercy Scanner controls")
    @discord.app_commands.describe(action="start, stop, or test", universe="Universe ID", place="Place ID")
    async def scan_command(self, interaction: discord.Interaction, action: str, universe: str = None, place: str = None):
        if not self.webhook_url:
            await interaction.response.send_message("❌ WEBHOOK_URL not set", ephemeral=True)
            return

        action = action.lower().strip()

        if action == "start":
            if self.running:
                await interaction.response.send_message("⚠ Scanner already running", ephemeral=True)
                return

            await interaction.response.defer()
            
            self.universe_id = universe or UNIVERSE_ID
            self.place_id = place or ""
            self.running = True
            self.last_message_id = None
            self.last_servers_hash = None

            try:
                playing, game = await self.get_game_data()
                if playing is None:
                    await interaction.followup.send("❌ Failed to fetch from Roblox API — check UNIVERSE_ID")
                    self.running = False
                    return

                icon = await self.get_game_icon()
                place_id = self.place_id or (str(game.get("rootPlaceId")) if game else None)
                servers = await self.get_server_list(place_id) if place_id else []
                server_count = len(servers) if servers else (max(1, round(playing / 50)) if playing > 0 else 0)
                servers_hash = (playing, tuple(sorted((s.get("id"), s.get("playing")) for s in servers[:30])))
                
                ok = self.send_webhook(playing, server_count, servers, icon)
                self.last_servers_hash = servers_hash
                print(f"✓ Scanner started — universe {self.universe_id}")
                await interaction.followup.send(f"✓ Scanner started\n**Universe:** `{self.universe_id}`\n**Players:** `{playing}`\n**Servers:** `{server_count}`")
            except Exception as e:
                await interaction.followup.send(f"❌ Error: {e}")
                self.running = False

        elif action == "stop":
            if not self.running:
                await interaction.response.send_message("⚠ Scanner not running", ephemeral=True)
                return
            self.running = False
            self.delete_old_message()
            print("✗ Scanner stopped")
            await interaction.response.send_message("✓ Scanner stopped", ephemeral=True)

        elif action == "test":
            await interaction.response.defer(ephemeral=True)
            try:
                r = requests.post(f"{self.webhook_url}?wait=true", json={"embeds": [{"title": "Ercy Scanner — Test", "description": "Webhook connected.", "color": 0x9B59B6, "timestamp": datetime.now(timezone.utc).isoformat(), "footer": {"text": "Ercy Scanner"}}]}, timeout=12)
                if r.status_code in (200, 204):
                    await interaction.followup.send("✓ Webhook test successful")
                else:
                    await interaction.followup.send(f"❌ Webhook returned {r.status_code}")
            except Exception as e:
                await interaction.followup.send(f"❌ {e}")
        else:
            await interaction.response.send_message("❌ Use: start, stop, or test", ephemeral=True)


async def main():
    async with bot:
        await bot.add_cog(ErcyScanner(bot))
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
