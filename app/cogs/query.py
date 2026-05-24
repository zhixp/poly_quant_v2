"""
Query Cog: AI Analysis Slash Command
Modern /ask command for prediction market intelligence.
"""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from app.core.server_manager import server_manager
from app.core.database import db
from app.core.market_data import market_resolver
from app.core.market_mapping import market_mapping_service
from app.core.bookmaker_client import bookmaker_client
from app.core.metrics import metrics, MetricNames

logger = logging.getLogger("QueryCog")

class QueryCog(commands.Cog):
    """AI Market Analysis Commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def _fetch_vegas_odds(self, query: str, market_data: str) -> str:
        """
        Fetch bookmaker odds for cross-venue comparison.
        Returns formatted string for prompt injection, or empty string if no mappings.
        """
        try:
            # Extract Polymarket event slug from the query or market_data
            # Simple heuristic: look for polymarket.com/event/SLUG pattern
            import re
            event_slug = None
            market_slug = None
            
            # Try to extract from query first
            url_match = re.search(r'polymarket\.com/event/([^/?#]+)(?:/([^/?#]+))?', query)
            if url_match:
                event_slug = url_match.group(1)
                market_slug = url_match.group(2)
            
            # If not in query, try market_data
            if not event_slug and market_data:
                url_match = re.search(r'Event: (.+)', market_data)
                if url_match:
                    # Convert event title to slug (rough heuristic)
                    event_title = url_match.group(1).strip()
                    event_slug = event_title.lower().replace(' ', '-').replace('?', '')
            
            if not event_slug:
                logger.debug("No Polymarket event slug found, skipping Vegas odds")
                return ""
            
            # Look up mappings for this event
            mappings = await market_mapping_service.get_mappings_for_polymarket(
                event_slug,
                market_slug=market_slug,
                exact_market_only=bool(market_slug),
            )
            
            if not mappings:
                logger.debug(f"No bookmaker mappings found for event: {event_slug}")
                return ""
            
            # Fetch odds from each mapped venue
            vegas_lines = [
                "\n" + "="*60,
                "🏦 SHARP BOOKMAKER ODDS (VEGAS)",
                "="*60,
                f"Event: {mappings[0].normalized_name}",
                f"Polymarket event: {event_slug}" + (f" / market: {market_slug}" if market_slug else ""),
                ""
            ]
            
            for mapping in mappings:
                try:
                    odds = await bookmaker_client.get_odds(mapping.venue, mapping.venue_market_id)
                    
                    if odds:
                        vegas_lines.append(f"**{odds.venue.upper()}:**")
                        
                        # Format outcomes with implied probabilities / prediction-market prices
                        for outcome, prob in odds.implied_probs.items():
                            decimal_odds = odds.outcomes.get(outcome, 0)
                            if odds.venue.lower() == "kalshi":
                                vegas_lines.append(f"  {outcome}: {prob*100:.1f}% ({prob*100:.0f}¢)")
                            else:
                                vegas_lines.append(
                                    f"  {outcome}: {prob*100:.1f}% "
                                    f"(Decimal: {decimal_odds:.2f})"
                                )
                        
                        vegas_lines.append("")

                        if (
                            odds.venue.lower() == "kalshi"
                            and market_slug
                            and market_mapping_service.is_exact_active_mapping(
                                mapping, event_slug, market_slug, venue="kalshi"
                            )
                        ):
                            arb = await bookmaker_client.check_polymarket_kalshi_arb(
                                market_slug,
                                mapping.venue_market_id,
                            )
                            vegas_lines.extend(self._format_arb_check(arb))
                
                except Exception as e:
                    logger.warning(f"Failed to fetch odds from {mapping.venue}: {e}")
                    continue
            
            vegas_lines.extend([
                "="*60,
                "⚠️  USE THESE VEGAS ODDS TO ASSESS VALUE VS POLYMARKET.",
                "⚠️  POSITIVE SPREAD = POLYMARKET UNDERPRICED (BUY OPPORTUNITY).",
                "⚠️  NEGATIVE SPREAD = POLYMARKET OVERPRICED (SELL/AVOID).",
                "="*60 + "\n"
            ])
            
            return "\n".join(vegas_lines)
        
        except Exception as e:
            logger.error(f"Error fetching Vegas odds: {e}", exc_info=True)
            return ""

    def _format_arb_check(self, arb: dict) -> list:
        lines = [
            "DETERMINISTIC ARBITRAGE CONTEXT (AUTHORITATIVE; exact active DB mapping only):",
            "  Exact mapping used: true",
            "  Fuzzy matching used: false",
            "  Executable asks only: true",
            f"  Status: {arb.get('status', 'WATCH')}",
        ]
        for direction, data in (arb.get("directions") or {}).items():
            if data.get("status") == "WATCH" and data.get("reason"):
                lines.append(f"  {direction}: WATCH ({data['reason']})")
                continue
            lines.append(
                "  "
                f"{direction}: {data.get('status', 'WATCH')} | "
                f"cost={data.get('cost_per_unit')} | "
                f"profit/unit={data.get('profit_per_unit')} | "
                f"max_units={data.get('max_units')} | "
                f"total_profit={data.get('total_profit')}"
            )
        lines.append("  No fuzzy mappings or midpoint/last prices are eligible for ARB ALERT.")
        lines.append('  Judge rule: Do not claim executable arbitrage unless status is "ARB_ALERT"; if WATCH, explain why it is only a watch condition.')
        lines.append("")
        return lines
    
    @app_commands.command(name="ask", description="🤖 Get AI analysis on prediction markets")
    @app_commands.describe(
        question="Polymarket URL or question about prediction markets",
        outcome="(Optional) Specific outcome to analyze (e.g., 'December 6', 'President 66+')"
    )
    async def ask(self, interaction: discord.Interaction, question: str, outcome: str = None):
        """
        AI-powered market intelligence using 5-agent council.
        """
        await interaction.response.defer()
        
        # Multi-Tenant Permission Check
        if interaction.guild:
            config = await server_manager.get_server_config(interaction.guild.id)
            
            if not config:
                await interaction.followup.send(
                    "⚠️ **Server Not Configured**\n"
                    "Ask an admin to run `/setup` to enable PolyQuant in this server.",
                    ephemeral=True
                )
                return
            
            if not config.enabled:
                await interaction.followup.send(
                    "⏸️ **PolyQuant is disabled** in this server.",
                    ephemeral=True
                )
                return
            
            if config.is_banned:
                await interaction.followup.send(
                    "⛔ **This server is banned** from using PolyQuant.",
                    ephemeral=True
                )
                return
            
            # Rate Limit Check
            can_query = await server_manager.increment_query_count(interaction.guild.id)
            if not can_query:
                await interaction.followup.send(
                    f"⏱️ **Daily Limit Reached**\n"
                    f"Your server has used all **{config.max_queries_per_day}** queries for today.\n"
                    f"**Tier:** {config.tier.upper()}\n\n"
                    f"*Upgrade to Pro for 500 queries/day or Enterprise for unlimited access.*",
                    ephemeral=True
                )
                return
        
        # Sanitization
        safe_question = question.replace("@everyone", "").replace("@here", "")[:200]
        
        # Track request
        metrics.increment(MetricNames.ASK_REQUESTS)
        
        # 1. Memory Check (Speed)
        cached_response = db.get_cache(safe_question)
        if cached_response:
            metrics.increment(MetricNames.ASK_CACHE_HITS)
            await interaction.followup.send(f"⚡ **Instant Recall (Cache):**\n{cached_response}")
            return
        
        metrics.increment(MetricNames.ASK_CACHE_MISSES)

        # Send initial status
        await interaction.followup.send(f"🔍 **PolyQuant is Scanning:** *{safe_question}*...")

        try:
            # 2. Fetch Live Market Prices (CRITICAL: Prevents hallucination)
            try:
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
            
            # 2.5 Fetch Vegas/Bookmaker Odds (Cross-venue arbitrage data)
            vegas_data = await self._fetch_vegas_odds(safe_question, market_data)
            
            # 3. Gather News/Context (Eyes)
            search_data = await self.bot.router.deep_search(safe_question)
            
            # 4. Combine Market Prices + Vegas Odds + News Context
            # CRITICAL: Market data comes FIRST so AI sees real prices before anything else
            context_parts = []
            
            if market_data:
                # If user specified an outcome, add explicit instruction
                if outcome:
                    logger.info(f"🎯 User requested analysis on outcome: {outcome}")
                    market_data += f"\n\n{'='*60}\n"
                    market_data += f"🎯 USER REQUESTED ANALYSIS ON: {outcome}\n"
                    market_data += f"{'='*60}\n"
                    market_data += f"⚠️  CRITICAL: Analyze ONLY this outcome!\n"
                    market_data += f"⚠️  Your verdict MUST be about '{outcome}' specifically\n"
                    market_data += f"⚠️  DO NOT recommend a different outcome\n"
                    market_data += f"⚠️  Format: BUY_{outcome.upper().replace(' ', '_')} or HOLD\n"
                    market_data += f"{'='*60}\n"
                
                context_parts.append(market_data)
                logger.info(f"✅ Injected live Polymarket prices into context")
            else:
                logger.warning(f"⚠️ No Polymarket prices found - AI may hallucinate!")
            
            if vegas_data:
                context_parts.append(vegas_data)
                logger.info(f"✅ Injected Vegas/bookmaker odds into context")
            
            if search_data:
                context_parts.append(search_data)
            
            context_data = "\n\n".join(context_parts) if context_parts else ""
            
            if not context_data or len(context_data) < 50:
                await interaction.edit_original_response(
                    content=f"🔍 **PolyQuant is Scanning:** *{safe_question}*...\n⚠️ **Intel Low:** Searching deeper archives..."
                )

            # 5. The Council Deliberates (Brain)
            await interaction.edit_original_response(
                content=f"🔍 **PolyQuant is Scanning:** *{safe_question}*...\n⚖️ **The 5 Agents are Debating...**"
            )
            verdict, opinions = await self.bot.council.deliberate(safe_question, context_data)

            # 4. Format Output - Clean & Simple
            import json
            import re
            
            # Try to parse verdict as JSON, fallback to raw text
            try:
                # Extract JSON from markdown code blocks if present
                verdict_text = verdict
                if "```json" in verdict_text:
                    verdict_text = re.search(r'```json\s*(\{.*?\})\s*```', verdict_text, re.DOTALL).group(1)
                elif "```" in verdict_text:
                    verdict_text = re.search(r'```\s*(\{.*?\})\s*```', verdict_text, re.DOTALL).group(1)
                
                # Parse JSON
                verdict_data = json.loads(verdict_text)
                
                # Extract clean fields
                final_verdict = verdict_data.get('final_verdict', 'UNCERTAIN')
                confidence = verdict_data.get('confidence_score', 0)
                rationale = verdict_data.get('one_line_rationale', 'Analysis inconclusive.')
                primary_source = verdict_data.get('primary_source_name')
                primary_source_time = verdict_data.get('primary_source_time')
                quoted_prices = verdict_data.get('quoted_market_prices')
                scenarios = verdict_data.get('scenario_analysis', {})
                
                # Format verdict nicely for multi-candidate markets
                if final_verdict.startswith('BUY_'):
                    # Multi-candidate market: "BUY_ASFURA" → "BUY ASFURA"
                    candidate_name = final_verdict.replace('BUY_', '').replace('_', ' ').title()
                    display_verdict = f"🎯 BUY {candidate_name}"
                elif final_verdict in ['YES', 'STRONG_YES']:
                    display_verdict = f"✅ {final_verdict}"
                elif final_verdict in ['NO', 'STRONG_NO']:
                    display_verdict = f"❌ {final_verdict}"
                elif final_verdict == 'HOLD':
                    display_verdict = f"⏸️ {final_verdict}"
                elif final_verdict == 'AVOID':
                    display_verdict = f"⛔ {final_verdict}"
                else:
                    display_verdict = final_verdict
                
                # Build optional structured data block
                data_lines = []
                if primary_source:
                    if primary_source_time:
                        data_lines.append(f"Source: {primary_source} (time: {primary_source_time})")
                    else:
                        data_lines.append(f"Source: {primary_source}")
                elif primary_source_time:
                    data_lines.append(f"Data time: {primary_source_time}")

                if quoted_prices:
                    if isinstance(quoted_prices, list):
                        # Filter out empties and stringify defensively
                        cleaned_prices = [str(p).strip() for p in quoted_prices if str(p).strip()]
                        if cleaned_prices:
                            data_lines.append("Prices:")
                            data_lines.extend(f"- {p}" for p in cleaned_prices)
                    else:
                        prices_str = str(quoted_prices).strip()
                        if prices_str:
                            data_lines.append(f"Prices: {prices_str}")

                data_block = ""
                if data_lines:
                    data_block = "\n\n**Data:**\n" + "\n".join(data_lines)
                
                # Build scenario block if present
                scenario_block = ""
                if scenarios and isinstance(scenarios, dict):
                    base = scenarios.get('base_case', '').strip()
                    upside = scenarios.get('upside_case', '').strip()
                    downside = scenarios.get('downside_case', '').strip()
                    
                    if base or upside or downside:
                        scenario_lines = []
                        if base:
                            scenario_lines.append(f"**Base:** {base}")
                        if upside:
                            scenario_lines.append(f"**Upside:** {upside}")
                        if downside:
                            scenario_lines.append(f"**Downside:** {downside}")
                        
                        if scenario_lines:
                            scenario_block = "\n\n**Scenarios:**\n" + "\n".join(scenario_lines)

                # Build clean output
                final_output = f"""**🎯 POLYQUANT ANALYSIS**

**Question:** {safe_question}

**Verdict:** {display_verdict}
**Model confidence (0–100, heuristic):** {confidence}%

**Reasoning:**
{rationale}{data_block}{scenario_block}

*Note: Model confidence is subjective and not a calibrated probability. Analysis complete. Data verified across multiple sources.*"""
                
            except (json.JSONDecodeError, AttributeError, KeyError) as e:
                # Fallback: Use raw text if JSON parsing fails
                logger.warning(f"Failed to parse verdict JSON: {e}")
                metrics.increment(MetricNames.ASK_JSON_PARSE_FAILURES)
                final_output = f"""**🎯 POLYQUANT ANALYSIS**

**Question:** {safe_question}

{verdict}

*Analysis complete.*"""
            
            # 5. Save to Memory (with guild_id for multi-tenant analytics)
            guild_id = interaction.guild.id if interaction.guild else None
            db.save_log(safe_question, final_output, guild_id)
            
            await interaction.edit_original_response(content=final_output)

        except Exception as e:
            logger.error(f"Ask Command Failed: {e}", exc_info=True)
            metrics.increment(MetricNames.ASK_ERRORS)
            
            # Try to send error to user
            try:
                await interaction.edit_original_response(
                    content=f"❌ **Error:** Intelligence systems unresponsive.\n\n"
                            f"*The team has been notified. Please try again in a moment.*"
                )
            except:
                # If edit fails, try followup
                try:
                    await interaction.followup.send(
                        content="❌ **Error:** Intelligence systems unresponsive.",
                        ephemeral=True
                    )
                except:
                    pass
            
            from app.core.watchdog import watchdog
            if "Intelligence systems" not in str(e):
                await watchdog.alert("Command /ask", str(e), "ERROR")

async def setup(bot):
    """Loads the cog."""
    await bot.add_cog(QueryCog(bot))

