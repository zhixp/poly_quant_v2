# 🚨 CRITICAL FIX: Data Pipeline Failures

## Status: Bot is showing 50% for all outcomes (default fallback)

---

## 🔍 **Root Cause Analysis**

### **Issue #1: Default Price Fallback (DANGEROUS)**

**Location:** `app/core/market_data.py` lines 220-221, 256-257, 305-308

**The Bug:**
```python
outcome_prices = market.get('outcomePrices', ['0.50', '0.50'])  # ❌ DEFAULT!
yes_price = self._safe_float(outcome_prices[1], default=0.5)    # ❌ DEFAULT!
```

**Why This is Dangerous:**
- When Polymarket API returns empty/malformed data
- Code defaults to 50% for ALL outcomes
- Makes every market look like a coin flip
- Bot says HOLD or makes random picks
- **User thinks prices are real, but they're fake!**

**Evidence from User:**
- Bitcoin $1M: 50% ❌ (default)
- Bitcoin $250K: 50% ❌ (default)  
- Bitcoin $200K: 50% ❌ (default)
- All tied = Bot confused

---

### **Issue #2: DuckDuckGo Rate Limit**

**Location:** Search functionality

**The Bug:**
```
WARNING | Router | DDG Failed: DuckDuckGoSearchException: Ratelimit
```

**Impact:**
- No news context for AI
- Bot relies only on question title
- Increases hallucination risk

---

### **Issue #3: Gemini API Rate Limiting**

**Location:** Hydra key rotation

**The Bug:**
```
WARNING | Hydra | ⛔ Key AIzaS... hit 429. Quarantined for 60s
```

**Impact:**
- Keys burning too fast
- Need backoff strategy
- May run out of keys during high usage

---

## ✅ **THE FIX**

### **Fix #1: KILL THE DEFAULTS - Fail Fast, Fail Loud**

**Philosophy:** Better to crash than lie to the user!

**Update `app/core/market_data.py`:**

```python
def _format_multi_market_data(self, event: Dict, markets: List[Dict]) -> str:
    """
    Format multi-outcome market data for prompt injection.
    CRITICAL: NO DEFAULTS - Fail if data is missing!
    """
    from datetime import datetime
    
    output = ["\n" + "="*60]
    output.append("🚨 MULTI-OUTCOME MARKET (NOT BINARY YES/NO!)")
    output.append("="*60)
    output.append(f"⚠️  MARKET TYPE: CATEGORICAL (Multiple specific outcomes)")
    output.append(f"⚠️  DO NOT OUTPUT 'YES' OR 'NO' - Choose specific outcome name!")
    output.append(f"⚠️  TODAY'S DATE: {datetime.now().strftime('%B %d, %Y')} - IGNORE ANY PAST DATES!")
    output.append("")
    output.append(f"Event: {event.get('title', 'Unknown')}")
    event_volume = self._safe_float(event.get('volume', 0), default=0.0)
    output.append(f"Volume: ${event_volume:,.0f}")
    output.append(f"Total Outcomes: {len(markets)}")
    output.append("")
    output.append("ALL AVAILABLE OUTCOMES (Pick ONE by name):")
    output.append("-" * 60)
    
    # Sort markets by YES price (descending)
    sorted_markets = []
    for market in markets:
        question = market.get('question', '')
        outcome_prices = market.get('outcomePrices', [])
        
        # ✅ NEW: NO DEFAULTS - Fail if missing
        if not outcome_prices or len(outcome_prices) < 2:
            logger.error(f"❌ CRITICAL: Market '{question}' has no valid outcomePrices: {outcome_prices}")
            raise ValueError(f"Cannot fetch valid prices for market: {question}")
        
        # ✅ NEW: Validate prices are not null/empty
        yes_price = self._safe_float(outcome_prices[1], default=None)
        if yes_price is None:
            logger.error(f"❌ CRITICAL: Market '{question}' has null YES price: {outcome_prices}")
            raise ValueError(f"Cannot parse YES price for market: {question}")
        
        sorted_markets.append((market, yes_price))
    
    # Sort by YES price descending
    sorted_markets.sort(key=lambda x: x[1], reverse=True)
    
    # Display top outcome prominently
    if sorted_markets:
        top_market, top_price = sorted_markets[0]
        question = top_market.get('question', '')
        outcome_name = question.replace('Will ', '').replace('win?', '').strip()
        top_pct = top_price * 100
        volume = self._safe_float(top_market.get('volume', 0), default=0.0)
        
        output.append(f"\n🥇 FRONTRUNNER: {outcome_name}")
        output.append(f"  Price: ${top_price:.3f} ({top_pct:.0f}%)")
        output.append(f"  Volume: ${volume:,.0f}")
    
    # Show all other outcomes
    for market, yes_price in sorted_markets[1:]:
        question = market.get('question', '')
        outcome_name = question.replace('Will ', '').replace('win?', '').strip()
        yes_pct = yes_price * 100
        volume = self._safe_float(market.get('volume', 0), default=0.0)
        
        # Rank indicators
        if yes_pct >= 20:
            rank = "🥈 2ND PLACE" if len(output) < 15 else "   CONTENDER"
        elif yes_pct >= 5:
            rank = "   LONGSHOT"
        else:
            rank = "   UNLIKELY"
        
        output.append(f"\n{rank}: {outcome_name}")
        output.append(f"  Price: ${yes_price:.3f} ({yes_pct:.1f}%)")
        output.append(f"  Volume: ${volume:,.0f}")
    
    output.append("\n" + "="*60)
    output.append("⚠️  USE THESE EXACT PRICES. DO NOT MAKE UP NUMBERS.")
    output.append("⚠️  PICK THE OUTCOME WITH BEST VALUE OR SAY HOLD.")
    output.append("="*60)
    
    return "\n".join(output)
```

**Key Changes:**
1. ✅ **NO DEFAULTS** - Raises error if `outcomePrices` is empty
2. ✅ **Validates prices** - Checks for null/None values
3. ✅ **Fails loudly** - Throws `ValueError` instead of returning fake data
4. ✅ **Logs errors** - Shows exactly which market failed

---

### **Fix #2: Update Binary Market Formatter**

```python
def _format_binary_market_data(self, market: Dict) -> str:
    """
    Format binary market data for prompt injection.
    CRITICAL: NO DEFAULTS - Fail if data is missing!
    """
    from datetime import datetime
    
    question = market.get('question', 'Unknown')
    outcome_prices = market.get('outcomePrices', [])
    
    # ✅ NEW: NO DEFAULTS - Fail if missing
    if not outcome_prices or len(outcome_prices) < 2:
        logger.error(f"❌ CRITICAL: Binary market '{question}' has no valid outcomePrices: {outcome_prices}")
        raise ValueError(f"Cannot fetch valid prices for binary market: {question}")
    
    yes_price = self._safe_float(outcome_prices[1], default=None)
    no_price = self._safe_float(outcome_prices[0], default=None)
    
    if yes_price is None or no_price is None:
        logger.error(f"❌ CRITICAL: Binary market '{question}' has null prices: YES={outcome_prices[1]}, NO={outcome_prices[0]}")
        raise ValueError(f"Cannot parse prices for binary market: {question}")
    
    yes_pct = yes_price * 100
    no_pct = no_price * 100
    
    volume = self._safe_float(market.get('volume', 0), default=0.0)
    
    output = ["\n" + "="*60]
    output.append("🚨 BINARY MARKET (YES/NO ONLY)")
    output.append("="*60)
    output.append(f"⚠️  MARKET TYPE: BINARY (Two outcomes only)")
    output.append(f"⚠️  OUTPUT FORMAT: YES, NO, HOLD, or AVOID")
    output.append(f"⚠️  TODAY'S DATE: {datetime.now().strftime('%B %d, %Y')}")
    output.append("")
    output.append(f"Market: {question}")
    output.append(f"Volume: ${volume:,.0f}")
    output.append("")
    output.append("CURRENT ODDS:")
    output.append(f"  YES: ${yes_price:.3f} ({yes_pct:.0f}%)")
    output.append(f"  NO:  ${no_price:.3f} ({no_pct:.0f}%)")
    output.append("="*60)
    output.append("⚠️  USE THESE EXACT PRICES. DO NOT MAKE UP NUMBERS.")
    output.append("="*60)
    
    return "\n".join(output)
```

---

### **Fix #3: Update Query Cog to Handle Failures**

**Update `app/cogs/query.py`:**

```python
# Around line 175-200
try:
    # 3. Fetch live market data (CRITICAL - must have real prices!)
    market_data = await market_resolver.fetch_market_data(safe_question)
except ValueError as e:
    # Price fetch failed - DO NOT PROCEED
    logger.error(f"❌ CRITICAL: Cannot fetch valid market prices: {e}")
    await interaction.followup.send(
        f"❌ **Error: Cannot fetch market data**\n\n"
        f"The Polymarket API returned invalid or missing price data. "
        f"Cannot provide analysis without real prices.\n\n"
        f"**Error:** {str(e)}\n\n"
        f"Please try again in a few moments, or check if the market URL is correct.",
        ephemeral=True
    )
    return
except Exception as e:
    logger.error(f"❌ Unexpected error fetching market data: {e}", exc_info=True)
    await interaction.followup.send(
        f"❌ **Error: Market data fetch failed**\n\n"
        f"An unexpected error occurred while fetching market data.\n\n"
        f"**Error:** {str(e)}",
        ephemeral=True
    )
    return

if not market_data:
    # No market data found - DO NOT PROCEED
    logger.warning(f"⚠️ No Polymarket prices found for: {safe_question}")
    await interaction.followup.send(
        f"⚠️ **No market data found**\n\n"
        f"Could not find Polymarket data for this question. "
        f"Make sure you're providing a valid Polymarket URL.\n\n"
        f"**Tip:** Copy the full URL from Polymarket (e.g., `https://polymarket.com/event/...`)",
        ephemeral=True
    )
    return
```

---

### **Fix #4: Add Retry Logic for Polymarket API**

**Add to `app/core/market_data.py`:**

```python
async def _fetch_with_retry(self, url: str, max_retries: int = 3) -> Optional[Dict]:
    """
    Fetch from Polymarket API with retry logic.
    """
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    elif response.status == 429:
                        # Rate limited - wait and retry
                        wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                        logger.warning(f"⚠️ Polymarket API rate limit (429). Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"❌ Polymarket API returned {response.status}")
                        return None
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ Polymarket API timeout (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"❌ Error fetching from Polymarket: {e}")
            return None
    
    logger.error(f"❌ Failed to fetch from Polymarket after {max_retries} attempts")
    return None
```

---

## 🧪 **Testing After Fix**

### **Expected Behavior:**

**Scenario 1: Valid Market Data**
```
✅ Fetched prices from Polymarket
✅ Shows real percentages (not all 50%)
✅ Bot makes recommendation based on real data
```

**Scenario 2: Invalid/Missing Data**
```
❌ CRITICAL: Market 'X' has no valid outcomePrices
❌ Error: Cannot fetch valid market prices
→ Bot shows error message to user
→ Does NOT proceed with fake 50% prices
```

---

## 📝 **Summary**

**Problem:**
- Bot defaulting to 50% for all outcomes
- Makes every market look like coin flip
- Users think prices are real (they're not!)

**Solution:**
- Remove all default price fallbacks
- Fail loudly if prices are missing
- Show error to user instead of fake data
- Add retry logic for API failures

**Philosophy:**
- **Better to crash than lie**
- **Fail fast, fail loud**
- **Never show fake data to users**

---

**Status:** Ready to implement
**Priority:** CRITICAL
**ETA:** 30 minutes to apply all fixes

