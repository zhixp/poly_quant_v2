# Hallucination Prevention & User-Directed Analysis Plan

## Problem Statement

The bot currently:
1. ❌ Recommends expired dates (Nov 28 when today is Dec 2)
2. ❌ Picks random outcomes without user input
3. ❌ Doesn't let users specify which outcome they want analyzed
4. ❌ Tries to be "smart" and picks for the user (often wrong)

## Solution: User-Specified Outcome Analysis

### New Command Structure

```
/ask question:<url> outcome:<optional>
```

**Examples:**
```
/ask question:https://polymarket.com/event/venezuela-military... outcome:December 6
/ask question:https://polymarket.com/event/karoline-leavitt... outcome:President 66+
/ask question:https://polymarket.com/event/fed-rates (no outcome = binary market)
```

### How It Works

1. **User provides URL** → Bot fetches all outcomes
2. **If multi-outcome market:**
   - **Option A (outcome specified):** Analyze ONLY that specific outcome
   - **Option B (no outcome):** Show list of outcomes and ask user to pick
3. **If binary market:** Analyze YES/NO as normal

### Implementation Steps

#### Phase 1: Update `/ask` Command Schema
- Add optional `outcome` parameter
- Type: String (autocomplete would be nice but complex)
- Default: None

#### Phase 2: Update QueryCog Logic
```python
if outcome_specified:
    # Filter market data to ONLY show the requested outcome
    # Pass to Judge: "User wants analysis on: December 6"
    # Judge MUST respond about THAT outcome only
else:
    if multi_outcome_market:
        # Show user the list of outcomes
        # Ask them to re-run with outcome parameter
        return "This is a multi-outcome market. Please specify which outcome..."
    else:
        # Binary market, proceed as normal
```

#### Phase 3: Update Judge Prompt
```
NEW RULE: USER-SPECIFIED OUTCOME (HIGHEST PRIORITY)
- If the context says "USER WANTS ANALYSIS ON: [OUTCOME]", you MUST analyze ONLY that outcome
- Your verdict MUST be about that specific outcome: BUY_[OUTCOME] or HOLD
- DO NOT recommend a different outcome, even if you think it's better value
- Example: User asks about "December 6" → Verdict must be about December 6, not December 3
```

#### Phase 4: Market Data Filtering
When user specifies outcome:
```
🚨 USER-REQUESTED OUTCOME ANALYSIS
============================================================
⚠️  USER WANTS ANALYSIS ON: December 6
⚠️  ONLY ANALYZE THIS OUTCOME - DO NOT SUGGEST ALTERNATIVES
============================================================

REQUESTED OUTCOME:
🎯 December 6
  Price: $0.050 (5%)
  Volume: $7,447
  
CONTEXT (for comparison only):
- December 5: 4%
- December 7: 4%
- December 8: 2%

⚠️  YOUR VERDICT MUST BE ABOUT "DECEMBER 6" ONLY!
```

### Benefits

✅ **No more hallucinations** - Bot analyzes exactly what user asks for
✅ **No expired dates** - User won't ask about Nov 28 when it's Dec 2
✅ **Clear intent** - User explicitly states what they want
✅ **Better UX** - User controls the analysis
✅ **Simpler logic** - Bot doesn't need to "guess" best outcome

### Fallback Behavior

**If user doesn't specify outcome on multi-outcome market:**

```
🎯 POLYQUANT ANALYSIS

This is a MULTI-OUTCOME market with 39 options.

Please specify which outcome you want analyzed:

Available outcomes:
• December 2 (3%)
• December 3 (3%)
• December 4 (4%)
• December 5 (4%)
• December 6 (5%) ← Highest probability
• December 7 (4%)
• December 8 (2%)
... (showing top 10)

To analyze a specific outcome, use:
/ask question:<url> outcome:December 6
```

### Edge Cases

1. **User types wrong outcome name:**
   - Fuzzy match: "dec 6" → "December 6"
   - If no match: Show list of valid outcomes

2. **User asks about expired date:**
   - Bot warns: "⚠️ December 1 has already passed (today is Dec 2). This outcome is expired and worthless."
   - Still analyze if user insists (they might want historical data)

3. **Binary market with outcome specified:**
   - Ignore outcome parameter
   - Proceed with YES/NO analysis

### Migration Path

**Phase 1 (Immediate):**
- Add `outcome` parameter to `/ask` command
- If specified, filter market data and force Judge to analyze that outcome only

**Phase 2 (Next):**
- Add interactive picker (buttons/dropdown) for outcomes
- Better UX than typing outcome name

**Phase 3 (Future):**
- Auto-suggest outcomes based on:
  - Highest probability
  - Best value (underpriced)
  - Most volume
  - User's past preferences

## Implementation Code

### 1. Update `/ask` Command

```python
@app_commands.command(name="ask", description="🤖 Get AI analysis on prediction markets")
@app_commands.describe(
    question="Polymarket URL or question about prediction markets",
    outcome="(Optional) Specific outcome to analyze for multi-outcome markets"
)
async def ask(self, interaction: discord.Interaction, question: str, outcome: str = None):
    # ... existing code ...
```

### 2. Add Outcome Filtering Logic

```python
# After fetching market data
if outcome and market_data:
    # Check if this is a multi-outcome market
    if "MULTI-OUTCOME MARKET" in market_data:
        # Filter to show only the requested outcome
        market_data = self._filter_to_outcome(market_data, outcome)
        # Add explicit instruction for Judge
        market_data += f"\n\n⚠️ USER REQUESTED ANALYSIS ON: {outcome}\n"
        market_data += "⚠️ YOUR VERDICT MUST BE ABOUT THIS OUTCOME ONLY!\n"
```

### 3. Helper Method

```python
def _filter_to_outcome(self, market_data: str, requested_outcome: str) -> str:
    """
    Filter market data to highlight the user's requested outcome.
    Shows requested outcome prominently, with context of other outcomes.
    """
    # Parse market data to find the requested outcome
    # Fuzzy match if needed
    # Return filtered/highlighted version
```

### 4. Update Judge Prompt (Already Done)

Add to the top of judge.py:
```python
🚨 RULE #0: USER-SPECIFIED OUTCOME (OVERRIDES ALL OTHER RULES)
- If you see "USER REQUESTED ANALYSIS ON: [OUTCOME]", that is the ONLY outcome you should analyze
- Your verdict MUST be BUY_[THAT_OUTCOME] or HOLD
- DO NOT recommend a different outcome, even if you see better value elsewhere
- The user is asking specifically about that outcome for a reason
```

## Testing Plan

### Test Case 1: Binary Market (No Change)
```
/ask question:https://polymarket.com/event/fed-rates
Expected: Normal YES/NO analysis
```

### Test Case 2: Multi-Outcome with Outcome Specified
```
/ask question:https://polymarket.com/event/venezuela-military... outcome:December 6
Expected: Analysis of December 6 only, verdict: BUY_DECEMBER_6 or HOLD
```

### Test Case 3: Multi-Outcome without Outcome
```
/ask question:https://polymarket.com/event/venezuela-military...
Expected: List of outcomes + instruction to specify outcome
```

### Test Case 4: Expired Date Specified
```
/ask question:https://polymarket.com/event/venezuela-military... outcome:November 28
Expected: Warning that Nov 28 is expired, but still analyze if user wants
```

### Test Case 5: Invalid Outcome
```
/ask question:https://polymarket.com/event/venezuela-military... outcome:January 50
Expected: "Outcome not found. Available outcomes: ..."
```

## Rollout

1. ✅ Update Judge prompt with USER-SPECIFIED rule (DONE)
2. ✅ Add TODAY'S DATE to market data (DONE)
3. 🔄 Add `outcome` parameter to `/ask` command (NEXT)
4. 🔄 Implement filtering logic (NEXT)
5. 🔄 Test with real markets (NEXT)
6. 🔄 Deploy and monitor (NEXT)

## Success Metrics

- ✅ Zero recommendations for expired dates
- ✅ 100% accuracy when user specifies outcome
- ✅ Clear error messages when outcome not found
- ✅ User satisfaction with directed analysis

---

**Status: Ready to implement Phase 1 (outcome parameter)**

