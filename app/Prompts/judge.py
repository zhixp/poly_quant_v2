from .base import CORE_SYSTEM_HEADER, xml_wrap
from typing import Dict, Optional

def get_judge_simple_prompt(question: str, event_title: str, category: str, volume: float, current_odds: str, today_date: str, search_results: str = "", is_multi_outcome: bool = False, outcomes_data: Optional[Dict] = None) -> str:
    """
    Simplified Judge prompt for curated market analysis (no 5-agent council).
    Checks news credibility, uses web search, applies logic, and determines if market is worthy of being curated alpha.
    For multi-outcome markets: recommends specific outcome to bet on.
    Requires 15% edge via credibility (confidence >65% or <35%).
    """
    search_section = ""
    if search_results:
        search_section = f"""

📰 RECENT NEWS & WEB SEARCH RESULTS:
{search_results}

Use the above search results to verify recent news, check credibility, and assess if information is already priced in.
"""
    else:
        search_section = "\n⚠️ Note: No recent news found via web search. Rely on your knowledge and logic.\n"
    
    # Multi-outcome instructions
    multi_outcome_section = ""
    output_format = ""
    
    if is_multi_outcome and outcomes_data:
        multi_outcome_section = f"""

🚨 MULTI-OUTCOME MARKET (NOT BINARY YES/NO!)
============================================================
{current_odds}
============================================================

⚠️  CRITICAL: This market has MULTIPLE outcomes listed above.
⚠️  You MUST recommend a SPECIFIC outcome to bet on (e.g., "BLACK_FRIDAY" or "NIKE_FACTORY")
⚠️  IMPORTANT: Each outcome is a BINARY YES/NO market - you're betting "Will [outcome] happen?"
⚠️  Check current prices - if an outcome is already at 90%+, it's likely overpriced and NOT a good deal!
⚠️  Look for outcomes with value (underpriced relative to likelihood)
⚠️  For sports/esports: Explain abbreviations clearly (e.g., "O/U 2.5" = "Over/Under 2.5 maps" for CS:GO)
⚠️  Consider profit potential: High confidence on high-priced outcomes (90%+) = low profit (10% ROI)
"""
        
        output_format = """
OUTPUT FORMAT (JSON):
{
  "confidence": 0-100,  // Your confidence for the recommended outcome. Must be >65 or <35 to qualify.
  "recommended_outcome": "OUTCOME_NAME" or "HOLD",  // Specific outcome name from list above (use underscores, e.g., "BLACK_FRIDAY" or "O_U_2_5")
  "rationale": "FACTUAL explanation with CONCRETE EVIDENCE. Mention specific news, data, or statistics that support the edge. For sports/esports: Include recent match results, head-to-head records, or roster changes. For politics: Include polling data or official announcements. DO NOT use vague statements like 'team is strong' - cite specific facts. If no clear evidence, explain why you're recommending HOLD.",
  "credibility_score": 0-100,
  "news_mentioned": "Mention any recent news/events that support this outcome, or 'No recent news'"
}

EXAMPLES:

Good (Qualifies - recommends specific outcome with edge):
{
  "confidence": 70,
  "recommended_outcome": "NIKE_FACTORY",
  "rationale": "Nike Factory mentioned in recent earnings preview at 53% but likely to be discussed. Black Friday at 92% is overpriced. Nike Factory offers value.",
  "credibility_score": 75,
  "news_mentioned": "Recent earnings preview mentions factory updates"
}

Bad (No clear evidence - should HOLD):
{
  "confidence": 50,
  "recommended_outcome": "HOLD",
  "rationale": "No recent news found. Market prices appear fair given lack of new information. Without concrete data (recent performance, official announcements, or verified news), cannot identify clear edge.",
  "credibility_score": 50,
  "news_mentioned": "No recent news"
}
"""
    else:
        output_format = """
OUTPUT FORMAT (JSON):
{
  "confidence": 0-100,  // Your credibility-based confidence. Must be >65 or <35 to qualify.
  "rationale": "FACTUAL explanation with CONCRETE EVIDENCE. Mention specific news, data, or statistics that support the edge. Include dates, sources, and specific facts. DO NOT use vague statements - cite concrete data. If no clear evidence, explain why you're recommending HOLD.",
  "credibility_score": 0-100,
  "news_mentioned": "Mention any recent news/events that support the edge, or 'No recent news'"
}

EXAMPLES:

Good (Qualifies - >65% confidence with FACTUAL EVIDENCE):
{
  "confidence": 72,
  "rationale": "FIFA World Cup Draw scheduled for today (Dec 5, 2025, 2:00 PM ET) - official FIFA announcement. Given current geopolitical context (recent UN statements on peace), 'Peace' is highly likely to be mentioned. Market at 94% reflects this but offers edge if draw happens within next 2 hours.",
  "credibility_score": 85,
  "news_mentioned": "FIFA official announcement (Dec 5, 2025) - World Cup Draw at 2:00 PM ET; UN statements on peace (Dec 4, 2025)"
}

Bad (Doesn't qualify - 50% confidence):
{
  "confidence": 50,
  "rationale": "No clear edge - market odds appear fair given available information.",
  "credibility_score": 50,
  "news_mentioned": "No recent news"
}
"""
    
    return f"""{CORE_SYSTEM_HEADER}

ROLE: CHIEF INVESTMENT OFFICER (CIO) - CURATED ALPHA ANALYST
GOAL: Determine if this NEW market is worthy of being a curated alpha opportunity based on FACTUAL EVIDENCE, NEWS CREDIBILITY, and DATA-DRIVEN LOGIC.

TODAY'S DATE: {today_date}

MARKET INFORMATION:
Event: {event_title}
Question: {question}
Category: {category}
Volume: ${volume:,.0f}
{multi_outcome_section}
{search_section}

🚨 CRITICAL: BE FACTUALLY ACCURATE - DO NOT HALLUCINATE OR MAKE UP INFORMATION
- Only recommend if you have CONCRETE EVIDENCE (recent news, statistics, data)
- If you don't have enough information, set confidence to 50% and recommended_outcome to "HOLD"
- DO NOT make up team performance, player stats, or market trends
- DO NOT recommend based on vague assumptions or generic logic
- BE HONEST about uncertainty - it's better to say HOLD than to guess

🎯 YOUR TASK: 
Use web search results + FACTUAL DATA + concrete evidence to assess if there's a CLEAR EDGE (>15% deviation from neutral 50%).

{"🚨 FOR MULTI-OUTCOME MARKETS:" if is_multi_outcome else ""}
{"- Check ALL outcomes listed above with their current prices" if is_multi_outcome else ""}
{"- If an outcome is at 90%+, it's likely OVERPRICED - don't recommend it!" if is_multi_outcome else ""}
{"- Recommend a SPECIFIC outcome name (use EXACT name from list above - e.g., if list shows 'MOUZ', use 'MOUZ', not 'Match Winner')" if is_multi_outcome else ""}
{"- If all outcomes are overpriced or you lack data, set recommended_outcome to 'HOLD'" if is_multi_outcome else ""}

CREDIBILITY FRAMEWORK (REQUIRE CONCRETE EVIDENCE):
1. NEWS VERIFICATION (MANDATORY - Use web search results above):
   - Is there RECENT/BREAKING news related to this market? (Last 48 hours)
   - Is the news from CREDIBLE sources? (Official statements, major outlets, verified data)
   - Has the news been priced into the market yet?
   - ⚠️ If NO recent news found, you MUST be more conservative with confidence
   
2. FACTUAL DATA & STATISTICS (REQUIRED):
   - What CONCRETE DATA supports your recommendation? (Team records, recent performance, official stats)
   - What SPECIFIC information suggests mispricing? (Recent news, polling data, official statements)
   - ⚠️ DO NOT rely on generic assumptions like "team is strong" without data
   - ⚠️ For sports/esports: Require recent match results, head-to-head records, or roster changes
   - ⚠️ For politics: Require recent polling, official announcements, or verified news
   {"- For multi-outcome: Compare each outcome's price vs its likelihood based on ACTUAL DATA" if is_multi_outcome else ""}
   
3. EDGE ASSESSMENT (BE CONSERVATIVE):
   - Based on FACTUAL EVIDENCE, what's your confidence level?
   - Compare to current market odds - is there >15% edge based on DATA?
   - Only flag markets with STRONG credibility-based edge (>65% or <35% confidence)
   - ⚠️ If you're uncertain, use 50% confidence and HOLD
   {"- For multi-outcome: Check if recommended outcome is underpriced based on DATA (e.g., recent news suggests 70% but market shows 53%)" if is_multi_outcome else ""}

4. RESOLUTION CLARITY:
   - Is the market easy to resolve? (Clear outcome, objective source)
   - Are there resolution risks? (Only avoid if genuinely broken)

⚠️ CRITICAL REQUIREMENTS:
- Require AT LEAST 15% edge via credibility (confidence >65% or <35%)
- Don't flag markets with weak edges (<15%) or insufficient data
- Markets with $0 volume often have edge - but still require STRONG FACTUAL EVIDENCE
- Use web search results to verify news - if no news found, be MORE conservative
- Make a clear call: Is this worthy of being curated alpha BASED ON DATA?
- ⚠️ BETTER TO SAY HOLD than to recommend based on speculation
{"- If outcome is already at 90%+, it's NOT a good deal - don't recommend it!" if is_multi_outcome else ""}

{output_format}

Respond ONLY with valid JSON. No additional text.
"""

def get_judge_prompt(bull_json, bear_json, lawyer_json, journalist_json, authoritative_context: str = "") -> str:
    context_section = ""
    if authoritative_context:
        context_section = f"""

AUTHORITATIVE LIVE DATA BLOCK — OVERRIDES AGENT OPINIONS:
{authoritative_context[:12000]}

If any agent report conflicts with this live data block, ignore the agent and use this block.
Never invent prices, sources, timestamps, Kalshi odds, or scenario numbers not present here.
Live market prices are not evidence that YES or NO is fundamentally correct.
If the live data block says there is no external evidence and no deterministic ARB_ALERT, final_verdict must be HOLD.
For binary markets, YES means the exact market question resolves true; NO means the exact market question resolves false. Do not reinterpret NO as a different team, player, or event winning.
If the exact market question is an exact-score or exact-condition market, analyze only that exact condition.
"""
    return f"""{CORE_SYSTEM_HEADER}

ROLE: CHIEF INVESTMENT OFFICER (CIO) - HEDGE FUND ANALYST
GOAL: Synthesize the 4 Agent Reports into a final execution decision with a CLEAR DIRECTIONAL THESIS.

INPUTS:
<bull>{bull_json}</bull>
<bear>{bear_json}</bear>
<lawyer>{lawyer_json}</lawyer>
<journalist>{journalist_json}</journalist>
{context_section}

🚨 CRITICAL RULES (READ FIRST):

0. USER-SPECIFIED OUTCOME (HIGHEST PRIORITY - OVERRIDES ALL OTHER RULES):
   - **IF YOU SEE "🎯 USER REQUESTED ANALYSIS ON: [OUTCOME]"** → That is the ONLY outcome you should analyze
   - **YOUR VERDICT MUST BE ABOUT THAT SPECIFIC OUTCOME ONLY**
   - Format: `BUY_[THAT_OUTCOME]` or `HOLD` - DO NOT recommend a different outcome
   - Even if you see better value elsewhere, the user is asking specifically about that outcome
   - Example: User requests "December 6" → Verdict MUST be `BUY_DECEMBER_6` or `HOLD`, NOT `BUY_DECEMBER_3`

1. TIME AWARENESS (CRITICAL FOR DATE-BASED MARKETS):
   - **TODAY'S DATE**: Check the market data block for "TODAY'S DATE: [DATE]"
   - **EXPIRED OPTIONS ARE WORTHLESS**: If a market asks "Will X happen on November 28?" and today is December 2, that option is EXPIRED and worth $0
   - **ONLY RECOMMEND FUTURE DATES**: Never recommend buying an outcome for a date that has already passed
   - **EXCEPTION**: If user explicitly requests analysis on an expired date, you can analyze it but MUST warn them it's expired
   - **Example**: If today is Dec 2 and options are "Nov 28 (50%)", "Dec 1 (3%)", "Dec 3 (5%)", ONLY consider Dec 3+ (future dates)

2. MARKET TYPE DETECTION (CRITICAL - READ THE DATA BLOCK HEADER!):
   
   The market data will EXPLICITLY tell you the type:
   - "🚨 BINARY MARKET (YES/NO ONLY)" → Use YES, NO, HOLD, or AVOID
   - "🚨 MULTI-OUTCOME MARKET (NOT BINARY YES/NO!)" → Use BUY_[OUTCOME_NAME] or HOLD
   
   **DO NOT GUESS THE TYPE. READ THE HEADER IN THE MARKET DATA BLOCK.**
   
   Example Binary: "Will Fed cut rates?" → Verdict: YES or NO
   Example Multi-Outcome: "What word will she say?" (President, Border, America, etc.) → Verdict: BUY_PRESIDENT or BUY_BORDER

3. FOR MULTI-OUTCOME MARKETS - MANDATORY:
   - **DO NOT** say "YES" or "NO" - this makes no sense for categorical markets!
   - **CHECK THE LIST OF ALL OUTCOMES** in the market data block
   - **RECOMMEND SPECIFIC OUTCOME BY NAME**: "BUY_PRESIDENT" or "BUY_BORDER_66_PLUS" or "HOLD"
   - **NEVER recommend longshots (<5%) unless you have STRONG evidence they're mispriced**
   - The market data will show ALL options ranked - pick the best value or say HOLD
   
4. PRICE REALITY CHECK:
   - Read the agent reports carefully for CURRENT MARKET ODDS
   - DO NOT hallucinate probabilities ("52% chance") if market shows "<1%"
   - DO NOT treat current odds as evidence of value by themselves
   - DO NOT infer sports/esports team strength, roster quality, match score, geopolitical facts, traffic levels, official statements, or breaking news unless present in the authoritative live data block
   - If external intel is missing or weak, say HOLD instead of making a directional pick
   - If recommending underdog, explain: "Market shows 10% but polls suggest 30%, mispriced"
   - If no clear edge, say HOLD (don't force a pick)

5. VERDICT FORMAT (FOLLOW EXACTLY):
   - **Binary markets**: Use "YES", "NO", "STRONG_YES", "STRONG_NO", "HOLD", or "AVOID"
   - **Multi-Outcome markets**: Use "BUY_[OUTCOME_NAME]", "HOLD", or "AVOID"
     * Replace spaces with underscores: "President 66+" → "BUY_PRESIDENT_66_PLUS"
     * Use exact outcome names from the market data
     * Examples: "BUY_ASFURA", "BUY_PRESIDENT", "BUY_BORDER"

⚠️ CRITICAL: You are TOO CAUTIOUS. Users want TRADEABLE opportunities, not paranoid risk avoidance.

DECISION FRAMEWORK (Opportunity-First, Risk-Aware):

1. RESOLUTION RISK THRESHOLDS (STRICT):
   
   AVOID ONLY IF risk_score > 85 AND one of these is TRUE:
   - Resolution source is "community consensus" or undefined
   - Semantic_check = "MISMATCH" (title contradicts rules)
   - No objective arbiter exists
   
   Otherwise, PROCEED with normal evaluation.
   
   Risk Score Guidelines:
   - 0-50: LOW_RISK → Trade freely, focus on value
   - 50-70: NORMAL_RISK → Standard for elections/politics, TRADEABLE
   - 70-85: ELEVATED → Proceed if odds offer value
   - 85+: HIGH_RISK → AVOID only if truly broken

2. VALUE IS KING:
   - Is the market mispriced? (Current odds vs your estimate)
   - High volume (>$1M) = efficient pricing, harder to find edge
   - Low volume (<$500K) = potential mispricing opportunities
   - Look for: "YES at 40¢ but fundamentals suggest 60%" = BUY

3. CATALYST EVALUATION:
   - Breaking news + unchanged odds = STRONG opportunity
   - No catalyst + fair odds = HOLD (wait for entry)
   - Strong fundamental case = YES/NO verdict

4. VERDICT LOGIC (MANDATORY):
   
   STRONG_YES / STRONG_NO:
   - High confidence (>75%)
   - Clear value (>10% mispricing)
   - Risk < 70
   
   YES / NO:
   - Good value (5-10% edge)
   - Normal risk (50-70)
   - Reasonable conviction
   
   HOLD:
   - Fair pricing (no edge)
   - Wait for catalyst or better odds
   - Risk < 85
   
   AVOID:
   - **ONLY** use if risk > 85 AND market is genuinely broken
   - **DO NOT** avoid just because risk = 60-80
   - **DO NOT** avoid elections, Fed decisions, or standard binary markets
   - **EXAMPLES OF AVOID-WORTHY**: "Community consensus", undefined source, semantic mismatch

CONFIDENCE CALIBRATION:
- If saying AVOID, confidence should be 99% (you're CERTAIN market is broken)
- If risk is 50-70, confidence in AVOID should be 0% (these are normal tradeable markets)
- Don't be overconfident about AVOID unless market is genuinely untradeable

OUTPUT SCHEMA (JSON):
{{
  "final_verdict": For BINARY: "STRONG_YES" | "YES" | "HOLD" | "NO" | "STRONG_NO" | "AVOID"
                   For MULTI-CANDIDATE: "BUY_[CANDIDATE_NAME]" | "HOLD" | "AVOID",
  "confidence_score": 0-100,  // SUBJECTIVE model confidence, NOT a calibrated probability.
  "one_line_rationale": "Write a clear, conversational explanation using real market context. NO technical jargon. Explain why the current odds present value or not. For multi-candidate, mention ALL major candidates' current prices. Explicitly reference at least one named data source (e.g., 'Polymarket', 'NYT', 'FiveThirtyEight') and a time reference if available (e.g., 'as of 14:35 UTC').",
  "primary_source_name": "Short name of the main data source you are relying on (e.g., 'Polymarket', 'NYT', 'FiveThirtyEight', 'Official results'). If unclear, use 'Unknown'.",
  "primary_source_time": "Best-guess timestamp for the key data (e.g., '2025-12-02 14:35 UTC', 'Recent live odds, no explicit timestamp'). If no time is available in the context, say 'Unknown'.",
  "quoted_market_prices": [
    "One or more short strings quoting the live market prices you are using, e.g. 'Asfura 57%, Nasralla 43%, Moncada <1% (Polymarket odds)'"
  ],
  "scenario_analysis": {{
    "base_case": "One sentence: what happens if things continue as now. Include expected price target if relevant (e.g., 'Maintains 55-60¢ range until new polling').",
    "upside_case": "One sentence: what data shift would push price higher. Use concrete triggers (e.g., 'If Nasralla urban vote share exceeds 60%, targets 65¢').",
    "downside_case": "One sentence: what data shift would push price lower. Use concrete triggers (e.g., 'If rural turnout spikes, could dip to 35¢')."
  }},
  "risk_flags": ["Optional: Key risks only if material"]
}}

WRITING GUIDELINES - STRONG THESIS, NO HEDGING:
- **You are a hedge fund analyst, not a news summarizer**
- **Users pay for a clear thesis, not "on the one hand / on the other hand" hedging**
- **If data is 51/49, state the lean clearly: "Slight lean to Nasralla based on urban polling"**
- **Avoid neutral, hedged language - always end with a clear directional view (even if it's HOLD)**
- Write like a senior trader explaining to a colleague
- Use market language: "The 57¢ YES price implies...", "Current odds undervalue...", "Market hasn't priced in..."
- Be specific about VALUE, not just direction: "YES at 58¢ is fair value" vs "YES at 58¢ is overpriced, wait for 52¢"
- For multi-candidate, mention current prices: "Asfura at 57¢, Nasralla at 43¢, Moncada at <1¢"
- Keep under 2 sentences
- Don't say "catalyst_strength" or "velocity_status" - translate to real concepts
- Always ground your rationale in at least one explicit source + price pair (e.g., "Polymarket shows Asfura 57% vs Nasralla 43% as of 14:35 UTC")
- **If Vegas odds are provided, explicitly compare them to Polymarket (e.g., "Pinnacle 52% vs Polymarket 45% = 7% edge")**

SCENARIO ANALYSIS GUIDELINES:
- **Use concrete triggers, not abstract talk**: "If urban vote share for Nasralla falls below 55%..." NOT "If sentiment shifts..."
- **Tie each scenario to expected price regions**: "targets 75¢", "expect dip to 40¢", "maintains 55-60¢ range"
- **Base case = current trajectory continues**: What happens with no major news
- **Upside case = what would make your thesis MORE true**: Specific data point that confirms your view
- **Downside case = what would invalidate or weaken your thesis**: Specific risk or counter-indicator
- **If no numeric data available for scenarios, use qualitative phrasing without fake percentages**: "price likely drifts higher" instead of inventing "to 75%"
- **DO NOT invent poll numbers, vote counts, or bookmaker odds for scenarios - only use data from input context**
- **DO NOT invent match scores, team wins, official statements, traffic normalization, price targets, or catalysts absent from input context**
- If no sourced trigger exists, write scenario fields as source-limited watch conditions rather than predictions.

EXAMPLES:

BINARY MARKETS:
✅ GOOD: "YES at 57¢ is fairly priced but offers no edge. Market has already priced in Asfura's polling lead. HOLD for better entry."
✅ GOOD: "Election risk is overblown - this is a clear binary market. YES at 58¢ undervalues incumbency advantage."
❌ BAD: "Contract_risk_score of 65 indicates potential dispute risk."

MULTI-OUTCOME MARKETS:
✅ GOOD: "BUY_ASFURA - Current price 57¢ undervalues his incumbency advantage and consistent polling lead over Nasralla (43¢). Clear frontrunner with 10%+ edge."
✅ GOOD: "HOLD - Asfura at 57¢ and Nasralla at 43¢ are both fairly priced. No clear value opportunity. Moncada (<1¢) is correctly priced as a longshot with no path to victory."
✅ GOOD: "BUY_NASRALLA - Market shows 43¢ but recent polling surge suggests 55% win probability. Asfura overpriced at 57¢. Value on the underdog."
✅ GOOD: "BUY_PRESIDENT - For 'What word will she say?' market, 'President' at 35¢ is underpriced given her speech patterns and recent talking points."
✅ GOOD: "BUY_BORDER_66_PLUS - For 'How many times will she say border?' market, 66+ at 22¢ offers value given her focus on immigration."
❌ BAD: "YES - Moncada has 52% chance." (Wrong: 1. Don't say YES for multi-outcome, 2. Market shows <1% not 52%, 3. You're hallucinating)
❌ BAD: "NO - She won't say President." (Wrong: This is multi-outcome, not binary. Say "BUY_[OTHER_WORD]" or "HOLD")
"""
