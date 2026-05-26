import discord
import logging
import asyncio
import sys
from discord.ext import commands
from app.config import Config
from app.ai.hydra import HydraEngine
from app.ai.agents import AgentCouncil
from app.core.search_router import SearchRouter
from app.core.database import db
from app.core.watchdog import watchdog
from app.scanners.lag_hunter import LagHunter
from app.scanners.genesis_scanner import GenesisScanner
from app.scanners.inefficiency_scanner import InefficiencyScanner
from app.scanners.basket_scanner import BasketScanner
from app.scanners.resolution_assistant import ResolutionAssistant
from app.scanners.geo_sniper import GeoSniper
from app.scanners.cross_venue_arb_scanner import CrossVenueArbScanner
from app.scanners.wallet_tracker import WalletTracker
from app.core.server_manager import server_manager

# Logging Setup
import io
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(
            io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        )
    ]
)
logger = logging.getLogger("PolyQuant")

class PolyQuantBot(commands.Bot):
    def __init__(self):
        # SECURITY: Zero Trust Intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = False 
        intents.presences = False
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        
        self.hydra = HydraEngine()
        self.router = SearchRouter()
        self.council = AgentCouncil()
        self.lag_hunter = LagHunter(self)
        self.genesis_scanner = GenesisScanner(self)
        self.inefficiency_scanner = InefficiencyScanner(self)
        self.basket_scanner = BasketScanner(self)
        self.resolution_assistant = ResolutionAssistant(self)
        self.geo_sniper = GeoSniper(self)
        self.cross_venue_arb_scanner = CrossVenueArbScanner(self)
        self.wallet_tracker = WalletTracker(self)
        self._background_tasks_started = False

    async def on_ready(self):
        logger.info("--------------------------------------------------")
        logger.info(f"✅ PolyQuant Online: {self.user} (ID: {self.user.id})")
        logger.info("--------------------------------------------------")
        
        # 🕵️ THE LOCATOR
        if len(self.guilds) == 0:
            logger.critical("❌ The bot is NOT in any server. Re-invite it.")
        else:
            logger.info(f"📍 Connected to {len(self.guilds)} server(s):")
            for guild in self.guilds:
                logger.info(f"   - {guild.name} (ID: {guild.id})")
                # Auto-register all connected servers
                await server_manager.register_server(guild.id, guild.name)
        
        # Load Slash Command Cogs
        try:
            await self.load_extension("app.cogs.setup")
            await self.load_extension("app.cogs.admin")
            await self.load_extension("app.cogs.query")
            await self.load_extension("app.cogs.filter")
            logger.info("✅ Slash commands loaded")
        except Exception as e:
            logger.error(f"Failed to load cogs: {e}")
        
        # Sync slash commands with Discord
        try:
            synced = await self.tree.sync()
            logger.info(f"✅ Synced {len(synced)} slash command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
        
        # Start Background Tasks
        if self._background_tasks_started:
            logger.info("Background tasks already running; skipping duplicate startup")
            return
        self._background_tasks_started = True

        self.loop.create_task(self.lag_hunter.start())
        logger.info("📡 Lag Hunter: Active (Silent Mode)")
        
        self.loop.create_task(self.genesis_scanner.start())
        logger.info("🔮 Genesis Scanner: Active (Market Discovery)")

        self.loop.create_task(self.inefficiency_scanner.start())
        logger.info("⚖️ Inefficiency Scanner: Active (Macro Monitoring)")

        self.loop.create_task(self.basket_scanner.start())
        logger.info("🧺 Basket Scanner: Active (Sum<1 trades)")

        self.loop.create_task(self.resolution_assistant.start())
        logger.info("📘 Resolution Assistant: Active (Resolution Intel)")

        self.loop.create_task(self.geo_sniper.start())
        self.loop.create_task(self.cross_venue_arb_scanner.start())
        self.loop.create_task(self.wallet_tracker.start())
        logger.info("Cross-Venue Arb Scanner: Active (exact Poly/Kalshi mappings only)")
        logger.info("🐋 Wallet Tracker: Active (configured whale wallets)")
        logger.info("🛰️ Geo Sniper: Active (Geopolitical resolution alerts)")

        logger.info("✅ All systems operational - Dual Engine Mode")
    
    async def on_guild_join(self, guild: discord.Guild):
        """Called when bot joins a new server (Multi-Tenant Registration)."""
        logger.info(f"🆕 Joined new server: {guild.name} (ID: {guild.id})")
        await server_manager.register_server(guild.id, guild.name)
        
        # Send welcome message to first available channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                embed = discord.Embed(
                    title="👋 PolyQuant Has Arrived!",
                    description="**Real-Time Market Intelligence for Prediction Markets**",
                    color=0x00ff00
                )
                embed.add_field(
                    name="🛠️ Setup Required",
                    value="Use `/setup` to configure PolyQuant for your server.\n"
                          "Set alert channels, query channels, and preferences.",
                    inline=False
                )
                embed.add_field(
                    name="💡 Features",
                    value="• **Lag Hunter:** Real-time market lag detection\n"
                          "• **AI Analysis:** Multi-agent market intelligence\n"
                          "• **SaaS Platform:** Multi-tenant with rate limits",
                    inline=False
                )
                embed.set_footer(text="Powered by Gemini AI • Type /setup to begin")
                try:
                    await channel.send(embed=embed)
                    break
                except:
                    continue
    
    async def on_guild_remove(self, guild: discord.Guild):
        """Called when bot is kicked/leaves a server."""
        logger.info(f"👋 Left server: {guild.name} (ID: {guild.id})")
        # Note: We don't delete the server from DB (for analytics)

bot = PolyQuantBot()

@bot.command()
@commands.is_owner()
async def sync(ctx, guild_id: int = None):
    """
    !sync [guild_id] - Force sync slash commands (Owner only)
    - No args: Syncs globally (slow, up to 1 hour)
    - With guild_id: Syncs to specific server (instant)
    - Example: !sync 504583329400750080
    """
    try:
        if guild_id:
            # Sync to specific guild (instant)
            guild = discord.Object(id=guild_id)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            await ctx.send(
                f"✅ **Force Synced {len(synced)} commands to guild `{guild_id}`**\n"
                f"Commands available **instantly** in that server!\n\n"
                f"**Commands synced:**\n" + 
                "\n".join([f"• `/{cmd.name}` - {cmd.description}" for cmd in synced[:5]])
            )
            logger.info(f"Force synced {len(synced)} commands to guild {guild_id}")
        else:
            # Global sync (slow, but applies to all servers)
            synced = await bot.tree.sync()
            await ctx.send(
                f"✅ **Globally synced {len(synced)} commands**\n"
                f"⏳ May take up to 1 hour to propagate to all servers.\n\n"
                f"**Tip:** Use `!sync {ctx.guild.id if ctx.guild else 'GUILD_ID'}` for instant sync to this server."
            )
            logger.info(f"Globally synced {len(synced)} commands")
    except Exception as e:
        await ctx.send(f"❌ **Sync failed:** {e}")
        logger.error(f"Command sync error: {e}")

@bot.command()
async def serverinfo(ctx):
    """!serverinfo - Get server ID for syncing commands"""
    if not ctx.guild:
        await ctx.send("❌ This command only works in a server, not DMs.")
        return
    
    embed = discord.Embed(
        title="📋 Server Information",
        description=f"Information for **{ctx.guild.name}**",
        color=0x00bfff
    )
    
    embed.add_field(
        name="Server ID",
        value=f"`{ctx.guild.id}`",
        inline=False
    )
    
    embed.add_field(
        name="Force Sync Command",
        value=f"```!sync {ctx.guild.id}```",
        inline=False
    )
    
    embed.add_field(
        name="Owner",
        value=f"{ctx.guild.owner.mention}",
        inline=True
    )
    
    embed.add_field(
        name="Members",
        value=f"{ctx.guild.member_count}",
        inline=True
    )
    
    embed.add_field(
        name="Created",
        value=f"<t:{int(ctx.guild.created_at.timestamp())}:R>",
        inline=True
    )
    
    embed.set_footer(text="Use this ID to force sync slash commands instantly")
    
    await ctx.send(embed=embed)

@bot.command()
async def ask(ctx, *, question):
    """/ask <question> - Triggers the War Room (Multi-Tenant)"""
    await ctx.send(
        "`!ask` is disabled because it used the old search-only analysis path. "
        "Use `/ask` instead; the slash command injects live Polymarket prices before AI analysis."
    )
    return
    
    # Multi-Tenant Permission Check
    if ctx.guild:
        config = await server_manager.get_server_config(ctx.guild.id)
        
        if not config:
            await ctx.send(
                "⚠️ **Server Not Configured**\n"
                "Ask an admin to run `/setup` to enable PolyQuant in this server."
            )
            return
        
        if not config.enabled:
            await ctx.send("⏸️ **PolyQuant is disabled** in this server.")
            return
        
        if config.is_banned:
            await ctx.send("⛔ **This server is banned** from using PolyQuant.")
            return
        
        # Rate Limit Check
        can_query = await server_manager.increment_query_count(ctx.guild.id)
        if not can_query:
            await ctx.send(
                f"⏱️ **Daily Limit Reached**\n"
                f"Your server has used all **{config.max_queries_per_day}** queries for today.\n"
                f"**Tier:** {config.tier.upper()}\n\n"
                f"*Upgrade to Pro for 500 queries/day or Enterprise for unlimited access.*"
            )
            return
    
    # Sanitization
    safe_question = question.replace("@everyone", "").replace("@here", "")[:200]
    
    # 1. Memory Check (Speed)
    cached_response = db.get_cache(safe_question)
    if cached_response:
        await ctx.send(f"⚡ **Instant Recall (Cache):**\n{cached_response}")
        return

    status_msg = await ctx.send(f"🔍 **PolyQuant is Scanning:** *{safe_question}*...")

    try:
        # 2. Gather Intel (Eyes)
        context_data = await bot.router.deep_search(safe_question)
        
        if not context_data or len(context_data) < 50:
            await status_msg.edit(content="⚠️ **Intel Low:** Searching deeper archives...")

        # 3. The Council Deliberates (Brain)
        await status_msg.edit(content="⚖️ **The 5 Agents are Debating...**")
        verdict, opinions = await bot.council.deliberate(safe_question, context_data)

        # 4. Format Output
        final_output = f"""
**🏛️ POLYQUANT WAR ROOM VERDICT**
{verdict}

**The Council's Arguments:**
🐂 **BULL:** {opinions.get('BULL 🐂', 'N/A')[:200]}...
🐻 **BEAR:** {opinions.get('BEAR 🐻', 'N/A')[:200]}...
⚖️ **LAWYER:** {opinions.get('LAWYER ⚖️', 'N/A')[:200]}...
🕵️ **SKEPTIC:** {opinions.get('SKEPTIC 🕵️', 'N/A')[:200]}...

*Sources Verified.*
        """
        
        # 5. Save to Memory (with guild_id for multi-tenant analytics)
        guild_id = ctx.guild.id if ctx.guild else None
        db.save_log(safe_question, final_output, guild_id)
        
        await status_msg.edit(content=final_output)

    except Exception as e:
        logger.error(f"Ask Command Failed: {e}")
        await status_msg.edit(content="❌ **Error:** Intelligence systems unresponsive.")
        # Only alert if it's a critical error (not just failed searches)
        if "Intelligence systems" not in str(e):
            await watchdog.alert("Command /ask", str(e), "ERROR")

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for prefix commands."""
    if isinstance(error, commands.NotOwner):
        await ctx.send("❌ **Permission Denied** - This command is owner-only.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ **Missing Argument:** {error.param.name}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ **Invalid Argument:** {error}")
    else:
        # Log unexpected errors
        logger.error(f"Command error: {error}")

if __name__ == "__main__":
    if not Config.DISCORD_TOKEN:
        logger.critical("MISSING DISCORD TOKEN")
        sys.exit(1)
    
    try:
        bot.run(Config.DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        logger.critical("INVALID DISCORD TOKEN - Check your .env file")
        sys.exit(1)
    except discord.errors.PrivilegedIntentsRequired:
        logger.critical("PRIVILEGED INTENTS REQUIRED - Enable in Discord Developer Portal")
        logger.critical("Go to: https://discord.com/developers/applications")
        logger.critical("Select your bot -> Bot -> Enable MESSAGE CONTENT INTENT")
        sys.exit(1)
