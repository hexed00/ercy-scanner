"""
Ercy Scanner — Live Roblox player + server list to Discord webhook
Purple Tkinter GUI. Webhook first. Auto-installs deps. Windows + Linux/Mac.
"""

# ============== AUTO INSTALL DEPS ==============
import sys
import subprocess

def _ensure_packages():
    needed = []
    try:
        import requests  # noqa: F401
    except ImportError:
        needed.append("requests")
    if needed:
        print("[Ercy] Installing:", ", ".join(needed))
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", *needed],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        print("[Ercy] Done.")

_ensure_packages()
# ===============================================

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import threading
import time
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

# ============== DEFAULTS ==============
DEFAULT_UNIVERSE_ID = "5946282691"
DEFAULT_PLACE_ID = ""
UPDATE_INTERVAL = 15
# ======================================

PURPLE_BG = "#1a0a2e"
PURPLE_PANEL = "#2d1b4e"
PURPLE_ACCENT = "#9b59b6"
PURPLE_LIGHT = "#c39bd3"
PURPLE_TEXT = "#e8daef"
PURPLE_ENTRY = "#3d2a5c"
PURPLE_BTN = "#8e44ad"
PURPLE_BTN_HOVER = "#a569bd"
PURPLE_SUCCESS = "#2ecc71"
PURPLE_ERROR = "#e74c3c"


class ErcyScanner:
    def __init__(self, root):
        self.root = root
        self.root.title("Ercy Scanner")
        self.root.geometry("720x640")
        self.root.minsize(640, 560)
        self.root.configure(bg=PURPLE_BG)
        self.root.resizable(True, True)

        # Windows: stop taskbar flicker / set icon-friendly
        try:
            if sys.platform == "win32":
                self.root.attributes("-alpha", 0.99)
                self.root.after(50, lambda: self.root.attributes("-alpha", 1.0))
        except Exception:
            pass

        self.webhook_url = ""
        self.universe_id = DEFAULT_UNIVERSE_ID
        self.place_id = DEFAULT_PLACE_ID
        self.running = False
        self.scanner_thread = None
        self.last_playing = None
        self.last_message_id = None
        self.last_servers_hash = None

        self._build_gui()
        self._center_window()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

    def _on_close(self):
        self.running = False
        self.root.destroy()

    def _build_gui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=PURPLE_BG)
        style.configure("TLabel", background=PURPLE_BG, foreground=PURPLE_TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=PURPLE_BG, foreground=PURPLE_LIGHT, font=("Segoe UI", 18, "bold"))
        style.configure("Header.TLabel", background=PURPLE_PANEL, foreground=PURPLE_LIGHT, font=("Segoe UI", 11, "bold"))

        # Title
        title = ttk.Label(self.root, text="◆ ERCY SCANNER ◆", style="Title.TLabel")
        title.pack(pady=(18, 4))
        sub = ttk.Label(
            self.root,
            text="Live Roblox players & server list → Discord webhook",
            font=("Segoe UI", 9),
        )
        sub.pack(pady=(0, 12))

        # === CONFIG PANEL ===
        cfg = tk.Frame(self.root, bg=PURPLE_PANEL, padx=14, pady=12)
        cfg.pack(fill="x", padx=16, pady=6)

        ttk.Label(cfg, text="Discord Webhook URL *", style="Header.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 2)
        )
        self.webhook_var = tk.StringVar()
        self.webhook_entry = tk.Entry(
            cfg,
            textvariable=self.webhook_var,
            bg=PURPLE_ENTRY,
            fg=PURPLE_TEXT,
            insertbackground=PURPLE_LIGHT,
            relief="flat",
            font=("Consolas", 10),
            width=70,
        )
        self.webhook_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10), ipady=6)
        self.webhook_entry.insert(0, "https://discord.com/api/webhooks/...")
        self.webhook_entry.bind("<FocusIn>", self._clear_placeholder)

        ttk.Label(cfg, text="Universe ID", style="Header.TLabel").grid(
            row=2, column=0, sticky="w", pady=(0, 2)
        )
        self.universe_var = tk.StringVar(value=DEFAULT_UNIVERSE_ID)
        tk.Entry(
            cfg,
            textvariable=self.universe_var,
            bg=PURPLE_ENTRY,
            fg=PURPLE_TEXT,
            insertbackground=PURPLE_LIGHT,
            relief="flat",
            font=("Consolas", 10),
            width=30,
        ).grid(row=3, column=0, sticky="w", pady=(0, 10), ipady=4)

        ttk.Label(
            cfg, text="Place ID (optional — auto from universe)", style="Header.TLabel"
        ).grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(0, 2))
        self.place_var = tk.StringVar(value=DEFAULT_PLACE_ID)
        tk.Entry(
            cfg,
            textvariable=self.place_var,
            bg=PURPLE_ENTRY,
            fg=PURPLE_TEXT,
            insertbackground=PURPLE_LIGHT,
            relief="flat",
            font=("Consolas", 10),
            width=28,
        ).grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(0, 10), ipady=4)

        ttk.Label(cfg, text="Update interval (seconds)", style="Header.TLabel").grid(
            row=4, column=0, sticky="w", pady=(0, 2)
        )
        self.interval_var = tk.StringVar(value=str(UPDATE_INTERVAL))
        tk.Entry(
            cfg,
            textvariable=self.interval_var,
            bg=PURPLE_ENTRY,
            fg=PURPLE_TEXT,
            insertbackground=PURPLE_LIGHT,
            relief="flat",
            font=("Consolas", 10),
            width=10,
        ).grid(row=5, column=0, sticky="w", pady=(0, 4), ipady=4)

        cfg.columnconfigure(0, weight=1)
        cfg.columnconfigure(1, weight=1)

        # === CONTROLS ===
        btn_frame = tk.Frame(self.root, bg=PURPLE_BG)
        btn_frame.pack(fill="x", padx=16, pady=10)

        self.start_btn = tk.Button(
            btn_frame,
            text="▶  START SCANNER",
            command=self.start_scanner,
            bg=PURPLE_BTN,
            fg="white",
            activebackground=PURPLE_BTN_HOVER,
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 11, "bold"),
            padx=16,
            pady=8,
            cursor="hand2",
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = tk.Button(
            btn_frame,
            text="■  STOP",
            command=self.stop_scanner,
            bg="#5c2d6e",
            fg="white",
            activebackground="#7d3c98",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 11, "bold"),
            padx=16,
            pady=8,
            cursor="hand2",
            state="disabled",
        )
        self.stop_btn.pack(side="left", padx=(0, 8))

        self.test_btn = tk.Button(
            btn_frame,
            text="TEST WEBHOOK",
            command=self.test_webhook,
            bg="#4a235a",
            fg=PURPLE_LIGHT,
            activebackground="#6c3483",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 10),
            padx=12,
            pady=8,
            cursor="hand2",
        )
        self.test_btn.pack(side="left")

        # Status
        self.status_var = tk.StringVar(value="Waiting for webhook…")
        self.status_label = tk.Label(
            self.root,
            textvariable=self.status_var,
            bg=PURPLE_BG,
            fg=PURPLE_ACCENT,
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.status_label.pack(fill="x", padx=18, pady=(0, 4))

        # Live stats
        stats = tk.Frame(self.root, bg=PURPLE_PANEL, padx=12, pady=10)
        stats.pack(fill="x", padx=16, pady=4)

        self.players_var = tk.StringVar(value="Players: —")
        self.servers_var = tk.StringVar(value="Servers: —")
        self.last_update_var = tk.StringVar(value="Last update: —")

        tk.Label(
            stats,
            textvariable=self.players_var,
            bg=PURPLE_PANEL,
            fg=PURPLE_SUCCESS,
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=(0, 24))
        tk.Label(
            stats,
            textvariable=self.servers_var,
            bg=PURPLE_PANEL,
            fg=PURPLE_LIGHT,
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=(0, 24))
        tk.Label(
            stats,
            textvariable=self.last_update_var,
            bg=PURPLE_PANEL,
            fg=PURPLE_TEXT,
            font=("Segoe UI", 10),
        ).pack(side="left")

        # Log
        log_frame = tk.Frame(self.root, bg=PURPLE_BG)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(6, 14))

        tk.Label(
            log_frame,
            text="Activity Log",
            bg=PURPLE_BG,
            fg=PURPLE_LIGHT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        self.log = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            bg="#12081f",
            fg=PURPLE_TEXT,
            insertbackground=PURPLE_LIGHT,
            relief="flat",
            font=("Consolas", 9),
            state="disabled",
            wrap="word",
        )
        self.log.pack(fill="both", expand=True, pady=(4, 0))

    def _clear_placeholder(self, event=None):
        if self.webhook_var.get().startswith("https://discord.com/api/webhooks/..."):
            self.webhook_var.set("")

    def log_msg(self, msg, level="info"):
        def _do():
            self.log.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            prefix = {"info": "•", "ok": "✓", "err": "✗", "warn": "!"}.get(level, "•")
            self.log.insert("end", f"[{ts}] {prefix} {msg}\n")
            self.log.see("end")
            self.log.configure(state="disabled")

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    def set_status(self, text, color=None):
        def _do():
            self.status_var.set(text)
            if color:
                self.status_label.configure(fg=color)

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.root.after(0, _do)

    def validate_webhook(self, url):
        url = (url or "").strip()
        if not url:
            return False
        low = url.lower()
        if "discord.com/api/webhooks/" not in low and "discordapp.com/api/webhooks/" not in low:
            return False
        try:
            path = urlparse(url).path
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 3 and parts[-3].lower() == "webhooks":
                return True
        except Exception:
            pass
        return False

    def test_webhook(self):
        url = self.webhook_var.get().strip()
        if not self.validate_webhook(url):
            messagebox.showerror("Ercy Scanner", "Enter a valid Discord webhook URL first.")
            return
        try:
            r = requests.post(
                f"{url}?wait=true",
                json={
                    "embeds": [
                        {
                            "title": "Ercy Scanner — Test",
                            "description": "Webhook connected. Scanner is ready.",
                            "color": 0x9B59B6,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "footer": {"text": "Ercy Scanner"},
                        }
                    ]
                },
                timeout=12,
            )
            if r.status_code in (200, 204):
                self.log_msg("Webhook test OK", "ok")
                self.set_status("Webhook OK — ready to scan", PURPLE_SUCCESS)
                messagebox.showinfo("Ercy Scanner", "Webhook test successful.")
            else:
                self.log_msg(f"Webhook test failed: {r.status_code}", "err")
                messagebox.showerror("Ercy Scanner", f"Webhook returned {r.status_code}\n{r.text[:200]}")
        except Exception as e:
            self.log_msg(f"Webhook error: {e}", "err")
            messagebox.showerror("Ercy Scanner", str(e))

    def start_scanner(self):
        url = self.webhook_var.get().strip()
        if not self.validate_webhook(url):
            messagebox.showerror("Ercy Scanner", "Enter a valid Discord webhook URL first.")
            self.webhook_entry.focus_set()
            return

        try:
            interval = max(5, int(self.interval_var.get().strip() or UPDATE_INTERVAL))
        except ValueError:
            interval = UPDATE_INTERVAL

        self.webhook_url = url
        self.universe_id = self.universe_var.get().strip() or DEFAULT_UNIVERSE_ID
        self.place_id = self.place_var.get().strip()
        self.running = True
        self.last_playing = None
        self.last_message_id = None
        self.last_servers_hash = None

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.webhook_entry.configure(state="disabled")
        self.set_status("Scanner running…", PURPLE_SUCCESS)
        self.log_msg(f"Started — universe {self.universe_id}, interval {interval}s", "ok")

        self.scanner_thread = threading.Thread(
            target=self._scan_loop, args=(interval,), daemon=True
        )
        self.scanner_thread.start()

    def stop_scanner(self):
        self.running = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.webhook_entry.configure(state="normal")
        self.set_status("Stopped", PURPLE_ACCENT)
        self.log_msg("Scanner stopped", "warn")

    # ---------- Roblox API ----------
    def get_game_data(self):
        try:
            r = requests.get(
                f"https://games.roblox.com/v1/games?universeIds={self.universe_id}",
                timeout=12,
            )
            data = r.json()
            if data.get("data"):
                g = data["data"][0]
                playing = g.get("playing", 0) or 0
                root_place = g.get("rootPlaceId")
                if root_place and not self.place_id:
                    self.place_id = str(root_place)
                return playing, g
        except Exception as e:
            self.log_msg(f"Game data error: {e}", "err")
        return None, None

    def get_game_icon(self):
        try:
            r = requests.get(
                f"https://thumbnails.roblox.com/v1/games/icons?universeIds={self.universe_id}&size=512x512&format=Png",
                timeout=10,
            )
            data = r.json()
            if data.get("data"):
                return data["data"][0].get("imageUrl")
        except Exception:
            pass
        return None

    def get_server_list(self, place_id, limit=50):
        if not place_id:
            return []
        servers = []
        cursor = None
        try:
            for _ in range(3):
                url = (
                    f"https://games.roblox.com/v1/games/{place_id}/servers/Public"
                    f"?sortOrder=Desc&excludeFullGames=false&limit={min(100, limit)}"
                )
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
            self.log_msg(f"Server list error: {e}", "err")
        return servers[:limit]

    def delete_old_message(self):
        if not self.last_message_id or not self.webhook_url:
            return
        try:
            requests.delete(
                f"{self.webhook_url}/messages/{self.last_message_id}", timeout=10
            )
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
            r = requests.post(
                f"{self.webhook_url}?wait=true", json=payload, timeout=14
            )
            if r.status_code == 200:
                self.last_message_id = r.json().get("id")
                return True
            else:
                self.log_msg(f"Webhook post {r.status_code}: {r.text[:120]}", "err")
        except Exception as e:
            self.log_msg(f"Webhook send failed: {e}", "err")
        return False

    def _scan_loop(self, interval):
        while self.running:
            try:
                playing, game = self.get_game_data()
                icon = self.get_game_icon()

                if playing is None:
                    self.set_status("API error — retrying…", PURPLE_ERROR)
                    time.sleep(interval)
                    continue

                place = self.place_id or (
                    str(game.get("rootPlaceId")) if game else None
                )
                servers = self.get_server_list(place) if place else []
                server_count = (
                    len(servers)
                    if servers
                    else (max(1, round(playing / 50)) if playing > 0 else 0)
                )

                servers_hash = (
                    playing,
                    tuple(
                        sorted(
                            (s.get("id"), s.get("playing")) for s in servers[:30]
                        )
                    ),
                )

                def update_ui():
                    self.players_var.set(f"Players: {playing}")
                    self.servers_var.set(f"Servers: {server_count}")
                    self.last_update_var.set(
                        f"Last update: {datetime.now().strftime('%H:%M:%S')}"
                    )
                    self.set_status(
                        f"Live — {playing} players / {server_count} servers",
                        PURPLE_SUCCESS,
                    )

                self.root.after(0, update_ui)

                if servers_hash != self.last_servers_hash:
                    ok = self.send_webhook(playing, server_count, servers, icon)
                    self.last_servers_hash = servers_hash
                    self.last_playing = playing
                    msg = f"Updated embed: {playing} players, {server_count} servers"
                    self.log_msg(msg, "ok" if ok else "err")
                else:
                    self.log_msg(f"No change ({playing} players)", "info")

            except Exception as e:
                self.log_msg(f"Loop error: {e}", "err")

            for _ in range(interval * 2):
                if not self.running:
                    break
                time.sleep(0.5)


def main():
    # Windows high-DPI awareness (optional, prevents blurry UI)
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                from ctypes import windll
                windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    root = tk.Tk()
    app = ErcyScanner(root)
    root.mainloop()


if __name__ == "__main__":
    main()