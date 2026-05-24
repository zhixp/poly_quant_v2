"""Resolution Assistant: surfaces official sources for markets nearing resolution."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import aiohttp
import discord

from app.core.server_manager import server_manager

logger = logging.getLogger("ResolutionAssistant")


class ResolutionAssistant:
    LOOKAHEAD_HOURS = 48
    MAX_MARKETS_PER_SCAN = 5

    def __init__(self, bot):
        self.bot = bot
        self.alerted_markets = {}

    async def start(self):
        logger.info("📘 Resolution Assistant online")
        while True:
            try:
                await self.scan()
            except Exception as exc:
                logger.error(f"Resolution scan failed: {exc}", exc_info=True)
            await asyncio.sleep(900)

    async def scan(self):
        markets = await self._fetch_markets()
        if not markets:
            return

        pending = self._filter_near_resolution(markets)
        if not pending:
            return

        for market in pending[: self.MAX_MARKETS_PER_SCAN]:
            market_id = market.get("id") or market.get("slug")
            if not market_id:
                continue
            last_alert = self.alerted_markets.get(market_id)
            if last_alert and (datetime.now(timezone.utc) - last_alert).total_seconds() < 3600:
                continue

            sources = await self.bot.router.search(f"{market.get('question')} official site", max_results=3)
            if not sources:
                continue

            comparison = await self._compare_rules_with_sources(market, sources)
            await self._broadcast_summary(market, sources, comparison)
            self.alerted_markets[market_id] = datetime.now(timezone.utc)

    async def _fetch_markets(self) -> List[Dict]:
        url = "https://gamma-api.polymarket.com/markets"
        params = {"active": "true", "limit": 200}
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

    def _filter_near_resolution(self, markets: List[Dict]) -> List[Dict]:
        upcoming = []
        horizon = datetime.now(timezone.utc) + timedelta(hours=self.LOOKAHEAD_HOURS)
        for market in markets:
            close_str = market.get("closeDate") or market.get("endDate") or market.get("expiryDate")
            if not close_str:
                continue
            try:
                close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            except Exception:
                continue
            if datetime.now(timezone.utc) <= close_dt <= horizon:
                upcoming.append(market)
        return upcoming

    async def _compare_rules_with_sources(self, market: Dict, sources: List[Dict]) -> str:
        rules = market.get("description") or market.get("rules") or "Rules not provided."
        source_text = []
        for idx, src in enumerate(sources, start=1):
            snippet = src.get("content", "")[:600]
            source_text.append(f"Source {idx}: {src.get('title')}\nURL: {src.get('url')}\nContent: {snippet}")

        prompt = (
            "You are PolyQuant's resolution assistant.\n"
            f"Market Question: {market.get('question')}\n"
            f"Official Rules: {rules}\n\n"
            "Below are potential official sources:\n"
            f"{chr(10).join(source_text)}\n\n"
            "Task: summarize whether the sources confirm resolution, cite which link is most official, "
            "and flag any conflicts. Respond in max 3 bullet points."
        )

        try:
            response = await self.bot.hydra.generate(prompt)
        except Exception as exc:
            logger.warning(f"Hydra analysis failed: {exc}")
            response = "Hydra unavailable. Review sources manually."
        return response

    async def _broadcast_summary(self, market: Dict, sources: List[Dict], summary: str):
        embed = discord.Embed(
            title="📘 Resolution Assistant",
            description=market.get("question", ""),
            color=0x3498DB,
        )
        embed.add_field(name="Top Sources", value=self._format_sources(sources), inline=False)
        embed.add_field(name="Analysis", value=summary[:1024], inline=False)
        embed.set_footer(text="Resolution Assistant • PolyOS")

        channels = await server_manager.get_all_curated_channels()
        if not channels:
            channels = await server_manager.get_all_alert_channels()

        for item in channels:
            if isinstance(item, tuple) and len(item) == 2:
                guild_id, channel_id = item
            else:
                guild_id, channel_id = item[0], item[1]
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except Exception as exc:
                    logger.debug(f"Failed to send resolution summary to {guild_id}: {exc}")

    def _format_sources(self, sources: List[Dict]) -> str:
        lines = []
        for src in sources[:3]:
            title = src.get("title") or src.get("url")
            url = src.get("url") or ""
            lines.append(f"• [{title}]({url})")
        return "\n".join(lines)

