"""
Admin Cog: Debug and administrative commands
Restricted to bot owner or configured admin roles.
"""
import asyncio
import logging
import time
import os
from datetime import datetime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from app.config import Config
from app.core.server_manager import server_manager
from app.core.database import db
from app.core.metrics import metrics, MetricNames

logger = logging.getLogger("AdminCog")

class AdminCog(commands.Cog):
    """Administrative and debug commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.sec_rss_url = os.getenv("SEC_RSS_URL", "https://www.sec.gov/news/pressreleases.rss")
        self.court_rss_url = os.getenv(
            "COURT_RSS_URL", "https://www.courtlistener.com/api/rest/v3/opinions/?format=rss"
        )
    
    @app_commands.command(name="debug_config", description="🔧 [ADMIN] Show server configuration status")
    @app_commands.checks.has_permissions(administrator=True)
    async def debug_config(self, interaction: discord.Interaction):
        """
        Shows current server configuration and alert channel status.
        Helps diagnose why LagHunter might be silent.
        """
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get all servers with alert channels configured
            alert_channels = await server_manager.get_all_alert_channels()
            
            # Get current server config
            if interaction.guild:
                config = await server_manager.get_server_config(interaction.guild.id)
                
                if not config:
                    await interaction.followup.send(
                        "⚠️ **This server is not registered.**\n"
                        "Run `/setup` to configure PolyQuant.",
                        ephemeral=True
                    )
                    return
                
                # Build status report
                status_lines = [
                    "**🔧 SERVER CONFIGURATION DEBUG**\n",
                    f"**Guild:** {interaction.guild.name} ({interaction.guild.id})",
                    f"**Tier:** {config.tier.upper()}",
                    f"**Enabled:** {'✅ Yes' if config.enabled else '❌ No'}",
                    f"**Banned:** {'⛔ Yes' if config.is_banned else '✅ No'}",
                    "",
                    "**Channels:**",
                    f"  Alert Channel: {f'<#{config.alert_channel_id}>' if config.alert_channel_id else '❌ Not Set'}",
                    f"  Query Channel: {f'<#{config.query_channel_id}>' if config.query_channel_id else '❌ Not Set'}",
                    "",
                    "**Rate Limits:**",
                    f"  Queries Today: {config.query_count_today}/{config.max_queries_per_day}",
                    f"  Last Reset: {config.last_reset.strftime('%Y-%m-%d %H:%M UTC') if config.last_reset else 'Never'}",
                    "",
                    "**Global Status:**",
                    f"  Total servers with alerts: {len(alert_channels)}",
                    "",
                    "**LagHunter Status:**"
                ]
                
                if config.alert_channel_id:
                    status_lines.append("  ✅ This server WILL receive lag alerts")
                else:
                    status_lines.append("  ⚠️ This server will NOT receive lag alerts (no alert_channel_id)")
                    status_lines.append("  💡 Run `/setup` and configure an alert channel")
                
                await interaction.followup.send("\n".join(status_lines), ephemeral=True)
            else:
                # DM context
                await interaction.followup.send(
                    f"**Global Status:**\n"
                    f"Total servers with alert channels: {len(alert_channels)}\n\n"
                    f"*Run this command in a server to see server-specific config.*",
                    ephemeral=True
                )
        
        except Exception as e:
            logger.error(f"Debug config failed: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ **Error:** {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="test_lag_hunter", description="🧪 [ADMIN] Test LagHunter system")
    @app_commands.describe(force_alert="Send a synthetic test alert to verify Discord path")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_lag_hunter(self, interaction: discord.Interaction, force_alert: bool = True):
        """
        Runs a single LagHunter scan in test mode.
        Useful for debugging why the hunter is silent.
        """
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check if bot has lag_hunter attribute
            if not hasattr(self.bot, 'lag_hunter'):
                await interaction.followup.send(
                    "❌ **LagHunter not initialized.**\n"
                    "The bot may not have started the LagHunter service.",
                    ephemeral=True
                )
                return
            
            await interaction.followup.send(
                "🧪 **Running LagHunter test...**\n"
                "This will take a few seconds...",
                ephemeral=True
            )
            
            # Run test
            result = await self.bot.lag_hunter.test_once(force_alert=force_alert)
            
            # Format results
            if result['status'] == 'success':
                scan_summary = result.get('last_scan', {})
                
                output_lines = [
                    "**🧪 LAGHUNTER TEST RESULTS**\n",
                    f"**Status:** ✅ Success",
                    f"**Test Alert Sent:** {'✅ Yes' if result.get('test_alert_sent') else '❌ No'}",
                    "",
                    "**Last Scan Metrics:**",
                    f"  Scan ID: #{scan_summary.get('scan_id', 'N/A')}",
                    f"  Feeds OK: {scan_summary.get('feeds_fetched', 0)}/{scan_summary.get('feeds_fetched', 0) + scan_summary.get('feeds_failed', 0)}",
                    f"  Total Entries: {scan_summary.get('total_entries', 0)}",
                    f"  Fresh Entries: {scan_summary.get('fresh_entries', 0)}",
                    f"  Already Seen: {scan_summary.get('already_seen', 0)}",
                    f"  Markets Fetched: {scan_summary.get('markets_fetched', 0)}",
                    f"  Matches Found: {scan_summary.get('matches_found', 0)}",
                    f"  Alerts Sent: {scan_summary.get('alerts_sent', 0)}",
                    "",
                    "**Interpretation:**"
                ]
                
                # Add diagnostic hints
                if scan_summary.get('feeds_fetched', 0) == 0:
                    output_lines.append("  ⚠️ No RSS feeds fetched - check network/RSS URLs")
                elif scan_summary.get('fresh_entries', 0) == 0:
                    output_lines.append("  ℹ️ No fresh entries (all >20 minutes old)")
                elif scan_summary.get('markets_fetched', 0) == 0:
                    output_lines.append("  ⚠️ No Polymarket markets fetched - check ClobClient")
                elif scan_summary.get('matches_found', 0) == 0:
                    output_lines.append("  ℹ️ No keyword matches between headlines and markets")
                elif scan_summary.get('alerts_sent', 0) == 0:
                    output_lines.append("  ⚠️ Matches found but no alerts sent - check alert channel config")
                else:
                    output_lines.append("  ✅ System operational")
                
                await interaction.edit_original_response(content="\n".join(output_lines))
            else:
                await interaction.edit_original_response(
                    content=f"❌ **Test Failed:**\n{result.get('error', 'Unknown error')}"
                )
        
        except Exception as e:
            logger.error(f"Test lag hunter failed: {e}", exc_info=True)
            await interaction.edit_original_response(
                content=f"❌ **Error:** {str(e)}"
            )
    
    @app_commands.command(name="test_geo_sniper", description="🛰️ [ADMIN] Test Geo Sniper system")
    @app_commands.describe(force_alert="Send a synthetic test alert to verify Discord path")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_geo_sniper(self, interaction: discord.Interaction, force_alert: bool = True):
        """Runs one Geo Sniper scan and optionally sends a test alert."""
        await interaction.response.defer(ephemeral=True)

        try:
            if not hasattr(self.bot, 'geo_sniper'):
                await interaction.followup.send(
                    "❌ **Geo Sniper not initialized.**",
                    ephemeral=True
                )
                return

            await interaction.followup.send(
                "🛰️ **Running Geo Sniper test...**\nChecking watched geopolitical markets + source language.",
                ephemeral=True
            )

            result = await self.bot.geo_sniper.test_once(force_alert=force_alert)
            scan_summary = result.get('last_scan', {})
            output_lines = [
                "**🛰️ GEO SNIPER TEST RESULTS**\n",
                f"**Status:** ✅ {result.get('status', 'unknown')}",
                f"**Test Alert Sent:** {'✅ Yes' if result.get('test_alert_sent') else '❌ No'}",
                "",
                "**Last Scan Metrics:**",
                f"  Scan ID: #{scan_summary.get('scan_id', 'N/A')}",
                f"  Markets Checked: {scan_summary.get('markets_checked', 0)}",
                f"  Source Hits: {scan_summary.get('source_hits', 0)}",
                f"  Signals Found: {scan_summary.get('signals_found', 0)}",
                f"  Alerts Sent: {scan_summary.get('alerts_sent', 0)}",
                f"  Duration: {scan_summary.get('duration_ms', 0)}ms",
                "",
                "**Interpretation:**",
            ]
            if scan_summary.get('markets_checked', 0) == 0:
                output_lines.append("  ⚠️ No watched markets fetched from Gamma API")
            elif scan_summary.get('source_hits', 0) == 0:
                output_lines.append("  ℹ️ No relevant source language found this scan")
            elif scan_summary.get('signals_found', 0) == 0:
                output_lines.append("  ℹ️ No price/rule dislocation above thresholds")
            elif scan_summary.get('alerts_sent', 0) == 0:
                output_lines.append("  ⚠️ Signals found but no alert channel configured")
            else:
                output_lines.append("  ✅ Geo Sniper operational")

            await interaction.edit_original_response(content="\n".join(output_lines))
        except Exception as e:
            logger.error(f"Test geo sniper failed: {e}", exc_info=True)
            await interaction.edit_original_response(content=f"❌ **Error:** {str(e)}")

    @app_commands.command(name="geo_sniper_stats", description="📊 [ADMIN] Show Geo Sniper statistics")
    @app_commands.checks.has_permissions(administrator=True)
    async def geo_sniper_stats(self, interaction: discord.Interaction):
        """Shows current Geo Sniper runtime statistics."""
        await interaction.response.defer(ephemeral=True)
        try:
            if not hasattr(self.bot, 'geo_sniper'):
                await interaction.followup.send("❌ **Geo Sniper not initialized.**", ephemeral=True)
                return
            sniper = self.bot.geo_sniper
            summary = sniper.last_scan_summary or {}
            await interaction.followup.send(
                "**📊 GEO SNIPER RUNTIME STATISTICS**\n\n"
                f"**Enabled:** {'✅ Yes' if sniper.enabled else '❌ No'}\n"
                f"**Interval:** {sniper.interval_seconds}s\n"
                f"**Total Scans:** {sniper.scan_count}\n"
                f"**Watched Events:** {', '.join(sniper.event_slugs)}\n"
                f"**Seen Alerts:** {len(sniper.seen_alerts)}\n\n"
                "**Last Scan:**\n"
                f"  Markets Checked: {summary.get('markets_checked', 0)}\n"
                f"  Source Hits: {summary.get('source_hits', 0)}\n"
                f"  Signals Found: {summary.get('signals_found', 0)}\n"
                f"  Alerts Sent: {summary.get('alerts_sent', 0)}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Geo stats failed: {e}", exc_info=True)
            await interaction.followup.send(f"❌ **Error:** {str(e)}", ephemeral=True)

    @app_commands.command(name="lag_hunter_stats", description="📊 [ADMIN] Show LagHunter statistics")
    @app_commands.checks.has_permissions(administrator=True)
    async def lag_hunter_stats(self, interaction: discord.Interaction):
        """Shows current LagHunter runtime statistics."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            if not hasattr(self.bot, 'lag_hunter'):
                await interaction.followup.send(
                    "❌ **LagHunter not initialized.**",
                    ephemeral=True
                )
                return
            
            hunter = self.bot.lag_hunter
            last_scan = hunter.last_scan_summary
            
            output_lines = [
                "**📊 LAGHUNTER RUNTIME STATISTICS**\n",
                f"**Total Scans:** {hunter.scan_count}",
                f"**Zero-Alert Streak:** {hunter.zero_alert_streak} scans",
                f"**Seen Links:** {len(hunter.seen_links)} cached",
                "",
                "**Last Scan Summary:**"
            ]
            
            if last_scan:
                output_lines.extend([
                    f"  Scan ID: #{last_scan.get('scan_id', 'N/A')}",
                    f"  Feeds: {last_scan.get('feeds_fetched', 0)} OK, {last_scan.get('feeds_failed', 0)} failed",
                    f"  Entries: {last_scan.get('total_entries', 0)} total, {last_scan.get('fresh_entries', 0)} fresh",
                    f"  Markets: {last_scan.get('markets_fetched', 0)}",
                    f"  Matches: {last_scan.get('matches_found', 0)}",
                    f"  Alerts: {last_scan.get('alerts_sent', 0)}",
                    "",
                    "**Per-Feed Details:**"
                ])
                
                for source, stats in last_scan.get('feed_details', {}).items():
                    output_lines.append(
                        f"  {source}: {stats['total']} entries, "
                        f"{stats['fresh']} fresh, {stats['matches']} matches"
                    )
            else:
                output_lines.append("  No scans completed yet")
            
            await interaction.followup.send("\n".join(output_lines), ephemeral=True)
        
        except Exception as e:
            logger.error(f"Stats command failed: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ **Error:** {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="metrics", description="📊 [ADMIN] Show system metrics")
    @app_commands.checks.has_permissions(administrator=True)
    async def show_metrics(self, interaction: discord.Interaction):
        """Shows production metrics and monitoring data."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            summary = metrics.get_summary()
            
            output_lines = [
                "**📊 SYSTEM METRICS**\n",
                f"**Uptime:** {summary['uptime_hours']:.1f} hours",
                "",
                "**📞 /ask Command:**",
                f"  Total Requests: {metrics.get_counter(MetricNames.ASK_REQUESTS)}",
                f"  Cache Hits: {metrics.get_counter(MetricNames.ASK_CACHE_HITS)}",
                f"  Cache Misses: {metrics.get_counter(MetricNames.ASK_CACHE_MISSES)}",
                f"  JSON Parse Failures: {metrics.get_counter(MetricNames.ASK_JSON_PARSE_FAILURES)}",
                f"  Errors: {metrics.get_counter(MetricNames.ASK_ERRORS)}",
                "",
                "**🔍 Lag Hunter:**",
                f"  Total Scans: {metrics.get_counter(MetricNames.LAG_HUNTER_SCANS)}",
                f"  Total Matches: {metrics.get_counter(MetricNames.LAG_HUNTER_MATCHES)}",
                f"  Total Alerts: {metrics.get_counter(MetricNames.LAG_HUNTER_ALERTS)}",
                f"  Zero-Alert Streak: {metrics.get_gauge(MetricNames.LAG_HUNTER_ZERO_ALERT_STREAK):.0f} scans",
                f"  Errors: {metrics.get_counter(MetricNames.LAG_HUNTER_ERRORS)}",
                "",
                "**📊 Market Data:**",
                f"  Polymarket Fetches: {metrics.get_counter(MetricNames.MARKET_DATA_FETCHES)}",
                f"  Vegas Odds Fetches: {metrics.get_counter(MetricNames.VEGAS_ODDS_FETCHES)}",
                f"  Errors: {metrics.get_counter(MetricNames.MARKET_DATA_ERRORS) + metrics.get_counter(MetricNames.VEGAS_ODDS_ERRORS)}",
                "",
                "**⚡ Rate Limiting:**",
                f"  Rate Limit Hits: {metrics.get_counter(MetricNames.RATE_LIMIT_HITS)}"
            ]
            
            # Calculate derived metrics
            ask_total = metrics.get_counter(MetricNames.ASK_REQUESTS)
            if ask_total > 0:
                cache_hit_rate = (metrics.get_counter(MetricNames.ASK_CACHE_HITS) / ask_total) * 100
                output_lines.append(f"\n**Cache Hit Rate:** {cache_hit_rate:.1f}%")
            
            lag_scans = metrics.get_counter(MetricNames.LAG_HUNTER_SCANS)
            if lag_scans > 0:
                alert_rate = (metrics.get_counter(MetricNames.LAG_HUNTER_ALERTS) / lag_scans) * 100
                output_lines.append(f"**Lag Hunter Alert Rate:** {alert_rate:.1f}%")
            
            await interaction.followup.send("\n".join(output_lines), ephemeral=True)
        
        except Exception as e:
            logger.error(f"Metrics command failed: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ **Error:** {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="health", description="🏥 [ADMIN] Run system health diagnostics")
    @app_commands.checks.has_permissions(administrator=True)
    async def health_check(self, interaction: discord.Interaction):
        """Runs connectivity checks against core external services."""
        await interaction.response.defer(ephemeral=True)

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                polymarket_task = asyncio.create_task(self._check_polymarket(session))
                cryptopanic_task = asyncio.create_task(self._check_cryptopanic(session))
                rss_task = asyncio.create_task(self._check_rss_feeds(session))

                polymarket_status, cryptopanic_status, rss_status = await asyncio.gather(
                    polymarket_task, cryptopanic_task, rss_task
                )

            exa_status, tavily_status = await asyncio.gather(
                self._check_exa(),
                self._check_tavily()
            )

            overall_color = self._determine_color([
                polymarket_status['status'],
                cryptopanic_status['status'],
                exa_status['status'],
                tavily_status['status'],
                *(r['status'] for r in rss_status)
            ])

            embed = discord.Embed(
                title="🏥 System Health Check",
                color=overall_color
            )
            embed.add_field(
                name="Polymarket (Gamma)",
                value=self._format_status(polymarket_status),
                inline=False
            )
            embed.add_field(
                name="Exa AI",
                value=self._format_status(exa_status),
                inline=False
            )
            embed.add_field(
                name="Tavily",
                value=self._format_status(tavily_status),
                inline=False
            )
            embed.add_field(
                name="CryptoPanic",
                value=self._format_status(cryptopanic_status),
                inline=False
            )

            rss_value = " | ".join(
                f"{self._status_icon(r['status'])} {r['name']}"
                for r in rss_status
            ) or "No RSS feeds configured"
            embed.add_field(name="RSS Feeds", value=rss_value, inline=False)

            embed.set_footer(text=f"Checked at {datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC")

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"/health diagnostics failed: {e}", exc_info=True)
            await interaction.followup.send(f"❌ **Health check failed:** {e}", ephemeral=True)

    async def _check_polymarket(self, session: aiohttp.ClientSession):
        url = "https://gamma-api.polymarket.com/events"
        params = {"limit": "1"}
        start = time.perf_counter()
        try:
            async with session.get(url, params=params) as resp:
                latency_ms = (time.perf_counter() - start) * 1000
                if resp.status == 200:
                    return {"status": "ok", "message": f"Online (Latency: {latency_ms:.0f}ms)"}
                text = await resp.text()
                return {"status": "error", "message": f"HTTP {resp.status}: {text[:80]}"}
        except Exception as e:
            return {"status": "error", "message": f"Request failed: {e}"}

    async def _check_cryptopanic(self, session: aiohttp.ClientSession):
        if not Config.CRYPTOPANIC_API_KEY:
            return {"status": "warn", "message": "No API key configured"}
        url = "https://cryptopanic.com/api/v1/posts/"
        params = {"auth_token": Config.CRYPTOPANIC_API_KEY, "public": "true"}
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return {"status": "ok", "message": "Online"}
                elif resp.status == 401:
                    return {"status": "error", "message": "Invalid key (401)"}
                return {"status": "error", "message": f"HTTP {resp.status}"}
        except Exception as e:
            return {"status": "error", "message": f"Request failed: {e}"}

    async def _check_rss_feeds(self, session: aiohttp.ClientSession):
        feeds = {
            "SEC.gov": self.sec_rss_url,
            "CourtListener": self.court_rss_url
        }
        results = []
        for name, url in feeds.items():
            if not url:
                results.append({"name": name, "status": "warn", "message": "URL not configured"})
                continue
            try:
                async with session.head(url, allow_redirects=True) as resp:
                    status = resp.status
                    if status == 405:
                        async with session.get(url) as get_resp:
                            status = get_resp.status
            except Exception:
                status = None

            if status == 200:
                results.append({"name": name, "status": "ok", "message": "Reachable"})
            elif status is None:
                results.append({"name": name, "status": "error", "message": "Request failed"})
            else:
                results.append({"name": name, "status": "error", "message": f"HTTP {status}"})
        return results

    async def _check_exa(self):
        if not Config.EXA_KEYS:
            return {"status": "warn", "message": "No API key configured"}
        try:
            from exa_py import Exa
        except Exception as e:
            return {"status": "error", "message": f"Import failed: {e}"}

        key = Config.EXA_KEYS[0]

        def run_search():
            client = Exa(key)
            client.search("test", num_results=1)

        try:
            await asyncio.to_thread(run_search)
            return {"status": "ok", "message": "Connected"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _check_tavily(self):
        if not Config.TAVILY_API_KEY:
            return {"status": "warn", "message": "No API key configured"}
        try:
            from tavily import TavilyClient
        except Exception as e:
            return {"status": "error", "message": f"Import failed: {e}"}

        client = TavilyClient(api_key=Config.TAVILY_API_KEY)

        def run_search():
            client.search(query="test", search_depth="basic", max_results=1)

        try:
            await asyncio.to_thread(run_search)
            return {"status": "ok", "message": "Connected"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _format_status(self, result):
        return f"{self._status_icon(result['status'])} {result['message']}"

    def _status_icon(self, status):
        return {
            "ok": "✅",
            "warn": "⚠️",
            "error": "❌"
        }.get(status, "❔")

    def _determine_color(self, statuses):
        if any(status == "error" for status in statuses):
            return 0xE74C3C  # red
        if any(status == "warn" for status in statuses):
            return 0xF39C12  # orange
        return 0x2ECC71  # green

async def setup(bot):
    """Loads the cog."""
    await bot.add_cog(AdminCog(bot))
