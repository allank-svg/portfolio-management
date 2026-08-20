"""
Portfolio Manager
Tracks current holdings, today's performance, and recommendation changes
Compares today's research vs yesterday's to flag recommendation shifts
"""

import json
from datetime import datetime
from config import HOLDINGS, CASH

def get_portfolio_performance(current_quotes):
    """
    Calculate portfolio KPIs and position-level performance
    """
    rows = []
    tot_cost = tot_val = tot_day = 0

    for holding in HOLDINGS:
        sym = holding["symbol"]
        qty = holding["qty"]
        avg = holding["avg_cost"]
        cost = holding["invested"]

        # Get current price
        if sym in current_quotes:
            last = current_quotes[sym].get("last", avg)
            prevclose = current_quotes[sym].get("prevclose", avg)
        else:
            last = avg
            prevclose = avg

        val = qty * last
        pl = val - cost
        plp = 100 * pl / cost if cost else 0
        day = qty * (last - prevclose)
        dayp = 100 * (last - prevclose) / prevclose if prevclose else 0

        tot_cost += cost
        tot_val += val
        tot_day += day

        rows.append({
            "symbol": sym,
            "name": holding.get("name", sym),
            "qty": qty,
            "avg_cost": avg,
            "current_price": last,
            "position_value": val,
            "unrealized_pl": pl,
            "unrealized_pl_pct": plp,
            "today_pl": day,
            "today_pl_pct": dayp,
            "thesis": holding.get("thesis", ""),
            "earnings": holding.get("earnings", "")
        })

    tot_pl = tot_val - tot_cost
    acct = tot_val + CASH
    port_ret = 100 * tot_pl / tot_cost if tot_cost else 0

    return {
        "positions": sorted(rows, key=lambda x: x["today_pl_pct"], reverse=True),
        "kpis": {
            "account_value": acct,
            "equity_value": tot_val,
            "cash": CASH,
            "invested": tot_cost,
            "unrealized_pl": tot_pl,
            "unrealized_pl_pct": port_ret,
            "today_pl": tot_day,
            "num_positions": len(rows)
        },
        "timestamp": datetime.now().strftime("%A %d %b %Y, %-I:%M %p ET")
    }

def compare_research_to_yesterday(today_research, yesterday_research=None):
    """
    Compare today's research recommendations to yesterday's
    Identify which positions have changing recommendations
    This drives the "BUY MORE / SELL / HOLD" action items
    """

    if not yesterday_research:
        yesterday_research = {"top_10_recommendations": []}

    today_map = {r['symbol']: r for r in today_research['top_10_recommendations']}
    yesterday_map = {r['symbol']: r for r in yesterday_research['top_10_recommendations']}

    # All symbols that appear in either list
    all_symbols = set(today_map.keys()) | set(yesterday_map.keys())

    changes = []

    for symbol in all_symbols:
        today_rec = today_map.get(symbol)
        yesterday_rec = yesterday_map.get(symbol)

        # Symbol dropped from top 10 (was ranked, no longer)
        if yesterday_rec and not today_rec:
            changes.append({
                'symbol': symbol,
                'change': 'DROPPED_FROM_TOP_10',
                'yesterday': yesterday_rec['recommendation'],
                'today': None,
                'action': 'CONSIDER_SELL',
                'reason': f"Dropped from top 10. Yesterday recommendation: {yesterday_rec['recommendation']}"
            })

        # Symbol entered top 10 (new opportunity)
        elif today_rec and not yesterday_rec:
            changes.append({
                'symbol': symbol,
                'change': 'ENTERED_TOP_10',
                'yesterday': None,
                'today': today_rec['recommendation'],
                'action': 'CONSIDER_BUY' if today_rec['recommendation'] == 'BUY' else 'MONITOR',
                'reason': f"New top 10 candidate. Today recommendation: {today_rec['recommendation']}"
            })

        # Recommendation changed
        elif today_rec and yesterday_rec and today_rec['recommendation'] != yesterday_rec['recommendation']:
            changes.append({
                'symbol': symbol,
                'change': 'RECOMMENDATION_CHANGED',
                'yesterday': yesterday_rec['recommendation'],
                'today': today_rec['recommendation'],
                'action': f"SHIFT_{yesterday_rec['recommendation']}_TO_{today_rec['recommendation']}",
                'reason': f"Recommendation shifted from {yesterday_rec['recommendation']} to {today_rec['recommendation']}"
            })

    return changes

def get_portfolio_dashboard(current_quotes, today_research, yesterday_research=None):
    """
    Primary executive view: Portfolio Today
    Shows current performance + recommendation changes + action items
    """

    portfolio = get_portfolio_performance(current_quotes)
    recommendation_changes = compare_research_to_yesterday(today_research, yesterday_research)

    # Generate action items from research
    action_items = []

    for rec in today_research['buy_signals']:
        action_items.append({
            'type': 'BUY',
            'symbol': rec['symbol'],
            'reason': f"Score {rec['composite_score']:.0f}/100: {rec['reasoning']}",
            'upside': rec['upside_to_fair'],
            'fair_value': rec['fair_value'],
            'current_price': rec['current_price']
        })

    for rec in today_research['sell_signals']:
        action_items.append({
            'type': 'SELL',
            'symbol': rec['symbol'],
            'reason': f"Score {rec['composite_score']:.0f}/100: Thesis deteriorating or overvalued",
            'downside': -rec['upside_to_fair'],
            'fair_value': rec['fair_value'],
            'current_price': rec['current_price']
        })

    # Filter to only positions we actually hold
    held_symbols = {p['symbol'] for p in portfolio['positions']}
    held_changes = [c for c in recommendation_changes if c['symbol'] in held_symbols]

    return {
        'portfolio': portfolio,
        'recommendation_changes': held_changes,
        'action_items': action_items,
        'summary': {
            'recommendations_changed': len(held_changes),
            'buy_signals': len(today_research['buy_signals']),
            'sell_signals': len(today_research['sell_signals']),
            'total_positions': len(portfolio['positions'])
        }
    }

def save_research_archive(research_report, archive_file="/home/claude/research_archive.jsonl"):
    """
    Save daily research to archive for tracking recommendation history
    """
    try:
        with open(archive_file, "a") as f:
            f.write(json.dumps(research_report) + "\n")
    except:
        pass

def get_yesterday_research(archive_file="/home/claude/research_archive.jsonl"):
    """
    Load yesterday's research report from archive
    """
    try:
        with open(archive_file, "r") as f:
            lines = f.readlines()
            if lines:
                return json.loads(lines[-1])
    except:
        pass
    return None

if __name__ == "__main__":
    from research_engine import get_daily_research
    import os

    # Load current quotes
    try:
        with open("/home/claude/dash/quote_cache.json", "r") as f:
            quotes = json.load(f)
    except:
        quotes = {}

    # Get today's research
    today_research = get_daily_research()

    # Get yesterday's research from archive
    yesterday_research = get_yesterday_research()

    # Build dashboard
    dashboard = get_portfolio_dashboard(quotes, today_research, yesterday_research)

    print(json.dumps(dashboard, indent=2, default=str))
