"""Inefficiency Scanner (PolyOS Data Layer).
Combines RSS intelligence and macro data (FMP) to find price lags.
FIXED: Now properly filters old markets, checks activity, and provides clear edge reasoning."""
import asyncio
import logging
import os
import re
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord

from app.core.fmp_client import fmp_client
from app.core.server_manager import server_manager

logger = logging.getLogger("InefficiencyScanner")


class InefficiencyScanner:
    RSS_FEEDS = {
        "SEC": os.getenv("SEC_RSS_URL", "https://www.sec.gov/news/pressreleases.rss"),
        "CourtListener": os.getenv(
            "COURT_RSS_URL", "https://www.courtlistener.com/api/rest/v3/opinions/?format=rss"
        ),
    }

    ECON_KEYWORDS = {
        "inflation": ["inflation", "cpi", "consumer price"],
        "jobs": ["payroll", "jobs", "unemployment"],
        "rates": ["fed", "interest rate", "fomc", "rate"],
        "gdp": ["gdp", "growth"],
    }

    NEGATIVE_TERMS = {"charged", "sued", "fraud", "indicted", "investigation", "out", "resigns", "leaves"}
    POSITIVE_TERMS = {"approves", "wins", "cleared", "approved", "passes", "hires", "partners"}
    
    # Configuration
    PRICE_THRESHOLD = 0.15
    MAX_MARKET_AGE_DAYS = 30  # Only check markets created in last 30 days
    MIN_RECENT_ACTIVITY_HOURS = 72  # Market should have activity in last 72 hours
    MIN_KEYWORD_MATCHES = 2  # Require at least 2 keyword matches for relevance
    
    def __init__(self, bot):
        self.bot = bot
        self.alerted_events = set()
        self.alerted_headlines = set()
        self.alerted_markets = set()  # Track markets we've already alerted on

    async def start(self):
        logger.info("⚖️ Inefficiency Scanner online")
        while True:
            try:
                await self.scan()
            except Exception as exc:
                logger.error(f"Inefficiency scan failure: {exc}", exc_info=True)
            await asyncio.sleep(300)

    async def scan(self):
        markets = await self._fetch_markets()
        if not markets:
            logger.debug("No markets fetched for inefficiency scan")
            return

        # Filter markets by age and activity
        active_markets = self._filter_active_markets(markets)
        logger.info(f"📊 Filtered {len(active_markets)}/{len(markets)} markets (age/activity filter)")
        
        if not active_markets:
            logger.debug("No active markets after filtering")
            return

        econ_events = await fmp_client.get_economic_calendar()
        if econ_events:
            await self._process_economic_events(econ_events, active_markets)

        rss_entries = await self._fetch_rss_entries()
        if rss_entries:
            await self._process_rss_entries(rss_entries, active_markets)

    def _filter_active_markets(self, markets: List[Dict]) -> List[Dict]:
        """
        Filter markets to only include:
        1. Markets created in last MAX_MARKET_AGE_DAYS
        2. Markets with recent activity (volume > 0 OR created recently)
        3. Markets that aren't closed/expired
        """
        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(days=self.MAX_MARKET_AGE_DAYS)
        activity_cutoff = now - timedelta(hours=self.MIN_RECENT_ACTIVITY_HOURS)
        
        filtered = []
        for market in markets:
            # Check if market is closed
            if market.get("closed", False):
                continue
            
            # Check market creation date
            created_at = self._parse_market_date(market.get("createdAt") or market.get("created_at"))
            if created_at and created_at < cutoff_date:
                logger.debug(f"⏰ Skipping old market: {market.get('question', 'Unknown')[:50]} (created {created_at.date()})")
                continue
            
            # Check for recent activity
            volume = self._safe_float(market.get("volume", 0), default=0.0)
            last_trade = self._parse_market_date(market.get("lastTrade") or market.get("last_trade"))
            
            # Allow markets with $0 liquidity IF they're very new (created in last 7 days)
            # This handles cases like "Mark will have interview with nikhil kamath in 2025"
            is_new = created_at and created_at > (now - timedelta(days=7))
            has_activity = volume > 0 or (last_trade and last_trade > activity_cutoff)
            
            if not has_activity and not is_new:
                logger.debug(f"💤 Skipping inactive market: {market.get('question', 'Unknown')[:50]} (vol=${volume:.0f}, last_trade={last_trade})")
                continue
            
            filtered.append(market)
        
        return filtered

    def _parse_market_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse market date from various formats."""
        if not date_str:
            return None
        
        if isinstance(date_str, datetime):
            if date_str.tzinfo is None:
                return date_str.replace(tzinfo=timezone.utc)
            return date_str.astimezone(timezone.utc)
        
        # Try ISO format
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except:
            pass
        
        # Try RFC 822 format
        try:
            dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
            return dt.astimezone(timezone.utc)
        except:
            pass
        
        return None

    async def _process_economic_events(self, events: List[Dict], markets: List[Dict]):
        for event in events:
            event_id = f"econ:{event.get('date')}:{event.get('event')}"
            if event_id in self.alerted_events:
                continue

            signal = self._interpret_economic_event(event)
            if not signal:
                continue

            related = self._match_markets(signal["keywords"], markets)
            if not related:
                continue

            for market in related:
                market_id = market.get("slug") or market.get("condition_id") or market.get("question")
                if market_id in self.alerted_markets:
                    continue
                
                mismatch_result = self._is_price_mismatch(signal, market)
                if mismatch_result["is_mismatch"]:
                    await self._broadcast_embed(
                        title="⚡ Macro ⟷ Polymarket Inefficiency",
                        description=signal["headline"],
                        market=market,
                        extra_fields=[
                            ("Economic Event", signal["headline"]),
                            ("Actual vs Estimate", signal["delta_text"]),
                            ("Expectation", signal["expected_direction"]),
                            ("Market Question", market.get("question", "Unknown")),
                            ("Current YES Price", f"{mismatch_result['yes_price']:.2%}"),
                            ("Edge", mismatch_result["edge_reason"]),
                        ],
                        color=0xF39C12,
                    )
                    self.alerted_events.add(event_id)
                    self.alerted_markets.add(market_id)
                    break

    async def _process_rss_entries(self, entries: List[Dict], markets: List[Dict]):
        now = datetime.now(timezone.utc)
        for entry in entries:
            headline_id = entry.get("link") or entry.get("title")
            if not headline_id or headline_id in self.alerted_headlines:
                continue

            published = entry.get("published")
            if published and now - published > timedelta(hours=6):
                continue

            signal = self._interpret_headline(entry.get("title", ""))
            if not signal:
                continue

            related = self._match_markets(signal["keywords"], markets)
            if not related:
                continue

            for market in related:
                market_id = market.get("slug") or market.get("condition_id") or market.get("question")
                if market_id in self.alerted_markets:
                    continue
                
                yes_price = self._extract_yes_price(market)
                if yes_price is None:
                    continue

                # Check if this is a relevant match (not just keyword overlap)
                relevance = self._check_relevance(entry.get("title", ""), market.get("question", ""))
                if relevance < 0.5:
                    logger.debug(f"🔍 Low relevance ({relevance:.2f}): '{entry.get('title', '')[:40]}' vs '{market.get('question', '')[:40]}'")
                    continue

                mismatch_result = self._check_price_mismatch(signal, market, yes_price)
                if mismatch_result["is_mismatch"]:
                    volume = self._safe_float(market.get("volume", 0), default=0.0)
                    created_at = self._parse_market_date(market.get("createdAt") or market.get("created_at"))
                    market_age = (now - created_at).days if created_at else None
                    
                    await self._broadcast_embed(
                        mismatch_result["title"],
                        entry.get("title") or "Breaking news",
                        market,
                        [
                            ("Headline", f"[{entry.get('title')}]({entry.get('link')})"),
                            ("Current YES Price", f"{yes_price:.2%}"),
                            ("Volume", f"${volume:,.0f}"),
                            ("Market Age", f"{market_age} days old" if market_age is not None else "Unknown"),
                            ("Edge", mismatch_result["edge_reason"]),
                        ],
                        color=mismatch_result["color"],
                    )
                    self.alerted_headlines.add(headline_id)
                    self.alerted_markets.add(market_id)
                    break

    def _check_relevance(self, headline: str, market_question: str) -> float:
        """
        Check semantic relevance between headline and market question.
        Returns score 0-1, where 1 is highly relevant.
        """
        headline_lower = headline.lower()
        question_lower = market_question.lower()
        
        # Extract key entities (proper nouns, important terms)
        headline_words = set(re.findall(r'\b[A-Z][a-z]+\b', headline))  # Proper nouns
        headline_words.update(re.findall(r'\b[a-z]{5,}\b', headline_lower))  # Longer words
        
        question_words = set(re.findall(r'\b[A-Z][a-z]+\b', market_question))  # Proper nouns
        question_words.update(re.findall(r'\b[a-z]{5,}\b', question_lower))  # Longer words
        
        # Remove common stop words
        stop_words = {"will", "have", "been", "this", "that", "with", "from", "they", "were",
                     "about", "would", "there", "their", "which", "when", "what", "some",
                     "could", "other", "than", "then", "these", "more", "many", "most"}
        headline_words = {w.lower() for w in headline_words if w.lower() not in stop_words}
        question_words = {w.lower() for w in question_words if w.lower() not in stop_words}
        
        if not headline_words or not question_words:
            return 0.0
        
        # Calculate Jaccard similarity
        intersection = headline_words & question_words
        union = headline_words | question_words
        
        if not union:
            return 0.0
        
        similarity = len(intersection) / len(union)
        
        # Boost score if key entities match (proper nouns)
        proper_nouns_headline = set(re.findall(r'\b[A-Z][a-z]+\b', headline))
        proper_nouns_question = set(re.findall(r'\b[A-Z][a-z]+\b', market_question))
        if proper_nouns_headline & proper_nouns_question:
            similarity = min(1.0, similarity + 0.3)
        
        return similarity

    def _check_price_mismatch(self, signal: Dict, market: Dict, yes_price: float) -> Dict:
        """
        Check if there's a price mismatch with context-aware logic.
        Returns dict with is_mismatch, title, color, and edge_reason.
        """
        question = (market.get("question") or "").lower()
        volume = self._safe_float(market.get("volume", 0), default=0.0)
        
        # Determine expected direction based on signal
        if signal["bias"] == "bearish":
            # Bearish news = YES should go DOWN
            # If YES is still high (>60%), that's a mismatch
            if yes_price > 0.6:
                # Calculate edge
                edge_pct = (yes_price - 0.4) * 100  # How much higher than fair value
                return {
                    "is_mismatch": True,
                    "title": "🚨 Negative News vs High Market Price",
                    "color": 0xE74C3C,
                    "edge_reason": f"Negative news but YES at {yes_price:.1%} (should be <40%). Potential {edge_pct:.0f}% overpricing."
                }
        elif signal["bias"] == "bullish":
            # Bullish news = YES should go UP
            # If YES is still low (<40%), that's a mismatch
            if yes_price < 0.4:
                # Calculate edge
                edge_pct = (0.6 - yes_price) * 100  # How much lower than fair value
                return {
                    "is_mismatch": True,
                    "title": "🚨 Positive News vs Low Market Price",
                    "color": 0x2ECC71,
                    "edge_reason": f"Positive news but YES at {yes_price:.1%} (should be >60%). Potential {edge_pct:.0f}% underpricing."
                }
        
        # No clear mismatch
        return {
            "is_mismatch": False,
            "title": "",
            "color": 0xF1C40F,
            "edge_reason": ""
        }

    def _interpret_economic_event(self, event: Dict) -> Dict:
        actual = self._safe_float(event.get("actual"))
        estimate = self._safe_float(event.get("estimate"))
        if actual is None or estimate is None:
            return {}

        delta = actual - estimate
        relative = abs(delta) / (abs(estimate) + 1e-6)
        if relative < self.PRICE_THRESHOLD:
            return {}

        headline = f"{event.get('event', 'Economic release')} {actual} vs {estimate}"
        keywords = self._derive_keywords(event.get("event", ""))
        expected = "YES pricing should jump" if delta > 0 else "NO pricing should rise"
        return {
            "headline": headline,
            "keywords": keywords,
            "delta": delta,
            "delta_text": f"Actual {actual} vs Estimate {estimate}",
            "bias": "hot" if delta > 0 else "cool",
            "expected_direction": expected,
        }

    def _is_price_mismatch(self, signal: Dict, market: Dict) -> Dict:
        """
        Check price mismatch for economic events.
        Returns dict with is_mismatch, yes_price, and edge_reason.
        """
        yes_price = self._extract_yes_price(market)
        if yes_price is None:
            return {"is_mismatch": False, "yes_price": None, "edge_reason": ""}

        question = (market.get("question") or "").lower()
        expects_yes = signal["bias"] == "hot"
        if any(word in question for word in ["below", "under", "less"]):
            expects_yes = signal["bias"] == "cool"

        if expects_yes and yes_price < 0.6:
            edge_pct = (0.6 - yes_price) * 100
            return {
                "is_mismatch": True,
                "yes_price": yes_price,
                "edge_reason": f"Economic data suggests YES should be >60% but market at {yes_price:.1%}. Potential {edge_pct:.0f}% underpricing."
            }
        if not expects_yes and yes_price > 0.4:
            edge_pct = (yes_price - 0.4) * 100
            return {
                "is_mismatch": True,
                "yes_price": yes_price,
                "edge_reason": f"Economic data suggests NO should be >60% but YES at {yes_price:.1%}. Potential {edge_pct:.0f}% overpricing."
            }
        
        return {"is_mismatch": False, "yes_price": yes_price, "edge_reason": ""}

    def _interpret_headline(self, title: str) -> Dict:
        if not title:
            return {}
        lower = title.lower()
        bias = None
        if any(term in lower for term in self.NEGATIVE_TERMS):
            bias = "bearish"
        elif any(term in lower for term in self.POSITIVE_TERMS):
            bias = "bullish"
        if not bias:
            return {}

        # Extract meaningful keywords (longer words, proper nouns)
        keywords = []
        # Proper nouns (capitalized words)
        keywords.extend(re.findall(r'\b[A-Z][a-z]+\b', title))
        # Longer words (4+ chars)
        keywords.extend([word.lower() for word in re.findall(r"[A-Za-z]{4,}", title)])
        
        # Remove duplicates and stop words
        seen = set()
        unique_keywords = []
        stop_words = {"will", "have", "been", "this", "that", "with", "from", "they", "were",
                     "about", "would", "there", "their", "which", "when", "what", "some",
                     "could", "other", "than", "then", "these", "more", "many", "most"}
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in stop_words and kw_lower not in seen:
                seen.add(kw_lower)
                unique_keywords.append(kw_lower)
        
        return {"bias": bias, "keywords": unique_keywords[:10]}

    def _match_markets(self, keywords: List[str], markets: List[Dict]) -> List[Dict]:
        """
        Match markets to keywords with improved relevance scoring.
        Requires at least MIN_KEYWORD_MATCHES matches.
        """
        if not keywords:
            return []
        
        keywords_lower = [kw.lower() for kw in keywords]
        matches = []
        
        for market in markets:
            question = (market.get("question") or "").lower()
            if not question:
                continue
            
            # Count keyword matches
            match_count = sum(1 for kw in keywords_lower if kw in question)
            
            # Require minimum matches for relevance
            if match_count >= self.MIN_KEYWORD_MATCHES:
                matches.append((market, match_count))
        
        # Sort by match count (best matches first)
        matches.sort(key=lambda x: x[1], reverse=True)
        
        # Return top 5 markets
        return [m[0] for m in matches[:5]]

    async def _fetch_rss_entries(self) -> List[Dict]:
        entries = []
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            for name, url in self.RSS_FEEDS.items():
                if not url:
                    continue
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        text = await resp.text()
                except Exception as exc:
                    logger.debug(f"RSS fetch failed for {name}: {exc}")
                    continue

                try:
                    from xml.etree import ElementTree as ET

                    root = ET.fromstring(text)
                    for item in root.findall(".//item")[:3]:
                        published_text = item.findtext("pubDate")
                        published = None
                        if published_text:
                            try:
                                published = datetime.strptime(
                                    published_text, "%a, %d %b %Y %H:%M:%S %z"
                                ).astimezone(timezone.utc)
                            except Exception:
                                published = datetime.now(timezone.utc)
                        entries.append(
                            {
                                "title": item.findtext("title"),
                                "link": item.findtext("link"),
                                "published": published,
                                "source": name,
                            }
                        )
                except Exception as exc:
                    logger.debug(f"RSS parse failed for {name}: {exc}")
                    continue
        return entries

    async def _fetch_markets(self) -> List[Dict]:
        params = {"active": "true", "closed": "false", "limit": "200"}
        url = "https://gamma-api.polymarket.com/markets"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        logger.warning(f"Gamma API returned {resp.status}")
                        return []
                    return await resp.json()
        except Exception as exc:
            logger.warning(f"Failed to fetch markets: {exc}")
            return []

    async def _broadcast_embed(self, title: str, description: str, market: Dict, extra_fields=None, color=0xF1C40F):
        embed = discord.Embed(title=title, description=description, color=color)
        embed.add_field(name="Polymarket Question", value=market.get("question", "Unknown"), inline=False)
        yes_price = self._extract_yes_price(market)
        if yes_price is not None:
            embed.add_field(name="YES Price", value=f"{yes_price:.2%}", inline=True)
        
        volume = self._safe_float(market.get("volume", 0), default=0.0)
        embed.add_field(name="Volume", value=f"${volume:,.0f}", inline=True)
        
        embed.add_field(name="Slug", value=market.get("slug", "N/A"), inline=True)
        if extra_fields:
            for name, value in extra_fields:
                embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text="Inefficiency Scanner • PolyOS")
        
        # Add reasoning about why this is inefficient
        if extra_fields:
            edge_field = next((f for f in extra_fields if f[0] == "Edge"), None)
            if edge_field:
                embed.add_field(name="💡 Why This Is Inefficient", value=edge_field[1], inline=False)

        channels = await server_manager.get_all_lag_hunter_channels()
        if not channels:
            logger.warning("No dedicated lag_hunter_channel_id configured; skipping inefficiency alert")
            return

        sent_count = 0
        for guild_id, channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                    sent_count += 1
                    logger.info(f"✅ Inefficiency alert sent: {market.get('question', 'Unknown')[:50]}")
                except Exception as exc:
                    logger.debug(f"Failed to send inefficiency alert to {guild_id}: {exc}")
        
        if sent_count == 0:
            logger.warning("⚠️ No channels configured for inefficiency alerts")

    def _extract_yes_price(self, market: Dict) -> Optional[float]:
        prices = market.get("outcomePrices") or []
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except json.JSONDecodeError:
                prices = []

        outcomes = market.get("outcomes") or []
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes = []

        cleaned = [self._safe_float(p) for p in prices]
        cleaned = [p for p in cleaned if p is not None]
        if not cleaned:
            return None

        yes_index = None
        for idx, outcome in enumerate(outcomes):
            if str(outcome).strip().lower() == "yes":
                yes_index = idx
                break

        if yes_index is None:
            yes_index = 0

        if yes_index >= len(cleaned):
            return None
        return cleaned[yes_index]

    def _derive_keywords(self, event_name: str) -> List[str]:
        lower = (event_name or "").lower()
        for key, words in self.ECON_KEYWORDS.items():
            if key in lower:
                return words
        return [word for word in lower.split() if len(word) > 4][:5]

    def _safe_float(self, value, default: Optional[float] = None) -> Optional[float]:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        stripped = str(value).replace("%", "").strip()
        try:
            return float(stripped)
        except ValueError:
            return default
