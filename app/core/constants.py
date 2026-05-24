"""
Constants for PolyQuant bot.
Hardcoded source of truth for Polymarket categories.
These must match Polymarket Gamma API exactly (case-sensitive).
"""

# Valid Polymarket categories (exact match from Gamma API)
VALID_CATEGORIES = [
    'Politics',
    'Crypto',
    'Sports',
    'Pop Culture',
    'Business',
    'Science',
    'Technology'
]

# Category descriptions for UI
CATEGORY_DESCRIPTIONS = {
    'Politics': 'Elections, government, policy',
    'Crypto': 'Cryptocurrency, blockchain, DeFi',
    'Sports': 'Sports events, games, competitions',
    'Pop Culture': 'Entertainment, celebrities, media',
    'Business': 'Companies, markets, economy',
    'Science': 'Research, discoveries, health',
    'Technology': 'Tech companies, products, innovation'
}

