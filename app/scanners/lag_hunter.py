import asyncio
import aiohttp
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET
from app.core.watchdog import watchdog
from app.core.market_mapping import market_mapping_service
from app.core.bookmaker_client import bookmaker_client
from app.core.metrics import metrics, MetricNames
from app.core.utils import is_spam_market

logger = logging.getLogger("LagHunter")

# Gamma API endpoint (public, no auth required)
GAMMA_API = "https://gamma-api.polymarket.com"
RSS_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss",
    "SEC Press": "https://www.sec.gov/news/pressreleases.rss",
    "FiveThirtyEight": "https://fivethirtyeight.com/all/feed",
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
}

def configured_rss_feeds():
    feeds = dict(RSS_FEEDS)
    extra = os.getenv("LAG_HUNTER_RSS_FEEDS", "")
    for idx, item in enumerate([x.strip() for x in extra.split(",") if x.strip()], start=1):
        if "=" in item:
            name, url = item.split("=", 1)
            feeds[name.strip() or f"Custom {idx}"] = url.strip()
        else:
            feeds[f"Custom {idx}"] = item
    return feeds

# High-signal keyword patterns for better matching
# Maps topics to preferred keywords (proper nouns, tickers, key terms)
TOPIC_KEYWORDS = {
    "Honduras": ["Honduras", "Nasralla", "Asfura", "Moncada", "Tegucigalpa"],
    "Fed": ["Fed", "Federal Reserve", "FOMC", "Powell", "rate", "basis points", "bps"],
    "Bitcoin": ["Bitcoin", "BTC", "crypto", "cryptocurrency"],
    "Election": ["election", "vote", "ballot", "primary", "caucus"],
    "NFL": ["NFL", "football", "Super Bowl"],
    "NBA": ["NBA", "basketball"],
}

# Stop words to exclude from keyword matching (common but low-signal)
STOP_WORDS = {
    "will", "have", "been", "this", "that", "with", "from", "they", "were",
    "about", "would", "there", "their", "which", "when", "what", "some",
    "could", "other", "than", "then", "these", "more", "many", "most"
}

class LagHunter:
    def __init__(self, bot):
        self.bot = bot
        # CLOB client no longer needed - using Gamma API directly for market fetching
        # Kept for backwards compatibility
        self.client = None
        self.seen_links = set()
        self.seen_alert_combos = set()  # Track (market_slug, news_link) to prevent duplicates
        self.scan_count = 0
        self.zero_alert_streak = 0
        self.last_scan_summary = {}
        self.rss_feeds = configured_rss_feeds()
        self.market_limit = int(os.getenv("LAG_HUNTER_MARKET_LIMIT", "500"))
        self.match_threshold = int(os.getenv("LAG_HUNTER_MATCH_THRESHOLD", "2"))
        self.freshness_hours = int(os.getenv("LAG_HUNTER_FRESHNESS_HOURS", "12"))

    def _normalize_timestamp(self, dt):
        """
        Ensure datetime objects are timezone-aware (UTC) for accurate comparisons.
        """
        if not isinstance(dt, datetime):
            return datetime.now(timezone.utc)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for matching: lowercase, strip punctuation, collapse whitespace.
        """
        # Lowercase
        text = text.lower()
        # Remove punctuation except spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        # Collapse multiple spaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _extract_keywords(self, title: str) -> list:
        """
        Extract high-signal keywords from a headline.
        Filters out stop words and short words, prioritizes proper nouns and key terms.
        """
        # Normalize
        normalized = self._normalize_text(title)
        words = normalized.split()
        
        # Filter keywords
        keywords = []
        for word in words:
            # Skip if too short
            if len(word) <= 3:
                continue
            # Skip stop words
            if word in STOP_WORDS:
                continue
            keywords.append(word)
        
        # Also extract any topic-specific keywords from original (case-sensitive for proper nouns)
        for topic, topic_keywords in TOPIC_KEYWORDS.items():
            for kw in topic_keywords:
                if kw.lower() in title.lower():
                    keywords.append(kw.lower())
        
        # Deduplicate while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        return unique_keywords
    
    def _match_score(self, headline_keywords: list, market_question: str) -> int:
        """
        Compute a simple match score between headline keywords and market question.
        Returns: number of matching keywords.
        """
        normalized_question = self._normalize_text(market_question)
        question_words = set(normalized_question.split())
        
        matches = 0
        for kw in headline_keywords:
            if kw in question_words or kw in normalized_question:
                matches += 1
        
        return matches

    async def start(self):
        logger.info("📡 Lag Hunter Active...")
        error_count = 0
        while True:
            try:
                await self.scan()
                error_count = 0  # Reset on success
            except Exception as e:
                error_count += 1
                logger.error(f"Lag Hunter Error: {e}")
                # Only alert if errors persist (3+ consecutive failures)
                if error_count >= 3:
                    await watchdog.alert("Lag Hunter", f"Persistent errors: {e}", "ERROR")
                    error_count = 0  # Reset to avoid spam
            
            await asyncio.sleep(60) # Scan every minute

    async def scan(self):
        """
        PERFORMANCE CRITICAL: Async RSS fetch + Market matching in <200ms
        Per poly.md Section 5: Non-blocking parallel processing
        """
        scan_start = datetime.now()
        self.scan_count += 1
        
        # Initialize scan metrics
        metrics = {
            'scan_id': self.scan_count,
            'feeds_fetched': 0,
            'feeds_failed': 0,
            'total_entries': 0,
            'fresh_entries': 0,
            'already_seen': 0,
            'markets_fetched': 0,
            'matches_found': 0,
            'alerts_sent': 0,
            'feed_details': {}
        }
        
        # No longer need CLOB client check - using Gamma API directly
        
        # Parallel fetch all RSS feeds (async)
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_rss_async(session, source, url) for source, url in self.rss_feeds.items()]
            all_entries = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Fetch markets ONCE per scan (not per entry)
        try:
            gamma_url = "https://gamma-api.polymarket.com/markets"
            params = {
                "limit": self.market_limit,
                "active": "true",
                "closed": "false"
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as gamma_session:
                async with gamma_session.get(gamma_url, params=params) as gamma_response:
                    if gamma_response.status == 200:
                        markets_data = await gamma_response.json()
                        logger.debug(f"✅ Fetched {len(markets_data)} markets from Gamma API")
                    else:
                        logger.warning(f"⚠️ Gamma API returned {gamma_response.status}")
                        markets_data = []
        except Exception as e:
            logger.error(f"❌ Failed to fetch markets from Gamma API: {e}")
            markets_data = []
        
        metrics['markets_fetched'] = len(markets_data)
        
        # Process each feed's entries
        for entries_data in all_entries:
            if isinstance(entries_data, Exception):
                metrics['feeds_failed'] += 1
                continue
            
            source, entries = entries_data
            metrics['feeds_fetched'] += 1
            feed_stats = {
                'total': len(entries),
                'fresh': 0,
                'seen': 0,
                'matches': 0
            }
            
            current_time = datetime.now(timezone.utc)
            for entry in entries[:3]:  # Limit to 3 most recent per feed
                try:
                    metrics['total_entries'] += 1
                    
                    # 1. Freshness Check (configurable; default 12h to avoid a dead scanner when feeds are quiet)
                    published = self._normalize_timestamp(entry['published'])
                    if current_time - published > timedelta(hours=self.freshness_hours):
                        continue
                    
                    feed_stats['fresh'] += 1
                    metrics['fresh_entries'] += 1
                        
                    if entry['link'] in self.seen_links:
                        feed_stats['seen'] += 1
                        metrics['already_seen'] += 1
                        continue
                    self.seen_links.add(entry['link'])

                    # 2. Extract high-signal keywords from headline
                    keywords = self._extract_keywords(entry['title'])
                    
                    if not keywords:
                        logger.debug(f"No keywords extracted from: {entry['title'][:50]}")
                        continue
                    
                    # 3. Match against pre-fetched markets with scoring
                    for m in markets_data:
                        # Gamma API returns 'question' field directly
                        market_question = m.get('question', '')
                        if not market_question:
                            continue
                        
                        match_score = self._match_score(keywords, market_question)
                        
                        # Require enough matching keywords for signal quality
                        if match_score >= self.match_threshold:
                            metrics['matches_found'] += 1
                            feed_stats['matches'] += 1
                            
                            # Gamma API uses 'slug' or 'condition_id' for market ID
                            market_slug = m.get('slug', '') or m.get('condition_id', '')
                            
                            # Check for duplicate (same market + same news)
                            alert_combo = (market_slug, entry['link'])
                            if alert_combo in self.seen_alert_combos:
                                logger.debug(f"Skipping duplicate alert: {market_slug[:20]}... + {entry['link'][:50]}...")
                                continue
                            
                            # Run agent analysis to check if news is actually relevant
                            is_relevant = await self._check_news_relevance(entry['title'], market_question, entry['link'])
                            
                            if not is_relevant:
                                logger.debug(f"Agent filtered out irrelevant match: '{entry['title'][:50]}' -> '{market_question[:50]}'")
                                continue
                            
                            logger.info(
                                f"✅ Relevant match (score={match_score}): "
                                f"'{entry['title'][:50]}...' -> '{market_question[:50]}...'"
                            )
                            
                            alert_sent = await self.alert_discord(
                                source, entry['title'], market_question, market_slug
                            )
                            if alert_sent:
                                self.seen_alert_combos.add(alert_combo)
                                metrics['alerts_sent'] += 1
                        elif match_score == 1:
                            # Log weak matches for debugging
                            logger.debug(
                                f"Weak match (score=1, skipped): "
                                f"'{entry['title'][:40]}' vs '{market_question[:40]}'"
                            )
                except Exception as e:
                    logger.debug(f"Entry processing error: {e}")
                    continue
            
            metrics['feed_details'][source] = feed_stats
        
        # Calculate scan duration
        scan_duration = (datetime.now() - scan_start).total_seconds() * 1000  # ms
        
        # Log comprehensive scan summary
        logger.info(
            f"📡 LagHunter Scan #{metrics['scan_id']} complete in {scan_duration:.0f}ms | "
            f"Feeds: {metrics['feeds_fetched']}/{len(self.rss_feeds)} OK | "
            f"Entries: {metrics['total_entries']} total, {metrics['fresh_entries']} fresh, {metrics['already_seen']} seen | "
            f"Markets: {metrics['markets_fetched']} | "
            f"Matches: {metrics['matches_found']} | "
            f"Alerts: {metrics['alerts_sent']}"
        )
        
        # Detailed per-feed logging (debug level)
        for source, stats in metrics['feed_details'].items():
            logger.debug(
                f"  └─ {source}: {stats['total']} entries, {stats['fresh']} fresh, "
                f"{stats['seen']} seen, {stats['matches']} matches"
            )
        
        # Track zero-alert streak and warn if prolonged
        if metrics['alerts_sent'] == 0:
            self.zero_alert_streak += 1
            if self.zero_alert_streak >= 10:  # 10 minutes of silence
                logger.warning(
                    f"⚠️ LagHunter: {self.zero_alert_streak} scans with zero alerts | "
                    f"Last scan: feeds_ok={metrics['feeds_fetched']}/{len(self.rss_feeds)}, "
                    f"markets={metrics['markets_fetched']}, fresh_entries={metrics['fresh_entries']}, "
                    f"matches={metrics['matches_found']}"
                )
                self.zero_alert_streak = 0  # Reset to avoid spam
        else:
            self.zero_alert_streak = 0
        
        # Update global metrics
        from app.core.metrics import metrics as global_metrics, MetricNames
        global_metrics.increment(MetricNames.LAG_HUNTER_SCANS)
        global_metrics.increment(MetricNames.LAG_HUNTER_MATCHES, metrics['matches_found'])
        global_metrics.increment(MetricNames.LAG_HUNTER_ALERTS, metrics['alerts_sent'])
        global_metrics.set_gauge(MetricNames.LAG_HUNTER_ZERO_ALERT_STREAK, self.zero_alert_streak)
        
        # Store summary for debug access
        self.last_scan_summary = metrics

    async def _fetch_rss_async(self, session: aiohttp.ClientSession, source: str, url: str):
        """
        Async RSS parser using aiohttp (replaces blocking feedparser)
        Returns: (source_name, list_of_entries)
        """
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status != 200:
                    return (source, [])
                
                xml_data = await resp.text()
                root = ET.fromstring(xml_data)
                
                entries = []
                # Parse RSS 2.0 or Atom feeds
                for item in root.findall('.//item')[:5]:  # Limit to 5 newest
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    pubdate_elem = item.find('pubDate')
                    
                    if title_elem is not None and link_elem is not None:
                        try:
                            # Parse RFC 822 date format (RSS standard)
                            pub_text = pubdate_elem.text if pubdate_elem is not None else datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')
                            pub_date = datetime.strptime(
                                pub_text,
                                '%a, %d %b %Y %H:%M:%S %z'
                            )
                        except:
                            pub_date = datetime.now(timezone.utc)
                        
                        entries.append({
                            'title': title_elem.text or "",
                            'link': link_elem.text or "",
                            'published': pub_date
                        })
                
                return (source, entries)
        except Exception as e:
            logger.warning(f"RSS Fetch Error [{source}]: {e}")
            return (source, [])
    
    async def _check_news_relevance(self, headline: str, market_question: str, news_link: str) -> bool:
        """
        Use AI agent to check if news is actually relevant to the market.
        Returns True only if news is genuinely relevant and could cause price movement.
        """
        try:
            from datetime import datetime
            
            # Create a simple prompt for relevance check
            prompt = f"""You are a market intelligence analyst. Determine if this news headline is RELEVANT to this prediction market.

NEWS HEADLINE: {headline}
NEWS LINK: {news_link}

PREDICTION MARKET: {market_question}

TODAY'S DATE: {datetime.now().strftime('%B %d, %Y')}

CRITICAL: Only return TRUE if:
1. The news directly relates to the market question (not just mentions same keywords)
2. The news could reasonably cause price movement in this market
3. The news is recent and actionable (not old/outdated information)

Return ONLY valid JSON:
{{
  "is_relevant": true or false,
  "reason": "Brief explanation"
}}

Examples:
- News: "Bitcoin hits $100k" + Market: "Will Bitcoin hit $100k by Dec 31?" → RELEVANT
- News: "MicroStrategy stock drops" + Market: "MicroStrategy sells any Bitcoin in 2025?" → RELEVANT (indirect but related)
- News: "CoinDesk article about STRF credit instrument" + Market: "MicroStrategy sells any Bitcoin in 2025?" → NOT RELEVANT (unrelated topic)
- News: "Bitcoin price discussion" + Market: "Will Ethereum dip to $1,000?" → NOT RELEVANT (different asset)

Respond ONLY with valid JSON. No additional text."""

            response = await self.bot.hydra.generate(prompt)
            
            # Parse JSON response
            import json
            import re
            
            # Try to find JSON
            json_match = re.search(r'\{[^{}]*"is_relevant"[^{}]*\}', response, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    is_relevant = result.get('is_relevant', False)
                    reason = result.get('reason', 'No reason provided')
                    logger.debug(f"Agent relevance check: {is_relevant} - {reason}")
                    return is_relevant
                except json.JSONDecodeError:
                    pass
            
            # Fallback: look for true/false in response
            if 'true' in response.lower() and 'is_relevant' in response.lower():
                return True
            if 'false' in response.lower() and 'is_relevant' in response.lower():
                return False
            
            # Default: parser failure means no source-grounded relevance. Do not spam.
            logger.warning(f"Could not parse agent response for relevance check. Defaulting to reject. Response: {response[:200]}")
            return False
            
        except Exception as e:
            logger.error(f"Agent relevance check failed: {e}")
            # On error, reject; a false positive lag alert is worse than silence.
            return False

    async def alert_discord(self, source, headline, market, market_slug=""):
        """
        Broadcasts lag alerts to ALL configured servers (Multi-Tenant).
        Per SaaS architecture: each server gets alerts in their dedicated Lag Hunter channel.
        Enriches alerts with Vegas odds if mappings exist.
        Returns: True if at least one alert was sent successfully.
        """
        import discord
        from app.core.server_manager import server_manager
        
        # Get all servers that have configured dedicated Lag Hunter channels.
        alert_channels = await server_manager.get_all_lag_hunter_channels()
        
        if not alert_channels:
            logger.warning("No dedicated lag_hunter_channel_id configured; skipping Lag Hunter alert")
            return False
        
        embed = discord.Embed(title="🚨 LAG DETECTED", color=0x00ff00)
        embed.add_field(name="News Source", value=f"{source}: {headline}", inline=False)
        embed.add_field(name="Polymarket Market", value=market, inline=False)
        
        # Try to enrich with Vegas odds if we have a market slug
        vegas_info = await self._fetch_vegas_for_alert(market_slug)
        if vegas_info:
            embed.add_field(name="📊 Cross-Venue Odds", value=vegas_info, inline=False)
            embed.add_field(
                name="Action", 
                value="⚡ **Check for arbitrage:** Compare Polymarket vs Vegas odds above", 
                inline=False
            )
        else:
            embed.add_field(
                name="Action", 
                value="⚡ Check for Price Lag - Potential Arbitrage Opportunity", 
                inline=False
            )
        
        embed.set_footer(text="PolyQuant Lag Hunter • Real-time Market Intelligence")
        
        # Broadcast to all servers
        sent_count = 0
        for guild_id, channel_id in alert_channels:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(embed=embed)
                    sent_count += 1
                else:
                    logger.warning(f"Channel {channel_id} not found for guild {guild_id}")
            except Exception as e:
                logger.error(f"Failed to send alert to guild {guild_id}: {e}")
        
        logger.info(f"📡 Lag alert broadcasted to {sent_count} servers")
        return sent_count > 0
    
    async def _fetch_vegas_for_alert(self, market_slug: str) -> str:
        """
        Fetch Vegas odds for enriching lag alerts.
        Returns formatted string or empty if no mappings.
        """
        if not market_slug:
            return ""
        
        try:
            # Try to extract event slug from market slug
            # Polymarket slugs often follow pattern: event-slug/market-slug or just event-slug
            event_slug = market_slug.split('/')[0] if '/' in market_slug else market_slug
            
            # Look up mappings
            mappings = await market_mapping_service.get_mappings_for_polymarket(event_slug)
            
            if not mappings:
                return ""
            
            # Fetch odds from first mapped venue (keep it concise for Discord embed)
            mapping = mappings[0]
            odds = await bookmaker_client.get_odds(mapping.venue, mapping.venue_market_id)
            
            if not odds:
                return ""
            
            # Format concisely for embed
            lines = [f"**{odds.venue.upper()}:**"]
            for outcome, prob in list(odds.implied_probs.items())[:3]:  # Max 3 outcomes
                lines.append(f"  {outcome}: {prob*100:.1f}%")
            
            return "\n".join(lines)
        
        except Exception as e:
            logger.debug(f"Could not fetch Vegas odds for alert: {e}")
            return ""
    
    async def test_once(self, force_alert: bool = True):
        """
        Admin/debug method: runs one scan iteration without seen_links filter.
        If force_alert=True, sends a synthetic test alert to verify Discord path.
        Returns: dict with scan metrics and test results.
        """
        logger.info("🧪 LagHunter TEST MODE: Running single scan...")
        
        # Temporarily clear seen_links for test
        original_seen = self.seen_links.copy()
        self.seen_links.clear()
        
        try:
            # Run one scan
            await self.scan()
            
            # Force a test alert if requested
            if force_alert:
                logger.info("🧪 Sending synthetic test alert...")
                test_sent = await self.alert_discord(
                    source="TEST",
                    headline="LagHunter Test Alert - System Operational",
                    market="Test Market: Will this alert reach Discord?"
                )
                
                return {
                    'status': 'success',
                    'test_alert_sent': test_sent,
                    'last_scan': self.last_scan_summary
                }
            else:
                return {
                    'status': 'success',
                    'test_alert_sent': False,
                    'last_scan': self.last_scan_summary
                }
        except Exception as e:
            logger.error(f"🧪 Test failed: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e)
            }
        finally:
            # Restore seen_links
            self.seen_links = original_seen
