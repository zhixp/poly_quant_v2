"""
Setup Cog: User-Facing Slash Commands
Allows server owners to configure PolyQuant for their server.
"""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from app.core.server_manager import server_manager

logger = logging.getLogger("SetupCog")

class SetupCog(commands.Cog):
    """Server Setup Commands for Multi-Tenant SaaS"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="setup", description="🛠️ Configure PolyQuant for your server")
    @app_commands.describe(
        action="What to configure",
        channel="The channel to use for the selected PolyQuant function"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Set Ask Channel (/ask analysis)", value="ask_channel"),
        app_commands.Choice(name="Set Lag Hunter Channel", value="lag_hunter_channel"),
        app_commands.Choice(name="Set New Markets Channel", value="new_markets_channel"),
        app_commands.Choice(name="Set Curated Markets Channel", value="curated_markets_channel"),
        app_commands.Choice(name="Set Arb Channel", value="arb_channel"),
        app_commands.Choice(name="Set Geo Channel", value="geo_channel"),
        app_commands.Choice(name="Set Copy Tracker Channel", value="copy_tracker_channel"),
        app_commands.Choice(name="Enable Bot", value="enable"),
        app_commands.Choice(name="Disable Bot", value="disable"),
        app_commands.Choice(name="View Current Settings", value="status")
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(
        self, 
        interaction: discord.Interaction, 
        action: app_commands.Choice[str],
        channel: discord.TextChannel = None
    ):
        """Main setup command with subcommands."""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild_id
        
        # Auto-register server if not already registered
        config = await server_manager.get_server_config(guild_id)
        if not config:
            await server_manager.register_server(guild_id, interaction.guild.name)
            logger.info(f"Auto-registered server: {interaction.guild.name}")
        
        action_value = action.value

        dedicated_channel_actions = {
            "ask_channel": {
                "setter": server_manager.set_ask_channel,
                "label": "Ask Channel",
                "missing": "You must specify a channel for /ask analysis.",
                "success": "/ask analysis is expected in",
            },
            "lag_hunter_channel": {
                "setter": server_manager.set_lag_hunter_channel,
                "label": "Lag Hunter Channel",
                "missing": "You must specify a channel for Lag Hunter alerts.",
                "success": "Lag Hunter alerts will be posted to",
            },
            "new_markets_channel": {
                "setter": server_manager.set_new_markets_channel,
                "label": "New Markets Channel",
                "missing": "You must specify a channel for new market alerts.",
                "success": "Genesis Scanner raw new markets will be posted to",
            },
            "curated_markets_channel": {
                "setter": server_manager.set_curated_markets_channel,
                "label": "Curated Markets Channel",
                "missing": "You must specify a channel for curated market alerts.",
                "success": "Genesis Scanner curated markets will be posted to",
            },
            "arb_channel": {
                "setter": server_manager.set_arb_channel,
                "label": "Arb Channel",
                "missing": "You must specify a channel for arbitrage alerts.",
                "success": "Arbitrage alerts will be posted to",
            },
            "geo_channel": {
                "setter": server_manager.set_geo_channel,
                "label": "Geo Channel",
                "missing": "You must specify a channel for Geo Sniper alerts.",
                "success": "Geo Sniper alerts will be posted to",
            },
            "copy_tracker_channel": {
                "setter": server_manager.set_copy_tracker_channel,
                "label": "Copy Tracker Channel",
                "missing": "You must specify a channel for copy tracker alerts.",
                "success": "Wallet/copy-trade tracker alerts will be posted to",
            },
        }

        if action_value in dedicated_channel_actions:
            action_config = dedicated_channel_actions[action_value]
            if not channel:
                await interaction.followup.send(
                    f"**Error:** {action_config['missing']}",
                    ephemeral=True
                )
                return

            success = await action_config["setter"](guild_id, channel.id)
            if success:
                await interaction.followup.send(
                    f"**{action_config['label']} Set!**\n"
                    f"{action_config['success']} {channel.mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"**Error:** Failed to set {action_config['label']}. Please run the DB migration and try again.",
                    ephemeral=True
                )
            return

        if action_value == "status":
            config = await server_manager.get_server_config(guild_id)
            if not config:
                await interaction.followup.send(
                    "**Server Not Registered**\n"
                    "Use `/setup ask_channel` or another channel setup action to register this server.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="PolyQuant Configuration",
                description=f"Settings for **{interaction.guild.name}**",
                color=0x00ff00 if config.enabled else 0xff0000
            )

            embed.add_field(
                name="Status",
                value="Enabled" if config.enabled else "Disabled",
                inline=True
            )
            embed.add_field(
                name="Tier",
                value=f"**{config.tier.upper()}**",
                inline=True
            )
            embed.add_field(
                name="Daily Queries",
                value=f"{config.query_count_today} / {config.max_queries_per_day}",
                inline=True
            )

            configured_channels = [
                ("Ask Channel (/ask Analysis)", config.ask_channel_id),
                ("Lag Hunter Channel", config.lag_hunter_channel_id),
                ("New Markets Channel", config.new_markets_channel_id),
                ("Curated Markets Channel", config.curated_markets_channel_id),
                ("Arb Channel", config.arb_channel_id),
                ("Geo Channel", config.geo_channel_id),
                ("Copy Tracker Channel", config.copy_tracker_channel_id),
            ]
            for name, channel_id in configured_channels:
                configured_channel = self.bot.get_channel(channel_id) if channel_id else None
                embed.add_field(
                    name=name,
                    value=configured_channel.mention if configured_channel else "Not Set",
                    inline=False
                )

            embed.set_footer(text="PolyQuant Multi-Tenant SaaS")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        if action_value == "ask_channel":
            if not channel:
                await interaction.followup.send(
                    "❌ **Error:** You must specify a channel for alert notifications.",
                    ephemeral=True
                )
                return
            
            success = await server_manager.set_ask_channel(guild_id, channel.id)
            if success:
                await interaction.followup.send(
                    f"✅ **Alert Channel Set!**\n"
                    f"Lag Hunter will now send market lag alerts to {channel.mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Error:** Failed to set alert channel. Please try again.",
                    ephemeral=True
                )
        
        elif action_value == "lag_hunter_channel":
            if not channel:
                await interaction.followup.send(
                    "❌ **Error:** You must specify a channel for query responses.",
                    ephemeral=True
                )
                return
            
            success = await server_manager.set_lag_hunter_channel(guild_id, channel.id)
            if success:
                await interaction.followup.send(
                    f"✅ **Query Channel Set!**\n"
                    f"AI analysis from `/ask` commands will be posted to {channel.mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Error:** Failed to set query channel. Please try again.",
                    ephemeral=True
                )
        
        elif action_value == "new_markets_channel":
            if not channel:
                await interaction.followup.send(
                    "❌ **Error:** You must specify a channel for new market alerts.",
                    ephemeral=True
                )
                return
            
            success = await server_manager.set_new_markets_channel(guild_id, channel.id)
            if success:
                await interaction.followup.send(
                    f"✅ **New Markets Channel Set!**\n"
                    f"Genesis Scanner will send ALL new markets to {channel.mention}\n\n"
                    f"*Note: This is a firehose feed - expect high volume!*",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Error:** Failed to set new markets channel. Please try again.",
                    ephemeral=True
                )
        
        elif action_value == "curated_markets_channel":
            if not channel:
                await interaction.followup.send(
                    "❌ **Error:** You must specify a channel for curated alerts.",
                    ephemeral=True
                )
                return
            
            success = await server_manager.set_curated_markets_channel(guild_id, channel.id)
            if success:
                await interaction.followup.send(
                    f"✅ **Curated Channel Set!**\n"
                    f"Genesis Scanner will send high-confidence opportunities to {channel.mention}\n\n"
                    f"*Note: These are rare, AI-analyzed picks with extreme confidence (>75% or <25%).*",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Error:** Failed to set curated channel. Please try again.",
                    ephemeral=True
                )
        
        elif action_value == "geo_channel":
            if not channel:
                await interaction.followup.send(
                    "❌ **Error:** You must specify a channel for Geo Sniper alerts.",
                    ephemeral=True
                )
                return
            
            success = await server_manager.set_geo_channel(guild_id, channel.id)
            if success:
                await interaction.followup.send(
                    f"✅ **Geo Channel Set!**\n"
                    f"Geo Sniper will post geopolitical mispriced-market alerts ONLY to {channel.mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Error:** Failed to set Geo channel. Please run the DB migration and try again.",
                    ephemeral=True
                )
        
        elif action_value == "copy_tracker_channel":
            if not channel:
                await interaction.followup.send(
                    "❌ **Error:** You must specify a channel for copy tracker alerts.",
                    ephemeral=True
                )
                return
            
            success = await server_manager.set_copy_tracker_channel(guild_id, channel.id)
            if success:
                await interaction.followup.send(
                    f"✅ **Copy Tracker Channel Set!**\n"
                    f"Wallet/copy-trade tracker alerts will be posted to {channel.mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Error:** Failed to set copy tracker channel. Please run the DB migration and try again.",
                    ephemeral=True
                )
        
        elif action_value == "enable":
            success = await server_manager.toggle_server(guild_id, True)
            if success:
                await interaction.followup.send(
                    "✅ **PolyQuant Enabled!**\n"
                    "The bot is now active in this server.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Error:** Failed to enable bot.",
                    ephemeral=True
                )
        
        elif action_value == "disable":
            success = await server_manager.toggle_server(guild_id, False)
            if success:
                await interaction.followup.send(
                    "⏸️ **PolyQuant Disabled!**\n"
                    "The bot will no longer respond in this server.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ **Error:** Failed to disable bot.",
                    ephemeral=True
                )
        
        elif action_value == "status":
            config = await server_manager.get_server_config(guild_id)
            if not config:
                await interaction.followup.send(
                    "⚠️ **Server Not Registered**\n"
                    "Use `/setup alert` or `/setup query` to register this server.",
                    ephemeral=True
                )
                return
            
            # Build status embed
            embed = discord.Embed(
                title="⚙️ PolyQuant Configuration",
                description=f"Settings for **{interaction.guild.name}**",
                color=0x00ff00 if config.enabled else 0xff0000
            )
            
            embed.add_field(
                name="Status",
                value="🟢 Enabled" if config.enabled else "🔴 Disabled",
                inline=True
            )
            
            embed.add_field(
                name="Tier",
                value=f"**{config.tier.upper()}**",
                inline=True
            )
            
            embed.add_field(
                name="Daily Queries",
                value=f"{config.query_count_today} / {config.max_queries_per_day}",
                inline=True
            )
            
            alert_channel = self.bot.get_channel(config.alert_channel_id) if config.alert_channel_id else None
            query_channel = self.bot.get_channel(config.query_channel_id) if config.query_channel_id else None
            new_markets_channel = self.bot.get_channel(config.new_markets_channel_id) if config.new_markets_channel_id else None
            curated_channel = self.bot.get_channel(config.curated_channel_id) if config.curated_channel_id else None
            geo_channel = self.bot.get_channel(config.geo_channel_id) if config.geo_channel_id else None
            copy_tracker_channel = self.bot.get_channel(config.copy_tracker_channel_id) if config.copy_tracker_channel_id else None
            
            embed.add_field(
                name="Alert Channel (Lag Hunter)",
                value=alert_channel.mention if alert_channel else "❌ Not Set",
                inline=False
            )
            
            embed.add_field(
                name="Query Channel (AI Analysis)",
                value=query_channel.mention if query_channel else "❌ Not Set",
                inline=False
            )
            
            embed.add_field(
                name="New Markets Channel (Genesis Firehose)",
                value=new_markets_channel.mention if new_markets_channel else "❌ Not Set",
                inline=False
            )
            
            embed.add_field(
                name="Curated Channel (Genesis High-Confidence)",
                value=curated_channel.mention if curated_channel else "❌ Not Set",
                inline=False
            )
            
            embed.add_field(
                name="Geo Channel (Geo Sniper Mispricing)",
                value=geo_channel.mention if geo_channel else "❌ Not Set",
                inline=False
            )
            
            embed.add_field(
                name="Copy Tracker Channel",
                value=copy_tracker_channel.mention if copy_tracker_channel else "❌ Not Set",
                inline=False
            )
            
            embed.set_footer(text="PolyQuant Multi-Tenant SaaS • Powered by Gemini")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @setup.error
    async def setup_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Error handler for setup command."""
        # Check if we can still respond to the interaction
        try:
            if isinstance(error, app_commands.errors.MissingPermissions):
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ **Permission Denied**\n"
                        "You need **Manage Server** permission to configure PolyQuant.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ **Permission Denied**\n"
                        "You need **Manage Server** permission to configure PolyQuant.",
                        ephemeral=True
                    )
            else:
                logger.error(f"Setup command error: {error}")
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ **Error:** Something went wrong. Please try again later.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ **Error:** Something went wrong. Please try again later.",
                        ephemeral=True
                    )
        except discord.errors.NotFound:
            # Interaction expired (>3s), just log it
            logger.warning(f"Setup command interaction expired: {error}")
        except Exception as e:
            # Don't crash on error handling errors
            logger.error(f"Error in setup error handler: {e}")

async def setup(bot):
    """Loads the cog."""
    await bot.add_cog(SetupCog(bot))


