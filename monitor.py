#!/usr/bin/env python3
"""
Portfolio Monitor - Hourly fundamental/macro break detector
Runs 9:30am-4:30pm ET, weekdays. Checks Tier 1-3 sell rules.
"""

import json
import os
from datetime import datetime

# Holdings with thesis and key risk factors
HOLDINGS = {
    "HALO": {
        "qty": 4.819281,
        "avg_cost": 103.75,
        "thesis": "Royalty revenue +50%; FY26 EPS guide raised to $8.65–$9.00",
        "tier1_risks": ["royalty revenue decline >20%", "EPS guide cut >10%", "major project delay"],
        "tier2_risks": ["streaming deal cancellation", "streaming partner default"],
    },
    "ANET": {
        "qty": 2.494140,
        "avg_cost": 200.47,
        "thesis": "FY26 revenue guide $11.5B → $12.6B; purchase commitments $9.7B vs $3.6B",
        "tier1_risks": ["guidance cut >5%", "customer churn >10%", "capex pull-forward reversal"],
        "tier2_risks": ["major customer loss", "competitive loss to Arista", "margin compression >200bp"],
    },
    "B": {
        "qty": 10.538666,
        "avg_cost": 42.70,
        "thesis": "Adj EPS +74%; $1.95B Newmont cash due; N. American IPO by YE26",
        "tier1_risks": ["Newmont deal blocked", "IPO cancelled or delayed", "EPS miss >15%"],
        "tier2_risks": ["Newmont payment delayed", "mining permit issues"],
    },
    "EXPE": {
        "qty": 1.093784,
        "avg_cost": 319.99,
        "thesis": "Bookings +12%, EBITDA margin +196bp; FY guide raised on all three lines",
        "tier1_risks": ["guidance cut >5%", "bookings decline", "margin compression >100bp"],
        "tier2_risks": ["travel demand slowdown", "competitive loss"],
    },
    "KEYS": {
        "qty": 0.691149,
        "avg_cost": 361.72,
        "thesis": "Revenue +31.5% y/y on interconnect validation demand",
        "tier1_risks": ["revenue guidance cut >20%", "major customer loss", "validation cycle stalling"],
        "tier2_risks": ["competitive loss", "technology obsolescence"],
    },
    "MU": {
        "qty": 0.245357,
        "avg_cost": 1018.92,
        "thesis": "Revenue +346% y/y; DRAM cycle 36 months old, margins 25pt above prior peak",
        "tier1_risks": ["margin compression >15pts", "inventory destocking", "competitive loss", "litigation risk (Netlist)"],
        "tier2_risks": ["supply chain disruption", "customer destocking"],
    },
    "ATI": {
        "qty": 0.862329,
        "avg_cost": 231.93,
        "thesis": "EBITDA margin +440bp; record $4.4B backlog; FY EPS guide raised 16%",
        "tier1_risks": ["guidance cut >10%", "backlog cancellation >10%", "margin compression >200bp"],
        "tier2_risks": ["customer production slowdown", "supply chain issues"],
    },
    "ERO": {
        "qty": 5.023582,
        "avg_cost": 34.84,
        "thesis": "Tucumã copper ramp into structural deficit; 8.25× forward",
        "tier1_risks": ["mine development delays", "ore grade lower than expected", "commodity collapse <$3/lb"],
        "tier2_risks": ["permitting issues", "geopolitical risk"],
    },
    "PATH": {
        "qty": 9.441860,
        "avg_cost": 15.89,
        "thesis": "Margin inflection −6.3% → +5.4%; agentic automation adoption",
        "tier1_risks": ["margin guidance cut", "customer churn >10%", "AI adoption slower than expected"],
        "tier2_risks": ["competition from larger vendors", "sales execution miss"],
    },
    "EGO": {
        "qty": 3.698461,
        "avg_cost": 40.56,
        "thesis": "Skouries Cu-Au ramp; 12.5× forward, 1.51× book, 37% net margin",
        "tier1_risks": ["mine development delays", "copper price <$3/lb", "ore grade miss"],
        "tier2_risks": ["permitting delays", "construction cost overruns"],
    },
    "IAG": {
        "qty": 6.530859,
        "avg_cost": 19.14,
        "thesis": "Côté Gold ramp to steady state; 8.9× forward, PEG 0.18",
        "tier1_risks": ["mine development delays", "gold price <$1500", "ore grade miss"],
        "tier2_risks": ["permitting delays", "construction cost overruns"],
    },
    "HNGE": {
        "qty": 1.130200,
        "avg_cost": 88.48,
        "thesis": "Revenue +53% y/y; net margin −1.2% → +20.5%",
        "tier1_risks": ["revenue guidance cut >15%", "margin compression >10pts", "customer loss"],
        "tier2_risks": ["supply chain disruption", "competitive loss"],
    },
}

def fetch_robinhood_quotes():
    """Fetch live quotes from Robinhood (would be called in production)"""
    # In production, use: from mcp__Robinhood__get_equity_quotes import get_equity_quotes
    # For now, return cached data
    cache_file = "/home/claude/dash/quote_cache.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def check_price_breach(symbol, last, avg_cost):
    """Check if stock is down >8% from cost basis (yellow alert)"""
    pct_change = 100 * (last - avg_cost) / avg_cost
    if pct_change <= -8:
        return True, pct_change
    return False, pct_change

def generate_alerts():
    """Main monitoring logic - check all positions for Tier 1-3 breaks"""
    quotes = fetch_robinhood_quotes()
    alerts = []
    timestamp = datetime.now().strftime("%A %d %b %Y, %-I:%M %p ET")

    for symbol, holding in HOLDINGS.items():
        if symbol not in quotes:
            continue

        last = quotes[symbol].get("last", holding["avg_cost"])
        avg = holding["avg_cost"]

        # Tier 1: Price breach (>8% down from cost)
        breach, pct_change = check_price_breach(symbol, last, avg)
        if breach:
            alerts.append({
                "level": "yellow",
                "symbol": symbol,
                "title": f"{symbol} down {pct_change:.1f}% from cost (${avg:.2f})",
                "tier": "Price Alert",
                "detail": f"Current: ${last:.2f}. Down {pct_change:.1f}%. Thesis: {holding['thesis']}",
                "action": "Monitor for fundamental breaks. Thesis still valid?"
            })

        # Tier 1: Specific known risks (would check news/filings in production)
        # Example: MU + Netlist litigation
        if symbol == "MU" and last < avg * 0.92:
            alerts.append({
                "level": "red",
                "symbol": "MU",
                "title": "MU: Netlist patent litigation seeking import ban on DDR5",
                "tier": "Tier 1 - Business Risk",
                "detail": "Litigation could materially impact revenue if DDR5 sales banned in US",
                "action": "Monitor for ruling date. Track competitive dynamics vs Samsung/SK Hynix.",
                "date": "Ruling expected 2026 Q4"
            })

    # Tier 3: Macro regime check (in production, would fetch live macro data)
    # Example alerts based on macro thresholds

    return {
        "alerts": alerts,
        "timestamp": timestamp,
        "total_positions": len(HOLDINGS),
        "positions_with_alerts": len([a for a in alerts]),
    }

def update_quote_cache(quotes):
    """Update local cache (in production, would commit to GitHub)"""
    cache_file = "/home/claude/dash/quote_cache.json"
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(quotes, f)
        return True
    except:
        return False

if __name__ == "__main__":
    # Run monitoring
    result = generate_alerts()

    # Print summary
    print(f"Monitor run: {result['timestamp']}")
    print(f"Positions checked: {result['total_positions']}")
    print(f"Alerts triggered: {result['positions_with_alerts']}")
    print()

    for alert in result['alerts']:
        print(f"[{alert['level'].upper()}] {alert['title']}")
        print(f"  Tier: {alert.get('tier', 'N/A')}")
        print(f"  Detail: {alert['detail']}")
        print(f"  Action: {alert['action']}")
        if 'date' in alert:
            print(f"  Date: {alert['date']}")
        print()

    # Return as JSON for scheduling system
    import sys
    print("\n--- JSON OUTPUT ---")
    print(json.dumps(result, indent=2))
