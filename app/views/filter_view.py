"""
Market Filter View - Discord UI for category filtering
"""
import discord
from discord import ui
import logging
from app.core.constants import VALID_CATEGORIES, CATEGORY_DESCRIPTIONS
from app.core.database import db
from app.core.server_manager import server_manager

logger = logging.getLogger("FilterView")


class MarketFilterView(ui.View):
    """
    Discord UI view for selecting market categories.
    Supports both Genesis Scanner (new markets) and Lag Hunter (news alerts).
    """
    
    def __init__(self, filter_type: str = "new_markets", guild_id: int = None):
        """
        Initialize the filter view.
        
        Args:
            filter_type: 'new_markets' or 'lag_hunter'
            guild_id: Discord guild ID
        """
        super().__init__(timeout=300)  # 5 minute timeout
        self.filter_type = filter_type
        self.guild_id = guild_id
        self.selected_categories = []
        
        # Create category select menu
        self.category_select = ui.Select(
            placeholder="Select categories to track (multi-select)",
            min_values=0,
            max_values=len(VALID_CATEGORIES),
            options=[
                discord.SelectOption(
                    label=cat,
                    description=CATEGORY_DESCRIPTIONS.get(cat, ''),
                    value=cat
                )
                for cat in VALID_CATEGORIES
            ]
        )
        self.category_select.callback = self.on_category_select
        self.add_item(self.category_select)
        
        # Load current filters to pre-select
        if guild_id:
            self._load_current_filters()
    
    async def _load_current_filters(self):
        """Load current filters from database and pre-select them."""
        try:
            current_filters = await db.get_server_filters(self.guild_id, self.filter_type)
            if current_filters:
                # Pre-select categories that match (case-sensitive)
                self.selected_categories = [cat for cat in current_filters if cat in VALID_CATEGORIES]
                # Update select menu default values
                self.category_select.default_values = self.selected_categories
        except Exception as e:
            logger.debug(f"Could not load current filters: {e}")
    
    async def on_category_select(self, interaction: discord.Interaction):
        """Handle category selection."""
        self.selected_categories = self.category_select.values
        
        # Update the view with confirm/clear buttons
        await self._update_view(interaction)
    
    async def _update_view(self, interaction: discord.Interaction):
        """Update the view with current selection and action buttons."""
        # Clear existing items
        self.clear_items()
        
        # Re-add select menu with current selection
        self.category_select.default_values = self.selected_categories
        self.add_item(self.category_select)
        
        # Add action buttons
        confirm_btn = ui.Button(
            label="✅ Confirm Selection",
            style=discord.ButtonStyle.green,
            emoji="✅"
        )
        confirm_btn.callback = lambda i: self.on_confirm(i)
        self.add_item(confirm_btn)
        
        clear_btn = ui.Button(
            label="🗑️ Clear All Filters",
            style=discord.ButtonStyle.red,
            emoji="🗑️"
        )
        clear_btn.callback = lambda i: self.on_clear(i)
        self.add_item(clear_btn)
        
        # Update the message
        selected_text = ", ".join(self.selected_categories) if self.selected_categories else "None (All Categories)"
        filter_name = "🔮 Genesis Scanner" if self.filter_type == "new_markets" else "📡 Lag Hunter"
        
        embed = discord.Embed(
            title=f"🎯 {filter_name} - Category Filter",
            description=f"**Selected:** {selected_text}\n\n"
                       f"Click **✅ Confirm** to save, or **🗑️ Clear All** to reset.",
            color=0x00bfff
        )
        embed.set_footer(text="Spam protection (15m, 5m, 1h, up/down) remains active")
        
        # Edit the message with updated view
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def on_confirm(self, interaction: discord.Interaction):
        """Save selected categories to database."""
        if not self.guild_id:
            await interaction.response.send_message(
                "❌ **Error:** Guild ID not set. Please use `/filter` command.",
                ephemeral=True
            )
            return
        
        # Auto-register server if needed
        config = await server_manager.get_server_config(self.guild_id)
        if not config:
            await server_manager.register_server(self.guild_id, interaction.guild.name)
        
        # Save filters
        success = await db.update_server_filters(
            self.guild_id,
            self.selected_categories,
            self.filter_type
        )
        
        if success:
            filter_name = "🔮 Genesis Scanner (New Markets)" if self.filter_type == "new_markets" else "📡 Lag Hunter (News Alerts)"
            selected_text = ", ".join(self.selected_categories) if self.selected_categories else "All Categories"
            
            embed = discord.Embed(
                title="✅ Filters Updated!",
                description=f"**System:** {filter_name}\n"
                          f"**Categories:** {selected_text}\n\n"
                          f"You will now only receive alerts for these categories.\n\n"
                          f"🛡️ **Spam Protection:** Auto-blocking 15m, 5m, 1h, 4h, up/down markets",
                color=0x00ff00
            )
            
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.send_message(
                "❌ **Error:** Failed to save filters. Database may not have required columns.\n\n"
                "Run `DATABASE_MIGRATION_GENESIS_V2.sql` in Supabase SQL Editor.",
                ephemeral=True
            )
    
    async def on_clear(self, interaction: discord.Interaction):
        """Clear all filters (set to None)."""
        if not self.guild_id:
            await interaction.response.send_message(
                "❌ **Error:** Guild ID not set. Please use `/filter` command.",
                ephemeral=True
            )
            return
        
        # Clear filters
        success = await db.update_server_filters(self.guild_id, [], self.filter_type)
        
        if success:
            filter_name = "🔮 Genesis Scanner" if self.filter_type == "new_markets" else "📡 Lag Hunter"
            
            embed = discord.Embed(
                title="✅ Filters Cleared!",
                description=f"**System:** {filter_name}\n\n"
                          f"Your server will now receive alerts for **ALL categories**.\n\n"
                          f"🛡️ **Spam Protection:** Auto-blocking 15m, 5m, 1h, 4h, up/down markets remains active.",
                color=0x00ff00
            )
            
            # Reset selection
            self.selected_categories = []
            self.category_select.default_values = []
            
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.send_message(
                "❌ **Error:** Failed to clear filters. Database may not have required columns.\n\n"
                "Run `DATABASE_MIGRATION_GENESIS_V2.sql` in Supabase SQL Editor.",
                ephemeral=True
            )


class FilterTypeView(ui.View):
    """
    Initial view to select which system to filter (Genesis vs LagHunter).
    """
    
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
    
    @ui.button(label="🔮 New Markets (Genesis Scanner)", style=discord.ButtonStyle.primary, row=0)
    async def new_markets_button(self, interaction: discord.Interaction, button: ui.Button):
        """Open filter view for Genesis Scanner."""
        view = MarketFilterView("new_markets", self.guild_id)
        embed = discord.Embed(
            title="🔮 Genesis Scanner - Category Filter",
            description="Select categories to track for **new market alerts**.\n\n"
                      "You can select multiple categories or leave empty for all categories.",
            color=0x00bfff
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @ui.button(label="📡 Lag Hunter (News Alerts)", style=discord.ButtonStyle.primary, row=0)
    async def lag_hunter_button(self, interaction: discord.Interaction, button: ui.Button):
        """Open filter view for Lag Hunter."""
        view = MarketFilterView("lag_hunter", self.guild_id)
        embed = discord.Embed(
            title="📡 Lag Hunter - Category Filter",
            description="Select categories to track for **news-based alerts**.\n\n"
                      "You can select multiple categories or leave empty for all categories.",
            color=0x00bfff
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @ui.button(label="🔄 Reset All Filters", style=discord.ButtonStyle.danger, row=1)
    async def reset_all_button(self, interaction: discord.Interaction, button: ui.Button):
        """Reset all filters for both systems."""
        success1 = await db.update_server_filters(self.guild_id, [], "new_markets")
        success2 = await db.update_server_filters(self.guild_id, [], "lag_hunter")
        
        if success1 or success2:
            embed = discord.Embed(
                title="✅ All Filters Reset!",
                description="**Both systems reset to default:**\n\n"
                          "• 🔮 Genesis Scanner: **All Categories**\n"
                          "• 📡 Lag Hunter: **All Categories**\n\n"
                          "🛡️ **Spam Protection:** Auto-blocking 15m, 5m, 1h, 4h, up/down markets remains active.",
                color=0x00ff00
            )
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.send_message(
                "❌ **Error:** Failed to reset filters. Database may not have required columns.\n\n"
                "Run `DATABASE_MIGRATION_GENESIS_V2.sql` in Supabase SQL Editor.",
                ephemeral=True
            )
    
    @ui.button(label="📊 View Current Filters", style=discord.ButtonStyle.secondary, row=1)
    async def view_status_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show current filter status."""
        config = await server_manager.get_server_config(self.guild_id)
        
        if not config:
            await interaction.response.send_message(
                "⚠️ **Server Not Registered**\n"
                "Use `/filter` to set up filters first.",
                ephemeral=True
            )
            return
        
        # Get filters safely
        new_markets_filters = config.get('market_filters') if isinstance(config, dict) else getattr(config, 'market_filters', None)
        lag_hunter_filters = config.get('lag_hunter_filters') if isinstance(config, dict) else getattr(config, 'lag_hunter_filters', None)
        
        embed = discord.Embed(
            title="🎯 Current Market Filters",
            description=f"Settings for **{interaction.guild.name}**",
            color=0x00bfff
        )
        
        embed.add_field(
            name="🔮 New Markets (Genesis)",
            value=new_markets_filters if new_markets_filters else "✅ All Categories",
            inline=False
        )
        
        embed.add_field(
            name="📡 Lag Hunter Alerts",
            value=lag_hunter_filters if lag_hunter_filters else "✅ All Categories",
            inline=False
        )
        
        embed.add_field(
            name="📋 Available Categories",
            value=", ".join(VALID_CATEGORIES),
            inline=False
        )
        
        embed.add_field(
            name="🛡️ Spam Protection",
            value="✅ Auto-blocking: 15m, 5m, 1h, 4h, 30m, up/down price markets",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

