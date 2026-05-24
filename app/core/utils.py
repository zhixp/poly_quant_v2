"""
Utility functions for PolyQuant bot.
Includes spam detection, text normalization, and other helpers.
"""
import re
from typing import Optional

# Global spam patterns - DISABLED (using variant grouping instead)
# Variant grouping ensures only 1 alert per event, preventing spam
# without blocking legitimate markets
SPAM_PATTERNS = [
    # All spam filtering disabled - variant grouping handles duplicates
]

# Compile patterns for performance
SPAM_REGEX = re.compile('|'.join(SPAM_PATTERNS), re.IGNORECASE) if SPAM_PATTERNS else None


def is_spam_market(text: str) -> bool:
    """
    Check if a market is spam based on global blacklist patterns.
    
    DISABLED: Spam filtering removed in favor of variant grouping.
    Variant grouping ensures only 1 alert per event (e.g., only alerts on
    the primary market when there are multiple outcomes like ETH $2800/$3000/$4000).
    
    Args:
        text: Market question, title, or slug to check
        
    Returns:
        False (spam filtering disabled)
        
    Examples:
        >>> is_spam_market("BTC Up or Down in 15m?")
        False  # No longer filtered - variant grouping handles it
        >>> is_spam_market("Will Trump win 2024?")
        False
        >>> is_spam_market("ETH > $3000?")
        False  # Grouped with other ETH price markets
    """
    if not text or not SPAM_REGEX:
        return False
    
    return False  # Disabled - variant grouping handles duplicates


def normalize_text(text: str) -> str:
    """
    Normalize text for matching: lowercase, strip punctuation, collapse whitespace.
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text string
    """
    if not text:
        return ""
    
    # Lowercase
    text = text.lower()
    # Remove punctuation except spaces
    text = re.sub(r'[^\w\s]', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_category_filters(filters: Optional[str]) -> Optional[list]:
    """
    Parse comma-separated category filters into a list.
    
    Args:
        filters: Comma-separated string like "Politics,Crypto,Sports" or None
        
    Returns:
        List of lowercase category names, or None if filters is None/empty
        
    Examples:
        >>> parse_category_filters("Politics, Crypto, Sports")
        ['politics', 'crypto', 'sports']
        >>> parse_category_filters(None)
        None
        >>> parse_category_filters("")
        None
    """
    if not filters:
        return None
    
    return [f.strip().lower() for f in filters.split(',') if f.strip()]


def validate_categories(categories: list) -> tuple[bool, list]:
    """
    Validate that categories are in the allowed list.
    Uses constants from app.core.constants (case-sensitive).
    
    Args:
        categories: List of category names to validate (case-sensitive)
        
    Returns:
        Tuple of (is_valid, invalid_categories)
        
    Examples:
        >>> validate_categories(['Politics', 'Crypto'])
        (True, [])
        >>> validate_categories(['Politics', 'Invalid'])
        (False, ['Invalid'])
    """
    from app.core.constants import VALID_CATEGORIES
    
    # Convert to set for O(1) lookup
    valid_set = set(VALID_CATEGORIES)
    
    # Case-sensitive validation
    invalid = [cat for cat in categories if cat not in valid_set]
    return (len(invalid) == 0, invalid)


# Export commonly used functions
__all__ = [
    'is_spam_market',
    'normalize_text',
    'parse_category_filters',
    'validate_categories',
]

