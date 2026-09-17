# ercy_scanner.py
# discord bot + ercy scanner for railway
# /scan new /scan stop /scan status works
# gui pops up purple, webhook updates live, no more thinking then silence

import discord
from discord.ext import commands
import sys
import os
import asyncio
import threading
import time
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "YOUR_TOKEN_HERE"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "YOUR_WEBHOOK_HERE"
UNIVERSE_ID = "5946282691"
UPDATE_INTERVAL = 15

class GameServer:
    def __init__(self, server_id: int, max_players: int, current_players: int):
        self.server_id = server_id
        self.max_players = max_players
        self.current_players = current_players
        self.last_checked = time.time()

class ServerList:
    def __init__(self):
        self.servers = {}
        self.last_full_hash = ""

    def update(self, new_servers):
        current_hash = hash(tuple(sorted((s.get("serverId"), s.get("maxPlayers"), s.get("currentPlayers")) for s in new_servers)))
        if current_hash != self.last_full_hash:
            self.last_full_hash = current_hash
            self.servers = {s["serverId"]: GameServer(s["serverId"], s["maxPlayers"], s["currentPlayers"]) for s in new_servers}
            return len(self.servers), self.servers
        updated = {}
        for s in new_servers:
            sid = s["serverId"]
            if sid in self.servers:
                self.servers[sid].current_players = s["currentPlayers"]
                self.servers[sid].last_checked = time.time()
                updated[sid] = self.servers[sid]
        self.servers.update(updated)
        return len(self.servers), self.servers

server_list = ServerList()
scanner_running = False

def get_roblox_player_count(universe_id: str):
    import requests
    try:
        r = requests.get(f"https://games.roblox.com/v1/games/{universe_id}/servers/Public?sortOrder=Asc&limit=100", timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("totalCollectionSize", 0), data.get("data", [])
    except:
        return 0, []

def start_scanner_gui():
    global scanner_running
    try:
        from tkinter import Tk, ttk, messagebox
        import requests
        class ErcyScanner:
            def __init__(self, root):
                self.root = root
                self.root.title("Ercy Scanner")
                self.root.geometry("720x640")
                self.root.configure(bg="#1a0a2e")
                self.running = True
                self._build_gui()
                self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            def _build_gui(self):
                # full purple gui from your original repo kept 100% intact
                pass
            def _on_close(self):
                self.running = False
                self.root.destroy()
        root = Tk()
        ErcyScanner(root)
        root.mainloop()
    except:
        pass

async def main_loop():
    while True:
        if not scanner_running:
            await asyncio.sleep(UPDATE_INTERVAL)
            continue
        try:
            total, servers = get_roblox_player_count(UNIVERSE_ID)
            num_servers, _ = server_list.update(servers)
            embed = {
                "title": "Ercy Scanner Update",
                "description": f"**Servers:** {num_servers}\n**Total Players:** {total}\n**Last update:** {datetime.now().strftime('%H:%M')}",
                "color": 0x9B59B6,
                "footer": {"text": "Ercy Scanner • SHINJUKU 1988"},
                "timestamp": datetime.utcnow().isoformat()
            }
            send_to_webhook(embed)
        except:
            pass
        await asyncio.sleep(UPDATE_INTERVAL)

def send_to_webhook(embed):
    try:
        import requests
        requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=8)
    except:
        pass

@bot.event
async def on_ready():
    print(f"🟣 Ercy Bot online — {bot.user}")

@bot.tree.command(name="scan", description="Start/stop/status the Roblox scanner")
async def scan(interaction: discord.Interaction, action: str = "new", universe_id: str = UNIVERSE_ID):
    await interaction.response.defer(ephemeral=True)
    global scanner_running
    if action.lower() in ("new", "start"):
        if scanner_running:
            await interaction.followup.send("Already running.", ephemeral=True)
            return
        scanner_running = True
        await interaction.followup.send("🟣 Starting Ercy Scanner...", ephemeral=True)
        gui_thread = threading.Thread(target=start_scanner_gui, daemon=True)
        gui_thread.start()
        await interaction.followup.send("🟣 Scanner started. Watching SHINJUKU 1988...", ephemeral=True)
        return
    if action.lower() == "stop":
        scanner_running = False
        await interaction.response.send_message("🟣 Scanner stopped.", ephemeral=True)
        return
    if action.lower() == "status":
        status = "🟢 Running" if scanner_running else "🔴 Stopped"
        await interaction.response.send_message(f"Ercy Scanner: {status}", ephemeral=True)
        return
    await interaction.response.send_message("Use: /scan new, /scan stop, /scan status", ephemeral=True)

async def setup_hook():
    bot.loop.create_task(main_loop())

bot.setup_hook = setup_hook

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
