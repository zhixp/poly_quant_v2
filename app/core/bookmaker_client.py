"""
Bookmaker Client: Fetches odds from external bookmakers (Vegas/sharp books)
Provides standardized odds format for cross-venue arbitrage detection.
"""
import asyncio
import aiohttp
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

logger = logging.getLogger("BookmakerClient")


@dataclass
class BookmakerOdds:
    """Standardized odds structure across venues."""
    venue: str
    market_id: str
    market_name: str
    outcomes: Dict[str, float]  # outcome_name -> decimal_odds
    implied_probs: Dict[str, float]  # outcome_name -> implied_probability
    timestamp: str
    raw_data: dict  # Original API response for debugging


@dataclass(frozen=True)
class ExecutableQuote:
    """Executable prediction-market price and available contract units."""
    price: Decimal
    size: Decimal
    source: str = "ask"


class OddsConverter:
    """Utility functions for odds format conversions."""
    
    @staticmethod
    def decimal_to_implied_prob(decimal_odds: float) -> float:
        """
        Convert decimal odds to implied probability.
        Example: 2.0 (even money) -> 50%
        """
        if decimal_odds <= 1.0:
            return 0.0
        return 1.0 / decimal_odds
    
    @staticmethod
    def american_to_decimal(american_odds: int) -> float:
        """
        Convert American odds to decimal.
        Example: +150 -> 2.5, -150 -> 1.67
        """
        if american_odds > 0:
            return (american_odds / 100.0) + 1.0
        else:
            return (100.0 / abs(american_odds)) + 1.0
    
    @staticmethod
    def american_to_implied_prob(american_odds: int) -> float:
        """
        Convert American odds directly to implied probability.
        """
        decimal = OddsConverter.american_to_decimal(american_odds)
        return OddsConverter.decimal_to_implied_prob(decimal)
    
    @staticmethod
    def polymarket_to_decimal(poly_price: float) -> float:
        """
        Convert Polymarket price (0-1) to decimal odds.
        Example: 0.57 -> 1.75
        """
        if poly_price <= 0 or poly_price >= 1:
            return 1.0
        return 1.0 / poly_price
    
    @staticmethod
    def normalize_probs(probs: Dict[str, float]) -> Dict[str, float]:
        """
        Normalize implied probabilities to sum to 100% (remove vig/overround).
        """
        total = sum(probs.values())
        if total == 0:
            return probs
        return {k: (v / total) for k, v in probs.items()}
    
    @staticmethod
    def calculate_edge(fair_prob: float, market_price: float, fees: float = 0.0) -> float:
        """
        Calculate edge: (fair_prob - market_price - fees).
        Positive edge = value bet.
        
        Args:
            fair_prob: Your estimated true probability (0-1)
            market_price: Current market price (0-1, e.g., Polymarket)
            fees: Transaction fees as decimal (e.g., 0.02 for 2%)
        
        Returns:
            Edge as decimal (e.g., 0.07 for 7% edge)
        """
        return fair_prob - market_price - fees

    @staticmethod
    def _canonical_outcome(name: str) -> str:
        normalized = str(name).strip().lower().replace("_", " ").replace("-", " ")
        aliases = {
            "y": "yes",
            "buy yes": "yes",
            "yes": "yes",
            "n": "no",
            "buy no": "no",
            "no": "no",
        }
        return aliases.get(normalized, " ".join(normalized.split()))

    @staticmethod
    def compare_prediction_market_prices(
        polymarket_prices: Dict[str, float],
        external_prices: Dict[str, float],
        fees: float = 0.02,
    ) -> Dict:
        """Compare like-for-like outcome prices across prediction venues.

        Outcome-name matching prevents comparing Polymarket YES with Kalshi NO
        or a parent event with a child/date market. Prices are probabilities
        in 0..1, not decimal odds.
        """
        external_by_key = {
            OddsConverter._canonical_outcome(name): price
            for name, price in external_prices.items()
        }
        matched = {}
        for poly_name, poly_price in polymarket_prices.items():
            key = OddsConverter._canonical_outcome(poly_name)
            if key not in external_by_key:
                continue
            external_price = float(external_by_key[key])
            poly_price = float(poly_price)
            edge = external_price - poly_price - fees
            matched[poly_name] = {
                "polymarket_price": poly_price,
                "external_price": external_price,
                "edge": edge,
                "edge_percent": edge * 100,
                "direction": "BUY_POLYMARKET" if edge > 0 else "BUY_EXTERNAL_OR_HOLD",
            }
        return {
            "status": "success" if matched else "no_matched_outcomes",
            "matched_outcomes": matched,
        }

    @staticmethod
    def calculate_prediction_market_arb(
        polymarket_yes_price: float,
        external_no_price: float,
        fees: float = 0.02,
    ) -> Dict:
        """Two-venue binary arb: buy YES on one venue + NO on another."""
        total_cost = float(polymarket_yes_price) + float(external_no_price) + float(fees)
        profit = 1.0 - total_cost
        return {
            "is_arbitrage": profit > 0,
            "total_cost": total_cost,
            "guaranteed_profit": profit,
            "guaranteed_profit_pct": profit * 100,
        }

    @staticmethod
    def _to_decimal(value: Any) -> Optional[Decimal]:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return dec if dec.is_finite() else None

    @staticmethod
    def polymarket_tokens_by_outcome(outcomes: List[Any], token_ids: List[Any]) -> Dict[str, str]:
        """Map Polymarket YES/NO labels to CLOB token IDs without index guessing."""
        if len(token_ids) < 2:
            return {}

        mapped: Dict[str, str] = {}
        for idx, outcome in enumerate(outcomes or []):
            if idx >= len(token_ids):
                continue
            label = OddsConverter._canonical_outcome(outcome)
            if label in {"yes", "no"}:
                mapped[label] = str(token_ids[idx])

        if "yes" not in mapped and len(token_ids) >= 1:
            mapped["yes"] = str(token_ids[0])
        if "no" not in mapped and len(token_ids) >= 2:
            mapped["no"] = str(token_ids[1])
        return mapped

    @staticmethod
    def best_polymarket_ask(book: Dict[str, Any]) -> Optional[ExecutableQuote]:
        """Select the lowest valid executable Polymarket ask from an order book."""
        best: Optional[ExecutableQuote] = None
        for level in book.get("asks") or []:
            if not isinstance(level, dict):
                continue
            price = OddsConverter._to_decimal(level.get("price"))
            size = OddsConverter._to_decimal(level.get("size"))
            if price is None or size is None or not (Decimal("0") < price < Decimal("1")) or size <= 0:
                continue
            quote = ExecutableQuote(price=price, size=size)
            if best is None or quote.price < best.price:
                best = quote
        return best

    @staticmethod
    def best_kalshi_bid(levels: List[Any]) -> Optional[ExecutableQuote]:
        """Select the highest valid Kalshi bid from orderbook_fp levels."""
        best: Optional[ExecutableQuote] = None
        for level in levels or []:
            if isinstance(level, dict):
                price_raw = level.get("price") or level.get("price_dollars")
                size_raw = level.get("count") or level.get("count_fp") or level.get("size")
            elif isinstance(level, (list, tuple)) and len(level) >= 2:
                price_raw, size_raw = level[0], level[1]
            else:
                continue

            price = OddsConverter._to_decimal(price_raw)
            size = OddsConverter._to_decimal(size_raw)
            if price is None or size is None or not (Decimal("0") < price < Decimal("1")) or size <= 0:
                continue
            quote = ExecutableQuote(price=price, size=size)
            if best is None or quote.price > best.price:
                best = quote
        return best

    @staticmethod
    def kalshi_implied_asks(orderbook: Dict[str, Any]) -> Dict[str, Optional[ExecutableQuote]]:
        """Compute Kalshi executable asks from highest valid opposite-side bids."""
        fp = orderbook.get("orderbook_fp") or orderbook
        yes_bid = OddsConverter.best_kalshi_bid(fp.get("yes_dollars") or [])
        no_bid = OddsConverter.best_kalshi_bid(fp.get("no_dollars") or [])

        return {
            "Yes": ExecutableQuote(price=Decimal("1") - no_bid.price, size=no_bid.size) if no_bid else None,
            "No": ExecutableQuote(price=Decimal("1") - yes_bid.price, size=yes_bid.size) if yes_bid else None,
        }

    @staticmethod
    def calculate_equal_payout_arb(
        yes_ask: Optional[ExecutableQuote],
        no_ask: Optional[ExecutableQuote],
        fees_per_unit: Decimal = Decimal("0"),
        slippage_buffer_per_unit: Decimal = Decimal("0"),
        min_profit: Decimal = Decimal("0.01"),
        min_size: Decimal = Decimal("1"),
    ) -> Dict[str, Any]:
        """One YES + one NO = guaranteed $1 payout."""
        if not yes_ask or not no_ask:
            return {"status": "WATCH", "reason": "missing executable ask"}
        if yes_ask.source != "ask" or no_ask.source != "ask":
            return {"status": "WATCH", "reason": "non-executable price source"}

        cost_per_unit = yes_ask.price + no_ask.price + fees_per_unit + slippage_buffer_per_unit
        profit_per_unit = Decimal("1") - cost_per_unit
        max_units = min(yes_ask.size, no_ask.size)
        total_profit = profit_per_unit * max_units
        status = "ARB_ALERT" if profit_per_unit >= min_profit and max_units >= min_size else "WATCH"
        return {
            "status": status,
            "cost_per_unit": cost_per_unit,
            "profit_per_unit": profit_per_unit,
            "max_units": max_units,
            "total_profit": total_profit,
        }


class BookmakerClient:
    """
    Client for fetching odds from external bookmakers.
    Currently supports: Kalshi public market fetch, with extensibility for others.
    """
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.converter = OddsConverter()
        self.min_arb_profit = self._env_decimal("MIN_ARB_PROFIT", "0.01")
        self.min_arb_size = self._env_decimal("MIN_ARB_SIZE", "1")
        self.arb_fees_per_unit = self._env_decimal("ARB_FEES_PER_UNIT", "0")
        self.arb_slippage_buffer = self._env_decimal("ARB_SLIPPAGE_BUFFER", "0")
    
    async def _ensure_session(self):
        """Lazy initialization of aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def _env_decimal(self, name: str, default: str) -> Decimal:
        value = OddsConverter._to_decimal(os.getenv(name, default))
        return value if value is not None else Decimal(default)

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
    
    async def get_odds(self, venue: str, market_id: str) -> Optional[BookmakerOdds]:
        """
        Fetch odds from a specific bookmaker.
        
        Args:
            venue: Bookmaker identifier ('pinnacle', 'betfair', etc.)
            market_id: Venue-specific market ID
        
        Returns:
            BookmakerOdds object or None if fetch fails
        """
        venue_lower = venue.lower()
        
        if venue_lower == 'kalshi':
            return await self._fetch_kalshi(market_id)
        elif venue_lower == 'pinnacle':
            return await self._fetch_pinnacle(market_id)
        elif venue_lower == 'betfair':
            return await self._fetch_betfair(market_id)
        elif venue_lower == 'draftkings':
            return await self._fetch_draftkings(market_id)
        else:
            logger.warning(f"Unsupported venue: {venue}")
            return None
    

    async def _fetch_kalshi(self, market_id: str) -> Optional[BookmakerOdds]:
        """Fetch a Kalshi market by exact ticker using the public trade API."""
        await self._ensure_session()
        url = f"https://api.elections.kalshi.com/trade-api/v2/markets/{market_id}"
        try:
            async with self.session.get(url, headers={"User-Agent": "PolyQuant/1.0"}, timeout=10) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("Kalshi market fetch failed %s: %s", resp.status, text[:160])
                    return None
                payload = await resp.json()
        except Exception as exc:
            logger.warning("Kalshi market fetch error for %s: %s", market_id, exc)
            return None

        market = payload.get("market") or payload

        def cents_mid(bid_key: str, ask_key: str, fallback_key: str = "last_price") -> Optional[float]:
            bid = market.get(bid_key)
            ask = market.get(ask_key)
            if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
                return (float(bid) + float(ask)) / 200.0
            fallback = market.get(fallback_key)
            if fallback is not None:
                return float(fallback) / 100.0
            return None

        yes_price = cents_mid("yes_bid", "yes_ask")
        no_price = cents_mid("no_bid", "no_ask")
        if yes_price is None and no_price is not None:
            yes_price = 1.0 - no_price
        if no_price is None and yes_price is not None:
            no_price = 1.0 - yes_price
        if yes_price is None or no_price is None:
            logger.warning("Kalshi market %s missing usable yes/no prices", market_id)
            return None

        outcomes = {"Yes": yes_price, "No": no_price}
        return BookmakerOdds(
            venue="kalshi",
            market_id=market_id,
            market_name=market.get("title") or market.get("subtitle") or market_id,
            outcomes=outcomes,
            implied_probs=outcomes.copy(),
            timestamp=market.get("last_update_time") or datetime.now(timezone.utc).isoformat(),
            raw_data=market,
        )

    async def fetch_polymarket_executable_quotes(self, market_slug: str) -> Dict[str, Optional[ExecutableQuote]]:
        """Fetch executable Polymarket YES/NO asks for an exact child market slug."""
        await self._ensure_session()
        async with self.session.get(
            "https://gamma-api.polymarket.com/markets",
            params={"slug": market_slug},
            timeout=10,
        ) as resp:
            if resp.status != 200:
                return {"Yes": None, "No": None}
            markets = await resp.json()

        if not markets:
            return {"Yes": None, "No": None}

        market = markets[0]
        tokens = OddsConverter.polymarket_tokens_by_outcome(
            self._json_list(market.get("outcomes")),
            self._json_list(market.get("clobTokenIds")),
        )
        if "yes" not in tokens or "no" not in tokens:
            return {"Yes": None, "No": None}

        payload = [{"token_id": tokens["yes"]}, {"token_id": tokens["no"]}]
        async with self.session.post("https://clob.polymarket.com/books", json=payload, timeout=10) as resp:
            if resp.status != 200:
                return {"Yes": None, "No": None}
            books = await resp.json()

        if isinstance(books, dict):
            books = books.get("data") or books.get("books") or []
        if not isinstance(books, list) or len(books) < 2:
            return {"Yes": None, "No": None}

        return {
            "Yes": OddsConverter.best_polymarket_ask(books[0]),
            "No": OddsConverter.best_polymarket_ask(books[1]),
        }

    async def fetch_kalshi_executable_quotes(self, ticker: str) -> Dict[str, Optional[ExecutableQuote]]:
        """Fetch executable Kalshi YES/NO asks implied from exact ticker orderbook bids."""
        await self._ensure_session()
        url = f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}/orderbook"
        async with self.session.get(url, headers={"User-Agent": "PolyQuant/1.0"}, timeout=10) as resp:
            if resp.status != 200:
                return {"Yes": None, "No": None}
            payload = await resp.json()
        return OddsConverter.kalshi_implied_asks(payload)

    async def check_polymarket_kalshi_arb(self, market_slug: str, kalshi_ticker: str) -> Dict[str, Any]:
        """Deterministic exact-mapping arb check. No fuzzy matching, no midpoint prices."""
        poly_quotes, kalshi_quotes = await asyncio.gather(
            self.fetch_polymarket_executable_quotes(market_slug),
            self.fetch_kalshi_executable_quotes(kalshi_ticker),
        )

        directions = {
            "BUY_POLY_YES_AND_KALSHI_NO": OddsConverter.calculate_equal_payout_arb(
                poly_quotes.get("Yes"),
                kalshi_quotes.get("No"),
                fees_per_unit=self.arb_fees_per_unit,
                slippage_buffer_per_unit=self.arb_slippage_buffer,
                min_profit=self.min_arb_profit,
                min_size=self.min_arb_size,
            ),
            "BUY_KALSHI_YES_AND_POLY_NO": OddsConverter.calculate_equal_payout_arb(
                kalshi_quotes.get("Yes"),
                poly_quotes.get("No"),
                fees_per_unit=self.arb_fees_per_unit,
                slippage_buffer_per_unit=self.arb_slippage_buffer,
                min_profit=self.min_arb_profit,
                min_size=self.min_arb_size,
            ),
        }
        status = "ARB_ALERT" if any(d["status"] == "ARB_ALERT" for d in directions.values()) else "WATCH"
        return {
            "status": status,
            "market_slug": market_slug,
            "kalshi_ticker": kalshi_ticker,
            "directions": directions,
        }

    async def _fetch_pinnacle(self, market_id: str) -> Optional[BookmakerOdds]:
        """
        Fetch odds from Pinnacle (sharp bookmaker).
        
        NOTE: This is a STUB implementation. Real integration requires:
        - Pinnacle API credentials
        - Proper authentication
        - Rate limiting
        - Market ID mapping
        
        Production code must not emit mock odds as real market data.
        """
        logger.warning(f"Pinnacle integration not configured; no odds returned for market {market_id}")
        return None
    
    async def _fetch_betfair(self, market_id: str) -> Optional[BookmakerOdds]:
        """
        Fetch odds from Betfair exchange.
        STUB: Implement when needed.
        """
        logger.warning(f"Betfair integration not implemented yet (market: {market_id})")
        return None
    
    async def _fetch_draftkings(self, market_id: str) -> Optional[BookmakerOdds]:
        """
        Fetch odds from DraftKings.
        STUB: Implement when needed.
        """
        logger.warning(f"DraftKings integration not implemented yet (market: {market_id})")
        return None
    
    async def compare_odds(
        self, 
        polymarket_price: float, 
        bookmaker_odds: BookmakerOdds,
        outcome_name: str,
        fees: float = 0.02  # 2% default Polymarket fees
    ) -> Dict:
        """
        Compare Polymarket price vs bookmaker odds for a specific outcome.
        
        Returns:
            Dict with comparison metrics including edge calculation.
        """
        # Get bookmaker implied prob for this outcome
        bookie_prob = bookmaker_odds.implied_probs.get(outcome_name)
        
        if bookie_prob is None:
            logger.warning(f"Outcome '{outcome_name}' not found in bookmaker odds")
            return {
                'status': 'error',
                'message': f"Outcome not found: {outcome_name}"
            }
        
        # Calculate edge (using bookmaker as "fair" probability)
        edge = self.converter.calculate_edge(bookie_prob, polymarket_price, fees)
        
        # Determine direction
        if edge > 0:
            direction = "BUY on Polymarket (underpriced)"
        elif edge < 0:
            direction = "SELL on Polymarket (overpriced)"
        else:
            direction = "Fair value"
        
        return {
            'status': 'success',
            'outcome': outcome_name,
            'polymarket_price': polymarket_price,
            'polymarket_implied_prob': polymarket_price,  # Already a probability
            'bookmaker_venue': bookmaker_odds.venue,
            'bookmaker_decimal_odds': bookmaker_odds.outcomes.get(outcome_name),
            'bookmaker_implied_prob': bookie_prob,
            'edge': edge,
            'edge_percent': edge * 100,
            'fees': fees,
            'direction': direction,
            'spread': abs(bookie_prob - polymarket_price)
        }


# Global instance
bookmaker_client = BookmakerClient()
