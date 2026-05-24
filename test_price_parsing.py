"""
Quick test script to verify price parsing fixes.
Tests both market_data.py and genesis_scanner.py normalization.
"""
import json
import asyncio
import pytest
from app.core.market_data import market_resolver
from app.scanners.genesis_scanner import GenesisScanner

# Mock bot for GenesisScanner
class MockBot:
    pass

@pytest.mark.asyncio
async def test_market_resolver():
    """Test MarketResolver with North Carolina Senate market"""
    print("\n" + "="*60)
    print("TEST 1: MarketResolver (market_data.py)")
    print("="*60)
    
    query = "https://polymarket.com/event/north-carolina-republican-senate-primary-winner?tid=1764705644816"
    
    try:
        result = await market_resolver.fetch_market_data(query)
        if result:
            print("[PASS] Market data fetched successfully")
            print("\nFormatted Output:")
            print(result[:500])  # First 500 chars
            
            # Check for correct prices
            if "Michele Morrow" in result:
                if "7c" in result or "0.07" in result:
                    print("\n[PASS] Michele Morrow shows correct price (~7c)")
                elif "93c" in result or "0.93" in result:
                    print("\n[FAIL] Michele Morrow shows WRONG price (93c - reading NO)")
                else:
                    print("\n[WARN] Michele Morrow price format unclear")
            
            if "Thomas Tillis" in result:
                if "10c" in result or "0.1" in result:
                    print("[PASS] Thomas Tillis shows correct price (~10c)")
                elif "90c" in result or "0.9" in result:
                    print("[FAIL] Thomas Tillis shows WRONG price (90c - reading NO)")
        else:
            print("[FAIL] No market data returned")
    except Exception as e:
        print(f"[FAIL] Error: {e}")

def test_genesis_normalization():
    """Test GenesisScanner normalization methods"""
    print("\n" + "="*60)
    print("TEST 2: GenesisScanner Normalization")
    print("="*60)
    
    scanner = GenesisScanner(MockBot())
    
    # Test 1: JSON string normalization
    test_cases = [
        {
            "name": "JSON String (Michele Morrow)",
            "input": '["0.07", "0.93"]',
            "expected": ["0.07", "0.93"]
        },
        {
            "name": "Already a list",
            "input": ["0.76", "0.24"],
            "expected": ["0.76", "0.24"]
        },
        {
            "name": "Invalid JSON",
            "input": "not-json",
            "expected": []
        }
    ]
    
    print("\nTesting _normalize_outcome_prices:")
    for test in test_cases:
        result = scanner._normalize_outcome_prices(test["input"])
        status = "[PASS]" if result == test["expected"] else "[FAIL]"
        print(f"{status} {test['name']}: {result}")
    
    # Test 2: YES price extraction
    print("\nTesting _extract_yes_price:")
    
    test_markets = [
        {
            "name": "Michele Morrow (YES at index 0)",
            "market": {
                "outcomePrices": '["0.07", "0.93"]',
                "outcomes": '["Yes", "No"]',
                "question": "Will Michele Morrow win?"
            },
            "expected": 0.07
        },
        {
            "name": "Michael Whatley (YES at index 0)",
            "market": {
                "outcomePrices": '["0.765", "0.235"]',
                "outcomes": '["Yes", "No"]',
                "question": "Will Michael Whatley win?"
            },
            "expected": 0.765
        },
        {
            "name": "Standard binary (YES at index 1)",
            "market": {
                "outcomePrices": ["0.35", "0.65"],
                "outcomes": ["No", "Yes"],
                "question": "Will X happen?"
            },
            "expected": 0.65
        }
    ]
    
    for test in test_markets:
        result = scanner._extract_yes_price(test["market"])
        if result is not None and abs(result - test["expected"]) < 0.001:
            print(f"[PASS] {test['name']}: {result:.3f}")
        else:
            print(f"[FAIL] {test['name']}: Expected {test['expected']}, got {result}")
    
    # Test 3: Valid prices check
    print("\nTesting _has_valid_prices:")
    
    valid_test_cases = [
        {
            "name": "Valid JSON string prices",
            "market": {"outcomePrices": '["0.07", "0.93"]'},
            "expected": True
        },
        {
            "name": "Valid list prices",
            "market": {"outcomePrices": ["0.50", "0.50"]},
            "expected": True
        },
        {
            "name": "Empty prices",
            "market": {"outcomePrices": []},
            "expected": False
        },
        {
            "name": "Invalid JSON string",
            "market": {"outcomePrices": "not-json"},
            "expected": False
        }
    ]
    
    for test in valid_test_cases:
        result = scanner._has_valid_prices(test["market"])
        status = "[PASS]" if result == test["expected"] else "[FAIL]"
        print(f"{status} {test['name']}: {result}")

async def main():
    print("\n" + "="*60)
    print("PRICE PARSING FIX VERIFICATION")
    print("="*60)
    
    # Test 1: MarketResolver (async)
    await test_market_resolver()
    
    # Test 2: GenesisScanner (sync)
    test_genesis_normalization()
    
    print("\n" + "="*60)
    print("VERIFICATION COMPLETE")
    print("="*60)
    print("\nIf all tests pass, the fix is working correctly.")
    print("Deploy to Railway and monitor new market alerts.\n")

if __name__ == "__main__":
    asyncio.run(main())

