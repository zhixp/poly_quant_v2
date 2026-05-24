"""Live exact-mapping Polymarket/Kalshi arbitrage scanner."""
import asyncio
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

import discord

from app.core.bookmaker_client import bookmaker_client
from app.core.market_mapping import MarketMapping, market_mapping_service
from app.core.server_manager import server_manager

logger = logging.getLogger("CrossVenueArbScanner")


class CrossVenueArbScanner:
    """Read-only live arb alerts for exact active Polymarket/Kalshi mappings."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled = os.getenv("CROSS_VENUE_ARB_ENABLED", "true").lower() not in {"0", "false", "no"}
        self.interval_seconds = int(os.getenv("CROSS_VENUE_ARB_INTERVAL_SECONDS", "120"))
        self.max_mappings_per_scan = int(os.getenv("CROSS_VENUE_ARB_MAX_MAPPINGS", "50"))
        self.cooldown_seconds = int(os.getenv("CROSS_VENUE_ARB_COOLDOWN_SECONDS", "900"))
        self.last_alert: Dict[str, float] = {}
        self.scan_count = 0
        self.last_scan_summary: Dict[str, Any] = {}

    async def start(self):
        if not self.enabled:
            logger.info("Cross-venue arb scanner disabled by CROSS_VENUE_ARB_ENABLED=false")
            return

        logger.info("Cross-venue arb scanner online")
        while True:
            try:
                await self.scan()
            except Exception as exc:
                logger.error("Cross-venue arb scan failed: %s", exc, exc_info=True)
            await asyncio.sleep(self.interval_seconds)

    async def scan(self) -> Dict[str, Any]:
        self.scan_count += 1
        started = datetime.now(timezone.utc)
        mappings = await self._active_exact_kalshi_mappings()
        summary = {
            "scan_id": self.scan_count,
            "mappings_checked": 0,
            "alerts_found": 0,
            "alerts_sent": 0,
        }

        for mapping in mappings[: self.max_mappings_per_scan]:
            summary["mappings_checked"] += 1
            arb = await bookmaker_client.check_polymarket_kalshi_arb(
                mapping.polymarket_market_slug,
                mapping.venue_market_id,
            )
            alert_directions = self._alert_directions(arb)
            if not alert_directions:
                continue

            summary["alerts_found"] += len(alert_directions)
            if self._is_on_cooldown(mapping, alert_directions, arb):
                continue

            if await self._send_alert(mapping, arb, alert_directions):
                summary["alerts_sent"] += 1
                self._mark_alerted(mapping, alert_directions, arb)

        summary["duration_ms"] = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        self.last_scan_summary = summary
        logger.info(
            "CrossVenueArb scan #%s | mappings=%s alerts=%s sent=%s duration=%sms",
            summary["scan_id"],
            summary["mappings_checked"],
            summary["alerts_found"],
            summary["alerts_sent"],
            summary["duration_ms"],
        )
        return summary

    async def _active_exact_kalshi_mappings(self) -> List[MarketMapping]:
        mappings = await market_mapping_service.get_all_active_mappings()
        exact: List[MarketMapping] = []
        for mapping in mappings:
            if mapping.venue.lower() != "kalshi":
                continue
            if not mapping.polymarket_market_slug:
                continue
            if not market_mapping_service.is_exact_active_mapping(
                mapping,
                mapping.polymarket_event_slug,
                mapping.polymarket_market_slug,
                venue="kalshi",
            ):
                continue
            exact.append(mapping)
        return exact

    def _alert_directions(self, arb: Dict[str, Any]) -> List[str]:
        if arb.get("status") != "ARB_ALERT":
            return []
        return [
            direction
            for direction, data in (arb.get("directions") or {}).items()
            if data.get("status") == "ARB_ALERT"
        ]

    async def _send_alert(self, mapping: MarketMapping, arb: Dict[str, Any], alert_directions: List[str]) -> bool:
        channels = await server_manager.get_all_arb_channels()
        if not channels:
            logger.warning("No dedicated arb_channel_id configured; skipping cross-venue arb alert without fallback")
            return False

        embed = self._build_embed(mapping, arb, alert_directions)
        sent_count = 0
        for guild_id, channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning("Arb alert channel %s not found for guild %s", channel_id, guild_id)
                continue
            try:
                await channel.send(embed=embed)
                sent_count += 1
            except Exception as exc:
                logger.error("Failed to send arb alert to guild %s: %s", guild_id, exc)

        if sent_count == 0:
            logger.warning("Cross-venue arb alert was not sent to any configured arb_channel_id")
        return sent_count > 0

    def _build_embed(self, mapping: MarketMapping, arb: Dict[str, Any], alert_directions: List[str]) -> discord.Embed:
        embed = discord.Embed(
            title="POLY/KALSHI ARB ALERT",
            description=mapping.normalized_name,
            color=0xF1C40F,
        )
        embed.add_field(name="Polymarket", value=mapping.polymarket_market_slug, inline=False)
        embed.add_field(name="Kalshi", value=mapping.venue_market_id, inline=False)

        for direction in alert_directions[:4]:
            data = (arb.get("directions") or {}).get(direction, {})
            embed.add_field(
                name=direction.replace("_", " "),
                value=(
                    f"Cost/unit: {self._fmt_decimal(data.get('cost_per_unit'))}\n"
                    f"Profit/unit: {self._fmt_decimal(data.get('profit_per_unit'))}\n"
                    f"Max units: {self._fmt_decimal(data.get('max_units'))}\n"
                    f"Total profit: {self._fmt_decimal(data.get('total_profit'))}"
                ),
                inline=False,
            )

        embed.add_field(
            name="Guardrails",
            value="Exact active DB mapping only. Executable asks only. No fuzzy/event-level live alerts.",
            inline=False,
        )
        embed.set_footer(text="PolyQuant Cross-Venue Arb - read-only alert")
        return embed

    def _is_on_cooldown(self, mapping: MarketMapping, alert_directions: List[str], arb: Dict[str, Any]) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        for key in self._alert_keys(mapping, alert_directions, arb):
            last = self.last_alert.get(key)
            if last and now - last < self.cooldown_seconds:
                return True
        return False

    def _mark_alerted(self, mapping: MarketMapping, alert_directions: List[str], arb: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).timestamp()
        for key in self._alert_keys(mapping, alert_directions, arb):
            self.last_alert[key] = now

    def _alert_keys(self, mapping: MarketMapping, alert_directions: List[str], arb: Dict[str, Any]) -> List[str]:
        keys = []
        directions = arb.get("directions") or {}
        for direction in alert_directions:
            data = directions.get(direction, {})
            profit = self._fmt_decimal(data.get("profit_per_unit"))
            size = self._fmt_decimal(data.get("max_units"))
            keys.append(f"{mapping.id}:{direction}:{profit}:{size}")
        return keys

    def _fmt_decimal(self, value: Any) -> str:
        if isinstance(value, Decimal):
            return str(value.quantize(Decimal("0.0001")))
        if value is None:
            return "unknown"
        return str(value)
