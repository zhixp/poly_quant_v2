"""
Market Data Fetcher: Extracts live prices from Polymarket
CRITICAL: This prevents AI hallucination by providing real-time market data.
"""
import aiohttp
import json
import logging
import re
from typing import Optional, Dict, List, Any

logger = logging.getLogger("MarketData")

class MarketResolver:
    """
    Fetches live market data from Polymarket API.
    Handles both binary and multi-candidate markets.
    """
    
    POLYMARKET_API = "https://gamma-api.polymarket.com"
    
    async def fetch_market_data(self, query: str) -> Optional[str]:
        """
        Extracts Polymarket URL from query and fetches live prices.
        CRITICAL: Auto-detects if market is Binary (Yes/No) or Multi-Outcome (Categorical).
        
        Args:
            query: User question (may contain Polymarket URL)
            
        Returns:
            Formatted string with live prices, or None if not a Polymarket query
        """
        # 1. Check if query contains Polymarket URL
        polymarket_url = self._extract_polymarket_url(query)
        if not polymarket_url:
            logger.debug("No Polymarket URL detected in query")
            return None
        
        # 2. Extract event slug or ID
        event_info = self._parse_polymarket_url(polymarket_url)
        if not event_info:
            logger.warning(f"Could not parse Polymarket URL: {polymarket_url}")
            return None
        
        # 3. Fetch market data from API and auto-detect type
        try:
            # If URL targets a child market under an event, fetch that exact market.
            # Parent ladder events (e.g. US/Iran peace deal by...?) contain many
            # date markets; comparing the parent instead of the child is a major
            # source of wrong odds/arbitrage calls.
            if event_info['type'] == 'event_market':
                return await self._fetch_single_market(event_info['market_slug'])

            # Try fetching as event first (works for both single and multi-outcome)
            if event_info['type'] == 'event':
                result = await self._fetch_and_classify_event(event_info['slug'])
                if result:
                    return result
            
            # Fallback: try as single market
            return await self._fetch_single_market(event_info['slug'])
        except Exception as e:
            logger.error(f"Failed to fetch market data: {e}")
            return None
    
    def _extract_polymarket_url(self, query: str) -> Optional[str]:
        """Extract Polymarket URL from query string."""
        # Match polymarket.com URLs
        match = re.search(r'https?://polymarket\.com/[^\s]+', query)
        return match.group(0) if match else None
    
    def _parse_polymarket_url(self, url: str) -> Optional[Dict]:
        """
        Parse Polymarket URL to extract event/market info.
        
        Examples:
        - /event/honduras-presidential-election → event slug
        - /event/honduras-presidential-election/will-nasry-... → specific market
        - /sports/nfl-2025/games/week/12/nfl-buf-pit-2025-11-30 → event slug
        """
        # Remove query params
        url = url.split('?')[0]
        
        # Event with optional child market: /event/EVENT_SLUG or /event/EVENT_SLUG/MARKET_SLUG
        event_child_match = re.search(r'/event/([^/]+)/([^/]+)$', url)
        if event_child_match:
            return {
                'type': 'event_market',
                'event_slug': event_child_match.group(1),
                'market_slug': event_child_match.group(2)
            }

        event_match = re.search(r'/event/([^/]+)', url)
        if event_match:
            return {
                'type': 'event',
                'slug': event_match.group(1)
            }
        
        # Sports event: /sports/.../SLUG
        sports_match = re.search(r'/sports/[^/]+/games/[^/]+/[^/]+/([^/]+)', url)
        if sports_match:
            return {
                'type': 'event',
                'slug': sports_match.group(1)
            }
        
        # Single market (fallback)
        parts = url.rstrip('/').split('/')
        if len(parts) > 0:
            return {
                'type': 'market',
                'slug': parts[-1]
            }
        
        return None
    
    async def _fetch_and_classify_event(self, event_slug: str) -> Optional[str]:
        """
        Fetch event and auto-detect if it's Binary or Multi-Outcome.
        CRITICAL FIX: Don't assume /event/ URLs are always multi-outcome.
        
        Returns formatted string with ALL outcomes listed.
        """
        url = f"{self.POLYMARKET_API}/events?slug={event_slug}"
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"API returned {response.status} for event {event_slug}")
                    return None
                
                data = await response.json()
                
                # Polymarket returns array of events
                if not data or len(data) == 0:
                    logger.warning(f"No event data found for {event_slug}")
                    return None
                
                event = data[0]
                markets = event.get('markets', [])
                
                if not markets:
                    logger.warning(f"No markets found in event {event_slug}")
                    return None
                
                # CRITICAL: Detect market type by counting outcomes
                if len(markets) == 1:
                    # Single market - check if it's truly binary
                    market = markets[0]
                    outcomes = market.get('outcomes', [])
                    outcome_prices = self._normalize_outcome_prices(market.get('outcomePrices'))
                    
                    # If only 2 outcomes (Yes/No), format as binary
                    if len(outcomes) == 2 or len(outcome_prices) == 2:
                        logger.info(f"Detected BINARY market: {market.get('question')}")
                        return self._format_binary_market_data(market)
                
                # Multiple markets OR single market with >2 outcomes = Multi-Outcome / Group
                logger.info(f"Detected MULTI-OUTCOME market with {len(markets)} options")
                return self._format_multi_market_data(event, markets)
    
    async def _fetch_event_markets(self, event_slug: str) -> str:
        """
        Legacy method - now redirects to _fetch_and_classify_event.
        Kept for backwards compatibility.
        """
        return await self._fetch_and_classify_event(event_slug)
    
    async def _fetch_single_market(self, market_slug: str) -> str:
        """
        Fetch data for a single binary market.
        
        Returns formatted string like:
        "LIVE MARKET PRICES:
        YES: 65% ($0.65)
        NO: 35% ($0.35)"
        """
        url = f"{self.POLYMARKET_API}/markets?slug={market_slug}"
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"API returned {response.status} for market {market_slug}")
                    return None
                
                data = await response.json()
                
                if not data or len(data) == 0:
                    logger.warning(f"No market data found for {market_slug}")
                    return None
                
                market = data[0]
                return self._format_binary_market_data(market)
    
    def _format_multi_market_data(self, event: Dict, markets: List[Dict]) -> str:
        """
        Format multi-outcome market data for prompt injection.
        
        CRITICAL: This must be clear and impossible for AI to ignore.
        """
        from datetime import datetime
        
        candidates = []
        for market in markets:
            name = (
                market.get('groupItemTitle')
                or market.get('question', '').replace('Will ', '').replace('win?', '').strip()
            )
            yes_price = self._extract_yes_price(market)
            volume = self._safe_float(market.get('volume', 0), default=0.0)
            if name and yes_price is not None:
                candidates.append({
                    'name': name.strip(),
                    'price': yes_price,
                    'volume': volume
                })
        
        if not candidates:
            raise ValueError("Could not extract any candidate names or prices from Polymarket event.")
        
        candidates.sort(key=lambda c: c['price'], reverse=True)
        
        output = ["\n" + "="*60]
        output.append("🚨 MULTI-OUTCOME MARKET (NOT BINARY YES/NO!)")
        output.append("="*60)
        output.append("⚠️  MARKET TYPE: GROUP / CATEGORICAL (Multiple specific outcomes)")
        output.append("⚠️  DO NOT OUTPUT 'YES' OR 'NO' - Choose a specific candidate name!")
        output.append(f"⚠️  TODAY'S DATE: {datetime.now().strftime('%B %d, %Y')} - IGNORE ANY PAST DATES!")
        output.append("")
        output.append(f"Event: {event.get('title', 'Unknown')}")
        event_volume = self._safe_float(event.get('volume', 0), default=0.0)
        output.append(f"Volume: ${event_volume:,.0f}")
        output.append(f"Total Candidates: {len(candidates)}")
        output.append("")
        output.append("RANKED CANDIDATE LIST (Use exact name or say HOLD):")
        output.append("-" * 60)
        
        medals = ["🥇", "🥈", "🥉"]
        for idx, candidate in enumerate(candidates, 1):
            badge = medals[idx-1] if idx <= len(medals) else f"{idx}."
            price_cents = candidate['price'] * 100
            price_text = f"{price_cents:.0f}¢" if price_cents >= 1 else "<1¢"
            output.append(f"{badge} {candidate['name']}: {price_text} ( ${candidate['price']:.3f} )")
            if candidate['volume'] > 0:
                output.append(f"    Volume: ${candidate['volume']:,.0f}")
        
        output.append("")
        
        output.append("="*60)
        output.append("⚠️  USE THESE EXACT PRICES. DO NOT MAKE UP NUMBERS.")
        output.append("⚠️  YOUR VERDICT MUST BE ONE OF THE OUTCOME NAMES ABOVE.")
        output.append("⚠️  EXAMPLE: 'BUY_PRESIDENT_66_PLUS' NOT 'YES' OR 'NO'!")
        output.append("="*60 + "\n")
        
        return "\n".join(output)

    def _extract_yes_price(self, market: Dict) -> Optional[float]:
        outcome_prices = self._normalize_outcome_prices(market.get('outcomePrices'))
        if not outcome_prices:
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

        if yes_index is None:
            yes_index = 0

        if yes_index >= len(outcome_prices):
            logger.debug(f"Yes index {yes_index} out of range for market {market.get('question')}")
            return None

        return self._safe_float(outcome_prices[yes_index], default=None)

    def _normalize_outcome_prices(self, prices: Any) -> List[Any]:
        """Convert raw outcomePrices (list or JSON string) into a list."""
        if isinstance(prices, list):
            return prices
        if isinstance(prices, str):
            try:
                parsed = json.loads(prices)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                logger.debug(f"Could not parse outcomePrices string: {prices}")
        return []

    def _safe_float(self, value, default: float = 0.0) -> float:
        """
        Safely convert API values to float.
        Handles strings like '"0.57"' or '0.57'.
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
    
    def _format_binary_market_data(self, market: Dict) -> str:
        """
        Format binary market data for prompt injection.
        """
        question = market.get('question', 'Unknown')
        outcome_prices = self._normalize_outcome_prices(market.get('outcomePrices'))
        
        # ✅ NO DEFAULTS - Fail if missing
        if not outcome_prices or len(outcome_prices) < 2:
            logger.error(f"❌ CRITICAL: Binary market '{question}' has no valid outcomePrices: {outcome_prices}")
            raise ValueError(f"Cannot fetch valid prices for binary market: {question}")
        
        outcomes = self._normalize_outcome_prices(market.get('outcomes', []))
        yes_index = None
        no_index = None
        for idx, outcome in enumerate(outcomes):
            label = str(outcome).strip().lower()
            if label == "yes":
                yes_index = idx
            elif label == "no":
                no_index = idx

        # Gamma normally returns outcomes/outcomePrices in [Yes, No] order.
        # Older code assumed [No, Yes], which inverted every binary market.
        if yes_index is None:
            yes_index = 0
        if no_index is None:
            no_index = 1 if len(outcome_prices) > 1 else None

        if no_index is None or yes_index >= len(outcome_prices) or no_index >= len(outcome_prices):
            raise ValueError(f"Cannot align Yes/No prices for binary market: {question}")

        yes_price = self._safe_float(outcome_prices[yes_index], default=None)
        no_price = self._safe_float(outcome_prices[no_index], default=None)
        
        if yes_price is None or no_price is None:
            logger.error(f"❌ CRITICAL: Binary market '{question}' has null prices: YES={outcome_prices[1]}, NO={outcome_prices[0]}")
            raise ValueError(f"Cannot parse prices for binary market: {question}")
        
        yes_pct = yes_price * 100
        no_pct = no_price * 100
        
        volume = self._safe_float(market.get('volume', 0), default=0.0)
        
        output = ["\n" + "="*60]
        output.append("🚨 BINARY MARKET (YES/NO ONLY)")
        output.append("="*60)
        output.append(f"⚠️  MARKET TYPE: BINARY (Only two outcomes: YES or NO)")
        output.append(f"⚠️  Your verdict should be: YES, NO, HOLD, or AVOID")
        output.append("")
        output.append(f"Market: {question}")
        output.append(f"Volume: ${volume:,.0f}")
        output.append("")
        output.append("CURRENT ODDS:")
        output.append(f"  YES: ${yes_price:.3f} ({yes_pct:.0f}%)")
        output.append(f"  NO:  ${no_price:.3f} ({no_pct:.0f}%)")
        output.append("="*60)
        output.append("⚠️  USE THESE EXACT PRICES. DO NOT MAKE UP NUMBERS.")
        output.append("⚠️  THIS IS A BINARY MARKET - VERDICT MUST BE YES/NO/HOLD/AVOID")
        output.append("="*60 + "\n")
        
        return "\n".join(output)


# Global instance
market_resolver = MarketResolver()


