"""Basket Scanner: detects mispriced multi-outcome markets where sum of prices < 1."""
import asyncio
import json
import logging
from datetime import datetime, timezone

import aiohttp
import discord

from app.core.server_manager import server_manager

logger = logging.getLogger("BasketScanner")


class BasketScanner:
    UNDERPRICED_THRESHOLD = 0.98
    COOLDOWN_SECONDS = 3600

    def __init__(self, bot):
        self.bot = bot
        self.last_alert: dict[str, float] = {}

    async def start(self):
        logger.info("🧮 Basket Scanner online")
        while True:
            try:
                await self.scan()
            except Exception as exc:
                logger.error(f"Basket scan failed: {exc}", exc_info=True)
            await asyncio.sleep(600)

    async def scan(self):
        markets = await self._fetch_markets()
        if not markets:
            return

        now = datetime.now(timezone.utc).timestamp()

        for market in markets:
            prices = self._extract_prices(market)
            if len(prices) < 3:
                continue
            total = sum(prices)
            if total >= self.UNDERPRICED_THRESHOLD:
                continue

            market_id = market.get("id") or market.get("slug")
            if not market_id:
                continue

            last = self.last_alert.get(market_id)
            if last and now - last < self.COOLDOWN_SECONDS:
                continue

            inefficiency = 1 - total
            await self._broadcast_alert(market, prices, inefficiency)
            self.last_alert[market_id] = now

    async def _fetch_markets(self):
        url = "https://gamma-api.polymarket.com/markets"
        params = {"active": "true", "closed": "false", "limit": 300}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(f"Gamma API status {resp.status}")
                        return []
                    return await resp.json()
        except Exception as exc:
            logger.warning(f"Gamma fetch failed: {exc}")
            return []

    async def _broadcast_alert(self, market, prices, edge):
        outcomes = self._json_list(market.get("outcomes"))
        price_lines = []
        for idx, price in enumerate(prices):
            name = outcomes[idx] if idx < len(outcomes) else f"Outcome {idx+1}"
            price_lines.append(f"- {name}: {price:.2f}")

        embed = discord.Embed(
            title="🧺 Basket Arbitrage Detected",
            description=market.get("question", "Multi-outcome market"),
            color=0x9B59B6,
        )
        embed.add_field(name="Total Price", value=f"{sum(prices):.2f}", inline=True)
        embed.add_field(name="Risk-Free Edge", value=f"{edge:.2%}", inline=True)
        embed.add_field(name="Breakdown", value="\n".join(price_lines[:8]), inline=False)
        embed.set_footer(text="Basket Scanner • PolyOS")

        channels = await server_manager.get_all_lag_hunter_channels()
        if not channels:
            logger.warning("No dedicated lag_hunter_channel_id configured; skipping basket alert")
            return

        sent_count = 0
        for guild_id, channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                    sent_count += 1
                except Exception as exc:
                    logger.debug(f"Failed to send basket alert to {guild_id}: {exc}")
            else:
                logger.warning(f"Basket alert channel {channel_id} not found for guild {guild_id}")

        if sent_count == 0:
            logger.warning("Basket alert was not sent to any configured lag_hunter_channel_id")

    def _extract_prices(self, market):
        prices = self._json_list(market.get("outcomePrices"))
        normalized = []
        for price in prices:
            try:
                normalized.append(float(price))
            except (TypeError, ValueError):
                continue
        return normalized

    def _json_list(self, value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []

