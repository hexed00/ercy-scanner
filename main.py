# ercy_scanner.py
# discord bot + ercy scanner for railway
# slash commands: /scan start, /scan stop, /scan test
# webhook sends exact embed, replaces old message every update

import discord
from discord.ext import commands, tasks
import os
import time
from datetime import datetime, timezone
import requests

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "YOUR_TOKEN_HERE"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "
https://discord.com/api/webhooks/1537445519914311730/0iKL1fgoR6IBiUwkPGgy0TrSC-e2Ku2_S5UOXdkIqGxf_P0omfVKH59tgPDELmrQRKyr"
UNIVERSE_ID = "5946282691"
UPDATE_INTERVAL = 15

class ErcyScanner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.webhook_url = ""
        self.universe_id = UNIVERSE_ID
        self.place_id = ""
        self.running = False
        self.last_message_id = None
        self.last_servers_hash = None

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"✓ Logged in as {self.bot.user}")

    def validate_webhook(self, url):
        url = (url or "").strip()
        if not url:
            return False
        low = url.lower()
        if "discord.com/api/webhooks/" not in low and "discordapp.com/api/webhooks/" not in low:
            return False
        try:
            if "/webhooks/" in url:
                return True
        except Exception:
            pass
        return False

    async def get_game_data(self):
        try:
            r = requests.get(f"https://games.roblox.com/v1/games?universeIds={self.universe_id}", timeout=12)
            data = r.json()
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
            r = requests.get(f"https://thumbnails.roblox.com/v1/games/icons?universeIds={self.universe_id}&size=512x512&format=Png", timeout=10)
            data = r.json()
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
            for _ in range(3):
                url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?sortOrder=Desc&excludeFullGames=false&limit={min(100, limit)}"
                if cursor:
                    url += f"&cursor={cursor}"
                r = requests.get(url, timeout=14)
                if r.status_code != 200:
                    break
                data = r.json()
                batch = data.get("data") or []
                servers.extend(batch)
                cursor = data.get("nextPageCursor")
                if not cursor or len(servers) >= limit:
                    break
                time.sleep(0.25)
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
            "fields": [
                {
                    "name": f"Server List ({min(len(servers), 25)} shown)",
                    "value": (server_text[:1020] or "—"),
                    "inline": False,
                }
            ],
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
                print(f"Webhook post {r.status_code}: {r.text[:120]}")
        except Exception as e:
            print(f"Webhook send failed: {e}")
        return False

    async def scan_loop(self):
        while self.running:
            try:
                playing, game = await self.get_game_data()
                icon = await self.get_game_icon()

                if playing is None:
                    await asyncio.sleep(UPDATE_INTERVAL)
                    continue

                place = self.place_id or (str(game.get("rootPlaceId")) if game else None)
                servers = await self.get_server_list(place) if place else []
                server_count = len(servers) if servers else (max(1, round(playing / 50)) if playing > 0 else 0)

                servers_hash = (playing, tuple(sorted((s.get("id"), s.get("playing")) for s in servers[:30])))

                if servers_hash != self.last_servers_hash:
                    ok = self.send_webhook(playing, server_count, servers, icon)
                    self.last_servers_hash = servers_hash
                    print(f"✓ Updated: {playing} players, {server_count} servers" if ok else f"✗ Webhook failed")
                else:
                    print(f"• No change ({playing} players)")

            except Exception as e:
                print(f"Loop error: {e}")

            await asyncio.sleep(UPDATE_INTERVAL)

    @discord.app_commands.command(name="scan", description="Scanner controls")
    @discord.app_commands.describe(
        action="start, stop, or test",
        webhook="Discord webhook URL (for start)",
        universe="Universe ID (for start)",
        place="Place ID (optional)"
    )
    async def scan_command(
        self,
        interaction: discord.Interaction,
        action: str,
        webhook: str = None,
        universe: str = None,
        place: str = None,
    ):
        action = action.lower().strip()

        if action == "start":
            if not webhook or not self.validate_webhook(webhook):
                await interaction.response.send_message("❌ Provide a valid Discord webhook URL", ephemeral=True)
                return
            self.webhook_url = webhook
            self.universe_id = universe or UNIVERSE_ID
            self.place_id = place or ""
            self.running = True
            self.last_message_id = None
            self.last_servers_hash = None
            print(f"✓ Scanner started — universe {self.universe_id}")
            await interaction.response.send_message(f"✓ Scanner started\n**Universe:** `{self.universe_id}`\n**Webhook:** Connected", ephemeral=False)
            await self.scan_loop()

        elif action == "stop":
            self.running = False
            print("✗ Scanner stopped")
            await interaction.response.send_message("✓ Scanner stopped", ephemeral=True)

        elif action == "test":
            if not webhook or not self.validate_webhook(webhook):
                await interaction.response.send_message("❌ Provide a valid Discord webhook URL", ephemeral=True)
                return
            try:
                r = requests.post(f"{webhook}?wait=true", json={"embeds": [{"title": "Ercy Scanner — Test", "description": "Webhook connected. Scanner is ready.", "color": 0x9B59B6, "timestamp": datetime.now(timezone.utc).isoformat(), "footer": {"text": "Ercy Scanner"}}]}, timeout=12)
                if r.status_code in (200, 204):
                    await interaction.response.send_message("✓ Webhook test successful", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ Webhook returned {r.status_code}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Use: start, stop, or test", ephemeral=True)


async def main():
    async with bot:
        await bot.add_cog(ErcyScanner(bot))
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
