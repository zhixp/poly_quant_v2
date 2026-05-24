# User Guide: Outcome Parameter for /ask Command

## What's New?

You can now **specify exactly which outcome you want analyzed** when asking about multi-outcome markets!

## Command Format

```
/ask question:<url> outcome:<optional>
```

## Examples

### Example 1: Analyze Specific Date
```
/ask question:https://polymarket.com/event/next-us-x-venezuela-military-engagement-on outcome:December 6
```

**Result:** Bot analyzes ONLY December 6, tells you if it's a good buy at 5%

### Example 2: Analyze Specific Word
```
/ask question:https://polymarket.com/event/what-will-karoline-leavitt-say outcome:President 66+
```

**Result:** Bot analyzes ONLY "President 66+" outcome

### Example 3: Binary Market (No Outcome Needed)
```
/ask question:https://polymarket.com/event/will-fed-cut-rates
```

**Result:** Normal YES/NO analysis (outcome parameter ignored for binary markets)

### Example 4: Multi-Outcome Without Specifying
```
/ask question:https://polymarket.com/event/venezuela-military...
```

**Result:** Bot shows you all available outcomes and their current prices

## Benefits

✅ **No More Hallucinations** - Bot analyzes exactly what you ask for
✅ **No Expired Dates** - You control which date to analyze
✅ **Clear Intent** - You tell the bot what you want
✅ **Better Analysis** - Focused on your specific interest

## Tips

### Tip 1: Check Current Prices First
Run `/ask` without outcome to see all options and their prices, then pick one:

```
Step 1: /ask question:<url>
        → See: December 6 (5%), December 7 (4%), December 8 (2%)

Step 2: /ask question:<url> outcome:December 6
        → Get detailed analysis on December 6
```

### Tip 2: Outcome Name Format
- Use the exact name from Polymarket: `December 6` not `Dec 6`
- Include special characters: `President 66+` not `President 66`
- Case doesn't matter: `december 6` works too

### Tip 3: Expired Dates
If you ask about a past date (e.g., November 28 when today is December 2):
- Bot will warn you it's expired
- But will still analyze if you want historical data

## What the Bot Does

### When You Specify an Outcome:

1. **Fetches all market data** from Polymarket
2. **Highlights your requested outcome** in the analysis
3. **Forces the Judge to analyze ONLY that outcome**
4. **Returns verdict**: `BUY_[YOUR_OUTCOME]` or `HOLD`

### Example Output:

```
🎯 POLYQUANT ANALYSIS

Question: https://polymarket.com/event/venezuela-military...

Verdict: 🎯 BUY DECEMBER_6
Model confidence (0–100, heuristic): 72%

Reasoning:
December 6 at 5¢ offers value given current geopolitical tensions. 
Polymarket shows 5% vs historical patterns suggesting 8-10% probability.

Data:
Source: Polymarket (time: December 02, 2025)
Prices:
- December 6: Price: $0.050 (5%) Volume: $7,447
- December 5: 4%
- December 7: 4%

Scenarios:
Base: Price maintains 4-6% range until Dec 5
Upside: If tensions escalate before Dec 6, targets 12-15%
Downside: If diplomatic progress, dips to 2-3%
```

## Common Questions

**Q: What if I misspell the outcome?**
A: The bot will try to match it. If it can't find it, it will show you available outcomes.

**Q: Can I analyze multiple outcomes at once?**
A: Not yet. Run `/ask` multiple times with different outcomes.

**Q: What if I don't know which outcome to pick?**
A: Run `/ask` without the outcome parameter first to see all options.

**Q: Does this work for binary markets?**
A: The outcome parameter is ignored for binary (YES/NO) markets.

**Q: Can I ask about an expired date?**
A: Yes, but the bot will warn you it's expired and worthless.

## Before vs After

### Before (Bot Picks for You):
```
/ask question:<url>
→ Bot: "BUY November 28" ❌ (expired date!)
```

### After (You Control):
```
/ask question:<url> outcome:December 6
→ Bot: "BUY December 6" ✅ (exactly what you asked for)
```

## Need Help?

If the bot's response doesn't match your requested outcome, please:
1. Check you spelled the outcome correctly
2. Make sure it's a multi-outcome market
3. Restart the bot to load latest updates
4. Report the issue with the exact command you used

---

**Happy Trading! 🎯**

