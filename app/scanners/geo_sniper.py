"""
Geo Sniper: read-only Polymarket geopolitical signal monitor.

This scanner is built for deadline/resolution markets where the edge is not
"headline guessing". It compares live Polymarket prices/flow against hard rule
wording and external source language, then posts watchlist alerts to configured
Discord alert channels. It never trades.
"""
import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

import aiohttp
import discord

from app.core.server_manager import server_manager

logger = logging.getLogger("GeoSniper")

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

# Keep explicit event slugs opt-in. A hardcoded default made the channel behave
# like an Iran ladder watcher instead of a broader geopolitics scanner.
DEFAULT_EVENT_SLUGS = []

GEO_KEYWORDS = {
    "iran", "u.s.", "us", "united states", "trump", "israel", "hezbollah",
    "hormuz", "strait", "ceasefire", "peace", "deal", "agreement", "war",
    "hostilities", "sanctions", "nuclear", "missile", "blockade", "ports",
    "china", "taiwan", "russia", "ukraine", "nato", "europe", "india",
    "pakistan", "turkey", "syria", "lebanon", "gaza", "palestine", "hamas",
    "venezuela", "colombia", "mexico", "canada", "korea", "japan", "election",
    "president", "prime minister", "military", "strike", "tariff", "border",
}

GEO_CONFIRMATION_TERMS = {
    "agreement", "ceasefire", "hostilities", "hormuz", "iran", "war", "sanctions",
}

NON_GEO_CATEGORIES = {
    "sports", "esports", "games", "gaming",
}

PERMANENT_TERMS = {
    "permanent", "lasting", "definitive", "final agreement", "formally adopt",
    "signed", "treaty", "permanently cease", "lasting end",
}

FRAMEWORK_TERMS = {
    "framework", "memorandum", "mou", "proposal", "preliminary", "interim",
    "temporary", "extension", "continued negotiations", "30 days", "final details",
    "largely negotiated", "could change", "progress", "talks",
}

DEFAULT_RSS_FEEDS = {
    "CNN Middle East": "https://rss.cnn.com/rss/edition_middleeast.rss",
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    # Truth Social is first-class for Trump/geopolitics catalysts.
    # If this public RSS endpoint ever changes, override via GEO_SNIPER_RSS_FEEDS.
    "Truth Social realDonaldTrump": "https://truthsocial.com/@realDonaldTrump.rss",
}

# Direct catalyst pages are useful for a live incident, but stale hardcoded
# articles can keep retriggering old narratives. Configure via env when needed.
DEFAULT_DIRECT_SOURCES = []


@dataclass
class GeoSignal:
    market_question: str
    market_slug: str
    url: str
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    signal: str
    side: str
    confidence: str
    risk: str
    catalyst: str
    move: Optional[float] = None
    whale_flow: Optional[str] = None


class GeoSniper:
    """Geopolitical Polymarket sniper scanner for Discord alerts."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled = os.getenv("GEO_SNIPER_ENABLED", "true").lower() not in {"0", "false", "no"}
        self.interval_seconds = int(os.getenv("GEO_SNIPER_INTERVAL_SECONDS", "300"))
        self.min_price_move = float(os.getenv("GEO_SNIPER_MIN_PRICE_MOVE", "0.07"))
        self.min_whale_usdc = float(os.getenv("GEO_SNIPER_MIN_WHALE_USDC", "15000"))
        self.max_markets_per_scan = int(os.getenv("GEO_SNIPER_MAX_MARKETS", "40"))
        self.broad_market_limit = int(os.getenv("GEO_SNIPER_BROAD_MARKET_LIMIT", "250"))
        self.discovery_pages = int(os.getenv("GEO_SNIPER_DISCOVERY_PAGES", "6"))
        self.max_alerts_per_scan = int(os.getenv("GEO_SNIPER_MAX_ALERTS_PER_SCAN", "6"))
        self.market_cooldown_seconds = int(os.getenv("GEO_SNIPER_MARKET_COOLDOWN_SECONDS", "21600"))
        self.family_cooldown_seconds = int(os.getenv("GEO_SNIPER_FAMILY_COOLDOWN_SECONDS", "3600"))
        self.seen_alerts = set()
        self.alert_cooldowns: Dict[str, float] = {}
        self.family_cooldowns: Dict[str, float] = {}
        self.scan_count = 0
        self.last_scan_summary: Dict[str, Any] = {}

        slugs = os.getenv("GEO_SNIPER_EVENT_SLUGS", ",".join(DEFAULT_EVENT_SLUGS))
        self.event_slugs = [s.strip() for s in slugs.split(",") if s.strip()]

        direct_sources = os.getenv("GEO_SNIPER_DIRECT_SOURCES", ",".join(DEFAULT_DIRECT_SOURCES))
        self.direct_sources = [s.strip() for s in direct_sources.split(",") if s.strip()]
        self.rss_feeds = self._configured_rss_feeds()

    async def start(self):
        if not self.enabled:
            logger.info("🛰️ Geo Sniper disabled by GEO_SNIPER_ENABLED=false")
            return

        logger.info("🛰️ Geo Sniper Active (read-only geopolitical alerts)")
        error_count = 0
        while True:
            try:
                await self.scan()
                error_count = 0
            except Exception as exc:
                error_count += 1
                logger.error(f"Geo Sniper error: {exc}", exc_info=True)
                if error_count >= 3:
                    error_count = 0
            await asyncio.sleep(self.interval_seconds)

    async def scan(self) -> Dict[str, Any]:
        self.scan_count += 1
        started = datetime.now(timezone.utc)
        summary = {
            "scan_id": self.scan_count,
            "markets_checked": 0,
            "source_hits": 0,
            "signals_found": 0,
            "alerts_sent": 0,
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            markets = await self._fetch_watch_markets(session)
            summary["markets_checked"] = len(markets)

            source_hits = await self._fetch_source_hits(session)
            summary["source_hits"] = len(source_hits)

            signals: List[GeoSignal] = []
            for market in markets[: self.max_markets_per_scan]:
                signal = await self._analyze_market(session, market, source_hits)
                if signal:
                    signals.append(signal)

            summary["signals_found"] = len(signals)
            sent_families = set()
            for signal in signals[: self.max_alerts_per_scan]:
                family_key = self._family_key(signal.market_slug, signal.signal, signal.catalyst)
                if family_key in sent_families or self._is_family_on_cooldown(family_key):
                    continue
                if await self._send_alert(signal):
                    summary["alerts_sent"] += 1
                    sent_families.add(family_key)
                    self._mark_family_seen(family_key)

        summary["duration_ms"] = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        self.last_scan_summary = summary
        logger.info(
            "🛰️ GeoSniper scan #%s | markets=%s sources=%s signals=%s alerts=%s duration=%sms",
            summary["scan_id"], summary["markets_checked"], summary["source_hits"],
            summary["signals_found"], summary["alerts_sent"], summary["duration_ms"],
        )
        return summary

    async def _fetch_watch_markets(self, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        markets: List[Dict[str, Any]] = []
        seen = set()

        for slug in self.event_slugs:
            url = f"{GAMMA_API}/events"
            async with session.get(url, params={"slug": slug}) as resp:
                if resp.status != 200:
                    logger.warning("Gamma event fetch failed for %s: %s", slug, resp.status)
                    continue
                events = await resp.json()
                for event in events or []:
                    parent_slug = event.get("slug", slug)
                    for market in event.get("markets", []) or []:
                        if market.get("closed") or not market.get("active", True):
                            continue
                        market_slug = market.get("slug") or market.get("id")
                        if not market_slug or market_slug in seen:
                            continue
                        seen.add(market_slug)
                        market["_parent_slug"] = parent_slug
                        markets.append(market)

        # Add high-volume active geopolitical markets from multiple Gamma pages.
        # The first volume-sorted page alone repeatedly surfaces the same
        # high-volume ladder and misses lower-volume geopolitics edge.
        per_page = max(1, min(self.broad_market_limit, 500))
        for page in range(max(1, self.discovery_pages)):
            params = {
                "limit": per_page,
                "offset": page * per_page,
                "active": "true",
                "closed": "false",
                "order": "volume",
                "ascending": "false",
            }
            async with session.get(f"{GAMMA_API}/markets", params=params) as resp:
                if resp.status != 200:
                    logger.warning("Gamma broad market fetch failed page=%s status=%s", page, resp.status)
                    continue
                for market in await resp.json():
                    if self._is_non_geo_market(market):
                        continue
                    if not self._is_geo_market_candidate(market):
                        continue
                    market_slug = market.get("slug") or market.get("id")
                    if not market_slug or market_slug in seen:
                        continue
                    seen.add(market_slug)
                    markets.append(market)

        return markets

    def _is_geo_market_candidate(self, market: Dict[str, Any]) -> bool:
        if self._is_non_geo_market(market):
            return False
        blob = " ".join(
            str(market.get(key) or "")
            for key in ("question", "description", "slug", "event_title", "groupItemTitle")
        )
        return self._has_geo_keyword(blob)

    async def _fetch_source_hits(self, session: aiohttp.ClientSession) -> List[Dict[str, str]]:
        hits: List[Dict[str, str]] = []

        # Direct catalyst pages: use when a known article is moving a market.
        for url in self.direct_sources[:5]:
            try:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text(errors="ignore")
                    text = self._html_to_text(html)
                    title = self._extract_title(html) or url
                    if self._is_geo_relevant(text):
                        hits.append({"source": self._source_name(url), "title": title, "url": url, "text": text[:6000]})
            except Exception as exc:
                logger.debug("Direct source fetch failed %s: %s", url, exc)

        # RSS/social feeds: broad net for fresh geopolitics headlines.
        # X is intentionally supported through configured RSS/export URLs only
        # (for example an external export bridge), not direct bot login scraping.
        for source, url in self.rss_feeds.items():
            try:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status != 200:
                        continue
                    xml_data = await resp.text(errors="ignore")
                    root = ET.fromstring(xml_data)
                    for item in root.findall(".//item")[:8]:
                        title = (item.findtext("title") or "").strip()
                        link = (item.findtext("link") or "").strip()
                        blob = f"{title} {link}"
                        if self._is_geo_relevant(blob):
                            hits.append({"source": source, "title": title, "url": link, "text": blob})
            except Exception as exc:
                logger.debug("RSS source fetch failed %s: %s", source, exc)

        return hits[:40]

    def _configured_rss_feeds(self) -> Dict[str, str]:
        feeds = dict(DEFAULT_RSS_FEEDS)

        # Format: Name=https://feed.url/rss,Other=https://...
        # Use this for custom news/RSS and Truth Social overrides.
        extra = os.getenv("GEO_SNIPER_RSS_FEEDS", "")
        for idx, item in enumerate([x.strip() for x in extra.split(",") if x.strip()], start=1):
            if "=" in item:
                name, url = item.split("=", 1)
                feeds[name.strip() or f"Custom RSS {idx}"] = url.strip()
            else:
                feeds[f"Custom RSS {idx}"] = item

        # X/Twitter is disabled by default until the Grok API source adapter is wired.
        enable_x_bridge = os.getenv("GEO_SNIPER_ENABLE_X_BRIDGE", "false").lower() in {"1", "true", "yes"}
        if not enable_x_bridge and os.getenv("GEO_SNIPER_X_RSS_FEEDS", "").strip():
            logger.warning("GEO_SNIPER_X_RSS_FEEDS configured but ignored because GEO_SNIPER_ENABLE_X_BRIDGE is false")
            return feeds

        # Optional convenience var for X/Twitter RSS-export bridges.
        # Format: Account=https://bridge/rss,Another=https://...
        x_feeds = os.getenv("GEO_SNIPER_X_RSS_FEEDS", "")
        for idx, item in enumerate([x.strip() for x in x_feeds.split(",") if x.strip()], start=1):
            if "=" in item:
                name, url = item.split("=", 1)
                feeds[f"X {name.strip()}"] = url.strip()
            else:
                feeds[f"X Feed {idx}"] = item
        return feeds

    async def _analyze_market(
        self,
        session: aiohttp.ClientSession,
        market: Dict[str, Any],
        source_hits: Sequence[Dict[str, str]],
    ) -> Optional[GeoSignal]:
        question = market.get("question") or "Unknown market"
        slug = market.get("slug") or str(market.get("id") or "")
        parent_slug = market.get("_parent_slug") or self._infer_parent_slug(slug)
        market_url = f"https://polymarket.com/event/{parent_slug}/{slug}" if parent_slug else f"https://polymarket.com/market/{slug}"

        yes_price, no_price = self._prices(market)
        if yes_price is None or no_price is None:
            return None

        token_ids = self._json_list(market.get("clobTokenIds"))
        yes_token = str(token_ids[0]) if token_ids else ""
        condition_id = market.get("conditionId") or market.get("condition_id") or ""

        move = None
        if yes_token:
            move = await self._recent_yes_move(session, yes_token, yes_price)

        whale_flow = ""
        if condition_id:
            whale_flow = await self._recent_whale_flow(session, condition_id)

        relevant_sources = self._matching_sources(question, source_hits)
        q_lower = question.lower()
        description = market.get("description") or ""
        source_blob = "\n".join(hit.get("text", "") for hit in relevant_sources).lower()

        signal = None
        side = "WATCH"
        confidence = "medium"
        risk = "Resolution may depend on exact official wording and Polymarket moderator interpretation."
        catalyst = relevant_sources[0]["title"] if relevant_sources else "Live Polymarket flow / price move"

        if "permanent peace deal" in q_lower and ("iran" in q_lower or "iran" in description.lower()):
            has_framework = any(term in source_blob for term in FRAMEWORK_TERMS)
            has_permanent = any(term in source_blob for term in PERMANENT_TERMS)
            if relevant_sources and has_framework and not has_permanent:
                signal = "headline pump vs rule wording: framework/MOU language without clear permanent peace confirmation"
                side = "WATCH NO / fade YES only if official wording stays interim"
                confidence = "medium-high"
                risk = "NO loses if both US and Iran clearly confirm a permanent/lasting end of hostilities before the deadline."
            elif relevant_sources and has_permanent:
                signal = "possible YES catalyst: source language includes permanent/lasting/signed agreement terms"
                side = "WATCH YES confirmation; do not chase until both-side official confirmation is clear"
                confidence = "medium"
                risk = "Headline may still be a proposal/framework; verify official US + Iranian statements."

        if not signal and move is not None and abs(move) >= self.min_price_move:
            direction = "YES squeeze" if move > 0 else "YES dump / NO bid"
            signal = f"price dislocation: {direction} of {move * 100:+.1f}c in recent history"
            side = "WATCH; verify catalyst before taking side"
            confidence = "medium"

        if not signal and whale_flow and relevant_sources:
            signal = "large recent flow detected in a geopolitical market"
            side = "WATCH orderbook + source confirmation"
            confidence = "low-medium"

        if not signal:
            return None

        alert_key = self._alert_key(slug, signal, catalyst)
        if self._is_alert_on_cooldown(alert_key):
            return None
        self._mark_alert_seen(alert_key)

        return GeoSignal(
            market_question=question,
            market_slug=slug,
            url=market_url,
            yes_price=yes_price,
            no_price=no_price,
            volume=self._safe_float(market.get("volume")),
            liquidity=self._safe_float(market.get("liquidity")),
            signal=signal,
            side=side,
            confidence=confidence,
            risk=risk,
            catalyst=catalyst,
            move=move,
            whale_flow=whale_flow or None,
        )

    async def _recent_yes_move(self, session: aiohttp.ClientSession, yes_token: str, current_yes: float) -> Optional[float]:
        try:
            params = {"market": yes_token, "interval": "1d", "fidelity": 15}
            async with session.get(f"{CLOB_API}/prices-history", params=params) as resp:
                if resp.status != 200:
                    return None
                history = (await resp.json()).get("history", [])
            if len(history) < 2:
                return None
            prior = float(history[-4]["p"] if len(history) >= 4 else history[0]["p"])
            return current_yes - prior
        except Exception:
            return None

    async def _recent_whale_flow(self, session: aiohttp.ClientSession, condition_id: str) -> str:
        try:
            async with session.get(f"{DATA_API}/trades", params={"market": condition_id, "limit": 80}) as resp:
                if resp.status != 200:
                    return ""
                trades = await resp.json()
        except Exception:
            return ""

        whales = []
        for trade in trades or []:
            try:
                notional = float(trade.get("price", 0)) * float(trade.get("size", 0))
            except (TypeError, ValueError):
                continue
            if notional >= self.min_whale_usdc:
                whales.append(
                    f"{trade.get('side')} {trade.get('outcome')} ${notional:,.0f} @ {float(trade.get('price', 0)):.2f}"
                )
        return "\n".join(whales[:3])

    async def _send_alert(self, signal: GeoSignal) -> bool:
        alert_channels = await server_manager.get_all_geo_channels()
        if not alert_channels:
            logger.warning("No dedicated geo_channel_id configured; skipping GeoSniper alert without fallback")
            return False

        embed = discord.Embed(title="🛰️ POLY GEO SNIPER", color=0x2dd4bf, url=signal.url)
        embed.add_field(name="Market", value=self._clip(signal.market_question, 1000), inline=False)
        embed.add_field(
            name="Current odds",
            value=f"YES {signal.yes_price * 100:.1f}% / NO {signal.no_price * 100:.1f}%",
            inline=True,
        )
        embed.add_field(name="Confidence", value=signal.confidence.upper(), inline=True)
        embed.add_field(name="Signal", value=self._clip(signal.signal, 1000), inline=False)
        embed.add_field(name="Catalyst", value=self._clip(signal.catalyst, 1000), inline=False)
        if signal.move is not None:
            embed.add_field(name="Recent move", value=f"YES {signal.move * 100:+.1f}c", inline=True)
        if signal.whale_flow:
            embed.add_field(name="Whale flow", value=self._clip(signal.whale_flow, 1000), inline=False)
        embed.add_field(name="Risk", value=self._clip(signal.risk, 1000), inline=False)
        embed.add_field(name="Action", value=self._clip(signal.side + " — read-only alert, user decides.", 1000), inline=False)
        embed.set_footer(text="PolyQuant Geo Sniper • rules > headlines • no auto-trading")

        sent = 0
        for guild_id, channel_id in alert_channels:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(embed=embed)
                    sent += 1
                else:
                    logger.warning("GeoSniper channel %s not found for guild %s", channel_id, guild_id)
            except Exception as exc:
                logger.error("GeoSniper failed to send alert to guild %s: %s", guild_id, exc)
        return sent > 0

    async def test_once(self, force_alert: bool = True) -> Dict[str, Any]:
        summary = await self.scan()
        test_alert_sent = False
        if force_alert:
            sample = GeoSignal(
                market_question="US x Iran permanent peace deal by May 26, 2026?",
                market_slug="geo-sniper-test",
                url="https://polymarket.com/event/us-x-iran-permanent-peace-deal-by/us-x-iran-permanent-peace-deal-by-may-26-2026",
                yes_price=0.55,
                no_price=0.45,
                volume=0,
                liquidity=0,
                signal="test alert: Geo Sniper Discord path operational",
                side="WATCH ONLY — no auto-trade",
                confidence="test",
                risk="Synthetic test alert.",
                catalyst="Manual /test_geo_sniper command",
            )
            test_alert_sent = await self._send_alert(sample)
        return {"status": "success", "test_alert_sent": test_alert_sent, "last_scan": summary}

    def _prices(self, market: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
        prices = self._json_list(market.get("outcomePrices"))
        outcomes = self._json_list(market.get("outcomes"))
        if len(prices) >= 2:
            try:
                yes_index = None
                no_index = None
                for idx, outcome in enumerate(outcomes):
                    label = str(outcome).strip().lower()
                    if label == "yes":
                        yes_index = idx
                    elif label == "no":
                        no_index = idx
                if outcomes and (yes_index is None or no_index is None):
                    logger.debug("Skipping non-YES/NO market in GeoSniper price extraction: %s", market.get("question"))
                    return None, None
                if yes_index is None:
                    yes_index = 0
                if no_index is None:
                    no_index = 1
                return float(prices[yes_index]), float(prices[no_index])
            except (TypeError, ValueError, IndexError):
                pass
        yes = market.get("bestBid") or market.get("lastTradePrice")
        if yes is not None:
            try:
                yes_f = float(yes)
                return yes_f, max(0.0, 1.0 - yes_f)
            except (TypeError, ValueError):
                return None, None
        return None, None

    def _json_list(self, value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []

    def _matching_sources(self, question: str, source_hits: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
        q = question.lower()
        q_tokens = {t for t in re.findall(r"[a-zA-Z]{4,}", q) if t not in {"will", "this", "that", "market", "deal"}}
        matches = []
        for hit in source_hits:
            blob = f"{hit.get('title', '')} {hit.get('text', '')}".lower()
            score = sum(1 for token in q_tokens if token in blob)
            if score >= 2 and self._has_geo_confirmation_term(blob):
                matches.append(hit)
        return matches

    def _alert_key(self, market_slug: str, signal: str, catalyst: str) -> str:
        source_fingerprint = re.sub(r"[^a-z0-9]+", "-", (catalyst or "no-source").lower()).strip("-")[:80]
        return f"{market_slug}:{self._signal_family(signal)}:{source_fingerprint}"

    def _signal_family(self, signal: str) -> str:
        text = (signal or "").lower()
        if "framework" in text or "mou" in text:
            return "rule-framework"
        if "permanent" in text or "signed agreement" in text:
            return "permanent-catalyst"
        if "yes squeeze" in text:
            return "price-yes-squeeze"
        if "yes dump" in text or "no bid" in text:
            return "price-yes-dump"
        if re.search(r"\byes\s*[+-]", text):
            return "price-yes-move"
        if re.search(r"\bno\s*[+-]", text):
            return "price-no-move"
        if "large recent flow" in text:
            return "source-backed-flow"
        return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:48] or "generic"

    def _is_alert_on_cooldown(self, alert_key: str) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        last_seen = self.alert_cooldowns.get(alert_key)
        if last_seen and now - last_seen < self.market_cooldown_seconds:
            return True
        return False

    def _mark_alert_seen(self, alert_key: str) -> None:
        now = datetime.now(timezone.utc).timestamp()
        self.seen_alerts.add(alert_key)
        self.alert_cooldowns[alert_key] = now

    def _family_key(self, market_slug: str, signal: str, catalyst: str) -> str:
        # Collapse ladder/date variants like us-x-iran-peace-by-may-26 / june-1
        # so one scan cannot flood Discord with the same narrative.
        family = re.sub(
            r"-(?:by-)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*-?\d{1,2}(?:-\d{4})?$",
            "",
            market_slug.lower(),
        )
        family = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", family)
        source = re.sub(r"[^a-z0-9]+", "-", (catalyst or "no-source").lower()).strip("-")[:48]
        return f"{family}:{self._signal_family(signal)}:{source}"

    def _is_family_on_cooldown(self, family_key: str) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        last_seen = self.family_cooldowns.get(family_key)
        return bool(last_seen and now - last_seen < self.family_cooldown_seconds)

    def _mark_family_seen(self, family_key: str) -> None:
        self.family_cooldowns[family_key] = datetime.now(timezone.utc).timestamp()

    def _is_geo_relevant(self, text: str) -> bool:
        return self._has_geo_keyword(text) and self._has_geo_confirmation_term(text)

    def _is_non_geo_market(self, market: Dict[str, Any]) -> bool:
        category_blob = " ".join(
            str(market.get(key) or "")
            for key in ("category", "subcategory", "event_title", "groupItemTitle")
        ).lower()
        question = str(market.get("question") or "").lower()
        return (
            any(category in category_blob for category in NON_GEO_CATEGORIES)
            or any(term in question for term in ("counter-strike", "valorant", "league of legends", "dota", "map winner", "moneyline"))
        )

    def _has_geo_keyword(self, text: str) -> bool:
        blob = text.lower()
        tokens = set(re.findall(r"[a-z0-9]+", blob))
        for keyword in GEO_KEYWORDS:
            normalized = keyword.lower()
            if " " in normalized:
                if normalized in blob:
                    return True
            elif normalized in {"us", "u.s."}:
                if normalized == "u.s." and re.search(r"(?<![a-z0-9])u\.s\.(?![a-z0-9])", blob):
                    return True
                if "us" in tokens:
                    return True
            elif normalized in tokens:
                return True
        return False

    def _has_geo_confirmation_term(self, text: str) -> bool:
        blob = text.lower()
        tokens = set(re.findall(r"[a-z0-9]+", blob))
        return any(term in tokens for term in GEO_CONFIRMATION_TERMS)

    def _html_to_text(self, html: str) -> str:
        html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_title(self, html: str) -> str:
        match = re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S)
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""

    def _source_name(self, url: str) -> str:
        host = re.sub(r"^https?://", "", url).split("/")[0]
        return host.replace("www.", "")

    def _infer_parent_slug(self, market_slug: str) -> str:
        if "us-x-iran-permanent-peace-deal-by" in market_slug:
            return "us-x-iran-permanent-peace-deal-by"
        return ""

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value or default)
        except (TypeError, ValueError):
            return default

    def _clip(self, text: str, limit: int) -> str:
        text = str(text or "")
        return text if len(text) <= limit else text[: limit - 1] + "…"
