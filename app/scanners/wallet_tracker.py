"""Polymarket whale wallet tracker.

Polls Polymarket public activity for configured wallets and posts read-only
copy-trade alerts to dedicated copy tracker channels. No trading side effects.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

import aiohttp
import discord

from app.core.server_manager import server_manager

logger = logging.getLogger("WalletTracker")

DATA_API = "https://data-api.polymarket.com"


class WalletTracker:
    """Track target Polymarket wallets and alert when they trade."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled = os.getenv("WALLET_TRACKER_ENABLED", "true").lower() not in {"0", "false", "no"}
        self.interval_seconds = int(os.getenv("WALLET_TRACKER_INTERVAL_SECONDS", "45"))
        self.activity_limit = int(os.getenv("WALLET_TRACKER_ACTIVITY_LIMIT", "25"))
        self.wallets = self._configured_wallets()
        self.seen_activity: Set[str] = set()
        self.scan_count = 0
        self.last_scan_summary: Dict[str, Any] = {}

    def _configured_wallets(self) -> Dict[str, str]:
        """Return {wallet_address: label} from WALLET_TRACKER_WALLETS.

        Format: `0xabc=Whale One,0xdef=Fund Wallet` or just `0xabc,0xdef`.
        """
        configured = os.getenv("WALLET_TRACKER_WALLETS", "")
        wallets: Dict[str, str] = {}
        for idx, item in enumerate([x.strip() for x in configured.split(",") if x.strip()], start=1):
            if "=" in item:
                address, label = item.split("=", 1)
                wallets[address.strip().lower()] = label.strip() or f"Wallet {idx}"
            else:
                wallets[item.lower()] = f"Wallet {idx}"
        return wallets

    async def start(self):
        if not self.enabled:
            logger.info("Wallet tracker disabled by WALLET_TRACKER_ENABLED=false")
            return
        if not self.wallets:
            logger.warning("Wallet tracker enabled but WALLET_TRACKER_WALLETS is empty; scanner idle")
            return

        logger.info("Wallet tracker online for %s wallet(s)", len(self.wallets))
        while True:
            try:
                await self.scan()
            except Exception as exc:
                logger.error("Wallet tracker scan failed: %s", exc, exc_info=True)
            await asyncio.sleep(self.interval_seconds)

    async def scan(self) -> Dict[str, Any]:
        self.scan_count += 1
        summary = {"scan_id": self.scan_count, "wallets_checked": 0, "activities_seen": 0, "alerts_sent": 0}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            for wallet, label in self.wallets.items():
                summary["wallets_checked"] += 1
                activities = await self._fetch_wallet_activity(session, wallet)
                summary["activities_seen"] += len(activities)
                for activity in reversed(activities):
                    key = self._activity_key(wallet, activity)
                    if key in self.seen_activity:
                        continue
                    self.seen_activity.add(key)
                    # First scan seeds state without spamming historical fills.
                    if self.scan_count == 1:
                        continue
                    if await self._send_alert(wallet, label, activity):
                        summary["alerts_sent"] += 1
        self.last_scan_summary = summary
        logger.info(
            "WalletTracker scan #%s | wallets=%s activities=%s alerts=%s",
            summary["scan_id"], summary["wallets_checked"], summary["activities_seen"], summary["alerts_sent"],
        )
        return summary

    async def _fetch_wallet_activity(self, session: aiohttp.ClientSession, wallet: str) -> List[Dict[str, Any]]:
        # `user` is the public data-api filter for a profile/proxy wallet.
        params = {"user": wallet, "limit": self.activity_limit}
        async with session.get(f"{DATA_API}/activity", params=params) as resp:
            if resp.status != 200:
                logger.warning("Wallet activity fetch failed for %s: %s", wallet, resp.status)
                return []
            payload = await resp.json()
        return payload if isinstance(payload, list) else []

    def _activity_key(self, wallet: str, activity: Dict[str, Any]) -> str:
        for field in ("transactionHash", "transaction_hash", "hash", "id"):
            if activity.get(field):
                return f"{wallet}:{activity[field]}"
        return ":".join(
            str(activity.get(field, ""))
            for field in ("proxyWallet", "timestamp", "conditionId", "asset", "side", "size", "price")
        )

    async def _send_alert(self, wallet: str, label: str, activity: Dict[str, Any]) -> bool:
        channels = await server_manager.get_all_copy_tracker_channels()
        if not channels:
            logger.warning("No dedicated copy_tracker_channel_id configured; skipping wallet alert without fallback")
            return False

        embed = self._build_embed(wallet, label, activity)
        sent = 0
        for guild_id, channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning("Copy tracker channel %s not found for guild %s", channel_id, guild_id)
                continue
            try:
                await channel.send(embed=embed)
                sent += 1
            except Exception as exc:
                logger.error("Failed to send wallet tracker alert to guild %s: %s", guild_id, exc)
        return sent > 0

    def _build_embed(self, wallet: str, label: str, activity: Dict[str, Any]) -> discord.Embed:
        side = str(activity.get("side") or activity.get("type") or "TRADE").upper()
        title = activity.get("title") or activity.get("market") or activity.get("question") or activity.get("slug") or "Polymarket activity"
        price = self._fmt_number(activity.get("price"))
        size = self._fmt_number(activity.get("size") or activity.get("amount"))
        outcome = activity.get("outcome") or activity.get("asset") or "unknown"
        tx_hash = activity.get("transactionHash") or activity.get("transaction_hash") or activity.get("hash")

        embed = discord.Embed(title="🐋 POLY WALLET TRACKER", color=0x8b5cf6)
        embed.add_field(name="Wallet", value=f"{label}\n`{wallet}`", inline=False)
        embed.add_field(name="Action", value=side, inline=True)
        embed.add_field(name="Outcome/Asset", value=str(outcome)[:1000], inline=True)
        embed.add_field(name="Market", value=str(title)[:1000], inline=False)
        if price != "unknown":
            embed.add_field(name="Price", value=price, inline=True)
        if size != "unknown":
            embed.add_field(name="Size", value=size, inline=True)
        if tx_hash:
            embed.add_field(name="Tx", value=f"`{str(tx_hash)[:18]}…`", inline=True)
        embed.set_footer(text="PolyQuant Wallet Tracker • read-only whale flow")
        return embed

    def _fmt_number(self, value: Any) -> str:
        try:
            return f"{float(value):,.4g}"
        except (TypeError, ValueError):
            return "unknown"

    async def test_once(self, force_alert: bool = True) -> Dict[str, Any]:
        summary = await self.scan() if self.wallets else {"status": "idle", "reason": "no wallets configured"}
        test_sent = False
        if force_alert:
            sample = {
                "side": "BUY",
                "outcome": "YES",
                "title": "Wallet tracker test market",
                "price": "0.42",
                "size": "100",
                "transactionHash": "0xtest",
            }
            test_sent = await self._send_alert("0x0000000000000000000000000000000000000000", "TEST", sample)
        return {"status": "success", "test_alert_sent": test_sent, "last_scan": summary}
