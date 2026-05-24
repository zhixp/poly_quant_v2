"""
Filter Command - UI-based market filtering for admins
Uses Discord Select Menu to prevent invalid category input.
"""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from app.core.server_manager import server_manager
from app.views.filter_view import FilterTypeView

logger = logging.getLogger("FilterCog")


class FilterCog(commands.Cog):
    """UI-based command for setting market filters using Discord dropdown menus."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="filter", description="🎯 Filter which markets you see (UI-based)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def filter_command(self, interaction: discord.Interaction):
        """
        Open the filter UI to select categories for Genesis Scanner and Lag Hunter.
        Uses Discord Select Menu to prevent invalid category input.
        """
        guild_id = interaction.guild_id
        
        # Auto-register server if needed
        config = await server_manager.get_server_config(guild_id)
        if not config:
            await server_manager.register_server(guild_id, interaction.guild.name)
            logger.info(f"Auto-registered server: {interaction.guild.name}")
        
        # Create initial view to select filter type
        view = FilterTypeView(guild_id)
        
        embed = discord.Embed(
            title="🎯 Market Category Filters",
            description="Select which system you want to configure:\n\n"
                      "• **🔮 New Markets (Genesis Scanner)** - Filter new market alerts\n"
                      "• **📡 Lag Hunter (News Alerts)** - Filter news-based alerts\n\n"
                      "You can also **🔄 Reset All Filters** or **📊 View Current Filters**.",
            color=0x00bfff
        )
        embed.set_footer(text="Spam protection (15m, 5m, 1h, up/down) remains active")
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="reset_filters", description="🔄 Reset all market filters to default (all categories)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reset_filters_command(self, interaction: discord.Interaction):
        """
        Reset all filters for both Genesis Scanner and Lag Hunter.
        Sets both systems back to showing all categories.
        """
        from app.core.database import db
        
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild_id
        
        # Reset both filter types
        success1 = await db.update_server_filters(guild_id, [], "new_markets")
        success2 = await db.update_server_filters(guild_id, [], "lag_hunter")
        
        if success1 or success2:
            embed = discord.Embed(
                title="✅ All Filters Reset!",
                description="**Both systems reset to default:**\n\n"
                          "• 🔮 Genesis Scanner: **All Categories**\n"
                          "• 📡 Lag Hunter: **All Categories**\n\n"
                          "🛡️ **Spam Protection:** Auto-blocking 15m, 5m, 1h, 4h, up/down markets remains active.",
                color=0x00ff00
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ **Error:** Failed to reset filters. Database may not have required columns.\n\n"
                "Run `DATABASE_MIGRATION_GENESIS_V2.sql` in Supabase SQL Editor.",
                ephemeral=True
            )
    
    @filter_command.error
    async def filter_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Error handler for filter command."""
        try:
            if isinstance(error, app_commands.errors.MissingPermissions):
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ **Permission Denied**\n"
                        "You need **Manage Server** permission to set filters.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ **Permission Denied**\n"
                        "You need **Manage Server** permission to set filters.",
                        ephemeral=True
                    )
            else:
                logger.error(f"Filter command error: {error}")
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
            logger.warning(f"Filter command interaction expired: {error}")
        except Exception as e:
            logger.error(f"Error in filter error handler: {e}")


async def setup(bot):
    """Loads the cog."""
    await bot.add_cog(FilterCog(bot))

