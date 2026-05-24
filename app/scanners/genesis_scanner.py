"""
GenesisScanner: New Market Discovery Engine
Continuously monitors Polymarket Gamma API for newly created markets and:
1. Posts ALL new markets to the firehose channel (instant discovery)
2. Runs Hydra analysis on high-quality markets
3. Posts high-confidence opportunities to curated channel

PERSISTENCE:
- Loads seen_market_ids from database on startup
- Saves new markets to DB immediately (prevents restart spam)

FILTERING:
- Spam filter: Blocks 15m, 5m, 1h, 4h, up/down price markets
- Variant grouping: Only alerts on primary market per event (highest volume)
- Liquidity check: Skips markets with no/empty prices until they have liquidity
"""
import asyncio
import aiohttp
import json
import logging
import discord
from datetime import datetime, timedelta
from typing import Set, Dict, List, Optional
from app.core.watchdog import watchdog
from app.core.metrics import metrics, MetricNames
from app.core.server_manager import server_manager
from app.core.utils import is_spam_market
from app.core.database import db
from app.core.constants import VALID_CATEGORIES

logger = logging.getLogger("GenesisScanner")

# API endpoint for market discovery
GAMMA_API_BASE = "https://gamma-api.polymarket.com"

# Quality filters - subset of VALID_CATEGORIES for high-priority analysis
HIGH_QUALITY_CATEGORIES = {"Politics", "Crypto", "Sports", "Business", "Science", "Technology"}
MIN_LIQUIDITY = 0  # Markets must have liquidity > $0

# Persistence: How long to remember markets (7 days)
SEEN_MARKETS_RETENTION_DAYS = 7


class GenesisScanner:
    """
    The Market Discovery Engine - Two-phase filtering:
    Phase 1 (Firehose): Post ALL new markets immediately
    Phase 2 (Curator): Analyze quality markets and filter for high-confidence
    
    PERSISTENCE: Loads/saves seen_market_ids from database to survive restarts.
    VARIANT FILTER: Groups markets by event_slug, only alerts on primary.
    LIQUIDITY CHECK: Skips markets with no prices until they have liquidity.
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.seen_market_ids: Set[str] = set()
        self.seen_event_slugs: Set[str] = set()  # For variant deduplication
        self.seen_curated_markets: Set[str] = set()  # Track markets already curated (prevent re-alerting)
        self.pending_markets: Dict[str, Dict] = {}  # Markets waiting for liquidity
        self.scan_count = 0
        self.db_loaded = False
        
        # Performance metrics
        self.markets_discovered = 0
        self.markets_analyzed = 0
        self.alerts_sent = 0
    
    async def start(self):
        """
        Main loop: Continuously poll Gamma API for new markets.
        Multi-tenant: Broadcasts to all servers with configured channels.
        """
        logger.info("🔮 Genesis Scanner: Initializing (Multi-Tenant Mode)...")
        
        # Load seen markets from database (prevents restart spam)
        await self._load_seen_markets_from_db()
        
        logger.info("✅ Genesis Scanner Active - Will broadcast to all configured servers")
        
        error_count = 0
        while True:
            try:
                await self.scan()
                error_count = 0  # Reset on success
            except Exception as e:
                error_count += 1
                logger.error(f"Genesis Scanner Error: {e}", exc_info=True)
                
                # Alert on persistent errors
                if error_count >= 3:
                    await watchdog.alert(
                        "Genesis Scanner",
                        f"Persistent errors (3+ cycles): {e}",
                        "ERROR"
                    )
                    error_count = 0  # Reset to avoid spam
            
            # Poll every 30 seconds (aggressive discovery)
            await asyncio.sleep(30)
    
    async def _load_seen_markets_from_db(self):
        """
        Load previously seen market IDs from database.
        Prevents re-alerting on old markets after bot restart.
        """
        try:
            # Calculate retention cutoff
            cutoff = datetime.utcnow() - timedelta(days=SEEN_MARKETS_RETENTION_DAYS)
            
            # Try to fetch from database
            seen_records = await db.get_seen_markets(cutoff)
            
            if seen_records:
                for record in seen_records:
                    market_id = record.get('market_id')
                    event_slug = record.get('event_slug')
                    if market_id:
                        self.seen_market_ids.add(market_id)
                    if event_slug:
                        self.seen_event_slugs.add(event_slug)
                
                logger.info(f"🔮 Loaded {len(self.seen_market_ids)} seen markets from database")
            else:
                logger.info("🔮 No previous seen markets found (fresh start)")
            
            self.db_loaded = True
        except Exception as e:
            logger.warning(f"⚠️ Could not load seen markets from DB: {e}")
            logger.warning("🔮 Starting fresh (may re-alert on recent markets)")
            self.db_loaded = True
    
    async def _save_seen_market_to_db(self, market_id: str, event_slug: str):
        """
        Save a newly seen market to database for persistence.
        """
        try:
            await db.save_seen_market(market_id, event_slug)
        except Exception as e:
            logger.debug(f"Could not save seen market to DB: {e}")
    
    async def scan(self):
        """
        Single scan iteration:
        1. Fetch latest markets from Gamma API
        2. Filter for new markets (unseen)
        3. Apply variant deduplication (one alert per event)
        4. Check liquidity (skip if no prices)
        5. Post to firehose immediately
        6. Analyze high-quality markets with Hydra
        7. Post high-confidence to curated channel
        """
        scan_start = datetime.now()
        self.scan_count += 1
        
        # Fetch new markets from API
        markets = await self._fetch_new_markets()
        
        if not markets:
            logger.debug(f"Genesis Scan #{self.scan_count}: No new markets found")
            return
        
        logger.info(f"🔮 Genesis Scan #{self.scan_count}: Found {len(markets)} markets from API")
        logger.info(f"📋 Currently tracking {len(self.seen_market_ids)} seen markets, {len(self.seen_event_slugs)} seen events")
        
        # Track stats
        new_count = 0
        quality_count = 0
        analyzed_count = 0
        curated_count = 0
        skipped_spam = 0
        skipped_variant = 0
        skipped_no_liquidity = 0
        skipped_already_seen = 0
        
        # Fetch channel lists once per scan to avoid repeated DB hits
        firehose_channels = await server_manager.get_all_new_markets_channels()
        curated_channels = await server_manager.get_all_curated_markets_channels()
        
        logger.info(f"📢 Broadcasting to {len(firehose_channels)} firehose channels, {len(curated_channels)} curated channels")
        
        if not firehose_channels:
            logger.warning("⚠️ No firehose channels configured! Run /setup to configure new_markets_channel")
            return
        if not curated_channels:
            logger.warning("No dedicated curated_markets_channel_id configured; skipping Genesis curated alerts")
        
        # Group markets by event_slug to prevent duplicate alerts
        # One event = one alert (prevents 15 pings for FIFA World Cup Draw with 15 outcomes)
        event_markets = self._group_markets_by_event(markets)
        
        # Process each event once (only alert on first/primary market)
        for event_key, markets_in_event in event_markets.items():
            # Determine if this is an event (has event_slug) or standalone market
            event_slug = markets_in_event[0].get('event_slug', '') if markets_in_event else ''
            is_event = bool(event_slug)
            
            # Skip if we've already alerted on this event
            if is_event and event_slug in self.seen_event_slugs:
                skipped_already_seen += len(markets_in_event)
                continue
            
            # Pick primary market (first one, or highest volume if available)
            primary_market = self._get_primary_market(markets_in_event)
            if not primary_market:
                continue
            
            market_id = primary_market.get('id')
            if not market_id:
                continue
            
            # For standalone markets (no event_slug), check if already seen
            if not is_event and market_id in self.seen_market_ids:
                skipped_already_seen += 1
                continue
            
            # Extract basic info for logging
            question = primary_market.get('question', '')
            event_title = primary_market.get('event_title', '')
            category = primary_market.get('category', 'Unknown')
            
            # FILTER: ETH/BTC/SOL up/down price markets - BLOCK ALL (any timeframe - they're spam)
            # Blocks all crypto up/down markets like "BTC up or down", not long-term like "Will Bitcoin hit $100k?"
            if self._is_crypto_price_market(question, event_title):
                skipped_spam += 1
                logger.debug(f"Filtered crypto up/down market: {question[:50]}")
                # Mark event as seen so we don't retry
                if is_event:
                    self.seen_event_slugs.add(event_slug)
                for m in markets_in_event:
                    self.seen_market_ids.add(m.get('id'))
                    await self._save_seen_market_to_db(m.get('id'), event_slug or '')
                continue
            
            logger.info(f"🆕 NEW MARKET DISCOVERED: {question[:60]}... | Category: {category} | Event: {event_title[:40]}")
            
            # PHASE 1: Firehose - Post ONE market per event (even $0 volume)
            # CRITICAL: Only mark as seen if alert is successfully sent
            alert_sent = await self._post_to_firehose(primary_market, firehose_channels)
            
            if alert_sent:
                # ✅ Alert sent successfully - mark event/market and all related markets as seen
                if is_event:
                    self.seen_event_slugs.add(event_slug)
                for m in markets_in_event:
                    self.seen_market_ids.add(m.get('id'))
                    await self._save_seen_market_to_db(m.get('id'), event_slug or '')
                new_count += 1
                self.markets_discovered += 1
            else:
                # ❌ Alert failed - queue for retry, don't mark as seen
                self.pending_markets[market_id] = primary_market
                logger.warning(f"⚠️ Alert failed for {question[:50]}... - queued for retry")
                continue
            
            # PHASE 2: Curator - Run Judge analysis (check news credibility, require 15% edge)
            # For multi-outcome events, pass all markets so Judge can see all outcomes
            # Skip if already curated (prevent re-alerting on old markets)
            if market_id in self.seen_curated_markets:
                logger.debug(f"Skipping already-curated market: {market_id}")
                continue
            
            try:
                # Check if this is multi-outcome event (has multiple markets/outcomes)
                is_multi_outcome = is_event and len(markets_in_event) > 1
                
                analysis = await self._analyze_with_judge(
                    primary_market, 
                    all_markets_in_event=markets_in_event if is_multi_outcome else None
                )
                analyzed_count += 1
                
                # Require 15% edge via credibility (confidence >65% or <35%)
                if analysis:
                    confidence = analysis.get('confidence', 50)
                    has_edge = self._has_15pct_edge(analysis)
                    logger.debug(f"Market {market_id[:8]}... analysis: confidence={confidence}, has_edge={has_edge}")
                    
                    if has_edge:
                        # Post to curated channel - only strong edges
                        await self._post_to_curated(
                            primary_market, 
                            analysis, 
                            curated_channels, 
                            is_multi_outcome=is_multi_outcome,
                            all_markets_in_event=markets_in_event if is_multi_outcome else None
                        )
                        # Mark as curated to prevent re-alerting
                        self.seen_curated_markets.add(market_id)
                        curated_count += 1
                        quality_count += 1
                    else:
                        logger.debug(f"Market {market_id[:8]}... skipped: confidence {confidence} doesn't meet 15% edge threshold")
                else:
                    logger.debug(f"Market {market_id[:8]}... skipped: no analysis returned")
            
            except Exception as e:
                logger.error(f"Analysis failed for market {market_id}: {e}")
        
        # Retry pending markets (those that failed to send before)
        await self._retry_pending_markets(firehose_channels, curated_channels)
        
        # Log scan results
        scan_duration = (datetime.now() - scan_start).total_seconds() * 1000
        logger.info(
            f"🔮 Genesis Scan #{self.scan_count} complete in {scan_duration:.0f}ms | "
            f"Fetched: {len(markets)} | Already Seen: {skipped_already_seen} | "
            f"New: {new_count} | Quality: {quality_count} | "
            f"Analyzed: {analyzed_count} | Curated: {curated_count} | "
            f"Filtered: spam={skipped_spam}, variant={skipped_variant}, no_liq={skipped_no_liquidity}"
        )
        
        # Update metrics
        metrics.increment(MetricNames.GENESIS_SCANS)
        metrics.increment(MetricNames.GENESIS_MARKETS_DISCOVERED, new_count)
        metrics.increment(MetricNames.GENESIS_MARKETS_ANALYZED, analyzed_count)
        metrics.increment(MetricNames.GENESIS_CURATED_ALERTS, curated_count)
    
    def _group_markets_by_event(self, markets: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group markets by event_slug for deduplication.
        Markets without event_slug are treated as standalone (use market_id as key).
        Returns dict: {event_slug: [market1, market2, ...]} or {market_id: [market]}
        """
        grouped = {}
        for market in markets:
            event_slug = market.get('event_slug', '')
            market_id = market.get('id', '')
            
            # Use event_slug if available, otherwise use market_id for standalone markets
            key = event_slug if event_slug else (market_id if market_id else 'unknown')
            
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(market)
        return grouped
    
    def _get_primary_market(self, markets: List[Dict]) -> Optional[Dict]:
        """
        Get the primary market from a list of variants.
        Primary = highest volume, or first if all zero.
        """
        if not markets:
            return None
        
        # Sort by volume (descending)
        sorted_markets = sorted(
            markets, 
            key=lambda m: self._safe_float(m.get('volume', 0)), 
            reverse=True
        )
        return sorted_markets[0]
    
    def _normalize_outcome_prices(self, prices) -> list:
        """
        Convert raw outcomePrices/outcomes (list or JSON string) into a list.
        CRITICAL: Polymarket API returns these as JSON strings, not arrays.
        """
        if isinstance(prices, list):
            return prices
        if isinstance(prices, str):
            try:
                parsed = json.loads(prices)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                logger.debug(f"Could not parse JSON string: {prices[:100]}")
        return []
    
    def _extract_yes_price(self, market: Dict) -> Optional[float]:
        """
        Extract YES price dynamically by checking outcomes list.
        CRITICAL: Don't assume index 1 is always YES.
        """
        outcome_prices = self._normalize_outcome_prices(market.get('outcomePrices'))
        if not outcome_prices or len(outcome_prices) < 2:
            return None
        
        # Normalize outcomes (can also be a JSON string)
        outcomes_raw = market.get('outcomes', [])
        outcomes = self._normalize_outcome_prices(outcomes_raw) if outcomes_raw else []
        
        yes_index = None
        if isinstance(outcomes, list) and outcomes:
            for idx, outcome in enumerate(outcomes):
                label = str(outcome).strip().lower()
                if label == "yes":
                    yes_index = idx
                    break
        
        # Fallback: Gamma normally returns [Yes, No] when labels are missing.
        if yes_index is None:
            yes_index = 0
        
        if yes_index >= len(outcome_prices):
            logger.debug(f"YES index {yes_index} out of range for {market.get('question', 'Unknown')}")
            return None
        
        return self._safe_float(outcome_prices[yes_index], default=None)
    
    def _has_valid_prices(self, market: Dict) -> bool:
        """
        Check if market has valid prices (not empty/unknown).
        Returns False if prices are missing or invalid.
        CRITICAL: Must normalize JSON strings first.
        """
        outcome_prices = self._normalize_outcome_prices(market.get('outcomePrices'))
        
        # Must have at least 2 prices (YES/NO)
        if not outcome_prices or len(outcome_prices) < 2:
            question = market.get('question', 'Unknown')
            raw_prices = market.get('outcomePrices')
            logger.debug(f"❌ Invalid prices for '{question[:50]}...': raw={raw_prices}, normalized={outcome_prices}")
            return False
        
        # Check that prices are not null/empty strings
        for price in outcome_prices:
            if price is None or price == '' or price == 'null':
                return False
            
            # Try to parse as float
            try:
                parsed = self._safe_float(price, None)
                if parsed is None or parsed <= 0:
                    return False
            except:
                return False
        
        return True
    
    async def _retry_pending_markets(self, firehose_channels, curated_channels):
        """
        Retry markets that failed to send before.
        Now processes them even if they have $0 volume.
        """
        if not self.pending_markets:
            return
        
        processed = []
        
        for market_id, market in list(self.pending_markets.items()):
            question = market.get('question', '')
            logger.debug(f"Retrying pending market: {question[:50]}")
            
            # Try to post to firehose (even with $0 volume)
            alert_sent = await self._post_to_firehose(market, firehose_channels)
            
            if alert_sent:
                # Success - mark as seen and process for curated
                event_slug = market.get('event_slug', '')
                self.seen_market_ids.add(market_id)
                await self._save_seen_market_to_db(market_id, event_slug)
                self.markets_discovered += 1
                
                # Also run through Hydra for curated (skip if already curated)
                if market_id not in self.seen_curated_markets:
                    try:
                        analysis = await self._analyze_with_judge(market)
                        if analysis and self._has_15pct_edge(analysis):
                            await self._post_to_curated(market, analysis, curated_channels, is_multi_outcome=False, all_markets_in_event=None)
                            self.seen_curated_markets.add(market_id)
                    except Exception as e:
                        logger.debug(f"Curated analysis failed for pending market: {e}")
                
                processed.append(market_id)
        
        # Remove processed markets from pending
        for market_id in processed:
            del self.pending_markets[market_id]
        
        # Clean up old pending markets (older than 1 hour)
        if len(self.pending_markets) > 100:
            # Keep only the newest 50
            sorted_pending = sorted(
                self.pending_markets.items(),
                key=lambda x: x[1].get('created_at', ''),
                reverse=True
            )[:50]
            self.pending_markets = dict(sorted_pending)
    
    async def _fetch_new_markets(self) -> List[Dict]:
        """
        Fetch latest markets from Polymarket Gamma API.
        Sorted by creation date (newest first).
        CRITICAL: Increased limit to catch all new markets.
        """
        url = f"{GAMMA_API_BASE}/events"
        params = {
            'closed': 'false',  # Only active markets
            'order': 'createdAt',
            'ascending': 'false',  # Newest first
            'limit': 100  # Increased to catch more new markets
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.error(f"Gamma API returned {resp.status}")
                        return []
                    
                    events = await resp.json()
                    logger.debug(f"📥 Fetched {len(events)} events from Gamma API")
                    
                    # Flatten events into markets
                    markets = []
                    for event in events:
                        # Each event can have multiple markets
                        event_markets = event.get('markets', [])
                        for market in event_markets:
                            # Enrich market with event-level data
                            market['event_title'] = event.get('title', '')
                            market['event_slug'] = event.get('slug', '')
                            market['category'] = event.get('category', 'Other')
                            market['created_at'] = event.get('createdAt', '')
                            markets.append(market)
                    
                    logger.debug(f"📊 Flattened into {len(markets)} individual markets")
                    return markets
        
        except asyncio.TimeoutError:
            logger.warning("Gamma API timeout")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return []
    
    def _is_high_quality(self, market: Dict) -> bool:
        """
        DEPRECATED: No longer used - we analyze ALL markets for curated.
        Kept for backwards compatibility.
        """
        return True  # All markets are analyzed now
    
    async def _analyze_with_judge(self, market: Dict, all_markets_in_event: List[Dict] = None) -> Optional[Dict]:
        """
        Run simplified Judge analysis on a market with web search.
        For multi-outcome markets: shows all outcomes and recommends specific one.
        Returns analysis dict with confidence score and recommended outcome (if multi-outcome).
        """
        try:
            from app.Prompts.judge import get_judge_simple_prompt
            from app.core.search_router import SearchRouter
            from datetime import datetime
            
            question = market.get('question', '')
            event_title = market.get('event_title', '')
            category = market.get('category', '')
            volume = self._safe_float(market.get('volume', 0))
            
            # Check if this is multi-outcome event
            is_multi_outcome = all_markets_in_event and len(all_markets_in_event) > 1
            
            # Format market data for Judge
            if is_multi_outcome:
                # Multi-outcome: format all outcomes with prices
                outcomes_data = self._format_all_outcomes(all_markets_in_event)
                odds_text = outcomes_data['formatted_outcomes']
            else:
                # Binary market: simple YES/NO odds
                yes_price = self._extract_yes_price(market)
                if yes_price is None:
                    odds_text = "YES: 50% | NO: 50%"  # Default for $0 volume
                else:
                    no_price = 1.0 - yes_price
                    odds_text = f"YES: {yes_price*100:.0f}%, NO: {no_price*100:.0f}%"
                outcomes_data = None
            
            # Perform web search for recent news/events related to this market
            search_query = f"{event_title} {question}" if event_title else question
            search_results = ""
            try:
                router = SearchRouter()
                search_data = await router.search(search_query, max_results=5)
                if search_data:
                    search_results = router.deep_search(search_query, max_results=5)
                    logger.debug(f"Web search found {len(search_data)} results for: {search_query[:50]}")
                else:
                    logger.debug(f"No search results for: {search_query[:50]}")
            except Exception as e:
                logger.warning(f"Web search failed for curated analysis: {e}")
                search_results = ""
            
            # Build simplified Judge prompt (checks news, credibility, uses web search, no full agent council)
            prompt = get_judge_simple_prompt(
                question=question,
                event_title=event_title,
                category=category,
                volume=volume,
                current_odds=odds_text,
                today_date=datetime.now().strftime('%B %d, %Y'),
                search_results=search_results,
                is_multi_outcome=is_multi_outcome,
                outcomes_data=outcomes_data
            )
            
            # Use Hydra (Judge-only, no 5-agent council)
            self.markets_analyzed += 1
            response = await self.bot.hydra.generate(prompt)
            
            # Parse response - expect JSON with confidence and rationale
            import json
            import re
            
            # Try to extract JSON from response (handle multi-outcome with recommended_outcome)
            json_pattern = r'\{[^{}]*(?:"confidence"|"recommended_outcome")[^{}]*\}'
            json_match = re.search(json_pattern, response, re.DOTALL)
            
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    analysis = {
                        'confidence': result.get('confidence', 50),
                        'rationale': result.get('rationale', 'No rationale provided'),
                        'credibility_score': result.get('credibility_score', 50)
                    }
                    
                    # For multi-outcome, include recommended outcome
                    if is_multi_outcome:
                        recommended = result.get('recommended_outcome', '')
                        if recommended:
                            analysis['recommended_outcome'] = recommended
                    
                    return analysis
                except json.JSONDecodeError:
                    pass
            
            # Fallback: Try to parse CONFIDENCE: format
            if "CONFIDENCE:" in response:
                parts = response.split("|")
                confidence_part = parts[0].strip()
                rationale_part = parts[1].strip() if len(parts) > 1 else ""
                
                confidence_str = confidence_part.replace("CONFIDENCE:", "").strip()
                try:
                    confidence = int(confidence_str)
                except ValueError:
                    match = re.search(r'\d+', confidence_str)
                    if match:
                        confidence = int(match.group())
                    else:
                        logger.warning(f"Could not parse confidence from response: {response[:200]}")
                        return None
                
                rationale = rationale_part.replace("RATIONALE:", "").strip()
                
                logger.debug(f"✅ Parsed Judge analysis from CONFIDENCE format: confidence={confidence}")
                return {
                    'confidence': confidence,
                    'rationale': rationale,
                    'credibility_score': confidence
                }
            
            logger.warning(f"⚠️ Could not parse Judge response. Preview: {response[:300]}")
            return None
        
        except Exception as e:
            logger.error(f"Judge analysis error: {e}")
            return None
    
    def _format_all_outcomes(self, markets: List[Dict]) -> Dict:
        """
        Format all outcomes from markets list for multi-outcome events.
        Returns dict with formatted_outcomes text and outcomes_list.
        """
        outcomes = []
        for market in markets:
            yes_price = self._extract_yes_price(market)
            volume = self._safe_float(market.get('volume', 0))
            
            # Skip if no price available
            if yes_price is None:
                continue
            
            # Extract outcome name - try multiple methods
            name = None
            
            # Method 1: Use groupItemTitle if available (cleanest)
            name = market.get('groupItemTitle', '').strip()
            
            # Method 2: Try extraction function
            if not name:
                name = self._extract_outcome_name(market)
            
            # Method 3: Fallback to question with basic cleanup
            if not name:
                question = market.get('question', '').strip()
                if question:
                    # Remove common patterns but keep the core
                    name = question.replace('Will ', '').replace('?', '').strip()
                    # If it's too long, truncate
                    if len(name) > 50:
                        name = name[:50]
            
            # Final fallback: use market ID or index
            if not name:
                name = f"Outcome {len(outcomes) + 1}"
            
            outcomes.append({
                'name': name.strip(),
                'price': yes_price,
                'volume': volume,
                'market': market  # Keep reference for later
            })
        
        if not outcomes:
            return {
                'formatted_outcomes': "No outcomes found",
                'outcomes_list': []
            }
        
        # Sort by price (highest first)
        outcomes.sort(key=lambda x: x['price'], reverse=True)
        
        # Format as text for Judge
        lines = []
        lines.append("ALL AVAILABLE OUTCOMES (Ranked by Current Price):")
        lines.append("-" * 60)
        
        medals = ["🥇", "🥈", "🥉"]
        for idx, outcome in enumerate(outcomes, 1):
            badge = medals[idx-1] if idx <= len(medals) else f"{idx}."
            price_pct = outcome['price'] * 100
            price_cents = outcome['price'] * 100
            price_text = f"{price_cents:.0f}¢" if price_cents >= 1 else "<1¢"
            
            vol_text = f" (${outcome['volume']:,.0f})" if outcome['volume'] > 0 else " ($0)"
            lines.append(f"{badge} {outcome['name']}: {price_text} ({price_pct:.0f}%){vol_text}")
        
        lines.append("-" * 60)
        lines.append("⚠️  IMPORTANT: Check current prices - if outcome is already at 90%+, it's likely overpriced!")
        
        return {
            'formatted_outcomes': "\n".join(lines),
            'outcomes_list': outcomes
        }
    
    def _has_15pct_edge(self, analysis: Dict) -> bool:
        """
        Check if market has at least 15% edge via credibility.
        Criteria: Confidence > 65% OR < 35% (15% edge from neutral 50%)
        """
        confidence = analysis.get('confidence', 50)
        return confidence > 65 or confidence < 35
    
    def _is_crypto_price_market(self, question: str, event_title: str) -> bool:
        """
        Check if this is a crypto UP/DOWN price prediction market (spam style).
        Only matches markets like "BTC up or down in 5m?", not "Will Bitcoin hit $100k by 2025?".
        """
        text = (question + " " + event_title).lower()
        crypto_keywords = ["eth", "ethereum", "btc", "bitcoin", "sol", "solana", "xrp", "ripple"]
        
        # Only match UP/DOWN price prediction pattern (the spam indicator)
        up_down_patterns = [
            "up or down", "up/down", "updown",
            "going up or down", "up or down in",
            "price up or down"
        ]
        
        has_crypto = any(crypto in text for crypto in crypto_keywords)
        has_up_down = any(pattern in text for pattern in up_down_patterns)
        
        # Must have BOTH crypto AND up/down pattern to be considered a spam price market
        return has_crypto and has_up_down
    
    def _is_multi_outcome_market(self, market: Dict) -> bool:
        """
        Check if market has multiple outcomes (>2 outcomes = multi-outcome).
        """
        outcomes = self._normalize_outcome_prices(market.get('outcomes', []))
        outcome_prices = self._normalize_outcome_prices(market.get('outcomePrices', []))
        
        # If we have outcomes list, check count
        if outcomes and len(outcomes) > 2:
            return True
        
        # If we have outcome prices, check count
        if outcome_prices and len(outcome_prices) > 2:
            return True
        
        return False
    
    async def _post_to_firehose(self, market: Dict, firehose_channels) -> bool:
        """
        Post a new market to ALL configured firehose channels (Multi-Tenant).
        Broadcasts to each server that has set a new_markets_channel_id.
        
        Returns:
            bool: True if alert was sent to at least one server, False otherwise
        """
        # Get all servers with firehose channels configured
        if not firehose_channels:
            # No servers configured - log once per scan
            if self.scan_count % 10 == 1:  # Log every 10 scans
                logger.debug("No servers configured for new markets alerts")
            return False
        
        try:
            # Extract market data
            event_title = market.get('event_title', 'Unknown Event')
            question = market.get('question', 'Unknown')
            category = market.get('category', 'Other')
            volume = self._safe_float(market.get('volume', 0))
            event_slug = market.get('event_slug', '')
            
            # SPAM GUARD: Filter ALL crypto up/down price markets (BLOCK ALL - they're spam)
            if self._is_crypto_price_market(question, event_title):
                logger.debug(f"Filtered crypto up/down market in firehose: {question[:50]}")
                return False
            
            # Get current odds (allow $0 volume markets - show 50/50 if no prices)
            yes_price = self._extract_yes_price(market)
            if yes_price is None:
                # No liquidity yet - show 50/50 as placeholder
                odds_text = "YES: 50% | NO: 50%"
            else:
                no_price = 1.0 - yes_price  # NO price is always inverse of YES in binary markets
                odds_text = f"YES: {yes_price*100:.0f}% | NO: {no_price*100:.0f}%"
            
            # Market URL
            market_url = f"https://polymarket.com/event/{event_slug}" if event_slug else ""
            
            # Build embed once (reused for all servers)
            embed = discord.Embed(
                title="🆕 NEW MARKET DETECTED",
                description=f"**{event_title}**\n{question}",
                color=0x00bfff,
                url=market_url if market_url else None
            )
            
            embed.add_field(name="Category", value=category, inline=True)
            embed.add_field(name="Volume", value=f"${volume:,.0f}", inline=True)
            embed.add_field(name="Current Odds", value=odds_text, inline=False)
            
            embed.set_footer(text="PolyQuant Genesis Scanner • New Market Discovery")
            embed.timestamp = datetime.utcnow()
            
            # Broadcast to servers (with per-server filtering)
            sent_count = 0
            for item in firehose_channels:
                # Handle both old format (guild_id, channel_id) and new format (guild_id, channel_id, filters)
                if len(item) == 3:
                    guild_id, channel_id, filters = item
                else:
                    guild_id, channel_id = item
                    filters = None
                
                try:
                    # Apply per-server category filter (case-sensitive matching)
                    if filters:
                        # Parse comma-separated filters (case-sensitive)
                        allowed_categories = [f.strip() for f in filters.split(',')]
                        if category not in allowed_categories:
                            logger.debug(f"Filtered {category} market for guild {guild_id} (allowed: {allowed_categories})")
                            continue
                    
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send(embed=embed)
                        sent_count += 1
                        logger.info(f"✅ Sent alert to guild {guild_id} (channel {channel_id})")
                    else:
                        logger.warning(f"⚠️ Channel {channel_id} not found for guild {guild_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to send firehose alert to guild {guild_id}: {e}")
            
            if sent_count > 0:
                self.alerts_sent += 1
                logger.info(f"📢 Market alert broadcasted to {sent_count} server(s): {question[:50]}...")
                return True  # ✅ Success!
            else:
                logger.warning(f"⚠️ Market not sent to any servers (category filters or channel not found): {question[:50]}...")
                return False  # ❌ No alerts sent
        
        except Exception as e:
            logger.error(f"Failed to build firehose embed: {e}")
            return False  # ❌ Exception occurred
    
    async def _post_to_curated(self, market: Dict, analysis: Dict, curated_channels, is_multi_outcome: bool = False, all_markets_in_event: List[Dict] = None):
        """
        Post a high-confidence market to ALL configured curated channels (Multi-Tenant).
        Broadcasts to each server that has set a curated_markets_channel_id.
        For multi-outcome markets, finds the specific market matching recommended outcome and provides direct link.
        """
        # Get all servers with curated channels configured
        if not curated_channels:
            logger.warning("No dedicated curated_markets_channel_id configured; skipping Genesis curated alert")
            return
        
        try:
            # Build detailed embed (reused for all servers)
            event_title = market.get('event_title', 'Unknown Event')
            question = market.get('question', 'Unknown')
            category = market.get('category', 'Other')
            volume = self._safe_float(market.get('volume', 0))
            event_slug = market.get('event_slug', '')
            
            confidence = analysis.get('confidence', 0)
            rationale = analysis.get('rationale', 'No rationale provided')
            recommended_outcome = analysis.get('recommended_outcome', '')
            
            # For multi-outcome markets, find the specific market matching recommended outcome
            specific_market_url = None
            recommended_market = None
            if is_multi_outcome and recommended_outcome and recommended_outcome != 'HOLD' and all_markets_in_event:
                recommended_market = self._find_market_by_outcome(all_markets_in_event, recommended_outcome)
                if recommended_market:
                    market_slug = recommended_market.get('slug', '')
                    if market_slug:
                        specific_market_url = f"https://polymarket.com/event/{event_slug}?outcome={market_slug}"
                    else:
                        # Fallback to event URL
                        specific_market_url = f"https://polymarket.com/event/{event_slug}" if event_slug else ""
                else:
                    # Fallback to event URL if can't find specific market
                    specific_market_url = f"https://polymarket.com/event/{event_slug}" if event_slug else ""
            
            # Get current odds (for multi-outcome, show recommended outcome's price)
            market_to_check = recommended_market if (is_multi_outcome and recommended_market) else market
            is_limit_market = self._is_limit_market(market_to_check)
            
            # Calculate profit potential (ROI) and determine bet type
            profit_info = None
            bet_type_label = ""
            
            if is_multi_outcome and recommended_market:
                yes_price = self._extract_yes_price(recommended_market)
                if yes_price is None:
                    odds_text = "YES: 50% | NO: 50%"
                else:
                    no_price = 1.0 - yes_price
                    odds_text = f"YES: {yes_price*100:.1f}% | NO: {no_price*100:.1f}%"
                    
                    # Calculate profit potential (ROI) - if YES wins, profit = (1 - yes_price) / yes_price
                    # Example: YES at 92¢ = 8¢ profit per $1 bet = 8.7% ROI
                    if yes_price > 0 and yes_price < 1:
                        roi_yes = ((1.0 - yes_price) / yes_price) * 100
                        roi_no = ((1.0 - no_price) / no_price) * 100 if no_price > 0 else 0
                        
                        # Determine if this is a "safe bet" (high confidence, high price, low profit)
                        is_safe_bet = confidence > 65 and yes_price > 0.85
                        
                        profit_info = {
                            'yes_price': yes_price,
                            'no_price': no_price,
                            'roi_yes': roi_yes,
                            'roi_no': roi_no,
                            'is_safe_bet': is_safe_bet
                        }
                        
                        if is_safe_bet:
                            bet_type_label = "🛡️ Safe Bet (Low Profit)"
                    
                    # Only show avg price warning for limit markets (not regular YES/NO % markets)
                    if is_limit_market and volume < 100:
                        odds_text += f"\n⚠️ Low liquidity (${volume:,.0f}) - Check **Avg. Price** before trading!"
            else:
                yes_price = self._extract_yes_price(market)
                if yes_price is None:
                    odds_text = "YES: 50% | NO: 50%"
                else:
                    no_price = 1.0 - yes_price
                    odds_text = f"YES: {yes_price*100:.1f}% | NO: {no_price*100:.1f}%"
                    
                    # Calculate profit potential (ROI)
                    if yes_price > 0 and yes_price < 1:
                        roi_yes = ((1.0 - yes_price) / yes_price) * 100
                        roi_no = ((1.0 - no_price) / no_price) * 100 if no_price > 0 else 0
                        
                        is_safe_bet = confidence > 65 and yes_price > 0.85
                        
                        profit_info = {
                            'yes_price': yes_price,
                            'no_price': no_price,
                            'roi_yes': roi_yes,
                            'roi_no': roi_no,
                            'is_safe_bet': is_safe_bet
                        }
                        
                        if is_safe_bet:
                            bet_type_label = "🛡️ Safe Bet (Low Profit)"
                    
                    # Only show avg price warning for limit markets (not regular YES/NO % markets)
                    if is_limit_market and volume < 100:
                        odds_text += f"\n⚠️ Low liquidity (${volume:,.0f}) - Check **Avg. Price** before trading!"
            
            # Market URL (use specific market URL for multi-outcome, otherwise event URL)
            market_url = specific_market_url or (f"https://polymarket.com/event/{event_slug}" if event_slug else "")
            
            # Determine color and label based on confidence (15% edge threshold)
            if confidence > 65:
                color = 0x00ff00  # Green for strong edge
                confidence_label = "🚨 CURATED ALPHA OPPORTUNITY"
            else:  # < 35
                color = 0xff6600  # Orange for contrarian play
                confidence_label = "🚨 CONTRARIAN ALPHA OPPORTUNITY"
            
            embed = discord.Embed(
                title=confidence_label,
                description=f"**{event_title}**\n{question}",
                color=color,
                url=market_url if market_url else None
            )
            
            embed.add_field(name="Category", value=category, inline=True)
            embed.add_field(name="Volume", value=f"${volume:,.0f}", inline=True)
            embed.add_field(name="Hydra Confidence", value=f"{confidence}%", inline=True)
            
            # For multi-outcome markets, show recommended outcome with direct link
            # Make it crystal clear WHAT to bet on
            if is_multi_outcome and recommended_outcome and recommended_outcome != 'HOLD':
                outcome_display = recommended_outcome.replace('_', ' ').title()
                
                # Expand abbreviations for clarity (e.g., "O/U 2.5" -> "Over/Under 2.5 maps")
                outcome_display_expanded = self._expand_outcome_abbreviation(outcome_display, event_title, question)
                
                # Clear betting instruction - what exactly to bet on
                outcome_text = f"**Bet: {outcome_display_expanded}**\n"
                
                if specific_market_url:
                    outcome_text += f"👆 [Click here to place your bet]({specific_market_url})"
                else:
                    outcome_text += "👆 Click the market link above to place your bet"
                
                embed.add_field(
                    name="🎯 What to Bet", 
                    value=outcome_text, 
                    inline=False
                )
            
            # Show current odds (simplified - no detailed profit calculations)
            embed.add_field(name="Current Odds", value=odds_text, inline=False)
            embed.add_field(name="Analysis", value=rationale, inline=False)
            
            embed.set_footer(text="PolyQuant Hydra Curator • High-Confidence Picks")
            embed.timestamp = datetime.utcnow()
            
            # Broadcast to all configured servers
            sent_count = 0
            for guild_id, channel_id in curated_channels:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send(embed=embed)
                        sent_count += 1
                    else:
                        logger.warning(f"Channel {channel_id} not found for guild {guild_id}")
                except Exception as e:
                    logger.error(f"Failed to send curated alert to guild {guild_id}: {e}")
            
            if sent_count > 0:
                outcome_text = f" → {recommended_outcome.replace('_', ' ').title()}" if (is_multi_outcome and recommended_outcome) else ""
                logger.info(f"🚨 Curated alert broadcasted to {sent_count} servers: {question[:50]}... (Confidence: {confidence}%){outcome_text}")
        
        except Exception as e:
            logger.error(f"Failed to build curated embed: {e}")
    
    def _extract_outcome_name(self, market: Dict) -> Optional[str]:
        """
        Extract clean outcome name from market.
        For "Will Broadcom say 'Organic'?" → returns "Organic"
        For "Will MOUZ win?" → returns "MOUZ"
        For "O/U 2.5" → returns "O/U 2.5"
        """
        # Prefer groupItemTitle (cleanest - e.g., "Organic", "MOUZ", "O/U 2.5")
        name = market.get('groupItemTitle', '').strip()
        if name:
            return name
        
        # Fallback: extract from question
        question = market.get('question', '').strip()
        if not question:
            return None
        
        # Try to extract quoted part (e.g., "Will X say 'Organic'?" → "Organic")
        import re
        quoted_match = re.search(r"['\"]([^'\"]+)['\"]", question)
        if quoted_match:
            return quoted_match.group(1)
        
        # Try to extract after "say" or "mention" (e.g., "Will Broadcom say Organic?" → "Organic")
        say_match = re.search(r"(?:say|mention)\s+(?:['\"])?([^?'\"]+)(?:['\"])?", question, re.IGNORECASE)
        if say_match:
            return say_match.group(1).strip()
        
        # Try to extract team/entity name before "win" (e.g., "Will MOUZ win?" → "MOUZ")
        win_match = re.search(r"Will\s+([A-Z][A-Z0-9\s]+?)\s+win", question, re.IGNORECASE)
        if win_match:
            return win_match.group(1).strip()
        
        # Try to extract after "Will" and before "?" (e.g., "Will X happen?" → "X")
        will_match = re.search(r"Will\s+(.+?)\s*\?", question, re.IGNORECASE)
        if will_match:
            name = will_match.group(1).strip()
            # Remove common patterns
            name = re.sub(r'\s+(?:say|mention|win|happen)', '', name, flags=re.IGNORECASE)
            if name:
                return name
        
        # Last resort: remove common patterns
        name = question.replace('Will ', '').replace('?', '').replace(' win', '').strip()
        # Remove company/entity name if present (e.g., "Broadcom say Organic" → "Organic")
        name = re.sub(r'^[A-Z][a-z]+\s+(?:say|mention)\s+', '', name, flags=re.IGNORECASE)
        
        return name if name else None
    
    def _find_market_by_outcome(self, markets: List[Dict], outcome_name: str) -> Optional[Dict]:
        """
        Find the specific market matching the recommended outcome name.
        Matches by groupItemTitle or question text.
        """
        # Normalize outcome name for matching
        outcome_normalized = outcome_name.replace('_', ' ').lower().strip()
        
        for market in markets:
            # Check groupItemTitle (common for multi-outcome markets)
            group_title = market.get('groupItemTitle', '').lower().strip()
            if group_title and outcome_normalized in group_title or group_title in outcome_normalized:
                return market
            
            # Check extracted outcome name
            extracted_name = self._extract_outcome_name(market)
            if extracted_name and outcome_normalized in extracted_name.lower():
                return market
            
            # Check question text
            question = market.get('question', '').lower()
            if outcome_normalized in question:
                return market
            
            # Try matching with underscores/spaces variations
            question_clean = question.replace('will ', '').replace('?', '').replace(' say ', '').replace(' mention ', '').strip()
            if outcome_normalized in question_clean or question_clean in outcome_normalized:
                return market
        
        return None
    
    def _expand_outcome_abbreviation(self, outcome: str, event_title: str, question: str) -> str:
        """
        Expand abbreviations in outcome names for clarity.
        Examples:
        - "O/U 2.5" -> "Over/Under 2.5 maps" (for CS:GO/esports)
        - "O/U 2.5" -> "Over/Under 2.5 goals" (for soccer)
        """
        outcome_lower = outcome.lower()
        text_lower = (event_title + " " + question).lower()
        
        # Check if it's a sports/esports market
        is_esports = any(term in text_lower for term in ['cs:go', 'counter-strike', 'esports', 'bo3', 'best of 3'])
        is_soccer = any(term in text_lower for term in ['soccer', 'football', 'fifa', 'world cup'])
        
        # Expand O/U (Over/Under)
        if 'o/u' in outcome_lower or 'over/under' in outcome_lower:
            if is_esports:
                outcome = outcome.replace('O/U', 'Over/Under').replace('o/u', 'Over/Under')
                if 'maps' not in outcome_lower:
                    outcome += ' maps'
            elif is_soccer:
                outcome = outcome.replace('O/U', 'Over/Under').replace('o/u', 'Over/Under')
                if 'goals' not in outcome_lower:
                    outcome += ' goals'
            else:
                outcome = outcome.replace('O/U', 'Over/Under').replace('o/u', 'Over/Under')
        
        return outcome
    
    def _is_limit_market(self, market: Dict) -> bool:
        """
        Detect if this is a limit market (measured in cents) vs regular YES/NO market (measured in %).
        Limit markets have average price available, regular YES/NO markets don't.
        
        Detection methods:
        1. Check if market has 'orderBook' or 'limit' in type/fields
        2. Check if market question mentions "limit"
        3. Check market type field if available
        """
        # Check market type or mechanism field
        market_type = market.get('type', '').lower()
        mechanism = market.get('mechanism', '').lower()
        
        if 'limit' in market_type or 'limit' in mechanism:
            return True
        
        # Check if question mentions limit orders
        question = market.get('question', '').lower()
        if 'limit' in question:
            return True
        
        # Check for order book presence (limit markets have order books)
        if 'orderBook' in market or 'order_book' in market:
            return True
        
        # Default: assume regular YES/NO market (not limit)
        # Most markets are regular YES/NO, so we default to False
        return False
    
    def _safe_float(self, value, default=None) -> Optional[float]:
        """
        Safely convert API values to float.
        Handles strings like '"0.57"' or '0.57'.
        Returns default (None) if conversion fails.
        """
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip().strip('"').strip("'")
            if stripped == "":
                return default
            try:
                return float(stripped)
            except ValueError:
                return default
        return default
    
    async def get_stats(self) -> Dict:
        """Return scanner statistics."""
        return {
            'scans': self.scan_count,
            'markets_discovered': self.markets_discovered,
            'markets_analyzed': self.markets_analyzed,
            'alerts_sent': self.alerts_sent,
            'seen_markets': len(self.seen_market_ids)
        }

