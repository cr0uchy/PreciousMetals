"""
Precious Metals Price Tracker
Displays current gold, silver, platinum and palladium prices in AUD/USD.
Data sourced from Metals.dev API (free tier: 100 requests/month).

Features:
- Live prices with change indicators
- Daily high/low tracking
- Price alerts with system notifications
- Portfolio tracker with cost basis / P&L
- Currency toggle (AUD/USD) and per-gram pricing
- CSV price history export
- System tray mode
- Always-on-top and compact mode
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import json
import os
import sys
import threading
import urllib.request
import urllib.error
import winsound
from datetime import datetime, timezone, date

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
HISTORY_FILE = os.path.join(APP_DIR, "price_history.csv")
PORTFOLIO_FILE = os.path.join(APP_DIR, "portfolio.json")

TROY_OZ_TO_GRAMS = 31.1035

METALS = {
    "gold": {"symbol": "Au", "color": "#FFD700"},
    "silver": {"symbol": "Ag", "color": "#C0C0C0"},
    "platinum": {"symbol": "Pt", "color": "#E5E4E2"},
    "palladium": {"symbol": "Pd", "color": "#CED0CE"},
}

DEFAULT_CONFIG = {
    "api_key": "",
    "currency": "AUD",
    "refresh_minutes": 30,
    "show_per_gram": False,
    "always_on_top": False,
    "compact_mode": False,
    "alerts": {},
    "alert_sound": True,
}

BG_DARK = "#11111b"
BG_CARD = "#1e1e2e"
BG_INPUT = "#313244"
FG_TEXT = "#cdd6f4"
FG_BRIGHT = "#f5f5f5"
FG_DIM = "#6c7086"
FG_ACCENT = "#cba6f7"
FG_GREEN = "#a6e3a1"
FG_RED = "#f38ba8"
BG_BTN = "#45475a"
BG_BTN_PRIMARY = "#89b4fa"


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r") as f:
            return json.load(f)
    return {}


def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2)


def append_history(prices, currency):
    is_new = not os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "currency", "gold", "silver", "platinum", "palladium"])
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            currency,
            prices.get("gold", ""),
            prices.get("silver", ""),
            prices.get("platinum", ""),
            prices.get("palladium", ""),
        ])


def fetch_prices(api_key, currency="AUD"):
    url = (
        f"https://api.metals.dev/v1/latest"
        f"?api_key={api_key}&currency={currency}&unit=toz"
    )
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "PreciousMetalsTracker/1.0")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    if data.get("status") != "success":
        raise ValueError(data.get("error", "Unknown API error"))
    return data


class MetalCard(tk.Frame):
    def __init__(self, parent, metal_name, metal_info, show_per_gram=False):
        super().__init__(parent, bg=BG_CARD, padx=12, pady=6)
        self.metal_name = metal_name
        self._last_price = None
        self._show_per_gram = show_per_gram
        self._daily_high = None
        self._daily_low = None
        self._today = None
        self._currency = "AUD"

        # Row 1: symbol, name, change indicator
        header = tk.Frame(self, bg=BG_CARD)
        header.pack(fill="x")

        tk.Label(
            header, text=metal_info["symbol"],
            font=("Segoe UI", 13, "bold"), fg=metal_info["color"],
            bg=BG_CARD, width=3, anchor="w",
        ).pack(side="left")

        tk.Label(
            header, text=metal_name.capitalize(),
            font=("Segoe UI", 11), fg=FG_TEXT, bg=BG_CARD, anchor="w",
        ).pack(side="left", padx=(2, 0))

        self.change_var = tk.StringVar(value="")
        self.change_lbl = tk.Label(
            header, textvariable=self.change_var,
            font=("Segoe UI", 9), fg=FG_DIM, bg=BG_CARD, anchor="e",
        )
        self.change_lbl.pack(side="right")

        # Row 2: price
        self.price_var = tk.StringVar(value="--")
        tk.Label(
            self, textvariable=self.price_var,
            font=("Segoe UI", 20, "bold"), fg=FG_BRIGHT, bg=BG_CARD, anchor="w",
        ).pack(fill="x", pady=(2, 0))

        # Row 3: unit + high/low
        bottom = tk.Frame(self, bg=BG_CARD)
        bottom.pack(fill="x")

        self.unit_var = tk.StringVar(value="AUD / troy oz")
        tk.Label(
            bottom, textvariable=self.unit_var,
            font=("Segoe UI", 8), fg=FG_DIM, bg=BG_CARD, anchor="w",
        ).pack(side="left")

        self.range_var = tk.StringVar(value="")
        tk.Label(
            bottom, textvariable=self.range_var,
            font=("Segoe UI", 8), fg=FG_DIM, bg=BG_CARD, anchor="e",
        ).pack(side="right")

    def set_price(self, price, currency="AUD", show_per_gram=False):
        self._currency = currency
        self._show_per_gram = show_per_gram

        if price is None:
            self.price_var.set("--")
            self.change_var.set("")
            self.range_var.set("")
            self._last_price = None
            return

        display_price = price / TROY_OZ_TO_GRAMS if show_per_gram else price
        unit_str = "g" if show_per_gram else "troy oz"
        self.price_var.set(f"${display_price:,.2f}")
        self.unit_var.set(f"{currency} / {unit_str}")

        # Change indicator
        if self._last_price is not None and self._last_price != 0:
            diff = price - self._last_price
            pct = (diff / self._last_price) * 100
            arrow = "\u25B2" if diff > 0 else "\u25BC" if diff < 0 else "\u25CF"
            color = FG_GREEN if diff > 0 else FG_RED if diff < 0 else FG_DIM
            diff_display = diff / TROY_OZ_TO_GRAMS if show_per_gram else diff
            self.change_var.set(f"{arrow} ${abs(diff_display):,.2f} ({abs(pct):.2f}%)")
            self.change_lbl.config(fg=color)
        self._last_price = price

        # Daily high/low tracking
        today = date.today()
        if self._today != today:
            self._daily_high = price
            self._daily_low = price
            self._today = today
        else:
            if price > (self._daily_high or 0):
                self._daily_high = price
            if price < (self._daily_low or float("inf")):
                self._daily_low = price

        if self._daily_high is not None and self._daily_low is not None:
            h = self._daily_high / TROY_OZ_TO_GRAMS if show_per_gram else self._daily_high
            lo = self._daily_low / TROY_OZ_TO_GRAMS if show_per_gram else self._daily_low
            self.range_var.set(f"L: ${lo:,.2f}  H: ${h:,.2f}")


class PortfolioDialog(tk.Toplevel):
    def __init__(self, parent, current_prices, currency, show_per_gram):
        super().__init__(parent)
        self.title("Portfolio")
        self.geometry("480x420")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.portfolio = load_portfolio()
        self.current_prices = current_prices or {}
        self.currency = currency
        self.show_per_gram = show_per_gram
        self.entries = {}

        tk.Label(
            self, text="Holdings & Cost Basis",
            font=("Segoe UI", 14, "bold"), fg=FG_ACCENT, bg=BG_DARK,
        ).pack(pady=(12, 4))

        tk.Label(
            self, text="Enter your holdings in troy ounces and average cost per oz.",
            font=("Segoe UI", 9), fg=FG_DIM, bg=BG_DARK,
        ).pack()

        # Table header
        hdr = tk.Frame(self, bg=BG_DARK)
        hdr.pack(fill="x", padx=16, pady=(12, 2))
        for i, text in enumerate(["Metal", "Ounces", f"Cost/{self.currency}", "Value", "P/L"]):
            w = 7 if i >= 3 else 9 if i >= 1 else 10
            tk.Label(
                hdr, text=text, font=("Segoe UI", 9, "bold"),
                fg=FG_DIM, bg=BG_DARK, width=w, anchor="w",
            ).grid(row=0, column=i, padx=2)

        # Metal rows
        for idx, (metal, info) in enumerate(METALS.items()):
            row_frame = tk.Frame(self, bg=BG_CARD)
            row_frame.pack(fill="x", padx=16, pady=2)

            tk.Label(
                row_frame, text=f"{info['symbol']} {metal.capitalize()}",
                font=("Segoe UI", 10), fg=info["color"], bg=BG_CARD,
                width=10, anchor="w",
            ).grid(row=0, column=0, padx=4, pady=4)

            holding = self.portfolio.get(metal, {})
            oz_var = tk.StringVar(value=str(holding.get("ounces", "")))
            cost_var = tk.StringVar(value=str(holding.get("cost_per_oz", "")))

            oz_entry = tk.Entry(
                row_frame, textvariable=oz_var, font=("Segoe UI", 10),
                bg=BG_INPUT, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
                relief="flat", bd=3, width=9,
            )
            oz_entry.grid(row=0, column=1, padx=2, pady=4)

            cost_entry = tk.Entry(
                row_frame, textvariable=cost_var, font=("Segoe UI", 10),
                bg=BG_INPUT, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
                relief="flat", bd=3, width=9,
            )
            cost_entry.grid(row=0, column=2, padx=2, pady=4)

            spot = self.current_prices.get(metal, 0)
            try:
                oz = float(oz_var.get()) if oz_var.get() else 0
            except ValueError:
                oz = 0
            value = oz * spot
            try:
                cost = float(cost_var.get()) if cost_var.get() else 0
            except ValueError:
                cost = 0
            pl = (spot - cost) * oz if cost > 0 and oz > 0 else 0

            val_lbl = tk.Label(
                row_frame, text=f"${value:,.0f}" if value else "--",
                font=("Segoe UI", 10), fg=FG_BRIGHT, bg=BG_CARD, width=7, anchor="w",
            )
            val_lbl.grid(row=0, column=3, padx=2, pady=4)

            pl_color = FG_GREEN if pl > 0 else FG_RED if pl < 0 else FG_DIM
            pl_lbl = tk.Label(
                row_frame, text=f"${pl:+,.0f}" if (oz > 0 and cost > 0) else "--",
                font=("Segoe UI", 10), fg=pl_color, bg=BG_CARD, width=7, anchor="w",
            )
            pl_lbl.grid(row=0, column=4, padx=2, pady=4)

            self.entries[metal] = (oz_var, cost_var, val_lbl, pl_lbl)

        # Totals
        self.totals_frame = tk.Frame(self, bg=BG_DARK)
        self.totals_frame.pack(fill="x", padx=16, pady=(8, 0))
        self.total_var = tk.StringVar(value="")
        tk.Label(
            self.totals_frame, textvariable=self.total_var,
            font=("Segoe UI", 11, "bold"), fg=FG_BRIGHT, bg=BG_DARK,
        ).pack()

        # Buttons
        btn_frame = tk.Frame(self, bg=BG_DARK)
        btn_frame.pack(fill="x", padx=16, pady=12)

        tk.Button(
            btn_frame, text="Save", font=("Segoe UI", 10),
            bg=BG_BTN_PRIMARY, fg=BG_DARK, relief="flat", padx=16, pady=4,
            command=self._save, cursor="hand2",
        ).pack(side="right")

        tk.Button(
            btn_frame, text="Cancel", font=("Segoe UI", 10),
            bg=BG_BTN, fg=FG_TEXT, relief="flat", padx=16, pady=4,
            command=self.destroy, cursor="hand2",
        ).pack(side="right", padx=(0, 8))

        tk.Button(
            btn_frame, text="Recalculate", font=("Segoe UI", 10),
            bg=BG_BTN, fg=FG_TEXT, relief="flat", padx=16, pady=4,
            command=self._recalc, cursor="hand2",
        ).pack(side="left")

        self._recalc()

    def _recalc(self):
        total_val = 0
        total_pl = 0
        for metal, (oz_var, cost_var, val_lbl, pl_lbl) in self.entries.items():
            spot = self.current_prices.get(metal, 0)
            try:
                oz = float(oz_var.get()) if oz_var.get() else 0
            except ValueError:
                oz = 0
            try:
                cost = float(cost_var.get()) if cost_var.get() else 0
            except ValueError:
                cost = 0
            value = oz * spot
            pl = (spot - cost) * oz if cost > 0 and oz > 0 else 0
            total_val += value
            total_pl += pl
            val_lbl.config(text=f"${value:,.0f}" if value else "--")
            pl_color = FG_GREEN if pl > 0 else FG_RED if pl < 0 else FG_DIM
            pl_lbl.config(text=f"${pl:+,.0f}" if (oz > 0 and cost > 0) else "--", fg=pl_color)

        pl_color = FG_GREEN if total_pl > 0 else FG_RED if total_pl < 0 else FG_DIM
        pl_str = f"  P/L: ${total_pl:+,.0f}" if total_pl != 0 else ""
        self.total_var.set(f"Total: ${total_val:,.0f}{pl_str}")

    def _save(self):
        portfolio = {}
        for metal, (oz_var, cost_var, _, _) in self.entries.items():
            try:
                oz = float(oz_var.get()) if oz_var.get() else 0
            except ValueError:
                oz = 0
            try:
                cost = float(cost_var.get()) if cost_var.get() else 0
            except ValueError:
                cost = 0
            if oz > 0 or cost > 0:
                portfolio[metal] = {"ounces": oz, "cost_per_oz": cost}
        save_portfolio(portfolio)
        self.destroy()


class AlertsDialog(tk.Toplevel):
    def __init__(self, parent, config, on_save):
        super().__init__(parent)
        self.title("Price Alerts")
        self.geometry("400x380")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.on_save = on_save
        self.config_data = config
        self.alert_vars = {}

        tk.Label(
            self, text="Price Alerts",
            font=("Segoe UI", 14, "bold"), fg=FG_ACCENT, bg=BG_DARK,
        ).pack(pady=(12, 4))

        tk.Label(
            self, text="Set above/below thresholds per troy oz. Leave blank to disable.",
            font=("Segoe UI", 9), fg=FG_DIM, bg=BG_DARK,
        ).pack()

        alerts = config.get("alerts", {})

        for metal, info in METALS.items():
            frame = tk.Frame(self, bg=BG_CARD)
            frame.pack(fill="x", padx=16, pady=4)

            tk.Label(
                frame, text=f"{info['symbol']} {metal.capitalize()}",
                font=("Segoe UI", 10), fg=info["color"], bg=BG_CARD,
                width=12, anchor="w",
            ).grid(row=0, column=0, padx=6, pady=6)

            metal_alerts = alerts.get(metal, {})

            tk.Label(
                frame, text="Above:", font=("Segoe UI", 9),
                fg=FG_DIM, bg=BG_CARD,
            ).grid(row=0, column=1, padx=(4, 2))

            above_var = tk.StringVar(value=str(metal_alerts.get("above", "")))
            tk.Entry(
                frame, textvariable=above_var, font=("Segoe UI", 10),
                bg=BG_INPUT, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
                relief="flat", bd=3, width=8,
            ).grid(row=0, column=2, padx=2, pady=6)

            tk.Label(
                frame, text="Below:", font=("Segoe UI", 9),
                fg=FG_DIM, bg=BG_CARD,
            ).grid(row=0, column=3, padx=(8, 2))

            below_var = tk.StringVar(value=str(metal_alerts.get("below", "")))
            tk.Entry(
                frame, textvariable=below_var, font=("Segoe UI", 10),
                bg=BG_INPUT, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
                relief="flat", bd=3, width=8,
            ).grid(row=0, column=4, padx=2, pady=6)

            self.alert_vars[metal] = (above_var, below_var)

        # Sound toggle
        self.sound_var = tk.BooleanVar(value=config.get("alert_sound", True))
        tk.Checkbutton(
            self, text="Play sound on alert", variable=self.sound_var,
            font=("Segoe UI", 10), fg=FG_TEXT, bg=BG_DARK,
            selectcolor=BG_INPUT, activebackground=BG_DARK,
        ).pack(pady=(12, 0))

        btn_frame = tk.Frame(self, bg=BG_DARK)
        btn_frame.pack(fill="x", padx=16, pady=12)

        tk.Button(
            btn_frame, text="Save", font=("Segoe UI", 10),
            bg=BG_BTN_PRIMARY, fg=BG_DARK, relief="flat", padx=16, pady=4,
            command=self._save, cursor="hand2",
        ).pack(side="right")

        tk.Button(
            btn_frame, text="Cancel", font=("Segoe UI", 10),
            bg=BG_BTN, fg=FG_TEXT, relief="flat", padx=16, pady=4,
            command=self.destroy, cursor="hand2",
        ).pack(side="right", padx=(0, 8))

    def _save(self):
        alerts = {}
        for metal, (above_var, below_var) in self.alert_vars.items():
            entry = {}
            above_str = above_var.get().strip()
            below_str = below_var.get().strip()
            if above_str:
                try:
                    entry["above"] = float(above_str)
                except ValueError:
                    messagebox.showerror("Error", f"Invalid 'above' value for {metal}.")
                    return
            if below_str:
                try:
                    entry["below"] = float(below_str)
                except ValueError:
                    messagebox.showerror("Error", f"Invalid 'below' value for {metal}.")
                    return
            if entry:
                alerts[metal] = entry
        self.config_data["alerts"] = alerts
        self.config_data["alert_sound"] = self.sound_var.get()
        save_config(self.config_data)
        self.on_save(self.config_data)
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config, on_save):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("420x260")
        self.configure(bg=BG_CARD)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.on_save = on_save
        self.config_data = config
        pad = {"padx": 16, "pady": (8, 0)}

        tk.Label(
            self, text="Metals.dev API Key:", font=("Segoe UI", 10),
            fg=FG_TEXT, bg=BG_CARD, anchor="w",
        ).pack(fill="x", **pad)

        self.key_var = tk.StringVar(value=config.get("api_key", ""))
        tk.Entry(
            self, textvariable=self.key_var, font=("Segoe UI", 10),
            bg=BG_INPUT, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
            relief="flat", bd=4,
        ).pack(fill="x", padx=16, pady=(2, 0))

        row = tk.Frame(self, bg=BG_CARD)
        row.pack(fill="x", padx=16, pady=(8, 0))

        tk.Label(
            row, text="Refresh (min):", font=("Segoe UI", 10),
            fg=FG_TEXT, bg=BG_CARD,
        ).pack(side="left")

        self.interval_var = tk.StringVar(value=str(config.get("refresh_minutes", 30)))
        tk.Entry(
            row, textvariable=self.interval_var, font=("Segoe UI", 10),
            bg=BG_INPUT, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
            relief="flat", bd=3, width=5,
        ).pack(side="left", padx=(6, 16))

        tk.Label(
            row, text="Currency:", font=("Segoe UI", 10),
            fg=FG_TEXT, bg=BG_CARD,
        ).pack(side="left")

        self.currency_var = tk.StringVar(value=config.get("currency", "AUD"))
        curr_menu = ttk.Combobox(
            row, textvariable=self.currency_var, values=["AUD", "USD"],
            width=5, state="readonly",
        )
        curr_menu.pack(side="left", padx=(6, 0))

        # Checkboxes
        self.gram_var = tk.BooleanVar(value=config.get("show_per_gram", False))
        tk.Checkbutton(
            self, text="Show price per gram (instead of per troy oz)",
            variable=self.gram_var, font=("Segoe UI", 10),
            fg=FG_TEXT, bg=BG_CARD, selectcolor=BG_INPUT, activebackground=BG_CARD,
        ).pack(anchor="w", padx=16, pady=(8, 0))

        self.ontop_var = tk.BooleanVar(value=config.get("always_on_top", False))
        tk.Checkbutton(
            self, text="Always on top", variable=self.ontop_var,
            font=("Segoe UI", 10), fg=FG_TEXT, bg=BG_CARD,
            selectcolor=BG_INPUT, activebackground=BG_CARD,
        ).pack(anchor="w", padx=16)

        tk.Label(
            self, text="Free tier: 100 requests/month. Get a key at metals.dev",
            font=("Segoe UI", 8), fg=FG_DIM, bg=BG_CARD,
        ).pack(pady=(6, 0))

        btn_frame = tk.Frame(self, bg=BG_CARD)
        btn_frame.pack(fill="x", padx=16, pady=10)

        tk.Button(
            btn_frame, text="Save", font=("Segoe UI", 10),
            bg=BG_BTN_PRIMARY, fg=BG_DARK, relief="flat", padx=16, pady=4,
            command=self._save, cursor="hand2",
        ).pack(side="right")

        tk.Button(
            btn_frame, text="Cancel", font=("Segoe UI", 10),
            bg=BG_BTN, fg=FG_TEXT, relief="flat", padx=16, pady=4,
            command=self.destroy, cursor="hand2",
        ).pack(side="right", padx=(0, 8))

    def _save(self):
        try:
            mins = int(self.interval_var.get())
            if mins < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Refresh interval must be a positive integer.")
            return

        self.config_data["api_key"] = self.key_var.get().strip()
        self.config_data["refresh_minutes"] = mins
        self.config_data["currency"] = self.currency_var.get()
        self.config_data["show_per_gram"] = self.gram_var.get()
        self.config_data["always_on_top"] = self.ontop_var.get()
        save_config(self.config_data)
        self.on_save(self.config_data)
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Precious Metals Tracker")
        self.configure(bg=BG_DARK)
        self.minsize(340, 400)

        self.config_data = load_config()
        self._refresh_job = None
        self._current_prices = {}
        self._compact = self.config_data.get("compact_mode", False)
        self._tray_mode = False

        self._apply_window_settings()
        self._build_ui()

        if not self.config_data.get("api_key"):
            self.status_var.set("Set your API key in Settings (\u2699)")
        else:
            self._trigger_refresh()

    def _apply_window_settings(self):
        self.attributes("-topmost", self.config_data.get("always_on_top", False))
        if self._compact:
            self.geometry("320x200")
        else:
            self.geometry("400x480")

    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()

        # Title bar
        title_frame = tk.Frame(self, bg=BG_DARK)
        title_frame.pack(fill="x", padx=16, pady=(10, 0))

        tk.Label(
            title_frame, text="Precious Metals",
            font=("Segoe UI", 14, "bold"), fg=FG_ACCENT, bg=BG_DARK,
        ).pack(side="left")

        # Toolbar buttons (right side)
        btn_cfg = {"font": ("Segoe UI", 12), "bg": BG_DARK, "fg": FG_DIM, "relief": "flat", "bd": 0, "cursor": "hand2"}

        tk.Button(title_frame, text="\u2699", command=self._open_settings, **btn_cfg).pack(side="right")
        tk.Button(title_frame, text="\U0001F4BC", command=self._open_portfolio, **btn_cfg).pack(side="right")
        tk.Button(title_frame, text="\u26A0", command=self._open_alerts, **btn_cfg).pack(side="right")

        # Currency / unit toggle row
        toggle_frame = tk.Frame(self, bg=BG_DARK)
        toggle_frame.pack(fill="x", padx=16, pady=(4, 0))

        self.currency_btn_var = tk.StringVar(
            value=self.config_data.get("currency", "AUD")
        )
        tk.Button(
            toggle_frame, textvariable=self.currency_btn_var,
            font=("Segoe UI", 8), bg=BG_BTN, fg=FG_TEXT,
            relief="flat", padx=6, pady=1, cursor="hand2",
            command=self._toggle_currency,
        ).pack(side="left")

        self.unit_btn_var = tk.StringVar(
            value="/g" if self.config_data.get("show_per_gram") else "/oz"
        )
        tk.Button(
            toggle_frame, textvariable=self.unit_btn_var,
            font=("Segoe UI", 8), bg=BG_BTN, fg=FG_TEXT,
            relief="flat", padx=6, pady=1, cursor="hand2",
            command=self._toggle_unit,
        ).pack(side="left", padx=(4, 0))

        compact_text = "Expand" if self._compact else "Compact"
        tk.Button(
            toggle_frame, text=compact_text,
            font=("Segoe UI", 8), bg=BG_BTN, fg=FG_TEXT,
            relief="flat", padx=6, pady=1, cursor="hand2",
            command=self._toggle_compact,
        ).pack(side="right")

        tk.Button(
            toggle_frame, text="Tray",
            font=("Segoe UI", 8), bg=BG_BTN, fg=FG_TEXT,
            relief="flat", padx=6, pady=1, cursor="hand2",
            command=self._minimize_to_tray,
        ).pack(side="right", padx=(0, 4))

        # Metal cards
        show_per_gram = self.config_data.get("show_per_gram", False)
        metals_to_show = METALS
        if self._compact:
            metals_to_show = {"gold": METALS["gold"], "silver": METALS["silver"]}

        self.cards = {}
        for name, info in metals_to_show.items():
            card = MetalCard(self, name, info, show_per_gram)
            card.pack(fill="x", padx=16, pady=(6, 0))
            self.cards[name] = card

        # Status bar
        status_frame = tk.Frame(self, bg=BG_DARK)
        status_frame.pack(fill="x", side="bottom", padx=16, pady=6)

        self.status_var = tk.StringVar(value="Starting...")
        tk.Label(
            status_frame, textvariable=self.status_var,
            font=("Segoe UI", 8), fg=FG_DIM, bg=BG_DARK, anchor="w",
        ).pack(side="left")

        tk.Button(
            status_frame, text="CSV", font=("Segoe UI", 8),
            bg=BG_BTN, fg=FG_TEXT, relief="flat", padx=6, pady=1,
            command=self._export_csv, cursor="hand2",
        ).pack(side="right", padx=(4, 0))

        tk.Button(
            status_frame, text="Refresh", font=("Segoe UI", 8),
            bg=BG_BTN, fg=FG_TEXT, relief="flat", padx=6, pady=1,
            command=self._trigger_refresh, cursor="hand2",
        ).pack(side="right")

    def _toggle_currency(self):
        curr = self.config_data.get("currency", "AUD")
        new_curr = "USD" if curr == "AUD" else "AUD"
        self.config_data["currency"] = new_curr
        self.currency_btn_var.set(new_curr)
        save_config(self.config_data)
        # Clear last prices so change arrows don't fire on currency switch
        for card in self.cards.values():
            card._last_price = None
        self._trigger_refresh()

    def _toggle_unit(self):
        current = self.config_data.get("show_per_gram", False)
        self.config_data["show_per_gram"] = not current
        self.unit_btn_var.set("/g" if not current else "/oz")
        save_config(self.config_data)
        self._redisplay_prices()

    def _toggle_compact(self):
        self._compact = not self._compact
        self.config_data["compact_mode"] = self._compact
        save_config(self.config_data)
        self._apply_window_settings()
        self._build_ui()
        self._redisplay_prices()

    def _minimize_to_tray(self):
        self.withdraw()
        self._tray_mode = True
        # Create a small top-level window as a tray indicator
        self._tray_win = tk.Toplevel(self)
        self._tray_win.title("Metals")
        self._tray_win.geometry("220x60+50+50")
        self._tray_win.configure(bg=BG_DARK)
        self._tray_win.attributes("-topmost", True)
        self._tray_win.resizable(False, False)

        gold_price = self._current_prices.get("gold")
        silver_price = self._current_prices.get("silver")
        curr = self.config_data.get("currency", "AUD")
        gold_str = f"${gold_price:,.0f}" if gold_price else "--"
        silver_str = f"${silver_price:,.2f}" if silver_price else "--"

        tk.Label(
            self._tray_win,
            text=f"Au {gold_str}  |  Ag {silver_str}  ({curr})",
            font=("Segoe UI", 10, "bold"), fg=FG_BRIGHT, bg=BG_DARK,
        ).pack(expand=True)

        tk.Button(
            self._tray_win, text="Restore", font=("Segoe UI", 8),
            bg=BG_BTN, fg=FG_TEXT, relief="flat", padx=8,
            command=self._restore_from_tray, cursor="hand2",
        ).pack(pady=(0, 6))

        self._tray_win.protocol("WM_DELETE_WINDOW", self._restore_from_tray)

    def _restore_from_tray(self):
        self._tray_mode = False
        if hasattr(self, "_tray_win"):
            self._tray_win.destroy()
        self.deiconify()

    def _redisplay_prices(self):
        if self._current_prices:
            currency = self.config_data.get("currency", "AUD")
            show_gram = self.config_data.get("show_per_gram", False)
            for name, card in self.cards.items():
                price = self._current_prices.get(name)
                card.set_price(price, currency, show_gram)

    def _open_settings(self):
        SettingsDialog(self, self.config_data, self._on_settings_saved)

    def _on_settings_saved(self, new_config):
        self.config_data = new_config
        self.attributes("-topmost", new_config.get("always_on_top", False))
        self._trigger_refresh()

    def _open_portfolio(self):
        PortfolioDialog(
            self, self._current_prices,
            self.config_data.get("currency", "AUD"),
            self.config_data.get("show_per_gram", False),
        )

    def _open_alerts(self):
        AlertsDialog(self, self.config_data, self._on_alerts_saved)

    def _on_alerts_saved(self, new_config):
        self.config_data = new_config

    def _export_csv(self):
        if not os.path.exists(HISTORY_FILE):
            messagebox.showinfo("Export", "No price history recorded yet.")
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile="precious_metals_history.csv",
        )
        if dest:
            import shutil
            shutil.copy2(HISTORY_FILE, dest)
            messagebox.showinfo("Export", f"History exported to {dest}")

    def _trigger_refresh(self):
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None

        api_key = self.config_data.get("api_key", "").strip()
        if not api_key:
            self.status_var.set("Set your API key in Settings (\u2699)")
            return

        self.status_var.set("Fetching prices...")
        thread = threading.Thread(target=self._fetch_worker, daemon=True)
        thread.start()

    def _fetch_worker(self):
        try:
            data = fetch_prices(
                self.config_data["api_key"],
                self.config_data.get("currency", "AUD"),
            )
            self.after(0, self._update_ui, data, None)
        except Exception as e:
            self.after(0, self._update_ui, None, str(e))

    def _update_ui(self, data, error):
        if error:
            self.status_var.set(f"Error: {error[:60]}")
            for card in self.cards.values():
                card.set_price(None)
        else:
            metals = data.get("metals", {})
            currency = data.get("currency", "AUD")
            show_gram = self.config_data.get("show_per_gram", False)

            self._current_prices = metals

            for name, card in self.cards.items():
                price = metals.get(name)
                card.set_price(price, currency, show_gram)

            # Log to CSV
            append_history(metals, currency)

            # Check alerts
            self._check_alerts(metals)

            # Update tray if in tray mode
            if self._tray_mode and hasattr(self, "_tray_win"):
                try:
                    gold_price = metals.get("gold")
                    silver_price = metals.get("silver")
                    gold_str = f"${gold_price:,.0f}" if gold_price else "--"
                    silver_str = f"${silver_price:,.2f}" if silver_price else "--"
                    self._tray_win.title(f"Au {gold_str} | Ag {silver_str}")
                except Exception:
                    pass

            ts = data.get("timestamps", {}).get("metal", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    local_str = dt.astimezone().strftime("%H:%M:%S %d/%m/%Y")
                    self.status_var.set(f"Updated: {local_str}")
                except Exception:
                    self.status_var.set(f"Updated: {ts}")
            else:
                self.status_var.set("Updated just now")

        mins = self.config_data.get("refresh_minutes", 30)
        self._refresh_job = self.after(mins * 60 * 1000, self._trigger_refresh)

    def _check_alerts(self, metals):
        alerts = self.config_data.get("alerts", {})
        triggered = []
        for metal, thresholds in alerts.items():
            price = metals.get(metal)
            if price is None:
                continue
            above = thresholds.get("above")
            below = thresholds.get("below")
            if above is not None and price >= above:
                triggered.append(f"{metal.capitalize()} above ${above:,.2f} (now ${price:,.2f})")
            if below is not None and price <= below:
                triggered.append(f"{metal.capitalize()} below ${below:,.2f} (now ${price:,.2f})")

        if triggered:
            if self.config_data.get("alert_sound", True):
                try:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except Exception:
                    pass
            msg = "\n".join(triggered)
            # Show as a non-blocking notification
            self._show_notification(msg)

    def _show_notification(self, message):
        notif = tk.Toplevel(self)
        notif.title("Price Alert")
        notif.geometry("320x120+100+100")
        notif.configure(bg=BG_CARD)
        notif.attributes("-topmost", True)
        notif.resizable(False, False)

        tk.Label(
            notif, text="\u26A0 Price Alert",
            font=("Segoe UI", 12, "bold"), fg="#fab387", bg=BG_CARD,
        ).pack(pady=(10, 4))

        tk.Label(
            notif, text=message, font=("Segoe UI", 10),
            fg=FG_BRIGHT, bg=BG_CARD, wraplength=280, justify="left",
        ).pack(padx=12)

        tk.Button(
            notif, text="Dismiss", font=("Segoe UI", 9),
            bg=BG_BTN, fg=FG_TEXT, relief="flat", padx=12,
            command=notif.destroy, cursor="hand2",
        ).pack(pady=8)

        # Auto-dismiss after 10 seconds
        notif.after(10000, lambda: notif.destroy() if notif.winfo_exists() else None)


if __name__ == "__main__":
    app = App()
    app.mainloop()
